from projspec.proj.base import ProjectSpec
from projspec.utils import AttrDict


class NodeProject(ProjectSpec):
    """Node.js project
    """

    def match(self):
        contents = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in contents}
        return "package.json" in basenames

    def parse(self):
        self._contents = AttrDict()
        self._artifacts = AttrDict()
