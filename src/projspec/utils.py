import enum
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable

import yaml


class Enum(enum.Enum):
    def __repr__(self):
        return self.name


class AttrDict(dict):
    """Contains a dict but allows attribute read access for compliant keys"""

    def __init__(self, *data, **kw):
        dic = False
        if len(data) == 1 and isinstance(data[0], (tuple, list)):
            types = {type(_) for _ in data[0]}
            if isinstance(data[0], dict):
                super().__init__(data[0])
            elif isinstance(data[0], list):
                super().__init__(
                    {camel_to_snake(next(iter(types)).__name__): data[0]}
                )
            else:
                dic = True
        else:
            dic = True
        if dic:
            super().__init__(
                {camel_to_snake(type(v).__name__): v for v in data}
            )
        self.update(kw)

    def __getattr__(self, item):
        if item in self:
            return self[item]
        raise AttributeError(item)

    def to_dict(self):
        return to_dict(self)


def to_dict(obj):
    from projspec.artifact import BaseArtifact
    from projspec.content import BaseContent

    if isinstance(obj, dict):
        # includes AttrDict
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (bytes, str)):
        return obj
    if isinstance(obj, Iterable):
        return [to_dict(_) for _ in obj]
    if isinstance(obj, (BaseArtifact, BaseContent)):
        return obj._repr2()
    return str(obj)


class IndentDumper(yaml.Dumper):
    def __init__(self, stream, **kw):
        super().__init__(stream, **kw)
        self.increase_indent()

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


cam_patt = re.compile(r"(?<!^)(?=[A-Z])")


def camel_to_snake(camel: str) -> str:
    # https://stackoverflow.com/a/1176023/3821154
    return re.sub(cam_patt, "_", camel).lower()


def to_camel_case(snake_str: str) -> str:
    # https://stackoverflow.com/a/19053800/3821154
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))


def _linked_local_path(path):
    return str(pathlib.Path(path).resolve())


class IsInstalled:
    """Checks if we can call commands, as a function of current environment"""

    cache = {}

    def __init__(self):
        # or maybe the value of $PATH
        self.env = _linked_local_path(sys.executable)

    def exists(self, cmd: str, refresh=False):
        if refresh or (self.env, cmd) not in self.cache:
            try:
                p = subprocess.Popen(
                    [cmd],
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
                p.terminate()
                p.wait()
                out = True
            except FileNotFoundError:
                out = False
            except subprocess.CalledProcessError:
                # failed due to missing args, but does exist
                out = True
            self.cache[(self.env, cmd)] = out
        return self.cache[(self.env, cmd)]

    def __contains__(self, item):
        # canonical use: `"python" in is_installed`
        # shutil.which?
        return self.exists(item)

    # TODO: persist cache


is_installed = IsInstalled()


def _yaml_no_jinja(fileobj):
    # TODO: rather than skip jinja stuff, we can copy conda code to parse it, but
    #  templates can involve function calls and reference to env vars we don't have
    txt = fileobj.read().decode()
    lines = []
    for line in txt.splitlines():
        if "{%" in line:
            continue
        if " # [" in line:
            line = line[: line.index(" # [")]
        if "{{" in line and "}}" in line:
            if line.strip()[0] == "-":
                # list element
                ind = line.index("-") + 2
                end = line[ind:].replace('"', "").replace("\\", "")
                lines.append(f'{line[:ind]}"{end}"')
            elif ":" in line:
                # key element
                ind = line.index(":") + 2
                end = line[ind:].replace('"', "").replace("\\", "")
                lines.append(f'{line[:ind]}"{end}"')
            else:
                # does not account for text block
                lines.append(line)
        else:
            lines.append(line)
    return yaml.safe_load("\n".join(lines))


def flatten(x: Iterable):
    """Descend into dictionaries to return a set of all of the leaf values"""
    # todo: only works on hashables
    # todo: pass set for mutation rather than create set on each recursion
    out = set()
    if isinstance(x, dict):
        x = x.values()
    for item in x:
        if isinstance(item, dict):
            out.update(flatten(item.values()))
        elif isinstance(item, (str, bytes)):
            # These are iterables whose items are also iterable, i.e.,
            # the first item of "item" is "i", which is also a string.
            out.add(item)
        else:
            try:
                out.update(flatten(item))
            except TypeError:
                out.add(item)
    return out
