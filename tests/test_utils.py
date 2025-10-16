import pytest

from projspec.content import BaseContent
from projspec.content.environment import Stack
from projspec.content.metadata import DescriptiveMetadata
from projspec.utils import AttrDict, get_cls, is_installed, sort_version_strings


def test_is_installed():
    assert "python" in is_installed


def test_attrdict():
    d = AttrDict({"a": 1, "b": 2, "c": 3})
    assert d.a == 1
    assert dict(d) == d

    d2 = AttrDict(a=1, b=2, c=3)
    assert d2 == d


def test_attrdict_entity():
    d = AttrDict(
        BaseContent(proj=None, artifacts=set()),
        DescriptiveMetadata(proj=None, artifacts=set()),
    )
    assert set(d) == {"base_content", "descriptive_metadata"}

    with pytest.raises(TypeError):
        AttrDict(
            [
                BaseContent(proj=None, artifacts=set()),
                DescriptiveMetadata(proj=None, artifacts=set()),
            ]
        )


def test_enum():
    st = Stack.PIP
    assert st == "PIP"
    assert st == 1
    assert st.snake_name() == "stack"
    cls = get_cls("Stack", "enum")
    assert isinstance(st, cls)
    assert st.to_dict()["klass"] == ["enum", "stack"]


def test_sort_versions():
    vers = ["1", "1.2.3", "1.0.3", "1.10.3", "1.10.3.dev1", "1.10.3.dev"]
    expected = ["1", "1.0.3", "1.2.3", "1.10.3", "1.10.3.dev", "1.10.3.dev1"]
    assert sort_version_strings(vers) == expected
