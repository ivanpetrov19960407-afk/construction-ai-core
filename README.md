# 🏗️ Construction AI Core

[![CI](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/ci.yml/badge.svg)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/ci.yml)
[![Docker Build](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/docker-build.yml/badge.svg)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/docker-build.yml)
[![Helm Lint](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/helm-lint.yml/badge.svg)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/actions/workflows/helm-lint.yml)
[![Release](https://img.shields.io/github/v/release/ivanpetrov19960407-afk/construction-ai-core)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/releases)
[![PRs](https://img.shields.io/github/issues-pr-closed/ivanpetrov19960407-afk/construction-ai-core)](https://github.com/ivanpetrov19960407-afk/construction-ai-core/pulls?q=is%3Apr+is%3Aclosed)

**ИИ-платформа для строительной отрасли — от генерации документов до сдачи объекта**

4 слоя · 8 агентов · 4 роли · мультитенантность · SaaS-биллинг · Kubernetes-ready

> Платформа для инженера ПТО, прораба, зам. генерального и специалиста по тендерам.

---

## Что работает прямо сейчас ✅

### Генерация документов
- ТК (Технологические карты), ППР, Деловые письма — DOCX + PDF
- КС-2 / КС-3 с подписанием ЭЦП (КриптоПро REST API)
- Исполнительные альбомы с автосборкой из АОСР и выгрузкой в MinIO / S3
- Экспорт КС-2 и М-29 в XML для 1С:Бухгалтерия

### ИИ и аналитика
- 8 агентов-оркестраторов (Researcher, Analyst, Author, Critic, Verifier, Legal, Formatter, Calculator)
- LLM-роутер: Perplexity → OpenAI → Claude → Deepseek (с fallback-цепочкой)
- RAG-база: 30+ строительных нормативов (СП, ГОСТ, 44-ФЗ)
- Предиктивная аналитика задержек стройки (ML + GPT-4o-mini, Redis-кеш 6ч)
- Чеклист готовности ИД по Приказу №522-пр (8 разделов: AR, KZH, KM, OV, VK, EM, SS, APS/PS)

### Интеграции
- ЭЦП / УКЭП — подпись + пакетная подпись + верификация (КриптоПро REST)
- ИСУП Минстроя — OAuth2, передача ИД, webhook обратного статуса
- 1С:Бухгалтерия — XML КС-2 и М-29
- Telegram-бот: /tk, /letter, /ks, /ppr, /analyze, /upload, /handover_check, /handover_forecast, /sign_doc, /sign_all

### Платформа
- Мультитенантность (org_id изоляция данных, TenantMiddleware)
- SaaS-биллинг: 4 плана (Free / Starter / Pro / Enterprise), квоты на ресурсы
- ЮKassa webhook для оплаты подписки
- White-label брендинг (логотип, цвета, домен на уровне org_id)
- Web Push уведомления (VAPID, Service Worker, offline-кеш)
- Desktop-приложение (Tauri 2 + React) — ChatPage, GenerateKS, GenerateLetter, GenerateTK, HandoverPage
- Kubernetes-ready: Helm Chart + HPA (auto-scale 2–10 реплик)

### Мониторинг и инфраструктура
- Prometheus + Grafana метрики
- CI/CD: GitHub Actions (ci.yml, docker-build.yml, desktop-build.yml, helm-lint.yml)
- Авто-бэкапы SQLite
- Alembic миграции (6 версий)

---

## Архитектура
┌──────────────────────────────────────────────────────┐
│ Слой интерфейсов │
│ Desktop (Tauri 2) · Telegram Bot · Web PWA │
├──────────────────────────────────────────────────────┤
│ API Layer (FastAPI) │
│ Auth (JWT) · Projects · Generate · Sign · Analytics │
│ Compliance (ГСН) · ИСУП · Billing · Branding │
├──────────────────────────────────────────────────────┤
│ Core (Python) │
│ Orchestrator (LangGraph) · LLM Router │
│ SchedulePredictor · BillingEngine · TenantMiddleware│
│ ExecAlbum · OneCExporter · CryptoPro · ISUPClient │
├──────────────────────────────────────────────────────┤
│ Хранилище │
│ SQLite / PostgreSQL · ChromaDB (RAG) │
│ Redis (кеш, сессии) · MinIO / S3 (файлы) │
└──────────────────────────────────────────────────────┘

text

---

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Health-check |
| POST | `/api/auth/register` | Регистрация (invite-code) |
| POST | `/api/auth/login` | JWT-аутентификация |
| GET | `/api/projects` | Список проектов (tenant) |
| POST | `/api/projects` | Создать проект |
| GET | `/api/projects/{id}/documents` | Документы проекта |
| POST | `/api/chat` | Чат с ИИ-помощником |
| POST | `/api/generate/tk` | Технологическая карта |
| POST | `/api/generate/letter` | Деловое письмо |
| POST | `/api/generate/ks` | КС-2 / КС-3 |
| POST | `/api/generate/ppr` | ППР |
| GET | `/api/generate/ks2/{id}/1c-xml` | КС-2 → XML для 1С |
| GET | `/api/generate/m29/{project_id}/1c-xml` | М-29 → XML для 1С |
| POST | `/api/sign/document` | Подписать документ (ЭЦП) |
| POST | `/api/sign/batch` | Пакетная подпись (до 20 документов) |
| GET | `/api/sign/verify/{id}` | Верификация подписи |
| POST | `/api/compliance/gsn-report/{project_id}` | Сформировать ГСН-отчёт |
| GET | `/api/compliance/gsn-checklist/{project_id}` | Чеклист ГСН |
| POST | `/api/isup/submit-document` | Передача ИД в ИСУП |
| POST | `/api/isup/callback` | Webhook статуса из ИСУП |
| GET | `/api/isup/submissions/{project_id}` | Статусы отправок ИСУП |
| GET | `/api/analytics/schedule/{project_id}` | Прогноз задержек |
| GET | `/api/analytics/dashboard/{project_id}` | Дашборд по проекту |
| GET | `/api/analytics/dashboard/all` | Сводный дашборд (high-risk) |
| GET | `/api/billing/plan` | Текущий тарифный план |
| POST | `/api/billing/plan` | Сменить план |
| GET | `/api/billing/usage` | Использование квот за месяц |
| POST | `/api/billing/webhook/yookassa` | ЮKassa payment webhook |
| GET | `/api/branding` | Брендинг org_id |
| PUT | `/api/branding` | Обновить брендинг |
| POST | `/api/push/subscribe` | Подписка Web Push |
| GET | `/metrics` | Prometheus метрики |

---


## Как получить short_id проекта

- Вызовите `GET /api/projects/mine` (или `GET /api/projects`) с вашим JWT или `X-API-Key`.
- В каждом объекте проекта поле `short_id` содержит короткий числовой идентификатор проекта.
- `short_id` можно использовать в compliance-эндпоинтах (`/api/compliance/gsn-checklist/{project_id}`, `/api/compliance/gsn-report/{project_id}`) наравне с UUID.

## Тарифные планы

| План | Проектов | AI-запросов/мес | Альбомов |
|------|----------|-----------------|----------|
| Free | 1 | 20 | 0 |
| Starter | 3 | 100 | 5 |
| Pro | 20 | 2 000 | 50 |
| Enterprise | ∞ | ∞ | ∞ |

---

## Быстрый старт

```bash
git clone https://github.com/ivanpetrov19960407-afk/construction-ai-core.git
cd construction-ai-core
cp .env.example .env
# Заполнить .env: OPENAI_API_KEY, DATABASE_URL, REDIS_URL, S3_*, CRYPTOPRO_*, BOT_TOKEN
uv sync
alembic upgrade head
uvicorn api.main:app --reload --port 8000
```

### Docker Compose

```bash
docker compose up -d
```

### Kubernetes (Helm)

```bash
helm install construction-ai helm/construction-ai/ \\n  --set image.tag=latest \\n  --set ingress.host=construction-ai.example.com \\n  --set-file env.secrets=secrets.env
```

---

## Переменные окружения (.env)

| Переменная | Описание |
|-----------|----------|
| `DATABASE_URL` | SQLite или PostgreSQL URL |
| `REDIS_URL` | Redis URL (redis://redis:6379) |
| `OPENAI_API_KEY` | OpenAI API ключ |
| `PERPLEXITY_API_KEY` | Perplexity API ключ |
| `BOT_TOKEN` | Telegram Bot Token |
| `S3_ENDPOINT_URL` | MinIO / S3 URL |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | S3 credentials |
| `CRYPTOPRO_REST_URL` | КриптоПро REST сервер URL |
| `CRYPTOPRO_API_KEY` | КриптоПро API ключ |
| `ISUP_API_URL` | ИСУП Минстроя URL |
| `ISUP_CLIENT_ID` / `ISUP_CLIENT_SECRET` | ИСУП OAuth2 credentials |
| `ISUP_ENABLED` | Включить интеграцию с ИСУП (true/false) |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | ЮKassa для биллинга |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | Web Push VAPID-ключи |
| `JWT_SECRET` | JWT secret (≥32 символов) |
| `MULTITENANCY_ENABLED` | Включить мультитенантность |
| `CORS_ORIGINS` | Разрешённые origins через CSV (например `tauri://localhost,http://localhost:1420`) |

### Разрешённые Origins (CORS)

- По умолчанию разрешены: `tauri://localhost`, `http://localhost:1420`, `https://vanekpetrov1997.fvds.ru`.
- Для production задавайте `CORS_ORIGINS` явно списком доверенных доменов и схем.
- Если используете wildcard `*`, сервер автоматически отключает `allow_credentials` (требование CORS-спецификации), поэтому для desktop/web с cookie/credentials используйте явный allowlist.

---

## Как получить LLM-ключи

- **OpenAI**: зайдите в https://platform.openai.com/api-keys, создайте новый API key и сохраните его в `OPENAI_API_KEY`.
- **GigaChat**: в кабинете разработчика Сбера (https://developers.sber.ru/) создайте OAuth-клиент и заполните `GIGACHAT_CREDENTIALS` в формате `base64(client_id:client_secret)`.

---

## Роли пользователей

| Роль | Доступ |
|------|--------|
| `admin` | Полный доступ, управление пользователями, биллинг |
| `pto_engineer` | Генерация документов, ЭЦП, аналитика, ГСН, ИСУП |
| `foreman` | Просмотр КГ, чаты с ИИ, загрузка файлов |
| `tender_specialist` | Анализ тендеров, генерация писем |

Новые пользователи регистрируются через invite-code. Коды настраиваются в `INVITE_CODES` в `.env`.

---

## Технологический стек

**Backend:** FastAPI 0.115, Python 3.11+, Pydantic v2, LangGraph, SQLAlchemy  
**LLM:** Perplexity API, OpenAI GPT-4o, Claude 3.5, Deepseek  
**RAG:** ChromaDB, sentence-transformers  
**Документы:** docxtpl, WeasyPrint, python-docx, pdfplumber  
**ЭЦП:** КриптоПро REST API (ГОСТ Р 34.10-2012)  
**Desktop:** Tauri 2.0, React 18, TypeScript, Zustand  
**Telegram:** aiogram 3.x  
**Инфраструктура:** Docker, Kubernetes + Helm, Prometheus, Grafana, Redis, MinIO  
**CI/CD:** GitHub Actions (4 workflow)

---

## Roadmap

- [x] Фаза 0 — tk-generator + Telegram-бот
- [x] Фаза 1 — MVP: FastAPI + 8 агентов + RAG + КС/ТК/ППР
- [x] Фаза 2 — Docker, CI/CD, мониторинг, бэкапы
- [x] Фаза 3 — Desktop (Tauri 2), JWT-авторизация, Redis, PostgreSQL
- [x] Фаза 4 — Исполнительная документация, ЭЦП, ИСУП, предиктивная аналитика, 1С-экспорт
- [x] Фаза 5 — Мультитенантность, биллинг (ЮKassa), Kubernetes, white-label, Web Push
- [ ] Фаза 6 — Marketplace плагинов, мобильное приложение (React Native), AI-сметник

---

**v0.5.0-beta · Фазы 0–5 завершены · Апрель 2026**
