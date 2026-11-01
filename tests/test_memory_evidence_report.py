from pathlib import Path

from docweave.memory_evidence_report import collect_memory_evidence_from_engine
from docweave.persistence.local_database import create_local_engine


def test_real_local_memory_evidence_reports_all_tables(tmp_path: Path) -> None:
    engine = create_local_engine("sqlite:///" + (tmp_path / "memory.db").as_posix())
    report = collect_memory_evidence_from_engine(engine)
    assert report.schema_ready
    assert len(report.table_counts) == 6
    assert all(row.row_count == 0 for row in report.table_counts)
    engine.dispose()


def test_missing_table_is_not_ready(tmp_path: Path) -> None:
    engine = create_local_engine("sqlite:///" + (tmp_path / "memory.db").as_posix())
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE document_relationships")
    report = collect_memory_evidence_from_engine(engine)
    assert not report.schema_ready
    assert any(not row.present for row in report.table_counts)
    engine.dispose()
