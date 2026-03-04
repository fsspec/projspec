import json

import pytest

from projspec.config import conf, get_conf, defaults, load_conf, temp_conf


def test_get_conf(tmpdir, monkeypatch):
    assert get_conf("library_path") == defaults()["library_path"]
    monkeypatch.setenv("PROJSPEC_LIBRARY_PATH", str(tmpdir))
    assert get_conf("library_path") == str(tmpdir)
    fn = str(tmpdir.join("projspec.json"))
    with open(fn, "wt") as f:
        json.dump({"temp": True, "scan_max_size": 1}, f)

    with temp_conf():
        load_conf(str(tmpdir))
        assert "temp" in conf
        with pytest.raises(Exception):
            get_conf("nonexistent")
        with pytest.raises(Exception):
            # because has no known type
            get_conf("temp")
        assert get_conf("scan_max_size") == 1
