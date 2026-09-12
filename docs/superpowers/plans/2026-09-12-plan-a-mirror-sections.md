# Plan A — Mirror Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `mirror.py` mirror any top-level section of agentic-design.ai (not only `/patterns`) and use it to fetch the four sections named in the spec.

**Architecture:** One stdlib-only script, `mirror.py`, gains two CLI flags. `pattern_urls(sitemap)` becomes `section_urls(sitemap, section)`; `main()` parses `--section` and `--out` with `argparse`. Nothing else changes: politeness, robots handling, backoff, raw/clean layout stay as they are.

**Tech Stack:** Python 3 stdlib (`argparse`, `re`, `urllib`), `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-12-agentic-patterns-catalog-design.md` §13. Decision record: `docs/adr/0001-catalog-design.md` §4.

**Repository:** this plan modifies `/opt/devel/DevMoi/agentic-design-mirror/` (not a git repository — there is nothing to commit; each task ends with the test run instead). The plan file itself lives in the catalog repo.

## Global Constraints

- No new dependencies. The script stays stdlib-only (spec §13: "No library swap").
- Default behaviour is unchanged: `python3 mirror.py` with no flags mirrors `/patterns` into `pages/`.
- Output layout under `--out` stays `raw/<relpath>` + `clean/<relpath>`.
- Politeness constants (`DELAY_S`, `JITTER_S`, `BACKOFF_S`, `MAX_CONSECUTIVE_FAILURES`) are not touched.
- Every `.py` change passes `python3 -m unittest test_mirror` with no network.
- Write comments and docstrings in short, active sentences (ASD-STE100).

---

### Task 1: `section_urls()` replaces `pattern_urls()`

**Files:**
- Modify: `/opt/devel/DevMoi/agentic-design-mirror/mirror.py:22-46`
- Test: `/opt/devel/DevMoi/agentic-design-mirror/test_mirror.py:11-33`

**Interfaces:**
- Consumes: nothing new.
- Produces: `section_urls(sitemap_xml: str, section: str) -> list[str]` — English URLs whose path is exactly `/<section>` or starts with `/<section>/`; `SECTIONS: tuple[str, ...]` — the five known section names.

- [ ] **Step 1: Extend the fixture sitemap and write the failing tests**

Edit `test_mirror.py`. Replace the `SITEMAP` constant and the `PatternUrls` class with:

```python
SITEMAP = """<?xml version="1.0"?>
<urlset>
<url><loc>https://agentic-design.ai/</loc></url>
<url><loc>https://agentic-design.ai/patterns</loc></url>
<url><loc>https://agentic-design.ai/patterns/routing</loc></url>
<url><loc>https://agentic-design.ai/patterns/routing/dynamic-routing</loc></url>
<url><loc>https://agentic-design.ai/fr/patterns/routing</loc></url>
<url><loc>https://agentic-design.ai/patterns-old</loc></url>
<url><loc>https://agentic-design.ai/ai-red-teaming</loc></url>
<url><loc>https://agentic-design.ai/ai-red-teaming/prompt-injection</loc></url>
<url><loc>https://agentic-design.ai/fr/ai-red-teaming/prompt-injection</loc></url>
<url><loc>https://agentic-design.ai/ai-red-teaming-guide</loc></url>
<url><loc>https://agentic-design.ai/model-architectures/moe</loc></url>
</urlset>"""


class SectionUrls(unittest.TestCase):
    def test_default_section_keeps_only_english_patterns_tree(self) -> None:
        self.assertEqual(
            mirror.section_urls(SITEMAP, "patterns"),
            [
                "https://agentic-design.ai/patterns",
                "https://agentic-design.ai/patterns/routing",
                "https://agentic-design.ai/patterns/routing/dynamic-routing",
            ],
        )

    def test_other_section_excludes_locales_and_prefix_lookalikes(self) -> None:
        self.assertEqual(
            mirror.section_urls(SITEMAP, "ai-red-teaming"),
            [
                "https://agentic-design.ai/ai-red-teaming",
                "https://agentic-design.ai/ai-red-teaming/prompt-injection",
            ],
        )

    def test_section_with_no_index_page_still_returns_children(self) -> None:
        self.assertEqual(
            mirror.section_urls(SITEMAP, "model-architectures"),
            ["https://agentic-design.ai/model-architectures/moe"],
        )

    def test_unknown_section_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            mirror.section_urls(SITEMAP, "billing")

    def test_known_sections_are_the_five_from_the_spec(self) -> None:
        self.assertEqual(
            mirror.SECTIONS,
            ("patterns", "ai-red-teaming", "ai-inference", "fine-tuning", "model-architectures"),
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /opt/devel/DevMoi/agentic-design-mirror && python3 -m unittest test_mirror.SectionUrls -v`
Expected: 5 failures/errors, `AttributeError: module 'mirror' has no attribute 'section_urls'` (and `SECTIONS`).

- [ ] **Step 3: Implement `section_urls` and `SECTIONS`**

In `mirror.py`, replace the `PATTERNS_ROOT` constant and the `pattern_urls` function:

```python
SITE = "https://agentic-design.ai"
# Top-level site sections this mirror knows how to fetch. Sizes on 2026-09-12: patterns 313,
# ai-red-teaming 113, model-architectures 25, ai-inference 21, fine-tuning 9.
SECTIONS = ("patterns", "ai-red-teaming", "ai-inference", "fine-tuning", "model-architectures")
```

```python
def section_urls(sitemap_xml: str, section: str) -> list[str]:
    """English URLs of one site section; locale variants (/fr/...) are excluded."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}; known: {', '.join(SECTIONS)}")
    root = f"{SITE}/{section}"
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap_xml)
    return [u for u in locs if u == root or u.startswith(root + "/")]
```

Delete `PATTERNS_ROOT` and `pattern_urls`. Update the module docstring's first line to
`"""Polite, resumable mirror of one section of https://agentic-design.ai for personal study.`

- [ ] **Step 4: Run the whole suite**

Run: `cd /opt/devel/DevMoi/agentic-design-mirror && python3 -m unittest test_mirror -v`
Expected: `SectionUrls` passes (5 tests). `main()` still references `pattern_urls` — it is not
covered by tests, so the suite is green; Task 2 fixes `main()`.

---

### Task 2: `--section` and `--out` flags

**Files:**
- Modify: `/opt/devel/DevMoi/agentic-design-mirror/mirror.py:164-186` (`main`)
- Test: `/opt/devel/DevMoi/agentic-design-mirror/test_mirror.py` (new class `ParseArgs`)

**Interfaces:**
- Consumes: `section_urls`, `SECTIONS` from Task 1.
- Produces: `parse_args(argv: list[str] | None = None) -> argparse.Namespace` with attributes `section: str` and `out: Path` (absolute; relative values resolve against the script's directory).

- [ ] **Step 1: Write the failing tests**

Append to `test_mirror.py`:

```python
class ParseArgs(unittest.TestCase):
    def test_defaults_keep_todays_behaviour(self) -> None:
        args = mirror.parse_args([])
        self.assertEqual(args.section, "patterns")
        self.assertEqual(args.out, Path(mirror.__file__).resolve().parent / "pages")

    def test_section_and_out_are_taken_from_flags(self) -> None:
        args = mirror.parse_args(["--section", "ai-red-teaming", "--out", "redteaming"])
        self.assertEqual(args.section, "ai-red-teaming")
        self.assertEqual(args.out, Path(mirror.__file__).resolve().parent / "redteaming")

    def test_absolute_out_is_kept(self) -> None:
        args = mirror.parse_args(["--out", "/tmp/x"])
        self.assertEqual(args.out, Path("/tmp/x"))

    def test_unknown_section_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit):
            mirror.parse_args(["--section", "billing"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest test_mirror.ParseArgs -v`
Expected: 4 errors, `AttributeError: module 'mirror' has no attribute 'parse_args'`.

- [ ] **Step 3: Implement `parse_args` and wire `main`**

Add `import argparse` to the imports. Replace `main()` with:

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI flags. A relative --out resolves against this file's directory, not the cwd."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--section", choices=SECTIONS, default="patterns",
                        help="site section to mirror (default: patterns)")
    parser.add_argument("--out", type=Path, default=Path("pages"),
                        help="output directory; raw/ and clean/ go under it (default: pages)")
    args = parser.parse_args(argv)
    if not args.out.is_absolute():
        args.out = Path(__file__).resolve().parent / args.out
    return args


def main() -> None:
    args = parse_args()
    contact = os.environ.get("CRAWLER_CONTACT")
    if not contact:
        sys.exit("Set CRAWLER_CONTACT=you@example.com so the site owner can reach you.")
    user_agent = f"agentic-design-mirror/1.0 (personal education; +mailto:{contact})"
    fetch: Fetch = lambda url: fetch_url(url, user_agent)

    robots = fetch(f"{SITE}/robots.txt")
    time.sleep(DELAY_S)
    sitemap = fetch(f"{SITE}/sitemap.xml")
    if sitemap.status != 200:
        sys.exit(f"could not fetch sitemap (HTTP {sitemap.status})")
    time.sleep(DELAY_S)

    urls = allowed_urls(robots.body, section_urls(sitemap.body, args.section), user_agent)
    print(f"{len(urls)} pages -> {args.out}  (~{len(urls) * (DELAY_S + JITTER_S / 2) / 60:.0f} min)")
    mirror(urls, args.out, fetch, time.sleep)
    print("done")
```

Update the module docstring usage line to:
`Usage:  CRAWLER_CONTACT=you@example.com python3 mirror.py [--section NAME] [--out DIR]`

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest test_mirror -v`
Expected: all tests pass (existing 17 + 5 + 4 = 26).

- [ ] **Step 5: Confirm the default invocation is a no-op on the existing mirror**

Run: `cd /opt/devel/DevMoi/agentic-design-mirror && python3 -c "import mirror; a = mirror.parse_args([]); print(a.section, a.out, (a.out / 'raw' / 'patterns').exists())"`
Expected: `patterns /opt/devel/DevMoi/agentic-design-mirror/pages True` — the existing tree is where the default points, so a re-run skips all 313 pages.

---

### Task 3: README and the four section runs

**Files:**
- Modify: `/opt/devel/DevMoi/agentic-design-mirror/README.md`

- [ ] **Step 1: Document the flags and the decision**

Replace the `## Run` section of `README.md` with:

````markdown
## Run

```sh
CRAWLER_CONTACT=you@example.com python3 mirror.py                      # /patterns → pages/
CRAWLER_CONTACT=you@example.com python3 mirror.py --section ai-red-teaming     --out redteaming
CRAWLER_CONTACT=you@example.com python3 mirror.py --section ai-inference       --out inference
CRAWLER_CONTACT=you@example.com python3 mirror.py --section fine-tuning        --out fine-tuning
CRAWLER_CONTACT=you@example.com python3 mirror.py --section model-architectures --out model-architectures
```

- Sizes from the sitemap on 2026-09-12: patterns 313, ai-red-teaming 113, model-architectures 25,
  ai-inference 21, fine-tuning 9. One request every 5–7 s.
- Ctrl-C any time; re-running skips pages already under `<out>/raw/`.
- Output: `<out>/raw/…` (HTML exactly as served) and `<out>/clean/…` (same page with scripts and
  preload hints removed, plus a `<base>` tag so the site's stylesheet and links resolve online).
- The script stays stdlib-only on purpose. The robots and backoff code is small and tested;
  `requests` or `protego` would add dependencies without changing behaviour.
````

- [ ] **Step 2: Run the four sections (network; ~17 min total)**

Run, one after another, from `/opt/devel/DevMoi/agentic-design-mirror` with `CRAWLER_CONTACT` set:

```sh
python3 mirror.py --section ai-red-teaming --out redteaming
python3 mirror.py --section ai-inference --out inference
python3 mirror.py --section fine-tuning --out fine-tuning
python3 mirror.py --section model-architectures --out model-architectures
```

- [ ] **Step 3: Verify page counts against the sitemap sizes**

Run:
```sh
for d in redteaming inference fine-tuning model-architectures; do printf '%-20s %s\n' "$d" "$(find $d/raw -name '*.html' | wc -l)"; done
```
Expected: `redteaming 113`, `inference 21`, `fine-tuning 9`, `model-architectures 25`. A lower
count means a page was skipped after backoff — re-run the same command; it resumes.

- [ ] **Step 4: Final test run**

Run: `python3 -m unittest test_mirror`
Expected: `OK`.
