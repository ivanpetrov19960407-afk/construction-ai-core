# Researcher security & evidence guarantees

- `access_scope` is fail-closed: supported scopes are `public|private|tenant|org|project|user`. Unknown/empty scope is rejected.
- Non-public scopes require explicit access context (`tenant_id/org_id/project_id/user_id` by scope).
- RAG retrieval receives access filters (`filter_scope`, `tenant_id`, `org_id`, `project_id`, `user_id`) and cache keys include scope + all identifiers + `security_policy_version`.
- Source text is always untrusted external content. Injection guard sanitizes snippets, tags suspicious payloads, and diagnostics keep machine-readable `code/message/severity/component`.
- Fact support policy:
  - supported only with real `source_id` + exact `evidence.quote` match in source text;
  - fuzzy/paraphrase-only does not pass as supported;
  - statuses: `supported|partially_supported|unsupported|conflicting`.
- `confidence_overall` is a support/evidence quality score, **not truth probability**.
