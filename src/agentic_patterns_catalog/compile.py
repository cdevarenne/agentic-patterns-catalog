"""Compile agent-facing Markdown from the store. Nothing here is hand-edited."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from .cli import register
from .model import Category, Pattern
from .paths import CATALOG_DIR, GENERATED_DIR
from .retrieval import build_embedding_cache, default_embedder
from .store import FileStore, Store

BUDGETS = {"CATALOG.md": 2000, "CATALOG-full.md": 16000}
FACET_COLUMNS = ("scale", "latency_cost", "token_cost", "risk_class", "maturity")


def token_estimate(text: str) -> int:
    """Rough token count: four characters per token."""
    return len(text) // 4


def _is_pack(p: Pattern) -> bool:
    return p.provenance.source.extraction == "free-pack"


def _full_line(p: Pattern, local: bool) -> str:
    if local or _is_pack(p):
        return f"- {p.id} — {p.content.tldr.what} — use when: {p.content.tldr.when}"
    if p.selection.problem_signals:
        return f"- {p.id} — {p.name} — {p.selection.problem_signals[0]}"
    return f"- {p.id} — {p.name}"


def _catalog_md(categories: list[Category], patterns: list[Pattern], local: bool) -> str:
    """One line per category. The description is site prose, so only `local` output quotes it."""
    counts: dict[str, int] = {}
    for p in patterns:
        counts[p.category] = counts.get(p.category, 0) + 1
    lines = ["# Agentic patterns — categories", "",
             "One line per category. Open `guides/<id>.md` or call `select` for patterns.", ""]
    lines += [f"- **{c.id}** — {c.description if local else c.name} — {counts.get(c.id, 0)} patterns"
              for c in categories]
    return "\n".join(lines) + "\n"


def _full_md(patterns: list[Pattern], local: bool) -> str:
    lines = ["# Agentic patterns — all records", ""]
    lines += [_full_line(p, local) for p in patterns]
    return "\n".join(lines) + "\n"


def _guide(cat: Category, patterns: list[Pattern], local: bool) -> str:
    """Facet table and alternatives. The description and implementationGuide are site prose: `local` only."""
    lines = [f"# {cat.name} — guide", ""]
    if local:
        lines += [cat.description, ""]
    g = cat.implementationGuide if local else None
    if g:
        for title, items in (("When to use", g.whenToUse), ("Best practices", g.bestPractices),
                             ("Common pitfalls", g.commonPitfalls)):
            if items:
                lines += [f"## {title}", ""] + [f"- {i}" for i in items] + [""]
    lines += ["## Patterns", "", "| id | name | complexity | " + " | ".join(FACET_COLUMNS) + " |",
              "|---|---|---|" + "---|" * len(FACET_COLUMNS)]
    for p in patterns:
        facets = [getattr(p.selection.facets, f) or "" for f in FACET_COLUMNS]
        lines.append(f"| {p.id} | {p.name} | {p.complexity} | " + " | ".join(facets) + " |")
    alts = [(p, r) for p in patterns for r in p.selection.relations if r.type == "alternative_to"]
    if alts:
        lines += ["", "## Alternatives", ""]
        for p, r in alts:
            lines.append(f"- {p.id} → {r.target}: {r.prefer_when or 'no preference recorded'}")
    return "\n".join(lines) + "\n"


def _sheet(p: Pattern) -> str:
    c = p.content
    lines = [f"# {p.name}" + (f" ({c.abbr})" if c.abbr else ""), "",
             f"Category: {p.category} | Complexity: {p.complexity}", "", c.description, "",
             "## In 30 seconds", "", f"- **What:** {c.tldr.what}", f"- **When:** {c.tldr.when}",
             f"- **Watch out:** {c.tldr.watchOut}", ""]
    if c.features:
        lines += ["## Key features", ""] + [f"- {f}" for f in c.features] + [""]
    if c.useCases:
        lines += ["## Use cases", ""] + [f"- {u}" for u in c.useCases] + [""]
    if c.example:
        lines += ["## Walkthrough example", "", "> Illustrative scenario from the source; figures are not measurements.",
                  "", "```text", c.example.rstrip(), "```", ""]
    if c.code:
        lang = next(iter(sorted(c.code)))
        lines += [f"## Implementation ({lang})", "", f"```{lang}", c.code[lang].rstrip(), "```", ""]
    if c.references:
        lines += ["## References", ""] + [f"- {r}" for r in c.references] + [""]
    lines += ["---", (f"Source: {p.provenance.source.url} (extraction: {p.provenance.source.extraction}, "
                       f"content sha256 {p.provenance.source.content_sha256[:12]}…)")]
    return "\n".join(lines) + "\n"


def compile_all(store: Store, *, local: bool = False) -> dict[str, str]:
    """Relative output path → text. `local` adds site prose (tldr for every record, category text); keep it out of git."""
    patterns = store.all()
    categories = store.categories()
    out = {"CATALOG.md": _catalog_md(categories, patterns, local), "CATALOG-full.md": _full_md(patterns, local)}
    for cat in categories:
        out[f"guides/{cat.id}.md"] = _guide(cat, [p for p in patterns if p.category == cat.id], local)
    for p in patterns:
        if local or _is_pack(p):
            out[f"sheets/{p.id}.md"] = _sheet(p)
    return out


def over_budget(outputs: dict[str, str]) -> list[str]:
    """Names of the budgeted outputs whose token estimate exceeds `BUDGETS`."""
    return [name for name, limit in BUDGETS.items() if name in outputs and token_estimate(outputs[name]) > limit]


def stale_files(out_dir: Path, outputs: dict[str, str]) -> list[Path]:
    """Files under `out_dir` that `outputs` does not produce. `local/` and dotfiles are left alone."""
    if not out_dir.exists():
        return []
    produced = {out_dir / rel for rel in outputs}
    return sorted(p for p in out_dir.rglob("*")
                  if p.is_file() and p not in produced and not p.name.startswith(".")
                  and "local" not in p.relative_to(out_dir).parts[:-1])


def write_all(store: Store, out_dir: Path = GENERATED_DIR, *, local: bool = False) -> tuple[list[Path], list[Path]]:
    """Compile into `out_dir`, delete files a fresh compile does not produce, and return (written, removed)."""
    outputs = compile_all(store, local=local)
    written = []
    for rel, text in outputs.items():
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    removed = stale_files(out_dir, outputs)
    for path in removed:
        path.unlink()
    return written, removed


def embed_extra_available() -> bool:
    """True when the `embed` extra is installed. It sets the default for `compile --embeddings`."""
    return importlib.util.find_spec("fastembed") is not None


@register("compile", "write CATALOG.md, CATALOG-full.md, guides and sheets")
def _cmd(parser: argparse.ArgumentParser):
    parser.add_argument("--root", type=Path, default=CATALOG_DIR)
    parser.add_argument("--out", type=Path, default=None, help="default: skills/agentic-patterns/generated (or …/local with --local)")
    parser.add_argument("--local", action="store_true", help="quote tldr for every record; output is gitignored")
    parser.add_argument("--embeddings", action=argparse.BooleanOptionalAction, default=None,
                        help="rebuild <root>/embeddings (default: on when the embed extra is installed)")

    def run(ns: argparse.Namespace) -> int:
        out_dir = ns.out or (GENERATED_DIR / "local" if ns.local else GENERATED_DIR)
        store = FileStore(ns.root)
        written, removed = write_all(store, out_dir, local=ns.local)
        outputs = {str(path.relative_to(out_dir)): path.read_text(encoding="utf-8") for path in written}
        bad = over_budget(outputs)
        for name in ("CATALOG.md", "CATALOG-full.md"):
            print(f"{name}: ~{token_estimate(outputs[name])} tokens (budget {BUDGETS[name]})")
        print(f"wrote {len(written)} files to {out_dir}"
              + (f"; removed {', '.join(str(p.relative_to(out_dir)) for p in removed)}" if removed else ""))
        want = embed_extra_available() if ns.embeddings is None else ns.embeddings
        embedder = default_embedder() if want else None
        if embedder is not None:
            # The cache is a build artifact beside the records it indexes. It is gitignored.
            path = build_embedding_cache(store.all(), embedder, ns.root / "embeddings")
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            print(f"embeddings: {path} ({len(meta['ids'])}, {meta['dim']})")
        return 1 if bad else 0
    return run
