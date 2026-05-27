import json
import os

import pytest

from projspec.config import (
    get_conf,
    defaults,
    load_conf,
    set_conf,
    temp_conf,
    populate_if_empty,
)


@pytest.fixture()
def temp_conf_dir(tmpdir):
    old = os.getenv("PROJSPEC_CONFIG_DIR")
    os.environ["PROJSPEC_CONFIG_DIR"] = str(tmpdir)
    yield str(tmpdir)
    if old:
        os.environ["PROJSPEC_CONFIG_DIR"] = old


def test_get_conf(tmpdir, monkeypatch):
    assert get_conf("library_path") == defaults()["library_path"]
    monkeypatch.setenv("PROJSPEC_LIBRARY_PATH", str(tmpdir))
    assert get_conf("library_path") == str(tmpdir)
    fn = str(tmpdir.join("projspec.json"))
    with open(fn, "wt") as f:
        json.dump({"temp": True, "scan_max_size": 1}, f)

    with temp_conf():
        with pytest.warns(UserWarning):
            # warns that "temp" is not a known key
            load_conf(str(tmpdir))
        with pytest.raises(Exception):
            get_conf("nonexistent")
        with pytest.raises(Exception):
            # was skipped
            get_conf("temp")
        assert get_conf("scan_max_size") == 1


def test_create_conf(temp_conf_dir):
    fn = f"{temp_conf_dir}/projspec.json"
    assert not os.path.exists(fn)
    populate_if_empty()
    assert os.path.exists(fn)


def test_create_conf_exists(temp_conf_dir):
    fn = f"{temp_conf_dir}/projspec.json"
    with open(fn, "wt") as f:
        f.write("{}")
    populate_if_empty()
    with open(fn, "rt") as f:
        assert f.read() == "{}"


def test_set_conf_error():
    with pytest.raises(ValueError):
        set_conf("nonexistent", True)
    with pytest.raises(ValueError):
        # fails to coerce
        set_conf("scan_max_files", "notanumber")
    with temp_conf():
        set_conf("scan_max_files", "1")
        assert get_conf("scan_max_files") == 1


# TODO: add tests with config file keys that don't exist in defaults (should make warning)
#  and values that don't match in type (should either coerce or raise warning if not
#  possible). In the case of environment variables, failure to coerce is a ValueError,
#  because it doesn't prevent import.
