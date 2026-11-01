from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from docweave.persistence.local_database import create_local_engine


def test_local_schema_has_six_tables_and_foreign_keys(tmp_path: Path) -> None:
    engine = create_local_engine("sqlite:///" + (tmp_path / "memory.db").as_posix())
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        "documents",
        "agent_runs",
        "proposals",
        "human_decisions",
        "file_history",
        "document_relationships",
    }
    assert inspector.get_foreign_keys("file_history")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    engine.dispose()


def test_local_schema_initialization_is_repeatable_and_persistent(
    tmp_path: Path,
) -> None:
    url = "sqlite:///" + (tmp_path / "memory.db").as_posix()
    first = create_local_engine(url)
    with first.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents VALUES "
                "('d','w','.','old.pdf','.','old.pdf',"
                ":hash,1,'discovered',CURRENT_TIMESTAMP)"
            ),
            {"hash": bytes(32)},
        )
    first.dispose()
    second = create_local_engine(url)
    with second.connect() as conn:
        assert (
            conn.execute(text("SELECT original_filename FROM documents")).scalar_one()
            == "old.pdf"
        )
    second.dispose()


@pytest.mark.parametrize(
    "url", ["postgresql://localhost/db", "sqlite://remote/db", "https://example.com"]
)
def test_nonlocal_database_is_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="local SQLite|Invalid SQLite|Could not parse"):
        create_local_engine(url)


def test_foreign_keys_reject_orphan_decisions(tmp_path: Path) -> None:
    engine = create_local_engine("sqlite:///" + (tmp_path / "memory.db").as_posix())
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO human_decisions VALUES "
                "('h','missing','reviewer','approve',NULL,CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()
