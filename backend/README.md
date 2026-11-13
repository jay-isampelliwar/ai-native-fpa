# Backend

FastAPI, LangGraph, PostgreSQL and Redis. The architecture is explained in the [root README](../README.md).

## Processes

| Process | Command, from `backend/` |
|---|---|
| API | `uv run fastapi dev app/main.py` |
| Agent worker | `uv run python -m app.features.runs.consumer` |
| Outbox publisher | `uv run python -m app.features.outbox.publisher` |
| Memory worker | `uv run python -m app.features.memory.worker` |

## Setup

```bash
cp .env.example .env        # then set OPENAI_API_KEY and JWT_SECRET
uv sync
uv run alembic upgrade head
```

Postgres and Redis must be running first. The commands are in the [root README](../README.md#run-it-locally).

## Common tasks

| Task | Command |
|---|---|
| Run the tests | `uv run pytest` |
| Make a migration | `uv run alembic revision --autogenerate -m "what changed"` |
| Apply migrations | `uv run alembic upgrade head` |
| Load market data | scripts in [scripts/market_data](scripts/market_data) |

## Where to look

- Folder map: [docs/folder.md](../docs/folder.md)
- Deep reference: [docs/PROJECT_CONTEXT.md](../docs/PROJECT_CONTEXT.md)
- Deploy guide: [deploy/README.md](deploy/README.md)
