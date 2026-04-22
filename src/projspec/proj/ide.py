"""Code project container config within IDEs"""
from projspec.artifact import BaseArtifact
from projspec.proj import ProjectSpec


class NvidiaAIWorkbench(ProjectSpec):
    spec_doc = (
        "https://docs.nvidia.com/ai-workbench/user-guide/latest/projects/spec.html"
    )

    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.project/spec.yaml")

    def parse(self) -> None:
        from projspec.artifact.process import Process

        # "opens" the project in the sense that it is set as the current context.
        # Editing still happens in jupyter/vscode/etc
        self.artifacts["set_project"] = Process(
            self.proj, cmd=["nvwb", "open", self.proj.url]
        )

    # create:
    # https://docs.nvidia.com/ai-workbench/user-guide/latest/reference/user-interface/cli.html#create-project


class JetbrainsIDE(ProjectSpec):
    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.idea")

    def parse(self) -> None:
        from projspec.artifact.process import Process

        self.artifacts["launch"] = Process(
            self.proj, cmd=["pycharm", ".", "nosplash", "dontReopenProjects"]
        )


class VSCode(ProjectSpec):
    spec_doc = (
        "https://code.visualstudio.com/docs/configure/settings#_settings-json-file"
    )

    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.vscode/settings.json")

    def parse(self) -> None:
        from projspec.artifact.process import Process

        self.artifacts["launch"] = Process(self.proj, cmd=["code", "."])


class Zed(ProjectSpec):
    spec_doc = "https://zed.dev/docs/configuring-zed#settings"

    def match(self) -> bool:
        return self.proj.fs.exists(f"{self.proj.url}/.zed/settings.json")

    def parse(self) -> None:
        from projspec.artifact.process import Process

        self.artifacts["launch"] = Process(self.proj, cmd=["zed", "."])
