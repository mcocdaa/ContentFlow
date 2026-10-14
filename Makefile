.PHONY: lint typecheck test test-skills check clean

lint:
	ruff check cli.py core/ config/ .agents/skills/figure-tutorial-video/scripts/ tests/

typecheck:
	mypy cli.py core/ config/ .agents/skills/figure-tutorial-video/scripts/ tests/

test:
	pytest -v

test-skills:
	node --test .agents/skills/byted-ark-seedance-skill/tests/*.test.js .agents/skills/byted-ark-seedream-skill/tests/*.test.js

check: lint typecheck test test-skills

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__ core/__pycache__ config/__pycache__ tests/__pycache__
