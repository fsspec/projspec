"""Unit tests for protocol-preserving helpers in the Qt app.

These test the pure-Python helpers only, so they run without PyQt5 installed.
"""

import json

import fsspec
import pytest

import projspec
from projspec.config import temp_conf
from projspec.library import ProjectLibrary
from projspec.qtapp.main import _rescan_path, _url_to_local


def _make_memory_project(root="/qt_rescan"):
    mfs = fsspec.filesystem("memory")
    try:
        mfs.rm(root, recursive=True)
    except FileNotFoundError:
        pass
    mfs.pipe(f"{root}/pyproject.toml", b'[project]\nname="x"\nversion="0.1"\n')
    return mfs, root


class TestRescanPath:
    def test_protocol_key_preferred(self):
        # a protocol-qualified key is returned verbatim, even with no entry
        assert _rescan_path("memory:///proj", None) == "memory:///proj"
        assert _rescan_path("s3://bucket/key", None) == "s3://bucket/key"

    def test_protocol_key_preferred_over_local_fs_entry(self):
        # Even if the stored entry's filesystem was (wrongly) reconstructed as
        # local, the protocol-qualified key wins.
        mfs, root = _make_memory_project()
        try:
            # an old-format serialised entry: stripped url -> local fs
            old_entry = {
                "klass": "project",
                "specs": {},
                "children": {},
                "contents": {},
                "artifacts": {},
                "url": root,
                "storage_options": {},
                "file_count": 1,
                "total_size": 10,
                "is_writable": True,
                "last_modified": None,
                "last_modified_by": None,
                "scanned_at": 1.0,
            }
            entry = projspec.Project.from_dict(old_entry)
            assert entry.is_local()  # the reconstructed fs is wrongly local
            # ...but the key's protocol is honoured
            assert _rescan_path(f"memory://{root}", entry) == f"memory://{root}"
        finally:
            mfs.rm(root, recursive=True)

    def test_local_key_uses_entry_unstrip(self):
        # a key without a protocol falls back to the entry's protocol-qualified
        # URL
        mfs, root = _make_memory_project("/qt_rescan2")
        try:
            proj = projspec.Project(f"memory://{root}", walk=False)
            # key has no protocol -> use the entry's unstrip_protocol
            assert _rescan_path(root, proj) == f"memory://{root}"
        finally:
            mfs.rm(root, recursive=True)

    def test_no_protocol_no_entry_returns_key(self):
        assert _rescan_path("/plain/path", None) == "/plain/path"


def test_rescan_path_roundtrip_reopens_remote():
    """A library entry saved+loaded then resolved via _rescan_path re-opens as
    the correct (non-local) filesystem."""
    mfs, root = _make_memory_project("/qt_rt")
    try:
        proj = projspec.Project(f"memory://{root}", walk=False)
        key = proj.fs.unstrip_protocol(proj.url)
        # serialise + deserialise as the library would
        dic = json.loads(json.dumps(proj.to_dict(compact=False)))
        entry = projspec.Project.from_dict(dic)
        path = _rescan_path(key, entry)
        reopened = projspec.Project(path, walk=False)
        assert not reopened.is_local()
        assert "python_library" in reopened.specs
    finally:
        mfs.rm(root, recursive=True)


def test_url_to_local():
    assert _url_to_local("file:///tmp/x") == "/tmp/x"
    assert _url_to_local("/tmp/x") == "/tmp/x"
    assert _url_to_local("memory://proj") == "memory://proj"
