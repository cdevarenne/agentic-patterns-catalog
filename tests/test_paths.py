import importlib
from pathlib import Path

import pytest

from agentic_patterns_catalog import paths


def test_default_root_is_the_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CATALOG_ROOT", raising=False)
    assert paths.repo_root() == Path(paths.__file__).resolve().parents[2]


def test_env_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "catalog").mkdir()
    monkeypatch.setenv("CATALOG_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()
    importlib.reload(paths)
    assert paths.CATALOG_DIR == tmp_path.resolve() / "catalog"
    monkeypatch.delenv("CATALOG_ROOT")
    importlib.reload(paths)  # restore the module for the rest of the suite


def test_override_must_point_at_a_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CATALOG_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="catalog/"):
        paths.repo_root()
