## [0.2.2] - 2026-04-20

### Added
- feat(llm): honest health-check + startup validation

## [0.2.1] - 2026-04-19

### Fixed
- fix(health): honest LLM status
- fix(cors): valid credentials+origins
- fix(bot): correct entrypoint, add /link validation, rate-limit
- fix(tauri): add missing permissions for logs folder

### Added
- feat(chat): markdown render + real RAG pipeline
- feat(kb): split personal vs global knowledge base
- feat(api): SSE for letter
- feat(compliance): accept short_id, fix 422→404
- feat(desktop): add PPR/Estimate/Tender/Analytics/Compliance/Billing/Auth pages

## [0.2.0] - 2026-04-14

### Added
- 30 этапов разработки завершены
- Полный список: PR #1–#37

### Changed
- Docker-образ оптимизирован с 1.5 ГБ до 500 МБ (multi-stage build)

- feat(ui): surface real SSE error reasons
