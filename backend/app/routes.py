import hmac
import uuid
from io import BytesIO
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import get_session
from app.models import Product
from app.schemas import ProductOut
from app.storage import make_image_url, upload_image

router = APIRouter(prefix="/api")


def to_product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        image_url=make_image_url(product.image_key),
        created_at=product.created_at,
    )


def get_image_info(content: bytes) -> tuple[str, str]:
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(
            status_code=400,
            detail="Файл не является корректным изображением",
        )

    image_types = {
        "JPEG": ("jpg", "image/jpeg"),
        "PNG": ("png", "image/png"),
        "WEBP": ("webp", "image/webp"),
    }

    if image_format is None or image_format not in image_types:
        raise HTTPException(
            status_code=415,
            detail="Поддерживаются только JPEG, PNG и WebP",
        )

    return image_types[image_format]


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
    offset: int = 0,
) -> list[ProductOut]:
    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=422,
            detail="limit должен быть от 1 до 100",
        )

    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail="offset не может быть меньше 0",
        )

    result = await session.scalars(
        select(Product)
        .order_by(Product.created_at.desc(), Product.id.desc())
        .limit(limit)
        .offset(offset)
    )

    return [to_product_out(product) for product in result.all()]


@router.post(
    "/admin/products",
    response_model=ProductOut,
    status_code=201,
)
async def create_product(
    session: Annotated[AsyncSession, Depends(get_session)],
    name: Annotated[str, Form(min_length=1, max_length=160)],
    file: Annotated[UploadFile, File()],
    authorization: Annotated[str | None, Header()] = None,
    source_update_id: Annotated[int | None, Form()] = None,
) -> ProductOut:
    expected_token = f"Bearer {settings.internal_api_token}"

    if authorization is None or not hmac.compare_digest(
        authorization,
        expected_token,
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный токен",
        )

    clean_name = name.strip()

    if not clean_name:
        raise HTTPException(
            status_code=422,
            detail="Название товара не должно быть пустым",
        )

    if source_update_id is not None:
        existing = await session.scalar(
            select(Product).where(
                Product.source_update_id == source_update_id,
            )
        )

        if existing is not None:
            return to_product_out(existing)

    content = await file.read(settings.max_image_size_bytes + 1)
    await file.close()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Файл пустой",
        )

    if len(content) > settings.max_image_size_bytes:
        raise HTTPException(
            status_code=413,
            detail="Максимальный размер фото — 8 МБ",
        )

    extension, content_type = get_image_info(content)

    if source_update_id is not None:
        object_name = f"telegram-{source_update_id}"
    else:
        object_name = uuid.uuid4().hex

    image_key = f"products/{object_name}.{extension}"

    try:
        await run_in_threadpool(
            upload_image,
            image_key,
            content,
            content_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Не удалось сохранить изображение в MinIO",
        ) from exc

    product = Product(
        name=clean_name,
        image_key=image_key,
        source_update_id=source_update_id,
    )
    session.add(product)

    try:
        await session.commit()
        await session.refresh(product)
        return to_product_out(product)
    except IntegrityError:
        await session.rollback()

        if source_update_id is not None:
            existing = await session.scalar(
                select(Product).where(
                    Product.source_update_id == source_update_id,
                )
            )

            if existing is not None:
                return to_product_out(existing)

        raise HTTPException(
            status_code=409,
            detail="Товар уже существует",
        )
