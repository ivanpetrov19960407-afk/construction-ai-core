# Exception → SSE error.code mapping

| Исключение | error.code | Примечание |
|---|---|---|
| `LLMProviderNotConfiguredError` | `llm_not_configured` | Провайдер LLM не настроен (нет ключа). |
| `asyncio.TimeoutError` | `llm_timeout` | Таймаут ответа LLM (60 сек). |
| Ошибки валидации (`*validation*` в тексте) | `validation_failed` | Невалидный payload/поля формы. |
| Ошибки RAG без релевантных данных (`rag` + `empty/no document`) | `rag_empty` | Пустой контекст RAG. |
| Любые прочие исключения | `internal` | Непредвиденная ошибка сервера. |
