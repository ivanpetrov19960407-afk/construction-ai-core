# CI/CD hardening

## Что проверяется в PR

`ci.yml` запускает обязательные джобы:

1. `lint` — `pre-commit run --all-files` (ruff, ruff-format, mypy strict, prettier, eslint, cargo fmt/clippy).
2. `typecheck` — отдельная строгая проверка `mypy --strict core/ api/`.
3. `test` — unit/integration тесты с покрытием (`pytest --cov=api --cov=core`).
4. `smoke` — динамический smoke по всем GET/POST роутам FastAPI без 500.
5. `alembic` — `alembic upgrade head && alembic check`.
6. `docker-build` — валидация сборки Docker-образа.
7. `helm` — `helm lint --strict` + `helm template` с `values.yaml` и `values.ci.yaml`.

## Локальная проверка перед PR

```bash
pre-commit install
pre-commit run --all-files
pytest tests/ -q
pytest tests/test_smoke_api.py -q
alembic upgrade head && alembic check
helm lint helm/* --strict
docker compose up -d && docker compose ps
```

## Релизы

`release.yml` запускается на тегах `v*`:

- сборка Desktop (Linux/macOS/Windows) через Tauri,
- docker build + push в GHCR,
- генерация SBOM (Syft),
- подпись контейнера (cosign),
- публикация GitHub Release с changelog.

## Dependabot

`.github/dependabot.yml` обновляет еженедельно:

- Python (`pip`),
- Node (`npm`),
- Rust (`cargo`),
- GitHub Actions,
- Docker.
