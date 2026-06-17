import projspec
import pytest

from projspec.content import BaseContent
from projspec.content.environment import Stack
from projspec.content.metadata import DescriptiveMetadata
from projspec.utils import (
    AttrDict,
    class_infos,
    get_cls,
    is_installed,
    sort_version_strings,
    run_subprocess,
    to_dict,
    from_dict,
)


def test_is_installed():
    assert "python" in is_installed


def test_attrdict():
    d = AttrDict({"a": 1, "b": 2, "c": 3})
    assert d.a == 1
    assert dict(d) == d

    d2 = AttrDict(a=1, b=2, c=3)
    assert d2 == d


def test_attrdict_entity():
    proj = object.__new__(projspec.Project)
    d = AttrDict(
        BaseContent(proj=proj),
        DescriptiveMetadata(proj=proj),
    )
    assert set(d) == {"base_content", "descriptive_metadata"}

    with pytest.raises(TypeError):
        AttrDict(
            [
                BaseContent(proj=proj),
                DescriptiveMetadata(proj=proj),
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


def test_to_dict_preserves_json_native_types():
    # JSON-native scalars must keep their type rather than being stringified,
    # so storage_options like {"anon": True} serialise to JSON `true`, not
    # the string "True".
    import json

    src = {
        "anon": True,
        "use_ssl": False,
        "port": 8080,
        "ratio": 0.5,
        "token": "abc",
        "missing": None,
        "nested": {"flag": True, "n": 3},
        "list": [True, 1, "x"],
    }
    d = to_dict(src)

    assert d["anon"] is True
    assert d["use_ssl"] is False
    assert d["port"] == 8080 and isinstance(d["port"], int)
    assert d["ratio"] == 0.5
    assert d["token"] == "abc"
    assert d["missing"] is None
    assert d["nested"]["flag"] is True
    assert d["list"] == [True, 1, "x"]

    # and it survives a real JSON round-trip as native types
    restored = json.loads(json.dumps(d))
    assert restored["anon"] is True
    assert restored["nested"]["flag"] is True
    # from_dict passes scalars through unchanged
    assert from_dict(restored)["anon"] is True


def test_storage_options_bool_roundtrip():
    # a Project's storage_options booleans must round-trip as real booleans
    import json

    p = projspec.Project(
        ".", walk=False, storage_options={"anon": True, "use_listings_cache": False}
    )
    js = json.dumps(p.to_dict(compact=False))
    assert '"anon": true' in js
    p2 = projspec.Project.from_dict(json.loads(js))
    assert p2.storage_options["anon"] is True
    assert p2.storage_options["use_listings_cache"] is False


def test_sort_versions():
    vers = ["1", "1.2.3", "1.0.3", "1.10.3", "1.10.3.dev1", "1.10.3.dev"]
    expected = ["1", "1.0.3", "1.2.3", "1.10.3", "1.10.3.dev", "1.10.3.dev1"]
    assert sort_version_strings(vers) == expected


def test_info():
    info = class_infos()
    assert "specs" in info
    assert "python_library" in info["specs"]
    assert info["specs"]["python_library"]["doc"]


def test_run():
    import subprocess

    with pytest.raises(RuntimeError):
        run_subprocess(["not-a-program"])
    out = run_subprocess(["echo", "word"], output=True)
    assert out.stdout.strip() == b"word"
    process = run_subprocess(["echo", "word"], popen=True)
    assert isinstance(process, subprocess.Popen)


def test_run_subprocess_missing_tool_suggests_install(monkeypatch):
    from projspec.tools import suggest

    monkeypatch.setattr(is_installed, "exists", lambda cmd, **kw: False)
    with pytest.raises(RuntimeError, match=suggest("uv")):
        run_subprocess(["uv", "sync"])


def test_run_subprocess_unknown_tool_no_info(monkeypatch):
    with pytest.raises(RuntimeError, match="No install information"):
        run_subprocess(["doesnotexist", "foo"])
