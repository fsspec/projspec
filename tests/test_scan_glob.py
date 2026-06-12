"""Tests for scan_glob() using fsspec's in-process memory filesystem.

The memory filesystem lets us create arbitrary project layouts without
touching the real filesystem, and works with any fsspec-backed path,
confirming that scan_glob() is genuinely filesystem-agnostic.
"""

import json

import pytest

import projspec
from projspec.__main__ import main
from projspec.utils import scan_glob


# ---------------------------------------------------------------------------
# Shared fixture: a memory filesystem pre-populated with two small projects
# ---------------------------------------------------------------------------

PYPROJECT_ALPHA = """\
[project]
name = "alpha"
version = "0.1.0"
"""

PYPROJECT_BETA = """\
[project]
name = "beta"
version = "2.0.0"
"""


@pytest.fixture(autouse=False)
def mem_projects():
    """Populate memory:// with two Python projects and a stray file.

    Layout::

        memory:///ws/alpha/pyproject.toml
        memory:///ws/beta/pyproject.toml
        memory:///ws/not_a_project        ← plain file, not a directory
    """
    import fsspec

    mfs = fsspec.filesystem("memory")
    # Wipe any /ws tree left by a previous test run in this process.
    try:
        mfs.rm("/ws", recursive=True)
    except FileNotFoundError:
        pass

    mfs.mkdir("/ws/alpha")
    mfs.mkdir("/ws/beta")
    with mfs.open("/ws/alpha/pyproject.toml", "wb") as f:
        f.write(PYPROJECT_ALPHA.encode())
    with mfs.open("/ws/beta/pyproject.toml", "wb") as f:
        f.write(PYPROJECT_BETA.encode())
    # A plain file at the glob level — must be silently skipped.
    with mfs.open("/ws/not_a_project", "wb") as f:
        f.write(b"stray file")

    yield mfs

    # Cleanup
    try:
        mfs.rm("/ws", recursive=True)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# scan_glob() API tests
# ---------------------------------------------------------------------------


def test_scan_glob_yields_projects(mem_projects):
    """Both directories are yielded as Project instances."""
    results = list(scan_glob("memory:///ws/*"))
    assert len(results) == 2
    assert all(isinstance(p, projspec.Project) for p in results)


def test_scan_glob_detects_specs(mem_projects):
    """Each project matches the python_library spec (has pyproject.toml)."""
    results = {p.path: p for p in scan_glob("memory:///ws/*")}
    assert "python_library" in results["/ws/alpha"].specs
    assert "python_library" in results["/ws/beta"].specs


def test_scan_glob_skips_files(mem_projects):
    """Plain files at the glob level are silently skipped."""
    results = list(scan_glob("memory:///ws/*"))
    paths = [p.path for p in results]
    assert not any("not_a_project" in path for path in paths)


def test_scan_glob_exact_path(mem_projects):
    """A pattern with no wildcards scans exactly that one directory."""
    results = list(scan_glob("memory:///ws/alpha"))
    assert len(results) == 1
    assert results[0].path == "/ws/alpha"


def test_scan_glob_no_match_warns(mem_projects, caplog):
    """A pattern that matches nothing logs a warning and yields nothing."""
    import logging

    with caplog.at_level(logging.WARNING, logger="projspec"):
        results = list(scan_glob("memory:///ws/does_not_exist"))
    assert results == []
    assert any("not found" in r.message.lower() for r in caplog.records)


def test_scan_glob_subset_pattern(mem_projects):
    """A pattern matching only one directory yields only that project."""
    results = list(scan_glob("memory:///ws/alp*"))
    assert len(results) == 1
    assert results[0].path == "/ws/alpha"


def test_scan_glob_add_to_library(mem_projects, tmp_path):
    """add_to_library=True persists each project to the library."""
    from projspec.config import temp_conf
    from projspec.library import ProjectLibrary

    lib_path = str(tmp_path / "lib.json")
    with temp_conf(library_path=lib_path):
        list(scan_glob("memory:///ws/*", add_to_library=True))
        lib = ProjectLibrary(lib_path)

    assert len(lib.entries) == 2
    keys = set(lib.entries)
    assert any("alpha" in k for k in keys)
    assert any("beta" in k for k in keys)


def test_scan_glob_metadata(mem_projects):
    """Projects scanned from memory:// have file_count and total_size set."""
    results = list(scan_glob("memory:///ws/*"))
    for proj in results:
        # memory fs exposes size in info dicts
        assert proj.file_count >= 1
        assert proj.total_size > 0


# ---------------------------------------------------------------------------
# CLI integration: `projspec scan memory:///ws/*`
# ---------------------------------------------------------------------------


def test_cli_scan_glob_default_output(mem_projects, capsys):
    """CLI scan with a memory:// glob prints a Project repr for each match."""
    main(["scan", "memory:///ws/*"], standalone_mode=False)
    out = capsys.readouterr().out
    assert out.count("<Project") == 2
    assert "alpha" in out
    assert "beta" in out


def test_cli_scan_glob_summary(mem_projects, capsys):
    """CLI scan --summary prints text_summary() for each match."""
    main(["scan", "memory:///ws/*", "--summary"], standalone_mode=False)
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "beta" in out


def test_cli_scan_glob_json_out(mem_projects, capsys):
    """CLI scan --json-out emits one JSON object per matched project."""
    main(["scan", "memory:///ws/*", "--json-out"], standalone_mode=False)
    out = capsys.readouterr().out
    # Each line is a separate JSON object
    lines = [l for l in out.splitlines() if l.strip().startswith("{")]
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert "specs" in obj


def test_cli_scan_single_path_still_works(mem_projects, capsys):
    """Backwards-compatibility: a plain path (no wildcard) still works."""
    main(["scan", "memory:///ws/beta"], standalone_mode=False)
    out = capsys.readouterr().out
    assert "beta" in out
    assert out.count("<Project") == 1


def test_cli_scan_multiple_paths(mem_projects, capsys):
    """Multiple explicit paths (shell-expanded) are each scanned."""
    main(
        ["scan", "memory:///ws/alpha", "memory:///ws/beta"],
        standalone_mode=False,
    )
    out = capsys.readouterr().out
    assert out.count("<Project") == 2
    assert "alpha" in out
    assert "beta" in out


def test_cli_scan_mixed_glob_and_explicit(mem_projects, capsys):
    """A glob pattern and an explicit path can both be passed together."""
    # The glob expands to alpha + beta; the explicit path adds beta again
    # (scan_glob will yield it a second time — deduplication is the caller's
    # responsibility, matching shell behaviour).
    main(
        ["scan", "memory:///ws/alp*", "memory:///ws/beta"],
        standalone_mode=False,
    )
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "beta" in out
