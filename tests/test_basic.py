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


def test_pickleable(proj):
    pickle.dumps(proj)


def test_get_file(proj):
    # not in scanning by default
    bool(proj.get_file("README.md"))
    # scanned
    bool(proj.get_file("pyproject.toml"))
