from projspec.proj import ProjectSpec


class Briefcase(ProjectSpec):
    spec_doc = "https://briefcase.readthedocs.io/en/stable/reference/configuration.html"

    def match(self) -> bool:
        return "briefcase" in self.proj.pyproject.get("tool", {})
