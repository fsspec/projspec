from projspec.artifact.installable import Wheel
from projspec.artifact.process import Process
from projspec.content.environment import Environment, Precision, Stack
from projspec.content.executable import Command
from projspec.content.package import PythonPackage
from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict


class PythonCode(ProjectSpec):
    """Code directly importable by python

    This applies to directories with __init__.py (i.e., not isolated .py files,
    or eggs). Could include .zip in theory.

    Such a structure does not declare any envs, deps, etc. It contains
    nothing interesting _except_ code.

     A package is executable if it contains a ``__main__.py`` file.
    """

    spec_doc = (
        "https://docs.python.org/3/reference/import.html#regular-packages"
    )

    def match(self) -> bool:
        basenames = {_.rsplit("/", 1)[-1] for _ in self.root.filelist}
        return "__init__.py" in basenames

    def parse(self):
        arts = AttrDict()
        exe = [
            _
            for _ in self.root.filelist
            if _.rsplit("/", 1)[-1] == "__main__.py"
        ]
        if exe:
            arts["process"] = AttrDict(
                main=Process(proj=self.root, cmd=["python", exe[0]])
            )
        self._artifacts = arts
        out = AttrDict(
            PythonPackage(
                proj=self.root,
                artifacts=set(),
                package_name=self.path.rsplit("/", 1)[-1],
            )
        )
        if arts:
            art = arts["process"]["main"]
            out["command"] = AttrDict(
                main=Command(proj=self.root, artifacts={art}, cmd=art.cmd)
            )
        self._contents = out


class PythonLibrary(ProjectSpec):
    """Complete buildable python project

    Defined by the existence of pyproject.toml or setup.py.
    """

    # setup.py never had a spec
    spec_doc = (
        "https://packaging.python.org/en/latest/specifications/pyproject-toml/"
    )

    def match(self) -> bool:
        basenames = {_.rsplit("/", 1)[-1] for _ in self.root.filelist}
        return "pyproject.toml" in basenames or "setup.py" in basenames

    def parse(self):
        basenames = {_.rsplit("/", 1)[-1] for _ in self.root.filelist}

        arts = AttrDict()
        if "build-system" in self.root.pyproject:
            # should imply that "python -m build" can run
            # With `--wheel` ?
            arts["wheel"] = Wheel(proj=self.root, cmd=["python", "-m", "build"])
        elif "setup.py" in basenames:
            arts["wheel"] = Wheel(
                proj=self.root, cmd=["python", "setup.py", "bdist_wheel"]
            )
        self._artifacts = arts

        conts = AttrDict()
        # not attempting to parse setup.py, although most commonly a subdirectory with
        # the same name as the repo is the python package
        proj = self.root.pyproject.get("project", None)
        env = AttrDict()
        if proj is not None:
            conts["python_package"] = PythonPackage(
                proj=self.root, artifacts=set(), package_name=proj["name"]
            )
            if "dependencies" in proj:
                env["default"] = Environment(
                    proj=self.root,
                    artifacts=set(),
                    precision=Precision.SPEC,
                    stack=Stack.PIP,
                    packages=proj["dependencies"],
                    channels=[],
                )
            if "optional-dependencies" in proj:
                for name, deps in proj["optional-dependencies"].items():
                    env[name] = Environment(
                        proj=self.root,
                        artifacts=set(),
                        precision=Precision.SPEC,
                        stack=Stack.PIP,
                        packages=deps,
                        channels=[],
                    )
            for x in ("scripts", "gui-scripts"):
                if x in proj:
                    cmd = AttrDict()
                    for name, script in proj["scripts"].items():
                        mod, func = script.rsplit(":", 1)
                        c = f"import sys; from {mod} import {func}; sys.exit({func}())"
                        cmd[name] = Command(
                            proj=self.root,
                            artifacts=set(),
                            cmd=["python", "-c", c],
                        )
                    conts["command"] = cmd
        if "dependency-groups" in self.root.pyproject:
            env.update(
                {
                    k: Environment(
                        proj=self.root,
                        artifacts=set(),
                        precision=Precision.SPEC,
                        stack=Stack.PIP,
                        packages=v,
                        channels=[],
                    )
                    for k, v in _resolve_groups(
                        self.root.pyproject["dependency-groups"]
                    ).items()
                }
            )
        if "default" not in env and "requirements.txt" in basenames:
            fn = f"{self.root.url}/requirements.txt"
            with self.root.fs.open(fn, "rt") as f:
                lines = f.readlines()
            env["default"] = Environment(
                proj=self.root,
                artifacts=set(),
                precision=Precision.SPEC,
                stack=Stack.PIP,
                packages=[l.rstrip() for l in lines if l and "#" not in l],
                channels=[],
            )

        if env:
            conts["environment"] = env
            # + venv artifact
        self._contents = conts


def _resolve_groups(dep) -> dict[str, list[str]]:
    # simplified version of
    # https://packaging.python.org/en/latest/specifications/dependency-groups/
    #   #reference-implementation
    # only resolves groups in order
    out = {}
    for name, deps in dep.items():
        out[name] = []
        for d in deps:
            if isinstance(d, str):
                out[name].append(d)
            elif isinstance(d, dict) and list(d) == ["include-group"]:
                out[name].extend(out[d["include-group"]])
    return out
