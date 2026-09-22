"""PostgresStore and PostgresLedger against the local instance. Skipped without CATALOG_PG_TEST_DSN."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("psycopg")
from tests.test_server import _p

from agentic_patterns_catalog import pgstore, retrieval, store
from agentic_patterns_catalog.model import content_hash


@pytest.fixture
def files(tmp_path: Path) -> store.FileStore:
    fs = store.FileStore(tmp_path, tmp_path / "cache", tmp_path / "emb")
    for p in (_p("content-router"), _p("semantic-router"), _p("episodic-memory", "memory-management")):
        fs.put(p)
    return fs


@pytest.fixture
def pg(pg_dsn: str, pg_schema: str) -> pgstore.PostgresStore:
    s = pgstore.PostgresStore(pg_dsn, schema=pg_schema)
    s.ensure_schema()
    return s


def test_sync_mirrors_the_files_and_the_version_agrees(pg: pgstore.PostgresStore, files: store.FileStore) -> None:
    counts = pg.sync_from(files)
    assert counts == {"patterns": 3, "categories": 0, "recipes": 0, "embeddings": 0, "removed": 0}
    assert [p.id for p in pg.all()] == ["content-router", "episodic-memory", "semantic-router"]
    assert pg.get("content-router").content.code == {"python": "# content-router"}
    assert store.content_version(pg.all()) == store.content_version(files.all())
    with pytest.raises(KeyError):
        pg.get("nope")


def test_sync_removes_rows_that_left_the_files(pg: pgstore.PostgresStore, files: store.FileStore, tmp_path: Path) -> None:
    pg.sync_from(files)
    (tmp_path / "patterns" / "routing" / "semantic-router.json").unlink()
    assert pg.sync_from(files)["removed"] == 1
    assert [p.id for p in pg.all()] == ["content-router", "episodic-memory"]


def test_put_writes_the_merged_record(pg: pgstore.PostgresStore, files: store.FileStore) -> None:
    pg.sync_from(files)
    changed = files.get("content-router")
    changed.content.description = "changed"
    changed.provenance.source.content_sha256 = content_hash(changed.content)
    pg.put(changed)
    assert pg.get("content-router").content.description == "changed"


def test_embeddings_round_trip_only_when_complete(pg: pgstore.PostgresStore, files: store.FileStore) -> None:
    emb = retrieval.HashEmbedder(dim=8)
    retrieval.build_embedding_cache(files.all(), emb, files.embeddings_dir)
    assert pg.sync_from(files, embeddings_model=emb.name)["embeddings"] == 3
    ids, matrix = pg.embeddings(emb.name)
    assert ids == ["content-router", "episodic-memory", "semantic-router"] and matrix.shape == (3, 8)
    assert np.allclose(matrix, retrieval.load_embedding_cache(files.all(), emb.name, files.embeddings_dir))
    assert pg.embeddings("other-model") is None


def test_ledger_appends_rows(pg_dsn: str, pg_schema: str, pg: pgstore.PostgresStore) -> None:
    ledger = pgstore.PostgresLedger(pg_dsn, schema=pg_schema)
    ledger.append(store.ActivityEvent("2026-09-21T00:00:00Z", "select", "a@x.com", "allow", {"task": "x"}, [], {}))
    ledger.append(store.ActivityEvent("2026-09-21T00:00:01Z", "select", "a@x.com", "result", {"task": "x"}, ["a", "b"],
                                      {"catalog_version": "abc"}))
    rows = ledger.tail(10)
    assert [(r["decision"], r["hits"]) for r in rows] == [("allow", []), ("result", ["a", "b"])]
    assert rows[1]["provenance"] == {"catalog_version": "abc"}


def test_store_and_ledger_from_env(pg_dsn: str, tmp_path: Path) -> None:
    assert isinstance(pgstore.store_from_env({}, tmp_path), store.FileStore)
    assert isinstance(pgstore.ledger_from_env({}), store.JsonlLedger)
    assert isinstance(pgstore.store_from_env({"CATALOG_STORE": "pg", "CATALOG_PG_DSN": pg_dsn}, tmp_path), pgstore.PostgresStore)
    with pytest.raises(ValueError, match="CATALOG_PG_DSN"):
        pgstore.store_from_env({"CATALOG_STORE": "pg"}, tmp_path)
    with pytest.raises(ValueError, match="CATALOG_LEDGER"):
        pgstore.ledger_from_env({"CATALOG_LEDGER": "redis"})
