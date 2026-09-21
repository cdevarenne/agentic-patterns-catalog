"""Pydantic models: the source of truth for every record shape. `schema/*.json` is generated from here."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import vocab as vocab_mod

Kind = Literal["pattern", "technique", "benchmark", "tool"]
RelationType = Literal["alternative_to", "composes_with", "requires", "precedes"]
Extraction = Literal["rsc-payload", "free-pack"]
EnrichmentMethod = Literal["llm-draft", "human", "derived"]

SELECTION_FIELDS = ("problem_signals", "preconditions", "contraindications", "facets", "relations")
# Ids and category ids are file and directory names: one lower-case path segment, no dots or slashes.
ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tldr(Strict):
    what: str
    when: str
    watchOut: str


class Flow(Strict):
    """The pattern's mechanism diagram. Nodes, edges and steps pass through unchanged."""
    title: str | None = None
    description: str | None = None
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []


class Content(Strict):
    """Source content. Field names follow the free pack's patterns.json where it has the field."""
    description: str
    tldr: Tldr
    abbr: str | None = None
    features: list[str] = []
    useCases: list[str] = []
    example: str | None = None
    code: dict[str, str] = {}
    references: list[str] = []
    flow: Flow | None = None
    details: dict[str, list[str]] = {}


class Facets(Strict):
    """Values must come from catalog/vocab/facets.json; construction fails on any other value."""
    scale: str | None = None
    latency_cost: str | None = None
    token_cost: str | None = None
    risk_class: str | None = None
    maturity: str | None = None

    @model_validator(mode="after")
    def _values_in_vocabulary(self) -> Facets:
        bad = vocab_mod.unknown_facet_values(self.model_dump(), vocab_mod.load_vocab())
        if bad:
            raise ValueError(f"unknown facet values: {', '.join(bad)}")
        return self


class Relation(Strict):
    type: RelationType
    target: str = Field(pattern=ID_PATTERN)
    prefer_when: str | None = None


class Selection(Strict):
    problem_signals: list[str] = []
    preconditions: list[str] = []
    contraindications: list[str] = []
    facets: Facets = Field(default_factory=Facets)
    relations: list[Relation] = []


class Source(Strict):
    url: str
    mirrored_at: str | None = None
    extraction: Extraction
    content_sha256: str


class Enrichment(Strict):
    method: EnrichmentMethod
    model: str | None = None
    date: str
    reviewed_by: str | None = None


class Provenance(Strict):
    source: Source
    enrichment: dict[str, Enrichment] = {}


class Pattern(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str
    category: str = Field(pattern=ID_PATTERN)
    kind: Kind = "pattern"
    complexity: str
    content: Content | None = None
    selection: Selection = Field(default_factory=Selection)
    provenance: Provenance

    @property
    def reviewed(self) -> bool:
        """True when every selection field has a human reviewer recorded."""
        enrichment = self.provenance.enrichment
        return all(f in enrichment and bool(enrichment[f].reviewed_by) for f in SELECTION_FIELDS)


class ImplementationGuide(Strict):
    whenToUse: list[str] = []
    bestPractices: list[str] = []
    commonPitfalls: list[str] = []


class Category(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str
    description: str
    detailedDescription: str | None = None
    whyImportant: str | None = None
    implementationGuide: ImplementationGuide | None = None
    technique_ids: list[str] = []
    provenance: Provenance


class RecipeStep(Strict):
    order: int
    pattern_id: str = Field(pattern=ID_PATTERN)
    role: str
    binding_notes: str | None = None


class Recipe(Strict):
    id: str = Field(pattern=ID_PATTERN)
    name: str
    use_case: str
    steps: list[RecipeStep]
    source_documents: list[str] = []
    provenance: Enrichment


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(content: Content) -> str:
    """SHA-256 of the canonical JSON of `content`. Same content, same hash, in any key order."""
    return hashlib.sha256(_canonical(content.model_dump(mode="json")).encode("utf-8")).hexdigest()


def dumps(model: BaseModel) -> str:
    """Canonical file text for a record: sorted keys, two-space indent, trailing newline."""
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def dumps_record(pattern: Pattern) -> str:
    """Canonical file text for a tracked record. The `content` key is left out: it is cache."""
    data = pattern.model_dump(mode="json", exclude={"content"})
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
