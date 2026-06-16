import json
import os
import time

from projspec import Project
from projspec.config import temp_conf
from projspec.library import ProjectLibrary

here = os.path.abspath(os.path.dirname(__file__))
root = os.path.dirname(here)


def test_library(tmp_path):
    fn = str(tmp_path / "library")
    library = ProjectLibrary(fn, auto_save=True)
    proj = Project(root)

    assert not os.path.exists(fn)
    assert not library.entries

    library.add_entry(root, proj)

    assert os.path.exists(fn)
    assert library.entries

    library.clear()

    assert not os.path.exists(fn)
    assert not library.entries


def test_filter(tmp_path):
    fn = str(tmp_path / "library")
    library = ProjectLibrary(None, auto_save=False)
    proj = Project(root)
    library.add_entry(root, proj)

    # empty filter
    assert library.filter([])

    # filter hit
    assert library.filter([("spec", "python_library")])

    # miss
    assert not library.filter([("spec", "xx")])


def test_scanned_at_set_on_scan(tmp_path):
    (tmp_path / "__init__.py").write_text("x = 1\n")
    before = time.time()
    proj = Project(str(tmp_path), walk=False)
    after = time.time()
    assert isinstance(proj.scanned_at, float)
    assert before <= proj.scanned_at <= after


def test_scanned_at_serialised_and_roundtrips(tmp_path):
    (tmp_path / "__init__.py").write_text("x = 1\n")
    proj = Project(str(tmp_path), walk=False)

    dic = proj.to_dict(compact=False)
    assert "scanned_at" in dic

    proj2 = Project.from_dict(dic)
    # round-trips back to the same numeric value (serialiser stringifies floats)
    assert isinstance(proj2.scanned_at, float)
    assert proj2.scanned_at == proj.scanned_at


def test_scanned_at_defaults_to_now_when_missing(tmp_path):
    (tmp_path / "__init__.py").write_text("x = 1\n")
    proj = Project(str(tmp_path), walk=False)

    dic = proj.to_dict(compact=False)
    dic.pop("scanned_at")  # simulate an older library without the field

    before = time.time()
    proj2 = Project.from_dict(dic)
    assert before <= proj2.scanned_at <= time.time() + 1


def _make_library_with_old_entry(tmp_path, age_seconds):
    """Create a library file containing one project scanned *age_seconds* ago."""
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "__init__.py").write_text("x = 1\n")
    fn = str(tmp_path / "library.json")

    proj = Project(str(proj_dir), walk=False)
    library = ProjectLibrary(fn, auto_save=True)
    key = proj.fs.unstrip_protocol(proj.url)
    library.add_entry(key, proj)

    # rewrite the saved scanned_at to be old
    data = json.load(open(fn))
    for entry in data.values():
        entry["scanned_at"] = time.time() - age_seconds
    json.dump(data, open(fn, "w"))
    return fn, key


def test_auto_rescan_refreshes_old_entry(tmp_path):
    fn, key = _make_library_with_old_entry(tmp_path, age_seconds=1000)

    with temp_conf(auto_rescan=10):  # threshold below the entry's age
        library = ProjectLibrary(fn)
    # the stale entry was rescanned -> timestamp is fresh
    assert library.entries[key].scanned_at >= time.time() - 5
    # ...and the refreshed library was written back to disk
    data = json.load(open(fn))
    assert float(data[key]["scanned_at"]) >= time.time() - 5


def test_auto_rescan_keeps_fresh_entry(tmp_path):
    fn, key = _make_library_with_old_entry(tmp_path, age_seconds=5)

    with temp_conf(auto_rescan=1000):  # threshold well above the entry's age
        library = ProjectLibrary(fn)
    # fresh enough -> not rescanned, original (old) timestamp preserved
    assert library.entries[key].scanned_at < time.time() - 1


def test_auto_rescan_disabled_with_zero(tmp_path):
    fn, key = _make_library_with_old_entry(tmp_path, age_seconds=10_000)
    old = json.load(open(fn))[key]["scanned_at"]

    with temp_conf(auto_rescan=0):  # disabled entirely
        library = ProjectLibrary(fn)
    # the very old entry is kept as-is, never rescanned
    assert abs(library.entries[key].scanned_at - old) < 1
