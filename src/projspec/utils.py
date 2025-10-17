import enum
import logging
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable

import toml
import yaml

enum_registry = {}


class Enum(enum.Enum):
    """Named enum values, so that str(x) looks like the label."""

    # TODO: does this need explicit deser for JSON?

    def __repr__(self):
        return self.name

    __str__ = __repr__

    def __init_subclass__(cls, **kwargs):
        enum_registry[camel_to_snake(cls.__name__)] = cls

    @classmethod
    def snake_name(cls):
        return camel_to_snake(cls.__name__)

    def to_dict(self, compact=False):
        if compact:
            return self.name
        return {"klass": ["enum", self.snake_name()], "value": self.value}

    def __eq__(self, other):
        if isinstance(other, int):
            return self.value == other
        return str(self) == str(other)


def get_enum_class(name):
    return enum_registry[name]


class AttrDict(dict):
    """Contains a dict but allows attribute read access for compliant keys."""

    def __init__(self, *data, **kw):
        dic = False
        if len(data) == 1 and isinstance(data[0], (tuple, list, dict)):
            types = {type(_) for _ in data[0]}
            if isinstance(data[0], dict):
                super().__init__(data[0])
            elif isinstance(data[0], list):
                if len(types) > 1:
                    raise TypeError("Multiple types ina  list")
                super().__init__({camel_to_snake(next(iter(types)).__name__): data[0]})
            elif isinstance(data[0], dict):
                super().__init__(data[0])
            else:
                dic = True
        else:
            dic = True
        if dic:
            super().__init__({camel_to_snake(type(v).__name__): v for v in data})
        self.update(kw)

    def __getattr__(self, item):
        if item in self:
            return self[item]
        raise AttributeError(item)

    def to_dict(self, compact=True):
        return to_dict(self, compact=compact)

    def __dir__(self):
        return sorted(list(super().__dir__()) + list(self))


def to_dict(obj, compact=True):
    """Make entity into JSON-serialisable dict representation"""
    if isinstance(obj, dict):
        return {
            k: (
                v.to_dict(compact=compact)
                if hasattr(v, "to_dict")
                else to_dict(v, compact=compact)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, (bytes, str)):
        return obj
    if isinstance(obj, Iterable):
        return [to_dict(_, compact=compact) for _ in obj]
    if hasattr(obj, "to_dict"):
        return obj.to_dict(compact=compact)
    return str(obj)


def from_dict(dic, proj=None):
    """Rehydrate the result of to_dict into projspec instances"""
    from projspec import Project

    if isinstance(dic, dict):
        if "klass" in dic:
            if dic["klass"] == "project":
                return Project.from_dict(dic)
            category, name = dic.pop("klass")
            cls = get_cls(name, category)
            obj = object.__new__(cls)
            obj.proj = proj
            obj.__dict__.update({k: from_dict(v, proj=proj) for k, v in dic.items()})
            return obj
        return AttrDict(**{k: from_dict(v, proj=proj) for k, v in dic.items()})
    elif isinstance(dic, list):
        return [from_dict(_, proj=proj) for _ in dic]
    else:
        return dic


class IndentDumper(yaml.Dumper):
    """Helper class to write YAML output with given prefix indent"""

    def __init__(self, stream, **kw):
        super().__init__(stream, **kw)
        self.increase_indent()

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


cam_patt = re.compile(r"(?<!^)(?=[A-Z])")


def camel_to_snake(camel: str) -> str:
    """CamelCase to snake_case converter"""
    # https://stackoverflow.com/a/1176023/3821154
    return re.sub(cam_patt, "_", camel).lower()


def to_camel_case(snake_str: str) -> str:
    """snake_case to camelCase converter"""
    # https://stackoverflow.com/a/19053800/3821154
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))


def _linked_local_path(path):
    return str(pathlib.Path(path).resolve())


class IsInstalled:
    """Checks if we can call commands, as a function of the current environment.

    Typical usage:

        >>> "python" in IsInstalled()
        True

    Results are cached by command and python executable, so that in the
    future we may be able to persist these for future sessions.

    An instance of this class is created at import: ``projspec.utils.is_installed``.
    """

    cache = {}

    def __init__(self):
        # or maybe the value of $PATH
        self.env = _linked_local_path(sys.executable)

    def exists(self, cmd: str, refresh=False):
        """Test if command can be called, by starting a subprocess

        This is more costly what some PATH lookup (i.e., what ``which()`` does), but also
        more rigorous.
        """
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
        """Allows syntax shortcut of ``"command" in ...``"""
        # shutil.which?
        return self.exists(item)

    # TODO: persist cache


is_installed = IsInstalled()

# {% set sha256 = "fff" %}
sj = re.compile(r'{%\s+set\s+(\S+)\s+=\s+"(.*)"\s+%}')


def _yaml_no_jinja(fileobj):
    """Read YAML text from the given file, attempting to evaluate jinja2 templates."""
    txt = fileobj.read().decode()
    lines = []
    variables = {}
    for line in txt.splitlines():
        if "{%" in line:
            if match := sj.search(line):
                key, var = match.groups()
                variables[key] = var
            continue
        if " # [" in line:
            line = line[: line.index(" # [")]
        if "{{" in line and "}}" in line:
            try:
                import jinja2

                line = jinja2.Template(line).render(variables)
                done = True
            except jinja2.TemplateError:
                logging.exception("Jinja Template Error")
                done = False
            except ImportError:
                done = False
            if not done:
                # include unrendered template
                if line.strip()[0] == "-":
                    # list element
                    ind = line.index("-") + 2
                    end = line[ind:].replace('"', "").replace("\\", "")
                    line = f'{line[:ind]}"{end}"'
                elif ":" in line:
                    # key element
                    ind = line.index(":") + 2
                    end = line[ind:].replace('"', "").replace("\\", "")
                    line = f'{line[:ind]}"{end}"'
            lines.append(line)
        else:
            lines.append(line)
    return yaml.load("\n".join(lines), Loader=yaml.CSafeLoader)


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


def deep_get(data: dict, path: str | list[str], default=None):
    """Fetch data from a nested dictionary at a given path."""
    if isinstance(path, str):
        path = path.split(".")
    for part in path:
        if part not in data:
            return default
        data = data[part]
    return data


def deep_set(data: dict, path: str | list[str], thing) -> None:
    """Set data in a nested dictionary at a given path."""
    if isinstance(path, str):
        path = path.split(".")
    for part in path[:-1]:
        data = data.setdefault(part, {})
    data[path[-1]] = thing


def sort_version_strings(versions: Iterable[str]) -> list[str]:
    """Sort typical python package version strings"""

    def int_or(x):
        try:
            return int(x)
        except ValueError:
            ma = re.search(r"(\d+)", x)
            if ma:
                return int(ma.group(1))
            else:
                return 0.001

    return sorted(versions, key=lambda s: [int_or(_) for _ in s.split(".")])


class PickleableTomlDecoder(toml.TomlDecoder):
    """Allows TOML empty tables to be picklable"""

    # https://github.com/uiri/toml/issues/362#issuecomment-842665836
    def get_empty_inline_table(self):
        return {}


def get_get_cls(registry="proj"):
    import projspec

    reg_map = {
        "projspec": projspec.proj.base.registry,
        "content": projspec.content.base.registry,
        "artifact": projspec.artifact.base.registry,
        "enum": enum_registry,
    }
    return reg_map[registry]


def get_cls(name, registry="proj"):
    """Find class by name and type

    name: str
        Class name in camel case (the typical real name) or snake equivalent
    registry: projspec|content|artifact|enum
        Category of class to find
    """
    return get_get_cls(registry)[camel_to_snake(name)]


def spec_class_qnames(registry="proj"):
    """Useful for generating lists of classes for documentation"""
    reg = get_get_cls(registry)
    for s in sorted(
        (
            ".".join([cls.__module__, cls.__name__]).removeprefix("projspec.")
            for cls in reg.values()
        )
    ):
        print("   ", s),
    for s in sorted(
        (
            ".. autoclass:: " + ".".join([cls.__module__, cls.__name__])
            for cls in reg.values()
        )
    ):
        print(s)
