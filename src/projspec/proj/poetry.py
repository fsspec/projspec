from projspec.proj import ProjectSpec


class PoetryProject(ProjectSpec):
    spec_doc = "https://python-poetry.org/docs/pyproject/"

    def match(self) -> bool:
        return "poetry" in self.root.metadata.get("tool")
