.PHONY: up down restart logs ps

up: ## Собрать и запустить проект
	docker compose up --build -d

down: ## Остановить контейнеры
	docker compose down

restart: ## Перезапустить контейнеры
	docker compose restart

logs: ## Смотреть логи всех контейнеров
	docker compose logs -f

ps: ## Проверить состояние контейнеров
	docker compose ps
