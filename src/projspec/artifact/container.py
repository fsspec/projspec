import subprocess

from projspec.proj.base import Project, ProjectExtra
from projspec.artifact import BaseArtifact


class DockerImage(BaseArtifact):
    def __init__(self, proj: Project, cmd=None, tag=None):
        if tag:
            cmd = ["docker", "build", ".", "-t", tag]
        else:
            cmd = ["docker", "build", "."]
        self.tag = tag
        super().__init__(proj, cmd=cmd)


class DockerRuntime(DockerImage):
    # Note: there are many optional arguments to docker; we could surface the most common
    #  ones (-it, -d, -p). This does the simplest thing.

    def _make(self, *args, **kwargs) -> None:
        """

        :param args: added to the docker run command
        :param kwargs: affect the docker run subprocess call
        """
        out = subprocess.check_output(self.cmd, cwd=self.proj.url, **kwargs)
        if self.tag:
            subprocess.check_call(["docker", "run", self.tag])
        else:
            lines = [
                l for l in out.splitlines() if l.startswith(b"Successfully built ")
            ]
            img = lines[-1].split()[-1]
            subprocess.check_call(
                ["docker", "run", img.decode()] + list(args), **kwargs
            )


class Docker(ProjectExtra):
    def match(self):
        return "Dockerfile" in self.proj.basenames

    def parse(self) -> None:
        self._artifacts["docker_image"] = DockerImage(self.proj)
        self._artifacts["docker_runtime"] = DockerRuntime(self.proj)
