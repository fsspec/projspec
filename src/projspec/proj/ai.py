from projspec.proj.base import ProjectFlag


class AIEnabled(ProjectFlag):
    """This project has text files intended for LLM/AI to read."""

    icon = "🤖"
    spec_doc = "https://agents.md/"

    def match(self) -> bool:
        return bool(
            {"AGENTS.md", "CLAUDE.md", ".specify"}.intersection(self.proj.basenames)
        )

    def parse(self) -> None:
        pass
