from contextlib import contextmanager
import json
import os
import warnings

from typing import Any

conf: dict[str, Any] = {}
default_conf_dir = os.path.join(os.path.expanduser("~"), ".config/projspec")


def conf_dir():
    """Location of the conf, and (normally) the library

    This is re-evaluated on every conf change, so PROJSPEC_CONFIG_DIR can
    be used to dynamically set a temporary location during a session.
    """
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
        "auto_rescan": 7 * 24 * 60 * 60,  # one week, in seconds
        "scan_types": [".py", ".yaml", ".yml", ".toml", ".json", ".md"],
        "scan_max_files": 100,
        "scan_max_size": 5 * 2**10,
        "remote_artifact_status": False,
        "capture_artifact_output": True,
        "preferred_install_methods": ["conda", "pip"],
        "data_min_fraction": 0.5,
        "data_min_file_size": 1024 * 1024,
        "data_min_total_size": 10 * 1024 * 1024,
        "data_min_play_size": 1,  # 64 * 1024,
        "data_consolidate_min_group": 3,
        "data_inspect_max_datasets": 50,
        "excludes": [
            "bld",
            "build",
            "dist",
            "env",
            "envs",
            "htmlcov",
            "node_modules",
            "site",
            "target",
            "venv",
        ],
    }


config_doc = {
    "library_path": "location of persisted project objects",
    "auto_rescan": (
        "maximum age (seconds) of a project loaded from the library before it "
        "is automatically rescanned and re-saved. Set to 0 to disable "
        "automatic rescanning. Default is one week."
    ),
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
    "data_min_fraction": (
        "fraction (0-1) of a project's total bytes that must be data files "
        "before a code/other project is also reported as a DataProject. Data "
        "below this fraction is only scanned if the project matches no other "
        "type, or individual files exceed data_min_file_size."
    ),
    "data_min_file_size": (
        "a single data file at or above this size (bytes) is considered "
        "significant enough to scan even in an otherwise code project."
    ),
    "data_min_total_size": (
        "minimum total size (bytes) of candidate data before a directory that "
        "also matches another project type is additionally reported as a "
        "DataProject (used together with data_min_fraction)."
    ),
    "data_min_play_size": (
        "floor (bytes) below which even a directory that matches no other "
        "project type is dismissed as toy/play data and not reported as a "
        "DataProject."
    ),
    "data_consolidate_min_group": (
        "minimum number of numbered/related files (e.g. 001.csv, 002.csv) that "
        "are consolidated into a single dataset."
    ),
    "data_inspect_max_datasets": (
        "do not run intake inspection if more than this many distinct datasets "
        "are found in a directory (avoids huge scans)."
    ),
    "excludes": (
        "directory names to skip when walking a project tree for child projects "
        "and file statistics. Directories whose names start with '.' or '_' are "
        "always skipped regardless of this setting."
    ),
}


def populate_if_empty():
    """If config file does not exist, write the defaults to it"""
    fn = f"{conf_dir()}/projspec.json"
    if not os.path.exists(fn):
        os.makedirs(conf_dir(), exist_ok=True)
        with open(fn, "w") as f:
            json.dump(defaults(), f)
    return fn


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
                        conf[k] = coerce(defs[k], v)
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
        if name not in config_doc:
            raise ValueError(f"Unknown config parameter {name}")
        val = conf.get(name, defaults()[name])
    return coerce(defaults()[name], val)


def set_conf(name: str, value: Any):
    """Set the value of the given conf parameter and save to the config file"""
    # TODO: require new value to be of same type as default?
    if name not in config_doc:
        raise ValueError
    if value:
        conf[name] = coerce(defaults()[name], value)
    else:
        conf.pop(name, None)
    save_conf(conf)


def save_conf(conf: dict):
    os.makedirs(conf_dir(), exist_ok=True)
    with open(f"{conf_dir()}/projspec.json", "wt") as f:
        json.dump(conf, f)


@contextmanager
def temp_conf(**kwargs):
    """Temporarily set the config in memory and on disk; both are restored on exit."""
    conf_file = f"{conf_dir()}/projspec.json"
    old_mem = conf.copy()
    # Snapshot the on-disk file so we can restore it even if set_conf() writes it.
    try:
        with open(conf_file) as _f:
            old_disk: str | None = _f.read()
    except FileNotFoundError:
        old_disk = None
    conf.update(kwargs)
    try:
        yield
    finally:
        conf.clear()
        conf.update(old_mem)
        # Restore (or remove) the config file to its pre-context state.
        if old_disk is None:
            try:
                os.unlink(conf_file)
            except FileNotFoundError:
                pass
        else:
            os.makedirs(conf_dir(), exist_ok=True)
            with open(conf_file, "w") as _f:
                _f.write(old_disk)
