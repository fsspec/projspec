from projspec.proj.base import ProjectSpec


class AIEnabled(ProjectSpec):
    """This project has text files intended for LLM/AI to read."""

    spec_doc = "https://agents.md/"

    def match(self) -> bool:
        return bool(
            {"AGENTS.md", "CLAUDE.md", ".specify"}.intersection(self.proj.basenames)
        )

    def parse(self) -> None:
        pass
