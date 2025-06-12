import enum
import pathlib
import re
import subprocess
import sys

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
