# Researcher security & evidence guarantees

- `access_scope` is fail-closed. Supported values: `public|private|tenant|org|project|user`.
- `access_scope=None` is interpreted as `public`.
- Empty scope (`""`) and unknown scope are rejected with `ResearchScopeError`.
- Non-public scopes require context:
  - `private|user` => `user_id`
  - `org` => `org_id`
  - `tenant` => `tenant_id`
  - `project` => `tenant_id + project_id`
- RAG retrieval always gets identity filters (`filter_scope`, `tenant_id`, `org_id`, `project_id`, `user_id`).
- If RAG engine cannot accept identity filters for non-public requests, collector fails closed (`rag_identity_filters_unsupported`).

## Fact validation policy

- Only **exact quote** evidence is accepted.
- Evidence checks source text in this order: `snippet`, `chunk_text`, `full_text`.
- `title/document` are metadata only, not primary evidence.
- Support statuses:
  - `supported` — quote found in source text.
  - `partially_supported` — at least one source supports, at least one source is missing/unsupported.
  - `conflicting` — quote found, but conflicts semantically with fact claim.
  - `unsupported` — not returned in verified facts; diagnostics remain machine-readable.
- If evidence can only be checked against `snippet` (no chunk/full text), diagnostic `snippet_only_evidence` is emitted.

## Prompt / injection model

- Source content is passed to LLM as **untrusted external data** inside JSON payload.
- Prompt builder never raw-slices final JSON output.
- InjectionGuard is a **heuristic layer, not complete defense**.
- Red-team detections include: role spoofing, override attempts (EN/RU), HTML/Markdown payloads, zero-width obfuscation, base64 payloads, prompt leak attempts.

## support_score / confidence_overall

- `confidence_overall` is backward-compatible alias of `support_score`.
- It is **not probability of truth**.
- LLM self-reported confidence is fixed at `0.0` and never inflates score.
- Conflicts, inactive sources, and missing jurisdiction for normative sources reduce score.
