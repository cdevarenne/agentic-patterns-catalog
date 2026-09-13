"""Controlled facet vocabulary. One data file; the schema, Postgres and rego derive from it."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import VOCAB_PATH

FACET_NAMES = ("scale", "latency_cost", "token_cost", "risk_class", "maturity")


def load_vocab(path: Path = VOCAB_PATH) -> dict[str, list[str]]:
    """Read facets.json. Every facet must be present with unique, non-empty values."""
    vocab: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(set(FACET_NAMES) - set(vocab))
    if missing:
        raise ValueError(f"{path} lacks facets {missing}")
    for name, values in vocab.items():
        if not values or len(values) != len(set(values)):
            raise ValueError(f"facet {name!r}: values must be non-empty and unique")
    return vocab


def unknown_facet_values(facets: dict[str, str | None], vocab: dict[str, list[str]]) -> list[str]:
    """`facet=value` entries that are set but not in the vocabulary."""
    return [f"{k}={v}" for k, v in facets.items() if v is not None and v not in vocab.get(k, [])]
