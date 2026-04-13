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

## Настройки
Настройки `API URL` и `API Key` сохраняются через `tauri-plugin-store` в:

- Linux/macOS: `~/.config/construction-ai/settings.json` (для Linux)
- Windows: `%APPDATA%/construction-ai/settings.json`

Значения используются в чате для вызова `POST {API_URL}/api/chat` с заголовком `X-API-Key`.
