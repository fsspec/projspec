from projspec.proj.base import ProjectSpec


class Node(ProjectSpec):
    """Node.js project"""

    spec_doc = "https://docs.npmjs.com/cli/v11/configuring-npm/package-json"

    def match(self):
        return "package.json" in self.root.basenames

    def parse(self):
        import json

        with self.root.fs.open(f"{self.root.url}/package.json", "rt") as f:
            json.load(f)
