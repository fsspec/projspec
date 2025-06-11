import os.path

import projspec

here = os.path.dirname(__file__)


def test_basic():
    proj = projspec.Project(os.path.dirname(here), walk=True)
    spec = proj.specs["python_library"]
    assert "wheel" in spec.artifacts
    assert proj.children
