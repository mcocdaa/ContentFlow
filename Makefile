.PHONY: lint typecheck test check clean

lint:
	ruff check cli.py core/ config/ tests/

typecheck:
	mypy cli.py core/ config/ tests/

test:
	pytest -v

check: lint typecheck test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ core/__pycache__ config/__pycache__ tests/__pycache__
