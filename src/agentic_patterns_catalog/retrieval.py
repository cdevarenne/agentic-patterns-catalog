"""`select`: facet filter → BM25 ∥ local embeddings → Reciprocal Rank Fusion. Deterministic; no network."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from rank_bm25 import BM25Okapi

from . import vocab as vocab_mod
from .cli import register
from .model import Pattern
from .paths import CATALOG_DIR, EMBEDDINGS_DIR
from .store import FileStore, Store, content_version

EMPTY_MESSAGE = "No pattern matches in the catalog."
K_RRF = 60
_TOKEN = re.compile(r"[a-z0-9]+")
Arms = Sequence[str]


def tokenize(text: str) -> list[str]:
    """Lower-case alphanumeric runs; the same tokenizer for the corpus and the query."""
    return _TOKEN.findall(text.lower())


def facet_arg(raw: str) -> tuple[str, str]:
    """argparse `type=` for `--facet NAME=VALUE`. Rejects a value with no `=`."""
    name, sep, value = raw.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError(f"expected NAME=VALUE, got {raw!r}")
    return name, value


def pattern_text(p: Pattern) -> str:
    """The text both arms index: name, tldr what/when, problem signals, use cases, and 'when to use' details.

    `tldr.watchOut` is excluded on purpose: it names failure modes, not the problem the pattern solves.
    Category-level `whenToUse` is excluded because it describes the category, not one pattern.
    """
    d = p.content.details
    parts = [p.name, p.content.tldr.what, p.content.tldr.when, *p.selection.problem_signals, *p.content.useCases,
             *d.get("when_to_use.use_when", []), *d.get("best_use_cases", []), *d.get("top_use_cases", [])]
    return " ".join(parts)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalize(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return v / norms


class HashEmbedder:
    """Deterministic bag-of-words hashing. For tests and as an offline stand-in; not a semantic model."""
    name = "hash-bow-256"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for row, text in enumerate(texts):
            for tok in tokenize(text):
                out[row, int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return _normalize(out)


class FastEmbedEmbedder:
    """Local ONNX embeddings via fastembed (extra `embed`)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding  # imported here so the core install stays light

        self.name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalize(np.asarray(list(self._model.embed(texts)), dtype="float32"))


def default_embedder() -> Embedder | None:
    """The fastembed embedder, or None (with one line on stderr) when it cannot load for any reason."""
    try:
        return FastEmbedEmbedder()
    except Exception as e:  # noqa: BLE001 — any load failure (no extra, no model, no network) means BM25 only
        print(f"semantic arm off: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def embedding_cache_path(model_name: str, dir: Path = EMBEDDINGS_DIR) -> Path:
    """The matrix file for `model_name`. A `/` in the name becomes `_`, so the name stays one file name."""
    return dir / f"{model_name.replace('/', '_')}.npy"


def _sorted_by_id(patterns: Sequence[Pattern]) -> list[Pattern]:
    return sorted(patterns, key=lambda p: p.id)


def build_embedding_cache(patterns: Sequence[Pattern], embedder: Embedder,
                          dir: Path = EMBEDDINGS_DIR) -> Path:
    """Embed every pattern in id order. Write the matrix and the sidecar. Return the matrix path.

    The sidecar records the model and the ids, so `load_embedding_cache` can reject a stale cache.
    """
    ordered = _sorted_by_id(patterns)
    matrix = embedder.embed([pattern_text(p) for p in ordered]).astype("float32")
    path = embedding_cache_path(embedder.name, dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, matrix)
    meta = {"model": embedder.name, "ids": [p.id for p in ordered], "dim": int(matrix.shape[1])}
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return path


def load_embedding_cache(patterns: Sequence[Pattern], embedder_name: str,
                         dir: Path = EMBEDDINGS_DIR) -> np.ndarray | None:
    """The cached matrix when it was built by `embedder_name` from these ids; else None.

    A cache that is absent, unreadable or stale is a miss, never an error: the caller embeds again.
    """
    path = embedding_cache_path(embedder_name, dir)
    sidecar = path.with_suffix(".json")
    if not (path.exists() and sidecar.exists()):
        return None
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        if meta.get("model") != embedder_name or meta.get("ids") != [p.id for p in _sorted_by_id(patterns)]:
            return None
        return np.load(path)
    except (OSError, ValueError):
        return None


def rrf(rankings: list[list[str]], k: int = K_RRF) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. Ties break by id so the order is reproducible."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, id in enumerate(ranking, start=1):
            scores[id] = scores.get(id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass
class Hit:
    id: str
    name: str
    category: str
    score_bm25: float | None
    score_semantic: float | None
    rrf_rank: int
    retrieval_path: str
    reviewed: bool
    provenance: dict[str, Any]
    relations: list[dict[str, Any]]


@dataclass
class SelectResult:
    hits: list[Hit]
    retrieval_path: str
    catalog_version: str
    auth: dict[str, str]
    empty_message: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matches(p: Pattern, facets: dict[str, str] | None) -> bool:
    return not facets or all(getattr(p.selection.facets, k, None) == v for k, v in facets.items())


class Selector:
    def __init__(self, patterns: list[Pattern], embedder: Embedder | None = None,
                 arms: Arms = ("bm25", "semantic"), version: str | None = None,
                 embedding_cache: bool = True) -> None:
        self.patterns = sorted(patterns, key=lambda p: p.id)
        self.arms = tuple(a for a in arms if a != "semantic" or embedder is not None)
        self.embedder = embedder if "semantic" in self.arms else None
        self.version = version or content_version(self.patterns)
        self.vocab = vocab_mod.load_vocab()
        texts = [pattern_text(p) for p in self.patterns]
        self._bm25 = (BM25Okapi([tokenize(t) or ["_"] for t in texts])
                      if "bm25" in self.arms and self.patterns else None)
        self._vectors = None
        if self.embedder is not None and self.patterns:
            cached = load_embedding_cache(self.patterns, self.embedder.name) if embedding_cache else None
            # `compile --embeddings` writes the cache; a selector never does.
            self._vectors = cached if cached is not None else self.embedder.embed(texts)

    @classmethod
    def from_store(cls, store: Store, embedder: Embedder | None = None, arms: Arms = ("bm25", "semantic")) -> Selector:
        return cls(store.all(), embedder, arms)

    def _validate(self, facets: dict[str, str] | None, k: int) -> None:
        if k < 1:
            raise ValueError("k must be >= 1")
        for name, value in (facets or {}).items():
            if name not in vocab_mod.FACET_NAMES:
                raise ValueError(f"unknown facet {name!r}; known: {', '.join(vocab_mod.FACET_NAMES)}")
            if value not in self.vocab[name]:
                raise ValueError(f"unknown value {value!r} for facet {name!r}")

    def select(self, task: str, facets: dict[str, str] | None = None, k: int = 5,
               subject: str = "stdio-local") -> SelectResult:
        self._validate(facets, k)
        idx = [i for i, p in enumerate(self.patterns) if _matches(p, facets)]
        path = "rrf" if len(self.arms) == 2 else (self.arms[0] if self.arms else "none")
        auth = {"subject": subject}
        if not idx:
            return SelectResult([], path, self.version, auth, EMPTY_MESSAGE)
        bm_scores: dict[str, float] = {}
        sem_scores: dict[str, float] = {}
        rankings: list[list[str]] = []
        if self._bm25 is not None:
            raw = self._bm25.get_scores(tokenize(task))
            bm_scores = {self.patterns[i].id: float(raw[i]) for i in idx if raw[i] > 0}
            rankings.append(sorted(bm_scores, key=lambda id: (-bm_scores[id], id)))
        if self._vectors is not None and self.embedder is not None:
            q = self.embedder.embed([task])[0]
            sims = self._vectors @ q
            sem_scores = {self.patterns[i].id: float(sims[i]) for i in idx}
            rankings.append(sorted(sem_scores, key=lambda id: (-sem_scores[id], id)))
        fused = rrf([r for r in rankings if r])
        if not fused:
            return SelectResult([], path, self.version, auth, EMPTY_MESSAGE)
        by_id = {p.id: p for p in self.patterns}
        hits = []
        for rank, (id, _) in enumerate(fused[:k], start=1):
            p = by_id[id]
            in_bm, in_sem = id in bm_scores, id in sem_scores
            hits.append(Hit(
                id=p.id, name=p.name, category=p.category,
                score_bm25=bm_scores.get(id), score_semantic=sem_scores.get(id), rrf_rank=rank,
                retrieval_path="rrf" if in_bm and in_sem else ("bm25" if in_bm else "semantic"),
                reviewed=p.reviewed, provenance=p.provenance.model_dump(mode="json"),
                relations=[r.model_dump(mode="json") for r in p.selection.relations],
            ))
        return SelectResult(hits, path, self.version, auth, None)


@register("select", "pick the patterns that fit a task")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("task")
    parser.add_argument("--facet", type=facet_arg, action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--no-embed", action="store_true", help="BM25 only")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)

    def run(ns: argparse.Namespace) -> int:
        facets = dict(ns.facet)
        embedder = None if ns.no_embed else default_embedder()
        try:
            res = Selector.from_store(FileStore(ns.root), embedder).select(ns.task, facets or None, ns.k)
        except ValueError as e:
            print(f"select: {e}", file=sys.stderr)
            return 2
        if ns.json:
            print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        elif res.empty_message:
            print(res.empty_message)
        else:
            for h in res.hits:
                print(f"{h.rrf_rank}. {h.id} [{h.category}] via {h.retrieval_path}"
                      f"  bm25={h.score_bm25 and round(h.score_bm25, 3)} sem={h.score_semantic and round(h.score_semantic, 3)}"
                      f"  reviewed={h.reviewed}")
            print(f"catalog {res.catalog_version}; path {res.retrieval_path}")
        return 0
    return run
