import json

import pytest

from projspec.config import conf, get_conf, defaults, load_conf


@pytest.fixture
def blank_conf(monkeypatch):
    old_conf = conf.copy()
    conf.clear()
    yield
    conf.update(old_conf)


def test_get_conf(blank_conf, tmpdir):
    assert get_conf("library_path") == defaults["library_path"]
    fn = str(tmpdir.join("projspec.json"))
    with open(fn, "wt") as f:
        json.dump({"temp": True}, f)

    load_conf(str(tmpdir))
    assert get_conf("temp") is True
