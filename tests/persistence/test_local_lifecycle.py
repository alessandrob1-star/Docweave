from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from test_simple_memory_repository import NOW, command

from docweave.persistence import (
    PersistenceDisposition,
    PersistHumanDecision,
    SQLiteSimpleMemoryRepository,
    SQLiteTransactionRunner,
)
from docweave.persistence.local_database import create_local_engine


def test_analysis_approval_and_restore_history_survive_reopen(tmp_path: Path) -> None:
    url = "sqlite:///" + (tmp_path / "memory.db").as_posix()
    engine = create_local_engine(url)
    repository = SQLiteSimpleMemoryRepository(SQLiteTransactionRunner(engine))
    analysis = command()
    assert repository.persist_analysis(analysis) is PersistenceDisposition.APPLIED
    assert (
        repository.persist_analysis(analysis)
        is PersistenceDisposition.IDEMPOTENT_REPLAY
    )
    decision = PersistHumanDecision(
        proposal_id=analysis.proposal_id,
        human_decision_id=uuid4(),
        actor_label="local-reviewer",
        decision="approve",
        decided_at_utc=NOW,
        document_id=analysis.document_id,
        operation="rename_and_move",
        previous_directory=analysis.original_directory,
        previous_filename=analysis.original_filename,
        next_directory=analysis.proposed_directory,
        next_filename=analysis.proposed_filename,
        file_status="succeeded",
    )
    assert repository.persist_human_decision(decision) is PersistenceDisposition.APPLIED
    assert (
        repository.persist_human_decision(decision)
        is PersistenceDisposition.IDEMPOTENT_REPLAY
    )
    engine.dispose()
    reopened = create_local_engine(url)
    with reopened.connect() as connection:
        document = connection.execute(text("SELECT * FROM documents")).mappings().one()
        assert document["original_filename"] == analysis.original_filename
        assert document["current_filename"] == analysis.proposed_filename
        assert (
            connection.execute(text("SELECT count(*) FROM file_history")).scalar() == 1
        )
        assert (
            connection.execute(text("SELECT count(*) FROM human_decisions")).scalar()
            == 1
        )
    reopened.dispose()


def test_rejected_proposal_does_not_change_stored_path(tmp_path: Path) -> None:
    engine = create_local_engine("sqlite:///" + (tmp_path / "memory.db").as_posix())
    repository = SQLiteSimpleMemoryRepository(SQLiteTransactionRunner(engine))
    analysis = replace(
        command(), document_id=uuid4(), agent_run_id=uuid4(), proposal_id=uuid4()
    )
    repository.persist_analysis(analysis)
    repository.persist_human_decision(
        PersistHumanDecision(
            proposal_id=analysis.proposal_id,
            human_decision_id=uuid4(),
            actor_label="local-reviewer",
            decision="reject",
            decided_at_utc=NOW,
        )
    )
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT current_filename FROM documents")).scalar()
            == analysis.original_filename
        )
        assert (
            connection.execute(text("SELECT count(*) FROM file_history")).scalar() == 0
        )
    engine.dispose()
