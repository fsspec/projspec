from contextlib import contextmanager
import json
import os

from typing import Any

conf: dict[str, dict[str, Any]] = {}
default_conf_dir = os.path.join(os.path.expanduser("~"), ".config/projspec")


def conf_dir():
    return os.environ.get("PROJSPEC_CONFIG_DIR", default_conf_dir)


def defaults():
    return {
        # location of persisted project objects
        "library_path": f"{conf_dir()}/library.json",
        # files automatically read before scanning
        "scan_types": [".py", ".yaml", ".yml", ".toml", ".json"],
        # don't scan files if more than this number in the project
        "scan_max_files": 100,
        # don't scan files bigger than this (in bytes)
        # In the future we may change this to reading this many bytes from the header.
        "scan_max_size": 5 * 2**10,
        "remote_artifact_status": False,  # check status for remote artifacts?
    }


def load_conf(path: str | None = None):
    fn = f"{path or conf_dir()}/projspec.json"
    conf.clear()
    if os.path.exists(fn):
        with open(fn) as f:
            conf.update(json.load(f))


load_conf()


def get_conf(name: str):
    """Fetch the value of the given conf parameter from the current config or defaults"""
    return conf[name] if name in conf else defaults()[name]


def set_conf(name: str, value: Any):
    """Set the value of the given conf parameter and save to the config file"""
    if value:
        conf[name] = value
    else:
        conf.pop(name, None)
    os.makedirs(conf_dir(), exist_ok=True)
    with open(f"{conf_dir()}/projspec.json", "wt") as f:
        json.dump(conf, f)


@contextmanager
def temp_conf(**kwargs):
    """Temporarily set the config"""
    old = conf.copy()
    conf.update(kwargs)
    try:
        yield
    finally:
        conf.clear()
        conf.update(old)
