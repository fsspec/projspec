import json
import pickle

import pytest

import projspec.utils


def test_basic(proj):
    spec = proj.specs["python_library"]
    assert "wheel" in spec.artifacts
    assert proj.all_artifacts()
    assert proj.children
    repr(proj)
    proj._repr_html_()


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
