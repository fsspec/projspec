from projspec.proj import ProjectSpec


class PoetryProject(ProjectSpec):
    spec_doc = "https://python-poetry.org/docs/pyproject/"

    def match(self) -> bool:
        back = (
            self.root.pyproject.get("build_system", {})
            .get("build-backend", "")
            .startswith("poetry.")
        )
        return "poetry" in self.root.pyproject.get("tool") or back

    def parse(self) -> None:
        # essentially the same as PythonLibrary?
        pass
