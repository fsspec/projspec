import re

import yaml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


def _yaml_no_jinja(fileobj):
    txt = fileobj.read().decode()
    txt2 = "\n".join(
        [
            # removes line-end selectors; we don't attempt to evaluate them
            # https://docs.conda.io/projects/conda-build/en/stable/resources/
            #   define-metadata.html#preprocess-selectors
            re.sub(r"# \[.*\n", "\n", _)
            for _ in txt.split("\n")
            if "{%" not in _
        ]
    )
    txt3 = re.sub(r"(?P<name>\{\{.*?\}\})", '"\\g<name>"', txt2)
    return yaml.safe_load(txt3)


class CondaRecipe(ProjectSpec):
    """Recipe package"""

    def match(self) -> bool:
        allfiles = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1] for _ in allfiles}
        return {"meta.yaml", "meta.yml", "conda.yaml"}.intersection(basenames)

    def parse(self) -> None:
        from projspec.artifact.installable import CondaPackage
        from projspec.content.environment import Environment, Precision, Stack

        allfiles = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in allfiles}
        meta = None
        for fn in ("meta.yaml", "meta.yml", "conda.yaml"):
            if fn in basenames:
                try:
                    with self.root.fs.open(basenames[fn], "rb") as f:
                        meta0 = _yaml_no_jinja(f)
                    # TODO: multiple output recipe
                    if "package" in meta0:
                        meta = meta0
                except (OSError, ValueError, UnicodeDecodeError):
                    pass
        if meta is None:
            raise ValueError
        art = CondaPackage(proj=self.root, cmd=["conda-build", self.root.url])
        self._artifacts = AttrDict(**{meta["package"]["name"]: art})
        self._contents = AttrDict(
            environment=AttrDict(
                {
                    k: Environment(
                        proj=self.root,
                        artifacts={art},
                        packages=v,
                        stack=Stack.CONDA,
                        precision=Precision.SPEC,
                    )
                    for k, v in meta["requirements"].items()
                }
            )
        )


class RattlerRecipe(CondaRecipe):
    # conda recipes are also valid for rattler if they don't havecomplex jinja.

    def match(self) -> bool:
        allfiles = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1] for _ in allfiles}
        return "recipe.yaml" in basenames

    def parse(self) -> None:
        from projspec.artifact.installable import CondaPackage
        from projspec.content.environment import Environment, Precision, Stack

        allfiles = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in allfiles}
        meta = None
        if "recipe.yaml" in basenames:
            try:
                with self.root.fs.open(basenames["recipe.yaml"], "rb") as f:
                    meta = _yaml_no_jinja(f)

            except (OSError, ValueError, UnicodeDecodeError):
                pass
        bits = [_ for _ in [meta] + meta.get("outputs", []) if "package" in _]
        cmd = [
            "rattler-build",
            "build",
            "-r",
            self.root.url,
            "--output-dir",
            f"{self.root.url}/output",
        ]
        for package in bits:
            art = CondaPackage(
                proj=self.root,
                cmd=cmd,
                path=f"{self.root.url}/output/noarch/repodata.json",
            )

        art = CondaPackage(proj=self.root, cmd=["conda-build", self.root.url])
        self._artifacts = AttrDict(conda_package=art)
        self._contents = AttrDict(
            environment=AttrDict(
                {
                    k: Environment(
                        proj=self.root,
                        artifacts={art},
                        packages=v,
                        stack=Stack.CONDA,
                        precision=Precision.SPEC,
                    )
                    for k, v in meta["requirements"].items()
                }
            )
        )
