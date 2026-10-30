import asyncio
import hmac
import logging
import os

import httpx
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    WebAppInfo,
)
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_BASE_URL = os.environ["WEBHOOK_BASE_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
CATALOG_API_URL = os.getenv("CATALOG_API_URL", "http://api:8000").rstrip("/")
INTERNAL_API_TOKEN = os.environ["INTERNAL_API_TOKEN"]
MINI_APP_URL = os.getenv("MINI_APP_URL", "").strip()
MAX_IMAGE_SIZE_BYTES = int(os.getenv("MAX_IMAGE_SIZE_BYTES", str(8 * 1024 * 1024)))
ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",")
    if value.strip()
}

if not WEBHOOK_BASE_URL.startswith("https://"):
    raise ValueError("WEBHOOK_BASE_URL должен быть публичным HTTPS-адресом")

if not WEBHOOK_SECRET:
    raise ValueError("WEBHOOK_SECRET не должен быть пустым")

if MINI_APP_URL and not MINI_APP_URL.startswith("https://"):
    raise ValueError("MINI_APP_URL должен быть HTTPS-адресом")

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()


def is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in ADMIN_IDS


def catalog_keyboard() -> InlineKeyboardMarkup | None:
    if not MINI_APP_URL:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть каталог",
                    web_app=WebAppInfo(url=MINI_APP_URL),
                )
            ]
        ]
    )


@dispatcher.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "У меня есть товар. Открой каталог:",
        reply_markup=catalog_keyboard(),
    )


@dispatcher.message(Command("create_product"))
async def create_product_command(message: Message) -> None:
    if not is_admin(message):
        await message.answer("Эта команда доступна только администратору.")
        return

    await message.answer(
        "Отправьте одним сообщением фотографию товара, "
        "а название напишите в подписи к фото."
    )


@dispatcher.message(lambda message: bool(message.photo))
async def receive_product_photo(
    message: Message,
    telegram_update_id: int,
) -> None:
    if not is_admin(message):
        return

    name = (message.caption or "").strip()
    if not name:
        await message.answer("Добавьте название товара в подпись к фотографии.")
        return

    if len(name) > 160:
        await message.answer("Название товара должно быть не длиннее 160 символов.")
        return

    photo = message.photo[-1]
    telegram_file = await bot.get_file(photo.file_id)

    if not telegram_file.file_path:
        raise RuntimeError("Telegram не вернул путь к фотографии")

    image_file = await bot.download_file(telegram_file.file_path)
    if image_file is None:
        raise RuntimeError("Не удалось скачать фотографию из Telegram")

    image_content = image_file.getvalue()

    if len(image_content) > MAX_IMAGE_SIZE_BYTES:
        await message.answer("Фотография слишком большая. Максимум — 8 МБ.")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{CATALOG_API_URL}/api/admin/products",
            headers={"Authorization": f"Bearer {INTERNAL_API_TOKEN}"},
            data={
                "name": name,
                "source_update_id": str(telegram_update_id),
            },
            files={
                "file": ("product.jpg", image_content, "image/jpeg"),
            },
        )

    if response.is_client_error:
        logger.error(
            "Catalog API rejected product: status=%s body=%s",
            response.status_code,
            response.text,
        )
        await message.answer("Не удалось добавить товар. Проверьте название и фото.")
        return

    # Ошибки сети и 5xx не подавляем: webhook должен вернуть ошибку,
    # чтобы Telegram мог повторить доставку update.
    response.raise_for_status()

    product = response.json()
    await message.answer(f"Товар «{product['name']}» добавлен в каталог.")


@dispatcher.message()
async def fallback(message: Message) -> None:
    # Регистрируется последним: срабатывает только тогда,
    # когда ни один из обработчиков выше не подошёл.
    await message.answer(
        "У меня есть товар. Открой каталог:",
        reply_markup=catalog_keyboard(),
    )


async def telegram_webhook(request: web.Request) -> web.Response:
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    # compare_digest сравнивает байты: со строками с не-ASCII символами он падает.
    if not hmac.compare_digest(
        received_secret.encode(),
        WEBHOOK_SECRET.encode(),
    ):
        return web.Response(status=403, text="Forbidden")

    try:
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": bot})
    except (ValueError, TypeError):
        return web.Response(status=400, text="Invalid update")

    try:
        await dispatcher.feed_update(
            bot,
            update,
            telegram_update_id=update.update_id,
        )
    except Exception:
        logger.exception("Failed to process Telegram update %s", update.update_id)
        return web.Response(status=500, text="Update processing failed")

    return web.Response(text="ok")


async def set_webhook_with_retry(max_attempts: int = 5) -> None:
    # Реплики стартуют одновременно, и Telegram может вернуть flood control.
    # В этом случае ждём указанное время и пробуем снова, а не падаем.
    for attempt in range(1, max_attempts + 1):
        try:
            await bot.set_webhook(
                url=f"{WEBHOOK_BASE_URL}/telegram/webhook",
                secret_token=WEBHOOK_SECRET,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
        except TelegramRetryAfter as error:
            logger.warning(
                "setWebhook rate limited (attempt %s/%s), retry in %s s",
                attempt,
                max_attempts,
                error.retry_after,
            )
            await asyncio.sleep(error.retry_after)
            continue

        logger.info("Telegram webhook configured")
        return

    raise RuntimeError("Не удалось установить webhook после нескольких попыток")


async def on_startup(_: web.Application) -> None:
    await set_webhook_with_retry()


async def on_cleanup(_: web.Application) -> None:
    await bot.session.close()


def main() -> None:
    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_post("/telegram/webhook", telegram_webhook)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    web.run_app(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )


if __name__ == "__main__":
    main()
