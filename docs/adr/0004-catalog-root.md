# ADR-0004 — The catalog is an in-tree tool with a `CATALOG_ROOT` override

Date: 2026-09-21
Status: Accepted. Closes issue #2.

## Context
`paths.ROOT` was `Path(__file__).resolve().parents[2]`. That is correct for an editable install
inside the checkout and wrong everywhere else: a wheel install resolves it to `site-packages`, and a
server started from another working directory cannot find `catalog/`, `schema/` or `eval/`.

## Decision
The package stays an in-tree tool: its data (`catalog/`, `schema/`, `eval/`, `var/`) lives beside
the source, not inside the package. `CATALOG_ROOT`, when set, names the checkout to use; it must
contain `catalog/`. No `importlib.resources` packaging of the data.

## Why
The data is the product and changes on its own cadence; the code is a thin tool over it. Moving
288 records, the vocabulary and the eval set into the wheel would make every enrichment a release.
An environment variable is enough for Plan C's server and for any script that imports the package
from elsewhere. If the catalog is ever consumed as a library by other projects, revisit with a
data package separate from the tool package.

## Consequences
- `paths.repo_root()` is the one place that decides; every other path derives from it.
- A wrong `CATALOG_ROOT` fails at import with a message naming the variable.
- Plan C documents `CATALOG_ROOT` in the server's start-up notes.
