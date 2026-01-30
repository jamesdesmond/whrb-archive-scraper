PYTHON ?= python

.PHONY: format lint test coverage

format:
	black .

lint:
	black --check .
	ruff check .

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov=src/whrb_archive --cov-report=term-missing
