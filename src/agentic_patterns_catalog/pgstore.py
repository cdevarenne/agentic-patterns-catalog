"""Postgres mirror of the files: `PostgresStore` and `PostgresLedger` (extra `pg`). Files stay the source of truth."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from .cli import register
from .model import Category, Pattern, Recipe
from .paths import CATALOG_DIR, CONTENT_CACHE_DIR, EMBEDDINGS_DIR
from .store import ActivityEvent, Embeddings, FileStore, JsonlLedger, Ledger, Store

SCHEMA_SQL = """
create extension if not exists vector;
create table if not exists {s}.pattern (
    id text primary key, doc jsonb not null, content_sha256 text not null, updated_at timestamptz not null default now());
create table if not exists {s}.category (id text primary key, doc jsonb not null);
create table if not exists {s}.recipe (id text primary key, doc jsonb not null);
create table if not exists {s}.pattern_embedding (
    id text not null references {s}.pattern(id) on delete cascade, model text not null, vec vector not null,
    primary key (id, model));
create table if not exists {s}.activity (
    id bigserial primary key, ts timestamptz not null, tool text not null, subject text not null,
    decision text not null, args jsonb not null, hits text[] not null, provenance jsonb not null);
"""


def _connect(dsn: str, schema: str):
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(f'create schema if not exists "{schema}"')
    conn.execute(f'set search_path to "{schema}", public')
    conn.execute("create extension if not exists vector")
    register_vector(conn)
    return conn


class PostgresStore:
    """Records as jsonb in `pattern.doc` (content included when the files had it cached)."""

    def __init__(self, dsn: str, schema: str = "public") -> None:
        self.dsn, self.schema = dsn, schema

    def _conn(self):
        return _connect(self.dsn, self.schema)

    def ensure_schema(self) -> None:
        with self._conn() as c:
            c.execute(SCHEMA_SQL.format(s=f'"{self.schema}"'))

    def all(self) -> list[Pattern]:
        with self._conn() as c:
            rows = c.execute("select doc from pattern order by id").fetchall()
        return [Pattern.model_validate(r[0]) for r in rows]

    def get(self, id: str) -> Pattern:
        with self._conn() as c:
            row = c.execute("select doc from pattern where id = %s", (id,)).fetchone()
        if row is None:
            raise KeyError(id)
        return Pattern.model_validate(row[0])

    def put(self, pattern: Pattern) -> None:
        """Upsert the merged record. `content` None keeps the stored content (the doc is merged before the write)."""
        if pattern.content is None:
            try:
                pattern = pattern.model_copy(update={"content": self.get(pattern.id).content})
            except KeyError:
                pass
        doc = json.dumps(pattern.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        with self._conn() as c:
            c.execute("insert into pattern (id, doc, content_sha256) values (%s, %s::jsonb, %s) "
                      "on conflict (id) do update set doc = excluded.doc, content_sha256 = excluded.content_sha256, "
                      "updated_at = now()", (pattern.id, doc, pattern.provenance.source.content_sha256))

    def categories(self) -> list[Category]:
        with self._conn() as c:
            return [Category.model_validate(r[0]) for r in c.execute("select doc from category order by id").fetchall()]

    def recipes(self) -> list[Recipe]:
        with self._conn() as c:
            return [Recipe.model_validate(r[0]) for r in c.execute("select doc from recipe order by id").fetchall()]

    def embeddings(self, model_name: str) -> Embeddings | None:
        """Vectors for every pattern in id order, or None when any pattern lacks one for `model_name`."""
        with self._conn() as c:
            n = c.execute("select count(*) from pattern").fetchone()[0]
            rows = c.execute("select p.id, e.vec from pattern p join pattern_embedding e on e.id = p.id "
                             "where e.model = %s order by p.id", (model_name,)).fetchall()
        if not rows or len(rows) != n:
            return None
        return [r[0] for r in rows], np.stack([
            np.asarray(r[1].to_numpy() if hasattr(r[1], "to_numpy") else r[1], dtype=np.float32) for r in rows
        ])

    def sync_from(self, files: FileStore, embeddings_model: str | None = None) -> dict[str, int]:
        """Make the tables equal to the files: upsert every record, delete the rest, copy the embedding cache."""
        from .retrieval import load_embedding_cache

        self.ensure_schema()
        patterns = files.all()
        ids = [p.id for p in patterns]
        for p in patterns:
            self.put(p)
        with self._conn() as c:
            removed = c.execute("delete from pattern where not (id = any(%s))", (ids,)).rowcount
            for table, docs in (("category", files.categories()), ("recipe", files.recipes())):
                c.execute(f"delete from {table}")
                for d in docs:
                    c.execute(f"insert into {table} (id, doc) values (%s, %s::jsonb)",
                              (d.id, json.dumps(d.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)))
            embedded = 0
            if embeddings_model:
                matrix = load_embedding_cache(patterns, embeddings_model, files.embeddings_dir)
                if matrix is not None:
                    c.execute("delete from pattern_embedding where model = %s", (embeddings_model,))
                    for id, vec in zip(sorted(ids), matrix, strict=True):
                        c.execute("insert into pattern_embedding (id, model, vec) values (%s, %s, %s)", (id, embeddings_model, vec))
                    embedded = len(ids)
        return {"patterns": len(ids), "categories": len(files.categories()), "recipes": len(files.recipes()),
                "embeddings": embedded, "removed": removed}


class PostgresLedger:
    """Append-only `activity` table; the shape of `ActivityEvent`, one row per event."""

    def __init__(self, dsn: str, schema: str = "public") -> None:
        self.dsn, self.schema = dsn, schema

    def append(self, event: ActivityEvent) -> None:
        with _connect(self.dsn, self.schema) as c:
            c.execute("insert into activity (ts, tool, subject, decision, args, hits, provenance) "
                      "values (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)",
                      (event.ts, event.tool, event.subject, event.decision, json.dumps(event.args),
                       event.hits, json.dumps(event.provenance)))

    def tail(self, n: int) -> list[dict[str, Any]]:
        """The last `n` rows, oldest first. For tests and for a look at the ledger."""
        with _connect(self.dsn, self.schema) as c:
            rows = c.execute("select ts, tool, subject, decision, args, hits, provenance from "
                             "(select * from activity order by id desc limit %s) t order by id", (n,)).fetchall()
        keys = ("ts", "tool", "subject", "decision", "args", "hits", "provenance")
        return [dict(zip(keys, r, strict=True)) for r in rows]


def _dsn(env: Mapping[str, str], what: str) -> str:
    dsn = env.get("CATALOG_PG_DSN")
    if not dsn:
        raise ValueError(f"{what}=pg needs CATALOG_PG_DSN")
    return dsn


def store_from_env(env: Mapping[str, str], root: Path = CATALOG_DIR) -> Store:
    """`CATALOG_STORE=file` (default) or `pg`."""
    kind = env.get("CATALOG_STORE", "file")
    if kind == "file":
        return FileStore(root, CONTENT_CACHE_DIR, EMBEDDINGS_DIR)
    if kind == "pg":
        return PostgresStore(_dsn(env, "CATALOG_STORE"), env.get("CATALOG_PG_SCHEMA", "public"))
    raise ValueError(f"CATALOG_STORE={kind!r}; known: file, pg")


def ledger_from_env(env: Mapping[str, str]) -> Ledger:
    """`CATALOG_LEDGER=jsonl` (default) or `pg`."""
    kind = env.get("CATALOG_LEDGER", "jsonl")
    if kind == "jsonl":
        return JsonlLedger()
    if kind == "pg":
        return PostgresLedger(_dsn(env, "CATALOG_LEDGER"), env.get("CATALOG_PG_SCHEMA", "public"))
    raise ValueError(f"CATALOG_LEDGER={kind!r}; known: jsonl, pg")


@register("sync-pg", "load the Postgres mirror from the files (extra pg)")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--dsn", default=os.environ.get("CATALOG_PG_DSN"), help="default: $CATALOG_PG_DSN")
    parser.add_argument("--schema", default=os.environ.get("CATALOG_PG_SCHEMA", "public"))
    parser.add_argument("--embeddings", metavar="MODEL", help="also copy the embedding cache for MODEL")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        if not ns.dsn:
            print("sync-pg: set --dsn or CATALOG_PG_DSN", file=sys.stderr)
            return 2
        counts = PostgresStore(ns.dsn, ns.schema).sync_from(FileStore(ns.root), ns.embeddings)
        print(" ".join(f"{k}={v}" for k, v in counts.items()))
        return 0
    return run
