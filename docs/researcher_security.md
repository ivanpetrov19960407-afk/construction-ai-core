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
- External web fallback policy:
  - `public`: web fallback allowed only after RAG completes and fallback decision is made.
  - `private|tenant|org|project|user`: web fallback blocked by default (`allow_external_web_for_private_scopes=False`).
  - When blocked, collector emits `web_fallback_blocked_private_scope` and returns gaps/diagnostics only.

## Fact validation policy

- Only **exact quote** evidence is accepted.
- Evidence checks source text in this order: `snippet`, `chunk_text`, `full_text`.
- `title/document` are metadata only, not primary evidence.
- Support statuses:
  - `supported` — quote found in source text.
  - `quote_found_but_not_entailing` — exact quote exists, but does not entail obligation/scope/version claim in fact.
  - `partially_supported` — at least one source supports, at least one source is missing/unsupported.
  - `conflicting` — quote found, but conflicts semantically with fact claim.
  - `unsupported` — not returned in verified facts; diagnostics remain machine-readable.
- Exact quote proves only string presence, not full semantic entailment.
- Normative claims should carry metadata (`jurisdiction`, `authority`, `document_version`, `effective_from/effective_to`, `is_active`) or explicit quote wording.
- If evidence can only be checked against `snippet` (no chunk/full text), diagnostic `snippet_only_evidence` is emitted.

## Prompt / injection model

- Source content is passed to LLM as **untrusted external data** inside JSON payload.
- Sanitization is applied to all source textual fields (`title`, `document`, `section`, `locator`, `snippet`, `chunk_text`, `full_text`) before prompt inclusion.
- Prompt builder never raw-slices final JSON output.
- Prompt contract includes explicit `allowed_source_ids`, strict quote requirements, and instruction to return a gap when evidence is insufficient.
- InjectionGuard is a **heuristic layer, not complete defense**.
- Red-team detections include: role spoofing, override attempts (EN/RU), HTML/Markdown payloads, zero-width obfuscation, base64 payloads, prompt leak attempts.

## support_score / confidence_overall

- `confidence_overall` is backward-compatible alias of `support_score`.
- It is **not probability of truth**.
- LLM self-reported confidence is fixed at `0.0` and never inflates score.
- Conflicts cap support score (hard cap), `quote_found_but_not_entailing` lowers coverage, snippet-only evidence is penalized.
- Inactive/outdated normative sources and missing normative jurisdiction reduce score.
- Independent-source gain applies only for different documents/authorities (two chunks from same doc are not independent).
