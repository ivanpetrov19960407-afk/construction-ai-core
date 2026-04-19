# Construction AI Desktop (Tauri 2 + React + TypeScript)

## Требования
- Node.js 20+
- Rust (stable)
- Системные зависимости Tauri для вашей ОС

## Установка
```bash
cd desktop
npm install
```

## Запуск в режиме разработки
```bash
npm run tauri dev
```

## Сборка production
```bash
npm run tauri build
```

## Структура проекта
- `src/` — UI (React + TypeScript)
- `src-tauri/` — Rust-команды Tauri

## Tauri плагины и permissions
- Плагины (`src-tauri/Cargo.toml` + `src-tauri/tauri.conf.json`):
  - `tauri-plugin-store`
  - `tauri-plugin-log`
  - `tauri-plugin-shell`
  - `tauri-plugin-fs`
  - `tauri-plugin-dialog`
  - `tauri-plugin-clipboard-manager`
- Capability `src-tauri/capabilities/default.json` включает:
  - `core:default`, `store:default`
  - `shell:allow-open`
  - `fs:allow-read-dir`
  - `path:default`
  - `dialog:allow-message`, `dialog:allow-ask`
  - Кастомные команды: `allow-get-api-url`, `allow-set-api-url`, `allow-pick-pdf-file`, `allow-read-pdf-file-bytes`, `allow-open-logs-folder`, `allow-copy-last-log-lines`, `allow-get-app-version`

## Настройки
Настройки `API URL` и `API Key` сохраняются через `tauri-plugin-store` в:

- Linux/macOS: `~/.config/construction-ai/settings.json` (для Linux)
- Windows: `%APPDATA%/construction-ai/settings.json`

Значения используются в чате для вызова `POST {API_URL}/api/chat` с заголовком `X-API-Key`.

## База знаний
- Страница KB работает в двух режимах:
  - `Моя база` — доступна любой роли, загрузка через `/api/rag/chat-upload`, список через `/api/rag/my-sources`.
  - `Глобальная база` — только для admin, загрузка через `/api/rag/ingest`, список через `/api/rag/sources`.
- Роль берётся из `GET /api/me` и кэшируется в `AuthContext`.
- При 403 показывается понятная ошибка доступа вместо `Failed to fetch`.

## Навигация и роли
- Разделы сгруппированы в sidebar: `База`, `Генерация`, `Анализ`, `Админ`.
- Роль `admin` видит все разделы, включая `Аналитика`, `Биллинг`, `Compliance`.
- Роль `pto_engineer` видит рабочие разделы генерации/анализа без админ-панели.
- Маршруты защищены `RequireAuth`: при отсутствии токена открывается `Login`, доступ к admin-страницам ограничен ролью.
