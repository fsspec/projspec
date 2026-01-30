from dataclasses import dataclass, field
from enum import auto

from projspec.proj.base import ProjectExtra
from projspec.content import BaseContent
from projspec.utils import Enum


class Stack(Enum):
    """The type of environment by packaging tech"""

    PIP = auto()
    CONDA = auto()
    NPM = auto()


class Precision(Enum):
    """Type of environment definition by the amount of precision"""

    # TODO: categories may be refined, e.g., whether items include architecture or hash
    SPEC = auto()
    LOCK = auto()


@dataclass
class Environment(BaseContent):
    """Definition of a python runtime environment"""

    stack: Stack
    precision: Precision
    packages: list[str]
    # This may be empty for loose specs; may include endpoints or index URLs.
    channels: list[str] = field(default_factory=list)

    def _repr2(self):
        out = {
            k: (v.name if isinstance(v, Enum) else v)
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k not in ("proj", "artifacts")
        }
        if not self.channels:
            out.pop("channels", None)
        return out


# TODO: if a project has both requirements and environment.yml, one will overwrite the other
class PythonRequirements(ProjectExtra):
    spec_doc = "https://pip.pypa.io/en/stable/reference/requirements-file-format/"

    def match(self) -> bool:
        return "requirements.txt" in self.proj.basenames

    def parse(self) -> None:
        deps = self.proj.fs.read_text(
            self.proj.basenames["requirements.txt"]
        ).splitlines()
        precision = Precision.LOCK if all("==" in _ for _ in deps) else Precision.SPEC
        self.contents["environment"] = Environment(
            stack=Stack.PIP,
            precision=precision,
            packages=deps,
            proj=self.proj,
            artifacts=set(),
        )


class CondaEnv(ProjectExtra):
    spec_doc = (
        "https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/"
        "manage-environments.html#create-env-file-manually"
    )

    def match(self) -> bool:
        return (
            "environment.yaml" in self.proj.basenames
            or "environment.yml" in self.proj.basenames
        )

    def parse(self) -> None:
        import yaml

        u = self.proj.basenames.get(
            "environment.yaml", self.proj.basenames.get("environment.yml")
        )
        deps = yaml.safe_load(self.proj.fs.open(u, "rt"))
        # TODO: split out pip deps
        self.contents["environment"] = Environment(
            stack=Stack.CONDA,
            precision=Precision.SPEC,
            packages=deps,
            channels=deps.get("channels"),
            proj=self.proj,
            artifacts=set(),
        )
