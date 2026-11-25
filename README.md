# YK Finance voice agent

A voice agent for loan payment reminders and early collections, built as if for a real lender. Work in progress.

Start here: `docs/engagement/problem-statement.md`, then `docs/engagement/design.md`. Decisions are in `DECISIONS.md`, the plan in `docs/PLAN.md`.

## Run locally

Needs Docker and [uv](https://docs.astral.sh/uv/).

```
docker compose up -d          # Postgres
uv sync
uv run python -m db.migrate   # create tables
uv run pytest -q              # unit + integration tests
```

Evals (needs `OPENAI_API_KEY` in `.env`):

```
uv run python -m evals.run_evals --k 3
```
