"""SQLite initialization for local-only persistent memory."""

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool


def create_local_engine(url: str, **kwargs: Any) -> Engine:
    """Reject network databases and initialize the versioned local schema."""
    parsed = make_url(url)
    if parsed.drivername != "sqlite" or parsed.host:
        raise ValueError("DocWeave requires a local SQLite database.")
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    if parsed.database != ":memory:":
        kwargs.setdefault("poolclass", NullPool)
    engine = create_engine(url, connect_args={"timeout": 30}, **kwargs)

    @event.listens_for(engine, "connect")
    def configure(connection: Any, _record: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")

    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with engine.begin() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        if version not in {0, 1}:
            raise ValueError("Unsupported local database schema version.")
        for statement in schema.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
        connection.exec_driver_sql("PRAGMA user_version=1")
    return engine
