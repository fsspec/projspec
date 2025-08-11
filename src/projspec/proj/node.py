from projspec.proj.base import ProjectSpec


class Node(ProjectSpec):
    """Node.js project"""

    spec_doc = "https://docs.npmjs.com/cli/v11/configuring-npm/package-json"

    def match(self):
        return "package.json" in self.proj.basenames

    def parse(self):
        import json

        with self.proj.fs.open(f"{self.proj.url}/package.json", "rt") as f:
            json.load(f)
