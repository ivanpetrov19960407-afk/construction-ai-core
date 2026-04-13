# 🏗️ Construction AI Core

**Универсальный ИИ-помощник для строительной отрасли**

4 слоя · 8 агентов · 4 роли пользователей

> Платформа для инженера ПТО, прораба, зам. генерального и специалиста по тендерам.

---

## Архитектура

```
┌─────────────────────────────────────────────┐
│  01 · Слой интерфейсов                      │
│  Desktop (Tauri 2) · Telegram · Web UI      │
├─────────────────────────────────────────────┤
│  02 · Ядро (Python Core)                    │
│  Оркестратор (LangGraph) · LLM Router       │
│  Session Memory                              │
├─────────────────────────────────────────────┤
│  03 · Генераторы и Анализаторы              │
│  ТК/ППР · Письма · КС-2/КС-3 · РД/ПСД     │
│  Нормативы                                   │
├─────────────────────────────────────────────┤
│  04 · Хранилище знаний (RAG)                │
│  ChromaDB/Qdrant · SQLite/PostgreSQL         │
│  Нормативы + Учебники + Справочники          │
└─────────────────────────────────────────────┘
```

## Агенты оркестратора

| # | Агент | Специализация |
|---|-------|---------------|
| 01 | 🔍 Researcher | Поиск по нормативам, RAG, анализ РД/ПСД |
| 02 | 📊 Analyst | Конфликт-анализ, оценка рисков |
| 03 | ✍️ Author | Генерация ТК, ППР, писем, отчётов |
| 04 | 🔎 Critic | Рецензирование черновиков |
| 05 | ✅ Verifier | KPI-проверка (confidence ≥ 0.95) |
| 06 | ⚖️ Legal Expert | Ссылки на НПА, юридическая проверка |
| 07 | 📐 Formatter | ГОСТ-форматирование DOCX |
| 08 | 🧮 Calculator | Расчёты объёмов, трудозатрат, смет |

## Структура проекта

```
construction-ai-core/
├── api/                    # FastAPI application
│   ├── main.py             # Точка входа
│   └── routes/
│       ├── health.py       # Health-check
│       ├── chat.py         # Чат-интерфейс
│       └── generate.py     # Генерация документов
├── core/                   # Ядро системы
│   ├── orchestrator.py     # Оркестратор (LangGraph)
│   └── llm_router.py       # Маршрутизация LLM
├── agents/                 # 8 агентов
│   ├── base.py             # Базовый класс
│   ├── researcher.py
│   ├── analyst.py
│   ├── author.py
│   ├── critic.py
│   ├── verifier.py
│   ├── legal_expert.py
│   ├── formatter.py
│   └── calculator.py
├── config/
│   ├── orchestrator.json   # Конфигурация агентов
│   └── settings.py         # Настройки (pydantic-settings)
├── templates/              # DOCX-шаблоны (Jinja2)
├── tests/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/ivanpetrov19960407-afk/construction-ai-core.git
cd construction-ai-core
```

### 2. Настроить окружение

```bash
cp .env.example .env
# Заполнить API-ключи в .env
```

### 3. Установить зависимости

```bash
# С uv (рекомендуется)
uv sync

# Или с pip
pip install -e ".[dev]"
```

### 4. Запустить сервер

```bash
uvicorn api.main:app --reload --port 8000
```

### 5. Или через Docker

```bash
docker compose up --build
```

### 6. Проверить

```bash
curl http://localhost:8000/health
# → {"status": "ok", "service": "construction-ai-core", "version": "0.1.0"}
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Health-check |
| POST | `/api/chat` | Чат с ИИ-помощником |
| POST | `/api/generate/tk` | Генерация технологической карты |
| POST | `/api/generate/letter` | Генерация делового письма |
| POST | `/api/generate/ks` | Генерация КС-2/КС-3 (Фаза 4) |

## Roadmap

- [x] **Фаза 0** — tk-generator (Node.js), Telegram-бот (laughing-memory)
- [ ] **Фаза 1** — MVP: FastAPI + Оркестратор + LLM Router + Telegram ← _мы здесь_
- [ ] **Фаза 2** — Генераторы: ТК/ППР, письма, PDF-парсер, RAG
- [ ] **Фаза 3** — Desktop GUI (Tauri), экраны «Нормативы» и «Архив»
- [ ] **Фаза 4** — КС-2/КС-3, OCR, полная RAG, инсталлятор

## Связанные репозитории

- [tk-generator](https://github.com/ivanpetrov19960407-afk/tk-generator) — генератор ТК/МК (Node.js)
- [laughing-memory](https://github.com/ivanpetrov19960407-afk/laughing-memory) — Telegram-бот (aiogram 3)

## Технологический стек

**Backend:** FastAPI, LangGraph, Python 3.11+, Pydantic v2  
**LLM:** Perplexity API, OpenAI, Claude, Deepseek  
**RAG:** ChromaDB → Qdrant  
**Документы:** docxtpl, pdfplumber, python-docx  
**Инфраструктура:** Docker, SQLite → PostgreSQL  
**Desktop:** Tauri 2 (Фаза 3)  
**Telegram:** aiogram 3  

---

**v0.1-alpha · In Development**
