import pytest
from pydantic import ValidationError

from agentic_patterns_catalog.model import (
    Category,
    Content,
    Enrichment,
    Facets,
    Pattern,
    Provenance,
    Source,
    Tldr,
    content_hash,
    dumps,
)


def make_pattern(**over) -> Pattern:
    content = Content(description="Routes by content.", tldr=Tldr(what="w", when="n", watchOut="o"))
    base = {
        "id": "content-based-routing", "name": "Content-Based Routing", "category": "routing",
        "complexity": "medium", "content": content,
        "provenance": Provenance(source=Source(url="https://agentic-design.ai/patterns/routing/content-based-routing",
                                                extraction="rsc-payload", content_sha256=content_hash(content))),
    }
    base.update(over)
    return Pattern(**base)


def test_content_hash_is_stable_and_order_independent() -> None:
    a = Content(description="d", tldr=Tldr(what="w", when="n", watchOut="o"), features=["x"])
    b = Content(tldr=Tldr(watchOut="o", when="n", what="w"), description="d", features=["x"])
    assert content_hash(a) == content_hash(b)
    assert len(content_hash(a)) == 64


def test_content_hash_changes_when_content_changes() -> None:
    a = Content(description="d", tldr=Tldr(what="w", when="n", watchOut="o"))
    b = Content(description="d2", tldr=Tldr(what="w", when="n", watchOut="o"))
    assert content_hash(a) != content_hash(b)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Tldr(what="w", when="n", watchOut="o", extra="no")  # type: ignore[call-arg]


def test_reviewed_requires_every_selection_field_to_have_a_reviewer() -> None:
    p = make_pattern()
    assert p.reviewed is False
    done = Enrichment(method="human", date="2026-09-12", reviewed_by="cdevarenne")
    p.provenance.enrichment = {
        f: done for f in ("problem_signals", "preconditions", "contraindications", "facets", "relations")
    }
    assert p.reviewed is True
    p.provenance.enrichment["facets"] = Enrichment(method="llm-draft", model="claude-opus-5", date="2026-09-12")
    assert p.reviewed is False


def test_dumps_is_canonical_json_with_trailing_newline() -> None:
    text = dumps(make_pattern())
    assert text.endswith("}\n")
    assert '"category": "routing"' in text
    assert text.index('"category"') < text.index('"complexity"')  # keys sorted


def test_category_provenance_has_the_pattern_shape() -> None:
    src = Source(url="u", extraction="rsc-payload", content_sha256="0" * 64)
    cat = Category(id="routing", name="Routing", description="d", provenance=Provenance(source=src))
    assert cat.provenance.enrichment == {}
    with pytest.raises(ValidationError):
        Category(id="routing", name="Routing", description="d", provenance=src)  # type: ignore[arg-type]


def test_facet_values_must_come_from_the_vocabulary() -> None:
    assert Facets().scale is None
    assert Facets(scale="fleet").scale == "fleet"
    with pytest.raises(ValidationError, match="scale=galaxy"):
        Facets(scale="galaxy")


def test_ids_are_single_path_segments() -> None:
    for bad in ("../x", "a/b", "Upper", "trailing-", "", "with space"):
        with pytest.raises(ValidationError):
            make_pattern(id=bad)
    with pytest.raises(ValidationError):
        make_pattern(category="../etc")
    assert make_pattern(id="a1-b2").id == "a1-b2"
