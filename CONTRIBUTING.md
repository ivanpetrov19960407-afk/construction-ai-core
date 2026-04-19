# Contributing

## Процесс

1. Сделайте fork репозитория.
2. Создайте ветку от `main` (`feature/<name>` или `fix/<name>`).
3. Установите хуки и прогоните проверки:

```bash
pre-commit install
pre-commit run --all-files
pytest tests/ -q
pytest tests/test_smoke_api.py -q
```

4. Зафиксируйте изменения с понятным сообщением коммита.
5. Откройте Pull Request в `main`.

## Требования к PR

- PR должен проходить `lint`, `typecheck`, `test`, `smoke`, `alembic`, `docker-build`, `helm`.
- Если изменяется схема БД — приложите Alembic-миграцию.
- Для крупных изменений опишите риски и план отката.
