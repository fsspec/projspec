import json
import pickle
import time

import pytest

import projspec.utils


def test_basic(proj):
    spec = proj["python_library"]
    assert "wheel" in spec.artifacts
    assert proj.all_contents()
    assert proj.all_artifacts()
    assert "src/projspec" in proj.children
    assert repr(proj).count("\n") == 0
    assert str(proj).count("\n") > 0
    proj._ipython_display_()


def test_humanize_age():
    from projspec.proj.base import _humanize_age

    now = time.time()
    assert _humanize_age(now) == "just now"
    assert _humanize_age(now + 100) == "just now"  # future / clock skew
    assert _humanize_age(now - 5 * 60) == "5 minutes ago"
    assert _humanize_age(now - 60) == "1 minute ago"
    assert _humanize_age(now - 3 * 3600) == "3 hours ago"
    assert _humanize_age(now - 1.5 * 86400) == "yesterday"
    assert _humanize_age(now - 10 * 86400) == "10 days ago"
    assert _humanize_age(now - 60 * 86400) == "2 months ago"
    assert _humanize_age(now - 400 * 86400) == "1 year ago"
    assert _humanize_age(now - 800 * 86400) == "2 years ago"


def test_scanned_at_in_stats_line(proj):
    # scanned_at should appear in the textual surfaces
    assert "scanned " in proj._stats_line()
    assert "scanned " in proj.text_summary()
    assert "scanned " in str(proj)
    # bare summary omits the stats line entirely
    assert "scanned " not in proj.text_summary(bare=True)


def test_errors():
    with pytest.raises(ValueError):
        projspec.Project.from_dict({})


def test_contains(proj):
    from projspec.artifact.installable import Wheel

    assert proj.python_library is not None
    assert "python_library" in proj
    assert proj.has_artifact_type([Wheel])


def test_serialise(proj):
    js = json.dumps(proj.to_dict(compact=False))
    projspec.Project.from_dict(json.loads(js))


def test_serialise_remote_preserves_filesystem():
    """A remote (non-local) project must round-trip through to_dict/from_dict
    with its filesystem intact.

    Regression: ``to_dict`` used to store the protocol-stripped ``self.path``
    (e.g. ``/proj`` for ``memory://proj``); ``from_dict`` then re-ran
    ``url_to_fs`` on that bare path and reconstructed a *local* filesystem, so
    remote projects were wrongly interpreted as local (and failed to scan /
    rescan).
    """
    import fsspec

    mfs = fsspec.filesystem("memory")
    try:
        mfs.rm("/ser_remote", recursive=True)
    except FileNotFoundError:
        pass
    mfs.pipe("/ser_remote/pyproject.toml", b'[project]\nname="x"\nversion="0.1"\n')
    try:
        p = projspec.Project("memory://ser_remote", walk=False)
        assert not p.is_local()

        dic = p.to_dict(compact=False)
        # protocol must be preserved in the serialised url
        assert dic["url"] == "memory:///ser_remote"

        p2 = projspec.Project.from_dict(json.loads(json.dumps(dic)))
        # filesystem reconstructed as memory (not local)
        assert not p2.is_local()
        assert "python_library" in p2.specs
    finally:
        mfs.rm("/ser_remote", recursive=True)


def test_pickleable(proj):
    pickle.dumps(proj)


def test_from_dict_without_backend_loads_and_displays(monkeypatch):
    """A project whose fsspec backend is unavailable must still deserialise,
    display, and re-serialise from its cached metadata; only operations that
    need the live filesystem (rescan) should fail.
    """
    import projspec.proj.base as base

    dic = {
        "klass": "project",
        "specs": {},
        "children": {},
        "contents": {},
        "artifacts": {},
        "url": "s3://my-bucket/my-proj",
        "storage_options": {},
        "file_count": 42,
        "total_size": 123456,
        "is_writable": False,
        "last_modified": None,
        "last_modified_by": None,
        "scanned_at": 1700000000.0,
    }

    real_url_to_fs = base.fsspec.url_to_fs

    def boom(path, **kwargs):
        if str(path).startswith("s3://"):
            raise ImportError("Install s3fs to access S3")
        return real_url_to_fs(path, **kwargs)

    monkeypatch.setattr(base.fsspec, "url_to_fs", boom)

    # loads without raising, with no live filesystem
    p = projspec.Project.from_dict(dic)
    assert p.fs is None

    # displays from cached metadata
    assert p.display_url == "s3://my-bucket/my-proj"
    assert not p.is_local()
    assert repr(p) == "<Project 's3://my-bucket/my-proj'>"
    assert p.file_count == 42
    assert p.total_size == 123456
    assert p.is_writable is False
    assert "s3://my-bucket/my-proj" in p.text_summary()
    str(p)  # must not raise

    # re-serialises, keeping the protocol-qualified URL
    assert p.to_dict(compact=False)["url"] == "s3://my-bucket/my-proj"

    # but a rescan fails with a clear, actionable error
    with pytest.raises(RuntimeError, match="backend is not installed"):
        p.resolve()


def test_get_file(proj):
    # not in scanning by default
    bool(proj.get_file("README.md"))
    # scanned
    bool(proj.get_file("pyproject.toml"))


def test_tree_stats_on_memory_fs():
    """File stats are computed correctly on a real (non-local) filesystem.

    ``memory://`` is an in-process fsspec backend, so this exercises the
    remote code path (protocol-prefixed URL, fsspec walk) end-to-end rather
    than monkey-patching ``walk``.
    """
    import fsspec

    mfs = fsspec.filesystem("memory")
    try:
        mfs.rm("/treestat", recursive=True)
    except FileNotFoundError:
        pass

    mfs.pipe("/treestat/a.txt", b"hello")
    mfs.pipe("/treestat/b.txt", b"data data")
    mfs.pipe("/treestat/sub/c.txt", b"world")
    # an excluded directory that must NOT be counted
    mfs.pipe("/treestat/node_modules/big.js", b"x" * 9999)

    try:
        proj = projspec.Project("memory://treestat", walk=False)
        # protocol is stripped from the stored path...
        assert "://" not in proj.url
        # ...but the (remote) tree was walked and counted correctly,
        # with node_modules excluded.
        assert proj.file_count == 3
        assert proj.total_size == len("hello") + len("data data") + len("world")
    finally:
        mfs.rm("/treestat", recursive=True)


def test_tree_stats_with_list_yielding_walk(tmp_path):
    """Regression: some (often remote) backends ignore ``detail=True`` in
    ``walk`` and yield plain name-lists.  _tree_stats must still count files
    rather than reporting zero.
    """
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("data data")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("world")
    # an excluded directory that must NOT be counted
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "big.js").write_text("x" * 9999)

    proj = projspec.Project(str(tmp_path), walk=False)
    assert proj.file_count == 3
    assert proj.total_size == len("hello") + len("data data") + len("world")

    # Now wrap fs.walk so it yields lists of names (detail ignored), mimicking
    # backends that caused "0 files" before the fix.
    proj2 = projspec.Project(str(tmp_path), walk=False)
    # fsspec caches filesystem instances per protocol, so patch on the instance
    # and restore afterwards to avoid leaking into other tests.
    orig_walk = type(proj2.fs).walk

    def list_walk(self, path, **kwargs):
        for dirpath, _dirs, _files in orig_walk(self, path, detail=False, topdown=True):
            yield dirpath, _dirs, _files

    proj2.fs.walk = list_walk.__get__(proj2.fs, type(proj2.fs))
    try:
        proj2.__dict__.pop("_tree_stats", None)
        assert proj2.file_count == 3
        assert proj2.total_size == proj.total_size
    finally:
        # remove the instance override so the shared (cached) fs is clean
        del proj2.fs.walk
