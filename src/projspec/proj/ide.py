"""Code project container config within IDEs"""

from projspec.proj import ProjectSpec


class NvidiaAIWorkbench(ProjectSpec):
    spec_doc = (
        "https://docs.nvidia.com/ai-workbench/user-guide/latest/projects/spec.html"
    )

    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.project/spec.yaml")

    def parse(self) -> None:
        ...


class JetbrainsIDE(ProjectSpec):
    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.idea")

    def parse(self) -> None:
        ...


class VSCode(ProjectSpec):
    spec_doc = (
        "https://code.visualstudio.com/docs/configure/settings#_settings-json-file"
    )

    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.vscode/settings.json")

    def parse(self) -> None:
        ...


class Zed(ProjectSpec):
    spec_doc = "https://zed.dev/docs/configuring-zed#settings"

    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.zed/settings.json")

    def parse(self) -> None:
        ...
