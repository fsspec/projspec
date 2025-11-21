import os

from projspec import Project
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
