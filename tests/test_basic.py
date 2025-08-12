import json
import os.path
import pickle

import projspec

here = os.path.dirname(__file__)


def test_basic():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    spec = proj.specs["python_library"]
    assert "wheel" in spec.artifacts
    assert proj.children


def test_serialise():
    import json

    proj = projspec.Project(os.path.dirname(here), walk=True)
    js = json.dumps(proj.to_dict(compact=False))
    json.loads(js)


def test_jsonable():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    json.dumps(proj.to_dict())


def test_pickleable():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    pickle.dumps(proj)
