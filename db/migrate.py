"""Apply SQL migrations in db/migrations in order. Each file runs once, in its own transaction.

Usage: uv run python -m db.migrate
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

MIGRATIONS = Path(__file__).parent / "migrations"
DEFAULT_URL = "postgresql://yk:yk@localhost:5432/yk"


def database_url():
    load_dotenv()
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def migrate(conn):
    """Apply pending migrations. Returns the names applied."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                 "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    conn.commit()
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied


if __name__ == "__main__":
    with psycopg.connect(database_url()) as conn:
        applied = migrate(conn)
    print(f"applied: {applied}" if applied else "up to date")
