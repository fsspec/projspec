from projspec.proj import ProjectSpec
from projspec.utils import AttrDict, _yaml_no_jinja

# lockfile format is as produced by conda-lock
# https://github.com/conda/conda-lock


class CondaProject(ProjectSpec):
    # not a spec, but a howto:
    spec_doc = "https://conda-incubator.github.io/conda-project/tutorial.html"

    def match(self) -> bool:
        # TODO: a .condarc or environment.yml file is actually enough, e.g.,
        #  https://github.com/conda-incubator/conda-project/tree/main/examples/condarc-settings
        #  but we could argue that such are not really _useful_ projects; but can you
        #  ever see a .condarc otherwise?
        # $ conda-project.yml
        # name: learn-cp
        #   environments:
        #     default:
        #     - environment.yml
        # variables: {}
        # commands: {}

        basenames = {_.rsplit("/", 1)[-1] for _ in self.root.filelist}
        return not basenames.isdisjoint(
            {"conda-project.yml", "conda-meta.yaml"}
        )

    def parse(self) -> None:
        cont = AttrDict()
        arts = AttrDict()
        try:
            with self.root.fs.open(f"{self.root.url}/conda-project.yml") as f:
                meta = _yaml_no_jinja(f)
        except FileNotFoundError:
            with self.root.fs.open(f"{self.root.url}/conda-project.yaml") as f:
                meta = _yaml_no_jinja(f)

        # lockfiles are called "conda-lock.<env_name>.yml"
        # envs live in ./envs/<env_name/

        self._contents = cont
        self._artifacts = arts
