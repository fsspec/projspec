import pytest

import projspec.proj
from projspec.utils import get_cls


@pytest.mark.parametrize(
    "cls_name",
    [
        "django",
        "streamlit",
        "python_code",
        "python_library",
        "JLabExtension",
        "IntakeCatalog",
        "DataPackage",
        "PyScript",
        "marimo",
    ],
)
def test_compliant(tmpdir, cls_name):
    path = str(tmpdir)
    cls = get_cls(cls_name)
    proj = cls.create(path)
    if not issubclass(cls, projspec.proj.ProjectExtra):
        assert cls_name in proj
    else:
        cls(proj).parse()


def test_cant_create(tmpdir):
    path = str(tmpdir)
    with pytest.raises(NotImplementedError):
        projspec.proj.ProjectSpec.create(path)
