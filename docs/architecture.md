# Architecture

## ChatRagPipeline (v4.2)

```mermaid
flowchart TD
  A[POST /api/chat] --> B[Orchestrator.process intent=chat]
  B --> C{Есть my-sources?}
  C -->|Да| D[Retriever: personal chunks top_k=6]
  C -->|Нет| E[Retriever: global chunks top_k=6]
  D --> F[Build system prompt with citations S1..S6]
  E --> F
  F --> G[LLM Router]
  G --> H[Response: reply + agents_used + sources]
  H --> I[SSE events: progress, source, done]
```

### Steps
1. Определение источника retrieval: персональная база пользователя (`username`) или fallback на глобальные документы.
2. Формирование контекста с цитируемыми фрагментами (`[S1]`, `[S2]`...).
3. Генерация ответа через LLM Router с ограничением: опираться на контекст.
4. Возврат `sources: [{title, page, score}]` и `agents_used: ["retriever", "responder"]`.
