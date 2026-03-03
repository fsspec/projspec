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
        "library_path": f"{conf_dir()}/library.json",
        "scan_types": [".py", ".yaml", ".yml", ".toml", ".json"],
        "scan_max_files": 100,
        "scan_max_size": 5 * 2**10,
        "remote_artifact_status": False,
    }


config_doc = {
    "library_path": "location of persisted project objects",
    "scan_types": "files extensions automatically read for scanning",
    "scan_max_files": "don't scan files if more than this number in the project",
    "scan_max_size": "don't scan files bigger than this (in bytes)",
    "remote_artifact_status": "whether to check status for remote artifacts",
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
    # TODO: require new value to be of same type as default?
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
    # TODO: only allow keys that exist in defaults()?
    conf.update(kwargs)
    try:
        yield
    finally:
        conf.clear()
        conf.update(old)
