import pytest

import projspec.proj


@pytest.mark.parametrize("cls_name", ["django", "streamlit"])
def test_compliant(tmpdir, cls_name):
    path = str(tmpdir)
    cls = projspec.proj.base.registry[cls_name]
    proj = cls.create(path)
    assert cls_name in proj


def test_cant_create(tmpdir):
    path = str(tmpdir)
    with pytest.raises(NotImplementedError):
        projspec.proj.ProjectSpec.create(path)
