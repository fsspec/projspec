from projspec.proj import ProjectSpec
from projspec.utils import _yaml_no_jinja


class CondaProject(ProjectSpec):
    spec_doc = "https://conda-incubator.github.io/conda-project/tutorial.html"

    def match(self) -> bool:
        basenames = {_.rsplit("/", 1)[-1] for _ in self.root.filelist}
        return basenames.isdisjoint({"conda-project.yml", "conda-meta.yaml"})

    def parse(self) -> None:
        # just stash for now
        # TODO: a .condarc or environment.yml file is actually enough, e.g.,
        # https://github.com/conda-incubator/conda-project/tree/main/examples/condarc-settings
        # but we could argue that such are not really _useful_ projects
        with self.root.fs.open(f"{self.root.url}/conda-project.yml") as f:
            self.meta = _yaml_no_jinja(f)
