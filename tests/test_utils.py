import pytest

from projspec.content import BaseContent
from projspec.content.metadata import DescriptiveMetadata
from projspec.utils import AttrDict, is_installed


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
