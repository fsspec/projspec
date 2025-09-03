import json
import os.path
import pickle

import pytest

import projspec.utils

here = os.path.dirname(__file__)


def test_basic():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    spec = proj.specs["python_library"]
    assert "wheel" in spec.artifacts
    assert proj.artifacts
    assert proj.children
    repr(proj)
    proj._repr_html_()


def test_errors():
    with pytest.raises(ValueError):
        projspec.Project.from_dict({})


def test_contains():
    from projspec.artifact.installable import Wheel

    proj = projspec.Project(os.path.dirname(here), walk=True)
    assert proj.python_library is not None
    assert "python_library" in proj
    assert proj.filter_by_type([Wheel])


def test_serialise():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    js = json.dumps(proj.to_dict(compact=False))
    projspec.Project.from_dict(json.loads(js))


def test_pickleable():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    pickle.dumps(proj)
