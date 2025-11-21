import json
import os

from typing import Any

conf: dict[str, dict[str, Any]] = {}
default_conf_dir = os.path.join(os.path.expanduser("~"), ".config/projspec")
conf_dir = os.environ.get("PROJSPEC_CONFIG_DIR", default_conf_dir)

defaults = {
    # location of persisted project objects
    "library_path": f"{conf_dir}/library.json",
}


def load_conf(path: str | None = None):
    fn = f"{path or default_conf_dir}/projspec.json"
    if os.path.exists(fn):
        with open(fn) as f:
            conf.update(json.load(f))


load_conf()


def get_conf(name: str):
    """Fetch the value of the given conf parameter from the current config or defaults"""
    return conf[name] if name in conf else defaults[name]
