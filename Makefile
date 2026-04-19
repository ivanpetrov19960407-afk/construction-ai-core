.PHONY: lint test smoke release

lint:
	pre-commit run --all-files

test:
	pytest tests/ -q

smoke:
	pytest tests/test_smoke_api.py -q

release:
	@echo "Create and push a semantic tag, e.g. v0.5.1"
	@echo "git tag v0.5.1 && git push origin v0.5.1"
