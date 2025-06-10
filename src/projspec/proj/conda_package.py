import re

import fsspec
import yaml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


def _yaml_no_jinja(fileobj):
    txt = fileobj.read().decode()
    txt2 = "\n".join([
        # removes line-end selectors; we don't attempt to evaluate them
        # https://docs.conda.io/projects/conda-build/en/stable/resources/
        #   define-metadata.html#preprocess-selectors
        re.sub(r"# \[.*\n", "\n", _)
        for _ in txt.split("\n") if "{%" not in _
    ])
    txt3 = re.sub(r"(?P<name>\{\{.*?\}\})", '"\\g<name>"', txt2)
    return yaml.safe_load(txt3)


class CondaRecipe(ProjectSpec):
    """Recipe package"""

    def match(self) -> bool:
        allfiles = self.root.filelist
        basenames = {_.rsplit('/', 1)[-1] for _ in allfiles}
        return {"meta.yaml", "meta.yml", "conda.yaml"}.intersection(basenames)

    def parse(self) -> None:
        from projspec.content.environment import Environment, Stack, Precision
        from projspec.artifact.installable import CondaPackage
        allfiles = self.root.filelist
        basenames = {_.rsplit('/', 1)[-1]: _ for _ in allfiles}
        meta = None
        for fn in ("meta.yaml", "meta.yml", "conda.yaml"):
            if fn in basenames:
                try:
                    with self.root.fs.open(basenames[fn], "rb") as f:
                        meta0 = _yaml_no_jinja(f)
                    if "package" in meta0:
                        meta = meta0
                except (IOError, ValueError, UnicodeDecodeError):
                    pass
        if meta is None:
            raise ValueError
        cont = AttrDict()
        art = CondaPackage(proj=self.root, cmd=["conda-build", self.root.url])
        self._artifacts = AttrDict(conda_package=art)
        self._contents = AttrDict(environment=AttrDict({k: Environment(proj=self.root, artifacts={art}, packages=v, stack=Stack.CONDA, precision=Precision.SPEC)
                                      for k, v  in meta["requirements"].items()}))




class RattlerRecipe(CondaRecipe):
    # all conda recipes are also valid for rattler
    # or we may later add both rattler and conda as artefacts to CondaRecipe
    # and keep this one explicitly for rattler-build

    def match(self) -> bool:
        allfiles = self.root.filelist
        basenames = {_.rsplit('/', 1)[-1] for _ in allfiles}
        return "recipe.yaml" in basenames

    def parse(self) -> None:
        allfiles = self.root.filelist
        basenames = {_.rsplit('/', 1)[-1]: _ for _ in allfiles}
        meta = None
        if "recipe.yaml" in basenames:
            try:
                with self.root.fs.open(basenames["recipe.yaml"], "rb") as f:
                    meta = _yaml_no_jinja(f)
            except (IOError, ValueError, UnicodeDecodeError):
                pass
        if "outputs" not in meta or all("package" not in _ for _ in meta["outputs"]):
            raise ValueError
        return False

