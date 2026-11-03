install:
    uv sync

run:
    uv run python -m timetabler

watch:
    uv run watchfiles --filter python 'python -m timetabler' src

lint:
    .venv/bin/ruff check src --select F,E9,PLE

typecheck:
    .venv/bin/mypy src/timetabler --ignore-missing-imports --check-untyped-defs

verify: lint typecheck

migrate:
    .venv/bin/alembic upgrade head
