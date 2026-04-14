# 🏗️ Construction AI Core

[![CI](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/ci.yml/badge.svg)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/ci.yml)
[![Docker Build](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/docker-build.yml/badge.svg)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/docker-build.yml)
[![Release](https://img.shields.io/github/v/release/ivanpetrov19960407-afk/construction-ai-core)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/releases)
[![PRs](https://img.shields.io/github/issues-pr-closed/ivanpetrov19960407-afk/construction-ai-core)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/pulls?q=is%3Apr+is%3Aclosed)

**Универсальный ИИ-помощник для строительной отрасли**

4 слоя · 8 агентов · 4 роли пользователей

> Платформа для инженера ПТО, прораба, зам. генерального и специалиста по тендерам.

---

## Текущий статус

**v0.2.0-beta** · Фаза 2 завершена · Деплой: https://ваш-домен.ru

### Что работает прямо сейчас ✅

- 8 агентов-оркестраторов (Researcher, Analyst, Author, Critic, Verifier, Legal, Formatter, Calculator)
- Telegram-бот с FSM-диалогами: /tk, /letter, /ks, /ppr, /analyze, /upload
- Генерация документов: ТК, ППР, Деловые письма, КС-2/КС-3 (DOCX + PDF)
- RAG-база: 30+ строительных нормативов (СП, ГОСТ, 44-ФЗ)
- LLM: Perplexity, OpenAI, Claude, Deepseek (с fallback-цепочкой)
- Мониторинг: Prometheus + Grafana
- Авто-бэкапы, CI/CD через GitHub Actions

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
│  ТК/ППР · Письма · КС-2/КС-3 · РД/ПСД        │
│  Нормативы                                   │
├─────────────────────────────────────────────┤
│  04 · Хранилище знаний (RAG)                │
│  ChromaDB/Qdrant · SQLite/PostgreSQL         │
│  Нормативы + Учебники + Справочники          │
└─────────────────────────────────────────────┘
```

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Health-check |
| POST | `/api/chat` | Чат с ИИ-помощником |
| POST | `/api/generate/tk` | Генерация технологической карты |
| POST | `/api/generate/letter` | Генерация делового письма |
| POST | `/api/generate/ks` | Генерация КС-2/КС-3 |
| POST | `/api/generate/ppr` | Генерация ППР |
| POST | `/api/analyze/tender` | Анализ тендерной документации |
| POST | `/api/rag/ingest` | Загрузка нормативов в RAG (admin) |
| GET | `/api/rag/sources` | Список загруженных источников |
| GET | `/metrics` | Prometheus метрики |
| GET | `/web` | Web Mini App |

## Roadmap

- [x] Фаза 0 — tk-generator + Telegram-бот
- [x] Фаза 1 — MVP: FastAPI + 8 агентов + RAG + документы
- [x] Фаза 2 — Стабилизация: Docker, CI, мониторинг, бэкапы, tk-bridge
- [ ] Фаза 3 — Desktop GUI (Tauri 2) + JWT + PostgreSQL + Redis ← мы здесь
- [ ] Фаза 4 — Сметный калькулятор, командная работа, мобильный UI

## Быстрый старт

```bash
git clone https://github.com/ivanpetrov19960407-afk/construction-ai-core.git
cd construction-ai-core
cp .env.example .env
uv sync
uvicorn api.main:app --reload --port 8000
```

## Технологический стек

**Backend:** FastAPI, LangGraph, Python 3.11+, Pydantic v2  
**LLM:** Perplexity API, OpenAI, Claude, Deepseek  
**RAG:** ChromaDB → Qdrant  
**Документы:** docxtpl, pdfplumber, python-docx  
**Инфраструктура:** Docker, Prometheus, Grafana, PostgreSQL, Redis-ready  
**Desktop:** Tauri 2 (Фаза 3)  
**Telegram:** aiogram 3

---

**v0.2.0-beta · Beta — доступно для тестирования**
