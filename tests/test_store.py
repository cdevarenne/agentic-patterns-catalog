import json
from pathlib import Path

import pytest

from agentic_patterns_catalog import store
from agentic_patterns_catalog.model import Content, Pattern, Provenance, Source, Tldr, content_hash


def _p(id: str, category: str = "routing") -> Pattern:
    c = Content(description=f"{id} d", tldr=Tldr(what="w", when="n", watchOut="o"))
    return Pattern(id=id, name=id.title(), category=category, complexity="low", content=c,
                   provenance=Provenance(source=Source(url="u", extraction="rsc-payload", content_sha256=content_hash(c))))


@pytest.fixture
def fs(tmp_path: Path) -> store.FileStore:
    s = store.FileStore(tmp_path, tmp_path / "cache")
    for p in (_p("b-pat"), _p("a-pat"), _p("c-pat", "memory-management")):
        s.put(p)
    return s


def test_put_writes_under_category_and_all_is_sorted_by_id(fs: store.FileStore, tmp_path: Path) -> None:
    assert (tmp_path / "patterns" / "routing" / "a-pat.json").exists()
    assert [p.id for p in fs.all()] == ["a-pat", "b-pat", "c-pat"]


def test_get_unknown_id_raises_key_error(fs: store.FileStore) -> None:
    with pytest.raises(KeyError):
        fs.get("nope")
    assert fs.get("a-pat").category == "routing"
    assert fs.get("c-pat").category == "memory-management"


def test_get_does_not_glob_or_leave_the_patterns_tree(fs: store.FileStore) -> None:
    for id in ("*", "*-pat", "../routing/a-pat", "routing/a-pat"):
        with pytest.raises(KeyError):
            fs.get(id)


def test_index_lists_every_pattern_with_hash_and_review_state(fs: store.FileStore, tmp_path: Path) -> None:
    idx = store.write_index(fs, tmp_path / "index.json")
    assert set(idx["patterns"]) == {"a-pat", "b-pat", "c-pat"}
    assert idx["patterns"]["a-pat"]["reviewed"] is False
    assert idx["patterns"]["a-pat"]["extraction"] == "rsc-payload"
    assert json.loads((tmp_path / "index.json").read_text())["patterns"]["c-pat"]["category"] == "memory-management"


def test_content_version_is_derived_from_record_content(fs: store.FileStore) -> None:
    v = store.content_version(fs.all())
    assert len(v) == 12 and int(v, 16) >= 0
    assert v == store.content_version(reversed(fs.all()))  # order-independent
    changed = _p("a-pat")
    changed.content.description = "different"
    changed.provenance.source.content_sha256 = content_hash(changed.content)
    fs.put(changed)
    assert store.content_version(fs.all()) != v


def test_index_carries_content_version_and_git_ref(fs: store.FileStore) -> None:
    idx = store.build_index(fs)
    assert idx["generated_from"] == store.content_version(fs.all())
    assert isinstance(idx["git_ref"], str) and 4 <= len(idx["git_ref"]) <= 20


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


def test_git_ref_ignores_commits_that_only_touch_the_index(tmp_path: Path) -> None:
    import subprocess

    def git(*args: str) -> str:
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"]}
        return subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True, text=True,
                              check=True, env=env).stdout.strip()
    git("init", "-q")
    (tmp_path / "catalog" / "patterns").mkdir(parents=True)
    (tmp_path / "catalog" / "patterns" / "a.json").write_text("{}")
    git("add", "."); git("commit", "-q", "-m", "record")
    first = git("log", "-1", "--format=%h")
    (tmp_path / "catalog" / "index.json").write_text("{}")
    git("add", "."); git("commit", "-q", "-m", "index only")
    assert store.git_ref(tmp_path) == first
    assert store.git_ref(tmp_path / "nowhere") == "uncommitted"
