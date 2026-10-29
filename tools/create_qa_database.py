"""Create a new local benchmark database; never reuses an existing name."""

from datetime import datetime, timezone
import psycopg
from psycopg import sql

name = "helm_qa_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
with psycopg.connect(
    "postgresql://helm:helm_local_demo_only@127.0.0.1:55439/postgres", autocommit=True
) as db:
    db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
print(name)
