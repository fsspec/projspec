from contextlib import contextmanager
import json
import os
import warnings

from typing import Any

conf: dict[str, dict[str, Any]] = {}
default_conf_dir = os.path.join(os.path.expanduser("~"), ".config/projspec")


def conf_dir():
    return os.environ.get("PROJSPEC_CONFIG_DIR", default_conf_dir)


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


def defaults():
    return {
        "library_path": f"{conf_dir()}/library.json",
        "scan_types": [".py", ".yaml", ".yml", ".toml", ".json", ".md"],
        "scan_max_files": 100,
        "scan_max_size": 5 * 2**10,
        "remote_artifact_status": False,
        "capture_artifact_output": True,
        "preferred_install_methods": ["conda", "pip"],
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
    "preferred_install_methods": (
        "ordered list of preferred installer names for install_tool(), "
        "e.g. ['uv', 'conda', 'pip']. Empty list uses the platform default."
    ),
}


def load_conf(path: str | None = None):
    fn = f"{path or conf_dir()}/projspec.json"
    conf.clear()
    if os.path.exists(fn):
        with open(fn) as f:
            new = json.load(f)
            defs = defaults()
            extra = set(new) - set(defs)
            if extra:
                warnings.warn(f"Unknown keys in config, skipping: {extra}")
            for k, v in new.items():
                if k in defs:
                    try:
                        conf[k] = coerce(v, defs[k])
                    except ValueError:
                        warnings.warn(
                            f"Failed to coerce {v} (key {k}) to "
                            f"type {defs[k]}; skipping"
                        )


load_conf()


def get_conf(name: str):
    """Fetch the value of the given conf parameter from the current config or defaults"""
    if f"PROJSPEC_{name.upper()}" in os.environ:
        val = os.environ[f"PROJSPEC_{name.upper()}"]
    else:
        assert name in config_doc, f"Unknown config parameter {name}"
        val = conf.get(name, defaults()[name])
    return coerce(defaults()[name], val)


def set_conf(name: str, value: Any):
    """Set the value of the given conf parameter and save to the config file"""
    # TODO: require new value to be of same type as default?
    if value:
        conf[name] = value
    else:
        conf.pop(name, None)
    save_conf(conf)


def save_conf(conf: dict):
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
