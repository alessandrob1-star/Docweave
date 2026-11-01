from pathlib import Path

from docweave.memory_schema_report import collect_memory_schema_from_engine
from docweave.persistence.local_database import create_local_engine


def test_schema_report_uses_actual_local_columns_and_keys(tmp_path: Path) -> None:
    engine = create_local_engine("sqlite:///" + (tmp_path / "memory.db").as_posix())
    report = collect_memory_schema_from_engine(engine)
    assert len(report.tables) == 6
    documents = next(row for row in report.tables if row.table_name == "documents")
    assert documents.primary_key_columns == ("document_id",)
    assert {"original_filename", "current_filename"} <= {
        column.name for column in documents.columns
    }
    history = next(row for row in report.tables if row.table_name == "file_history")
    assert len(history.foreign_keys) == 3
    engine.dispose()
