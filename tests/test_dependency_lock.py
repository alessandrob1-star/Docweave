import tomllib
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dependency_manifests_match() -> None:
    requirements = set((ROOT / "requirements.txt").read_text().splitlines())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert set(project["project"]["dependencies"]) == requirements
    assert requirements == {"PySide6==6.11.1", "SQLAlchemy==2.0.51"}


def test_lock_is_pinned_and_matches_runtime() -> None:
    lines = (ROOT / "requirements-lock.txt").read_text().splitlines()
    assert all("==" in line for line in lines if line)
    for package in ("PySide6", "SQLAlchemy", "shiboken6"):
        assert any(
            line.lower() == (package + "==" + version(package)).lower()
            for line in lines
        )
