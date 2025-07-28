from projspec.proj.base import ProjectSpec


class NodeProject(ProjectSpec):
    """Node.js project"""

    spec_doc = "https://docs.npmjs.com/cli/v11/configuring-npm/package-json"

    def match(self):
        contents = self.root.filelist
        basenames = {_.rsplit("/", 1)[-1]: _ for _ in contents}
        return "package.json" in basenames

    def parse(self):
        import json

        with self.root.fs.open(f"{self.root.url}/package.json", "rt") as f:
            json.load(f)
