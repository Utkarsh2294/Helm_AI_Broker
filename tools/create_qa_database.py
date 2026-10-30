"""Create a new local benchmark database; never reuses an existing name."""

from datetime import datetime, timezone
import psycopg
import sys
from psycopg import sql

name = "helm_qa_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
with psycopg.connect(
    "postgresql://helm:helm_local_demo_only@127.0.0.1:55439/postgres", autocommit=True
) as db:
    if "--latest" in sys.argv:
        row = db.execute(
            "SELECT datname FROM pg_database WHERE datname ~ '^helm_qa_[0-9]+$' ORDER BY datname DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise RuntimeError("No project QA database exists")
        name = row[0]
    else:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
print(name)
