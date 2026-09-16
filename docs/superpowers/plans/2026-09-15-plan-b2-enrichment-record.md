# Enrichment Record Implementation Plan (issue #4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tracked record identity + `selection` + `provenance` for all 288 patterns, and move site `content` into a gitignored cache that `catalog extract` and `catalog seed` rebuild — so the enrichment Plan E writes can be committed, while no site prose enters git.

**Architecture:** `Pattern.content` becomes optional. `FileStore` writes two files per record (the tracked record under `catalog/patterns/`, the content under `var/content/`) and merges them on load. Every consumer tolerates `content is None`. Nothing else about the catalog changes: ids, provenance, facets, retrieval, budgets and the verify gate all keep their current shapes.

**Tech Stack:** Python 3.14, uv, pydantic v2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md` §3, §4.1, §4.2c, §4.6, §7. Decision record: `docs/adr/0003-enrichment-is-the-tracked-record.md`. Tracking: issue #4.

## Global Constraints

- Python **3.14** via uv; `[project] dependencies` unchanged (pydantic, rank-bm25, beautifulsoup4).
- Before **every** commit: `uv run --extra lint ruff check .` and `uv run pytest -q -m "not mirror"`.
- Commit messages: one-line subject, no `Co-Authored-By` or `Claude-Session` trailer. This repository's owner is the sole author from the second commit onward.
- JSON on disk: `json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"`.
- Content cache lives under `var/content/<category>/<id>.json`. `var/` is already gitignored; it must stay that way.
- The tracked record must never contain site prose. After Task 6 a grep for any non-pack record's `tldr.what` across tracked files must return nothing.
- Work directly on `main`; no feature branch (solo repo).
- Docstrings and comments in ASD-STE100: short sentences, active voice, one idea each.

## File Structure

```
src/agentic_patterns_catalog/
├── paths.py      + CONTENT_CACHE_DIR                          (Task 1)
├── model.py      content optional; dumps_record()             (Task 1)
├── store.py      FileStore splits on put, merges on load      (Task 2)
├── extract.py    writes split; preserves existing selection   (Task 3)
├── seed.py       writes split from data/pack/patterns.json    (Task 4)
├── compile.py    tolerates content is None                    (Task 5)
├── retrieval.py  pattern_text tolerates content is None       (Task 5)
└── verify.py     hash check needs the cache; warns without it (Task 5)
.gitignore        inverted                                     (Task 6)
catalog/patterns/ 288 tracked records                          (Task 6)
```

---

### Task 1: `Pattern.content` becomes optional

**Files:**
- Modify: `src/agentic_patterns_catalog/paths.py`, `src/agentic_patterns_catalog/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces: `paths.CONTENT_CACHE_DIR: Path` (= `ROOT / "var" / "content"`); `Pattern.content: Content | None = None`; `model.dumps_record(pattern) -> str` — canonical JSON of the record **without** the `content` key; `model.dumps(model)` unchanged for every other model.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model.py`:

```python
def test_a_record_without_content_is_valid() -> None:
    p = Pattern(
        id="x-pat", name="X", category="routing", complexity="low",
        provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256="0" * 64)),
    )
    assert p.content is None


def test_dumps_record_omits_content_but_keeps_provenance() -> None:
    p = make_pattern()
    text = dumps_record(p)
    assert '"content"' not in text
    assert '"content_sha256"' in text
    assert text.endswith("}\n")
    assert json.loads(text)["selection"]["problem_signals"] == []
```

Add `dumps_record` to the import line at the top of the file, and `import json` if it is not already imported.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_model.py -q -k "without_content or dumps_record"`
Expected: `ImportError: cannot import name 'dumps_record'`.

- [ ] **Step 3: Implement**

In `paths.py`, after `EMBEDDINGS_DIR`:

```python
# Site content is a rebuildable cache, never tracked (ADR-0003). `var/` is gitignored.
CONTENT_CACHE_DIR = ROOT / "var" / "content"
```

In `model.py`, change the `Pattern.content` field to:

```python
    content: Content | None = None
```

and add beside `dumps`:

```python
def dumps_record(pattern: Pattern) -> str:
    """Canonical file text for a tracked record. The `content` key is left out: it is cache."""
    data = pattern.model_dump(mode="json", exclude={"content"})
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
```

- [ ] **Step 4: Regenerate the schemas and run the suite**

Run: `uv run catalog schema && uv run pytest -q -m "not mirror"`
Expected: schemas written; tests pass. `schema/pattern.schema.json` now shows `content` as `anyOf` with `null` and drops it from `required`.

- [ ] **Step 5: Commit**

```bash
uv run --extra lint ruff check .
git add -A
git commit -m "A pattern record can stand without its content"
```

---

### Task 2: `FileStore` splits on write and merges on read

**Files:**
- Modify: `src/agentic_patterns_catalog/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `model.dumps_record`, `paths.CONTENT_CACHE_DIR`.
- Produces: `FileStore(root: Path = CATALOG_DIR, cache: Path = CONTENT_CACHE_DIR)`; `FileStore.cache_path(category: str, id: str) -> Path`; `put` writes the record without content and writes the content to the cache when it is present; `all()`/`get()` attach cached content when the cache file exists. `Store` protocol gains nothing — `put`/`all`/`get` keep their signatures.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_put_writes_the_record_without_content_and_caches_the_content(tmp_path: Path) -> None:
    s = store.FileStore(tmp_path / "catalog", tmp_path / "cache")
    p = _p("a-pat")
    s.put(p)
    record = (tmp_path / "catalog" / "patterns" / "routing" / "a-pat.json").read_text()
    assert '"content"' not in record
    cached = json.loads((tmp_path / "cache" / "routing" / "a-pat.json").read_text())
    assert cached["tldr"]["what"] == p.content.tldr.what


def test_load_merges_the_cache_back_onto_the_record(tmp_path: Path) -> None:
    s = store.FileStore(tmp_path / "catalog", tmp_path / "cache")
    s.put(_p("a-pat"))
    loaded = s.get("a-pat")
    assert loaded.content is not None
    assert loaded.content.tldr.what == "w"
    assert [q.content.tldr.what for q in s.all()] == ["w"]


def test_a_record_without_a_cache_file_loads_with_no_content(tmp_path: Path) -> None:
    s = store.FileStore(tmp_path / "catalog", tmp_path / "cache")
    s.put(_p("a-pat"))
    (tmp_path / "cache" / "routing" / "a-pat.json").unlink()
    assert s.get("a-pat").content is None
    assert s.all()[0].content is None


def test_put_without_content_leaves_an_existing_cache_file_alone(tmp_path: Path) -> None:
    s = store.FileStore(tmp_path / "catalog", tmp_path / "cache")
    s.put(_p("a-pat"))
    s.put(s.get("a-pat").model_copy(update={"content": None}))
    assert s.get("a-pat").content is not None
```

Add `import json` to the test file if it is not already imported.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_store.py -q -k "cache or content"`
Expected: `TypeError: FileStore() takes 2 positional arguments` or an assertion on `'"content"' not in record`.

- [ ] **Step 3: Implement**

In `store.py`, import `Content` and `dumps_record` from `.model` and `CONTENT_CACHE_DIR` from `.paths`, then replace the `FileStore` head and its three record methods:

```python
class FileStore:
    """One tracked record per file under `root`, with its site content cached under `cache`."""

    def __init__(self, root: Path = CATALOG_DIR, cache: Path = CONTENT_CACHE_DIR) -> None:
        self.root = root
        self.cache = cache

    def cache_path(self, category: str, id: str) -> Path:
        """Where the site content for this record is cached. The cache is never tracked."""
        return self.cache / category / f"{id}.json"

    def _load(self, path: Path) -> Pattern:
        pattern = Pattern.model_validate_json(path.read_text(encoding="utf-8"))
        cached = self.cache_path(pattern.category, pattern.id)
        if not cached.is_file():
            return pattern
        content = Content.model_validate_json(cached.read_text(encoding="utf-8"))
        return pattern.model_copy(update={"content": content})

    def _pattern_paths(self) -> list[Path]:
        return sorted((self.root / "patterns").glob("*/*.json"), key=lambda p: p.stem)

    def all(self) -> list[Pattern]:
        return [self._load(p) for p in self._pattern_paths()]

    def get(self, id: str) -> Pattern:
        """The record with this id, or KeyError. `id` is used as a file name, never as a glob."""
        if not re.fullmatch(ID_PATTERN, id):
            raise KeyError(id)
        for category_dir in sorted((self.root / "patterns").iterdir()):
            path = category_dir / f"{id}.json"
            if path.is_file():
                return self._load(path)
        raise KeyError(id)

    def put(self, pattern: Pattern) -> None:
        """Write the record. Content, when the record carries it, goes to the cache instead."""
        path = self.root / "patterns" / pattern.category / f"{pattern.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps_record(pattern), encoding="utf-8")
        if pattern.content is None:
            return
        cached = self.cache_path(pattern.category, pattern.id)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(dumps(pattern.content), encoding="utf-8")
```

- [ ] **Step 4: Run the suite**

Run: `uv run pytest tests/test_store.py -q`
Expected: all pass. Other suites may fail here — Tasks 3-5 fix their callers.

- [ ] **Step 5: Commit**

```bash
uv run --extra lint ruff check .
git add -A
git commit -m "FileStore keeps the record and its cached content apart"
```

---

### Task 3: `catalog extract` writes the split and preserves enrichment

**Files:**
- Modify: `src/agentic_patterns_catalog/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: `store.FileStore`.
- Produces: `extract_mirror(mirror_dir, out_dir=CATALOG_DIR, *, cache_dir=CONTENT_CACHE_DIR, force=False) -> ExtractReport`; CLI gains `--cache DIR`. `extract_page` is unchanged.

**This is the dangerous task.** Today `extract_mirror` overwrites the whole record file. After Task 2 the tracked file carries `selection`, so a re-extract would erase every enrichment Plan E produces. The extractor must read the existing record's `selection` and carry it forward untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_extract.py`:

```python
def test_re_extracting_preserves_enrichment(fixtures: Path, tmp_path: Path) -> None:
    mirror = tmp_path / "mirror" / "routing"
    mirror.mkdir(parents=True)
    (mirror / "fixture-routing.html").write_text((fixtures / "page.html").read_text(encoding="utf-8"))
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)

    fs = store.FileStore(out, cache)
    enriched = fs.get("fixture-routing")
    enriched.selection.problem_signals = ["requests span several domains"]
    enriched.selection.facets.scale = "multi-agent"
    fs.put(enriched)

    extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)
    after = fs.get("fixture-routing")
    assert after.selection.problem_signals == ["requests span several domains"]
    assert after.selection.facets.scale == "multi-agent"
    assert after.content is not None and after.content.tldr.what.startswith("Matches")


def test_extract_writes_no_prose_into_the_tracked_record(fixtures: Path, tmp_path: Path) -> None:
    mirror = tmp_path / "mirror" / "routing"
    mirror.mkdir(parents=True)
    (mirror / "fixture-routing.html").write_text((fixtures / "page.html").read_text(encoding="utf-8"))
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    extract.extract_mirror(tmp_path / "mirror", out, cache_dir=cache)
    record = (out / "patterns" / "routing" / "fixture-routing.json").read_text()
    assert "Matches" not in record
    assert (cache / "routing" / "fixture-routing.json").is_file()
```

Add `from agentic_patterns_catalog import store` to the test file's imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_extract.py -q -k "preserves or no_prose"`
Expected: `TypeError: extract_mirror() got an unexpected keyword argument 'cache_dir'`.

- [ ] **Step 3: Implement**

In `extract.py`, import `FileStore` from `.store` and `CONTENT_CACHE_DIR` from `.paths`, then replace the signature and the write block of `extract_mirror`:

```python
def extract_mirror(mirror_dir: Path, out_dir: Path = CATALOG_DIR, *,
                   cache_dir: Path = CONTENT_CACHE_DIR, force: bool = False) -> ExtractReport:
    """Every `<category>/<slug>.html` under `mirror_dir` becomes a record, a cached content file
    and a category record. Enrichment already in a record is read back and kept."""
    report = ExtractReport()
    categories: dict[str, Category] = {}
    store = FileStore(out_dir, cache_dir)
    for page in sorted(mirror_dir.glob("*/*.html")):
```

Keep the body that builds `pattern` and `cats`. Replace the target/write block with:

```python
        target = out_dir / "patterns" / pattern.category / f"{pattern.id}.json"
        if _is_pack_record(target) and not force:
            report.skipped_pack += 1
            continue
        if not pattern.content.details:
            report.empty_details.append(pattern.id)
        if target.is_file():
            # The record on disk owns the enrichment. Extraction refreshes content, never selection.
            existing = Pattern.model_validate_json(target.read_text(encoding="utf-8"))
            pattern = pattern.model_copy(update={"selection": existing.selection})
        store.put(pattern)
        report.written += 1
```

In the `@register("extract", …)` block add:

```python
    parser.add_argument("--cache", type=Path, default=CONTENT_CACHE_DIR,
                        help="where extracted site content is cached (never tracked)")
```

and pass it through: `extract_mirror(ns.mirror, ns.out, cache_dir=ns.cache, force=ns.force)`.

- [ ] **Step 4: Run the suite**

Run: `uv run pytest tests/test_extract.py -q -m "not mirror"`
Expected: all pass, including the two new tests.

- [ ] **Step 5: Commit**

```bash
uv run --extra lint ruff check .
git add -A
git commit -m "Extraction refreshes content and never touches enrichment"
```

---

### Task 4: `catalog seed` writes the split

**Files:**
- Modify: `src/agentic_patterns_catalog/seed.py`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `store.FileStore`.
- Produces: `write_seed(pack_path=PACK_JSON, out_dir=CATALOG_DIR, *, cache_dir=CONTENT_CACHE_DIR) -> int`; CLI gains `--cache DIR`. `seed_from_pack` is unchanged.

The 11 free-pack records keep their prose in the tracked `data/pack/patterns.json`; `catalog seed` refills their cache from it, so no licensed text is lost.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_seed.py`:

```python
def test_seed_writes_records_and_fills_the_content_cache(fixtures: Path, tmp_path: Path) -> None:
    out, cache = tmp_path / "catalog", tmp_path / "cache"
    assert seed.write_seed(fixtures / "pack.json", out, cache_dir=cache) == 2
    record = next((out / "patterns" / "tool-use").glob("*.json")).read_text()
    assert '"content"' not in record
    cached = sorted((cache / "tool-use").glob("*.json"))
    assert len(cached) == 2
    assert "tldr" in json.loads(cached[0].read_text())
```

Add `import json` if the file lacks it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_seed.py -q -k cache`
Expected: `TypeError: write_seed() got an unexpected keyword argument 'cache_dir'`.

- [ ] **Step 3: Implement**

In `seed.py`, import `FileStore` and `CONTENT_CACHE_DIR`, then replace `write_seed`:

```python
def write_seed(pack_path: Path = PACK_JSON, out_dir: Path = CATALOG_DIR, *,
               cache_dir: Path = CONTENT_CACHE_DIR) -> int:
    """Write one record per pack entry and cache its content. Returns the count."""
    patterns = seed_from_pack(json.loads(pack_path.read_text(encoding="utf-8")))
    store = FileStore(out_dir, cache_dir)
    for p in patterns:
        store.put(p)
    return len(patterns)
```

Add the `--cache` argument to the `seed` subcommand exactly as Task 3 added it to `extract`, and pass `cache_dir=ns.cache`.

- [ ] **Step 4: Run the suite and commit**

Run: `uv run pytest tests/test_seed.py -q && uv run --extra lint ruff check .`

```bash
git add -A
git commit -m "Seeding fills the content cache from the tracked pack file"
```

---

### Task 5: Consumers tolerate a record with no content

**Files:**
- Modify: `src/agentic_patterns_catalog/compile.py`, `src/agentic_patterns_catalog/retrieval.py`, `src/agentic_patterns_catalog/verify.py`
- Test: `tests/test_compile.py`, `tests/test_retrieval.py`, `tests/test_verify.py`

**Interfaces:**
- Produces: `compile._full_line` falls back to `- <id> — <name>` when content is absent; `compile.compile_all` emits a sheet only for a record that has content; `retrieval.pattern_text` uses the fields that exist; `verify.check_records` compares the stored hash to live content only when content is present; `verify.run_warnings` reports how many records have no cached content.

- [ ] **Step 1: Write the failing tests**

In `tests/test_retrieval.py`:

```python
def test_pattern_text_works_without_content() -> None:
    p = _p("x", "unused").model_copy(update={"content": None})
    p.selection.problem_signals = ["requests span several domains"]
    text = r.pattern_text(p)
    assert "requests span several domains" in text and "x" in text
    res = r.Selector([p], embedder=None).select("requests span several domains", k=1)
    assert res.hits[0].id == "x"
```

In `tests/test_compile.py`:

```python
def test_a_record_without_content_falls_back_to_id_and_name(fs: store.FileStore, tmp_path: Path) -> None:
    bare = _p("bare-one").model_copy(update={"content": None})
    fs.put(bare)
    out = comp.compile_all(fs)
    assert "- bare-one — Bare-One" in out["CATALOG-full.md"]
    assert "sheets/bare-one.md" not in out
```

In `tests/test_verify.py`:

```python
def test_missing_cached_content_is_a_warning_not_a_problem(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    for path in (ctx.root / "patterns").glob("*/*.json"):
        data = json.loads(path.read_text())
        data["provenance"]["source"]["content_sha256"] = "0" * 64
        path.write_text(json.dumps(data))
    assert verify.run_checks(ctx)["records"] == []
    assert "content" in verify.run_warnings(ctx)
```

Note: `_ctx` builds its store through `FileStore`, so after Task 2 its records have no cached content unless the fixture writes one. If `_ctx` gained a cache directory, point it at `tmp_path / "cache"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_retrieval.py tests/test_compile.py tests/test_verify.py -q -k "without_content or fall_back or missing_cached"`
Expected: `AttributeError: 'NoneType' object has no attribute 'tldr'` from `pattern_text` and `_full_line`.

- [ ] **Step 3: Implement**

`retrieval.pattern_text`:

```python
def pattern_text(p: Pattern) -> str:
    """The text both arms index. `tldr.watchOut` and the category's `whenToUse` are left out on
    purpose: they describe risk and context, not what the pattern is for. Content may be absent."""
    parts = [p.name, *p.selection.problem_signals]
    if p.content is not None:
        d = p.content.details
        parts += [p.content.tldr.what, p.content.tldr.when, *p.content.useCases,
                  *d.get("when_to_use.use_when", []), *d.get("best_use_cases", []),
                  *d.get("top_use_cases", [])]
    return " ".join(parts)
```

`compile._full_line`: guard the two branches that read `p.content`:

```python
def _full_line(p: Pattern, local: bool) -> str:
    if p.content is not None and (local or _is_pack(p)):
        return f"- {p.id} — {p.content.tldr.what} — use when: {p.content.tldr.when}"
    if p.selection.problem_signals:
        return f"- {p.id} — {p.name} — {p.selection.problem_signals[0]}"
    return f"- {p.id} — {p.name}"
```

In `compile.compile_all`, change the sheet condition to `if p.content is not None and (local or _is_pack(p)):`.

`verify.check_records`: wrap the hash comparison:

```python
        if p.content is not None and p.provenance.source.content_sha256 != content_hash(p.content):
            problems.append(f"{p.id}: content_sha256 does not match content")
```

`verify.run_warnings`: add

```python
    missing = [p.id for p in FileStore(ctx.root).all() if p.content is None]
    if missing:
        warnings["content"] = [f"{len(missing)} records have no cached content; run `catalog extract`"]
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q -m "not mirror" && uv run --extra lint ruff check .`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Compiling, retrieval and verify accept a record with no cached content"
```

---

### Task 6: Flip the tracking boundary and rebuild

**Files:**
- Modify: `.gitignore`, `README.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md`
- Add to git: `catalog/patterns/**` (288 records)

- [ ] **Step 1: Rebuild both halves from the mirror**

```bash
uv run catalog extract --mirror /opt/devel/DevMoi/agentic-design-mirror/pages/raw/patterns
uv run catalog seed
uv run catalog index
uv run catalog compile
```
Expected: `written 277, skipped pack records 11, categories 24 …`; `seeded 11 records`; `indexed 288 patterns, 24 categories`.

- [ ] **Step 2: Flip `.gitignore`**

Replace the pattern-record block with:

```
# Site content is a rebuildable cache (ADR-0003), never tracked. The records themselves are ours.
var/
catalog/categories/
catalog/embeddings/
```

Delete the three lines that ignored `catalog/patterns/*` and re-included `tool-use/`.

- [ ] **Step 3: Prove no prose is about to be committed**

Run:
```bash
git add -A
uv run python -c "
import json, glob, subprocess
from pathlib import Path
tracked = set(subprocess.run(['git','ls-files'],capture_output=True,text=True).stdout.split())
blob = ''.join(Path(p).read_text() for p in tracked if p.endswith(('.md','.json')))
leak = [json.load(open(f))['tldr']['what'][:40] for f in glob.glob('var/content/*/*.json')]
hits = [t for t in leak if t and t in blob]
print('tracked records:', len([p for p in tracked if p.startswith('catalog/patterns/')]))
print('prose fragments leaked into tracked files:', len(hits), hits[:3])
"
```
Expected: `tracked records: 288`, `prose fragments leaked into tracked files: 0 []`.
If it is not 0, stop and report — do not commit.

- [ ] **Step 4: Update the three documents**

- `README.md`: the attribution paragraph now says the repository tracks all 288 records because they hold the project's own enrichment, and that site content is cached locally by `catalog extract` and never distributed. Add `catalog extract` to the quick start as the step that fills the cache.
- `CLAUDE.md`: replace the convention line about the 277 gitignored records with: records are tracked; site content is a gitignored cache under `var/content/`; `catalog extract` refreshes content and never overwrites `selection`.
- Spec §3 and §7: replace the "277 gitignored" wording with the ADR-0003 layout, and delete the §4.2c "not yet implemented" note.

- [ ] **Step 5: Full gate**

Run: `uv run --extra lint ruff check . && uv run pytest -q && uv run catalog verify`
Expected: all green, eight checks ok. `catalog verify` should now also print the content warning only if the cache is missing.

- [ ] **Step 6: Commit and push**

```bash
git add -A
git commit -m "Track the records and cache the site content (ADR-0003)"
git push origin main
gh issue close 4 -c "Implemented in \$(git rev-parse --short HEAD)."
```

---

## Self-review against the spec

- ADR-0003's decision — tracked record = identity + selection + provenance; content a rebuildable cache — is implemented by Tasks 1, 2 and 6. ✔
- The dangerous edit ADR-0003 names (extraction must preserve `selection`) has its own task and its own test. ✔
- `content_version` is untouched: it reads `provenance.source.content_sha256`, which stays in the tracked record. No task changes `store.content_version`. ✔
- Spec §7's compiled views keep working without content: `CATALOG.md` uses category names, `CATALOG-full.md` falls back to `id — name`, sheets are skipped. Task 5. ✔
- Spec §11's verify gate keeps all eight checks; only the stored-hash comparison becomes conditional, and a missing cache is a warning. Task 5. ✔
- Licence boundary: Task 6 step 3 asserts zero prose fragments in tracked files before the commit, and the pack's prose stays in `data/pack/patterns.json`. ✔
- Not covered, deliberately: `PostgresStore` (issue #7 builds it against this layout), and the embedding cache, which keys on `content_sha256` and so is unaffected.
