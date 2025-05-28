from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict


class NodeProject(ProjectSpec):
    """UV-runnable project

    Note: uv can run any python project, but this tests for uv-specific
    config. See also ``projspec.deploty.python.UVRunner``.
    """

    def match(self):
        contents = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in contents}
        return "package.json" in basenames

    def parse(self) -> AttrDict:
        self._contents = AttrDict()
        self._artifacts = AttrDict()
