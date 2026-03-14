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
        "capture_artifact_output": True,
    }


config_doc = {
    "library_path": "location of persisted project objects",
    "scan_types": "files extensions automatically read for scanning",
    "scan_max_files": "don't scan files if more than this number in the project",
    "scan_max_size": "don't scan files bigger than this (in bytes)",
    "remote_artifact_status": "whether to check status for remote artifacts",
    "capture_artifact_output": (
        "if True, capture and enqueue output from spawned Process artifacts. "
        "Otherwise, output appears on stdout/err."
    ),
}


def load_conf(path: str | None = None):
    fn = f"{path or conf_dir()}/projspec.json"
    conf.clear()
    if os.path.exists(fn):
        with open(fn) as f:
            conf.update(json.load(f))
    # TODO: warn on unknown keys?


load_conf()


def get_conf(name: str):
    """Fetch the value of the given conf parameter from the current config or defaults"""
    if f"PROJSPEC_{name.upper()}" in os.environ:
        val = os.environ[f"PROJSPEC_{name.upper()}"]
    else:
        assert name in config_doc, f"Unknown config parameter {name}"
        val = conf[name] if name in conf else defaults()[name]
    return coerce(defaults()[name], val)


def coerce(template, val):
    """ensure val has the same type as template"""
    typ = type(template)
    if typ is bool:
        return val in ("true", "True", "1", True, "T")
    if typ is list:
        return [coerce(template[0], _) for _ in val]
    if typ in (str, int, float):
        return typ(val)
    return val


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
