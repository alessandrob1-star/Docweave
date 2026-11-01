from pathlib import Path

import pytest

from docweave import runtime_preflight
from docweave.runtime_preflight import PreflightState, run_preflight


def test_preflight_reports_real_local_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "DOCWEAVE_DATABASE_URL", "sqlite:///" + (tmp_path / "memory.db").as_posix()
    )
    monkeypatch.setattr(runtime_preflight, "model_available", lambda: True)
    report = run_preflight(check_database=True)
    assert report.succeeded
    assert {c.name for c in report.checks} == {
        "runtime_config",
        "llm_client",
        "sqlite_connection",
        "docweave_schema",
    }


def test_model_unavailable_is_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "DOCWEAVE_DATABASE_URL", "sqlite:///" + (tmp_path / "memory.db").as_posix()
    )
    monkeypatch.setattr(runtime_preflight, "model_available", lambda: False)
    report = run_preflight()
    assert not report.succeeded
    assert (
        next(c for c in report.checks if c.name == "llm_client").state
        is PreflightState.FAIL
    )


def test_nonlocal_database_is_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCWEAVE_DATABASE_URL", "postgresql://remote/db")
    assert not run_preflight().succeeded
