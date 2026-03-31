import re

from projspec.proj import ProjectSpec
from projspec.proj.base import ParseFailed
from projspec.utils import AttrDict


class Golang(ProjectSpec):
    """A Go module project, identified by the presence of a go.mod file."""

    spec_doc = "https://go.dev/doc/modules/gomod-ref"

    def match(self) -> bool:
        return "go.mod" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Process
        from projspec.content.metadata import DescriptiveMetadata

        try:
            with self.proj.fs.open(self.proj.basenames["go.mod"], "rb") as f:
                text = f.read().decode()
        except OSError as exc:
            raise ParseFailed(f"Could not read go.mod: {exc}") from exc

        # ------------------------------------------------------------------ #
        # Parse go.mod directives with simple regex — avoids a Go dependency
        # ------------------------------------------------------------------ #
        # module path: "module example.com/mymodule"
        module_match = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
        module_path = module_match.group(1) if module_match else ""

        # minimum Go version: "go 1.21"
        go_ver_match = re.search(r"^go\s+(\S+)", text, re.MULTILINE)
        go_version = go_ver_match.group(1) if go_ver_match else ""

        # require directives — both single-line and block forms
        #   require example.com/foo v1.2.3
        #   require ( example.com/foo v1.2.3 // indirect )
        requires: list[str] = re.findall(
            r"^\s+?(\S+)\s+(\S+?)(?:\s*//.*)?$",
            # extract the body of require blocks
            "\n".join(
                "\n".join(block.splitlines())
                for block in re.findall(
                    r"^require\s*\(([^)]*)\)", text, re.MULTILINE | re.DOTALL
                )
            ),
            re.MULTILINE,
        )
        # Also catch single-line: "require example.com/foo v1.2.3"
        single_requires: list[tuple[str, str]] = re.findall(
            r"^require\s+(\S+)\s+(\S+)", text, re.MULTILINE
        )
        all_deps = [f"{mod} {ver}" for mod, ver in (requires + single_requires)]

        # ------------------------------------------------------------------ #
        # Contents
        # ------------------------------------------------------------------ #
        meta: dict[str, str] = {}
        if module_path:
            meta["module"] = module_path
        if go_version:
            meta["go"] = go_version

        self._contents = AttrDict(
            descriptive_metadata=DescriptiveMetadata(proj=self.proj, meta=meta)
        )

        # ------------------------------------------------------------------ #
        # Artifacts
        # ------------------------------------------------------------------ #
        arts = AttrDict()

        # go build ./... — compiles all packages; output depends on module layout
        arts["build"] = Process(
            proj=self.proj,
            cmd=["go", "build", "./..."],
        )

        # go test ./... — runs all tests
        arts["test"] = Process(
            proj=self.proj,
            cmd=["go", "test", "./..."],
        )

        # If there is a cmd/ subdirectory the convention is one binary per sub-package.
        # We model the whole tree as a single FileArtifact since we don't walk the tree.
        if self.proj.fs.isdir(f"{self.proj.url}/cmd"):
            arts["binary"] = FileArtifact(
                proj=self.proj,
                cmd=["go", "build", "-o", "bin/", "./cmd/..."],
                fn=f"{self.proj.url}/bin/*",
            )

        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        # https://go.dev/doc/tutorial/getting-started
        with open(f"{path}/go.mod", "w") as f:
            f.write("module example.com/hello")
        with open(f"{path}/hello.go", "w") as f:
            f.write(
                """package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
"""
            )
