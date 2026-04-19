# Telegram Bot

## Запуск

```bash
python -m telegram.main
```

Docker Compose использует тот же entrypoint: `python -m telegram.main`.

## Команды

- `/start` — старт и выбор роли.
- `/link <api_key>` — привязка API-ключа (с проверкой через `/api/me`).
- `/unlink` — отвязка API-ключа.
- `/whoami` — показать пользователя/роль из API.
- `/health` — количество активных сессий.
- `/tk`, `/ks`, `/letter` — генерация документов.

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота.
- `CORE_API_URL` — адрес API (например, `http://api:8000`).
- `TELEGRAM_WEBHOOK_URL` — URL webhook (опционально, если пусто — polling).
- `TELEGRAM_WEBHOOK_SECRET` — секрет webhook.
- `TELEGRAM_ADMIN_IDS` — список Telegram ID администраторов.
- `REDIS_URL` — Redis для rate-limit и хранения `tg:user:{chat_id}:api_key`.

## Деплой

1. Заполните `.env` (минимум `BOT_TOKEN`, `API_KEYS`, `REDIS_URL`).
2. Запустите сервисы:
   ```bash
   docker compose up -d api redis postgres telegram-bot
   ```
3. Проверьте:
   - `/health` API,
   - `/api/telegram/health`,
   - логи `docker compose logs telegram-bot`.
