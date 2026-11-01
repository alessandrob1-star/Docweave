"""Observable local model and database readiness checks."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from docweave.analysis.llm_gateway import model_available
from docweave.application_runtime import (
    RuntimeConfigurationError,
    RuntimeEnvironmentConfig,
    build_configured_classification_runtime,
)


class PreflightState(StrEnum):
    """Sanitized preflight state."""

    OK = "ok"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    """One content-free preflight result."""

    name: str
    state: PreflightState
    detail: str


@dataclass(frozen=True, slots=True)
class RuntimePreflightReport:
    """Preflight summary safe for terminal output."""

    checks: tuple[PreflightCheck, ...]

    @property
    def succeeded(self) -> bool:
        """Return true when no check failed."""
        return all(check.state is not PreflightState.FAIL for check in self.checks)


class RuntimeBundle(Protocol):
    """Configured runtime attributes needed by preflight checks."""

    @property
    def config(self) -> RuntimeEnvironmentConfig:
        """Return loaded runtime configuration."""

    @property
    def engine(self) -> Engine:
        """Return configured SQLAlchemy engine."""


RuntimeBuilder = Callable[[], RuntimeBundle]


def _default_runtime_builder() -> RuntimeBundle:
    return build_configured_classification_runtime()


def run_preflight(
    *,
    check_database: bool = False,
    runtime_builder: RuntimeBuilder = _default_runtime_builder,
) -> RuntimePreflightReport:
    checks: list[PreflightCheck] = []
    try:
        runtime = runtime_builder()
    except (RuntimeConfigurationError, ValueError, SQLAlchemyError) as error:
        return RuntimePreflightReport(
            (
                PreflightCheck(
                    "runtime_config", PreflightState.FAIL, type(error).__name__
                ),
            )
        )
    checks.append(PreflightCheck("runtime_config", PreflightState.OK, "loaded"))
    available = model_available()
    checks.append(
        PreflightCheck(
            "llm_client",
            PreflightState.OK if available else PreflightState.FAIL,
            "qwen2.5:14b-instruct:available"
            if available
            else "local_model_unavailable",
        )
    )
    if check_database:
        checks.extend(_database_checks(runtime.engine))
    else:
        checks.append(
            PreflightCheck("sqlite_connection", PreflightState.SKIP, "not_requested")
        )
    runtime.engine.dispose()
    return RuntimePreflightReport(tuple(checks))


def _database_checks(engine: Engine) -> tuple[PreflightCheck, ...]:
    try:
        tables = set(inspect(engine).get_table_names())
    except SQLAlchemyError:
        return (
            PreflightCheck("sqlite_connection", PreflightState.FAIL, "unavailable"),
        )
    required = {
        "documents",
        "agent_runs",
        "proposals",
        "human_decisions",
        "file_history",
        "document_relationships",
    }
    missing = sorted(required - tables)
    return (
        PreflightCheck("sqlite_connection", PreflightState.OK, "reachable"),
        PreflightCheck(
            "docweave_schema",
            PreflightState.FAIL if missing else PreflightState.OK,
            "missing:" + ",".join(missing) if missing else "ready",
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check local Ollama and SQLite readiness."
    )
    parser.add_argument("--database", action="store_true")
    args = parser.parse_args(argv)
    report = run_preflight(check_database=args.database)
    for check in report.checks:
        print(f"{check.name}: {check.state.value} ({check.detail})")
    return 0 if report.succeeded else 2


if __name__ == "__main__":
    raise SystemExit(main())
