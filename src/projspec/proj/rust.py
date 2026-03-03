import subprocess

import toml
from projspec.proj import ProjectSpec, PythonLibrary


class Rust(ProjectSpec):
    """A directory, which can build a binary executable or library with Cargo."""

    spec_doc = "https://doc.rust-lang.org/cargo/reference/manifest.html"

    def match(self) -> bool:
        return "Cargo.toml" in self.proj.basenames

    def parse(self):
        from projspec.content.metadata import DescriptiveMetadata
        from projspec.artifact.base import FileArtifact

        with self.proj.fs.open(f"{self.proj.url}/Cargo.toml", "rt") as f:
            meta = toml.load(f)
        self.contents["desciptive_metadata"] = DescriptiveMetadata(
            proj=self.proj, meta=meta.get("package")
        )
        self.artifacts["binary"]["debug"] = FileArtifact(
            proj=self.proj,
            cmd=["cargo", "build"],
            # extension is platform specific
            fn=f"{self.proj.url}/target/debug/{meta['package']['name']}.*",
        )
        self.artifacts["binary"]["release"] = FileArtifact(
            proj=self.proj,
            cmd=["cargo", "build", "--release"],
            # extension is platform specific
            fn=f"{self.proj.url}/target/release/{meta['package']['name']}.*",
        )

    @staticmethod
    def _create(path: str) -> None:
        subprocess.check_call(["cargo", "init"], cwd=path)


class RustPython(Rust, PythonLibrary):
    """A rust project designed for importing with python, perhaps with mixed rust/python code trees.

    This version assumes the build tool is ``maturin``, which may not be the only possibility.
    """

    spec_doc = "https://www.maturin.rs/config.html"

    def match(self) -> bool:
        # The second condition here is not necessarily required, it is enough to
        # have a python package directory with the same name as the rust library.

        # You can also have metadata.maturin in the Cargo.toml
        return Rust.match(self) and (
            "maturin" in self.proj.pyproject.get("tool", {})
            or self.proj.pyproject.get("build-system", {}).get("build-backend", "")
            == "maturin"
        )

    def parse(self):
        super().parse()
        Rust.parse(self)

    @staticmethod
    def _create(path: str) -> None:
        # will fail for existing python libraries, since it doesn't want to edit
        # the pyproject.toml build backend.
        subprocess.check_call(["maturin", "init", "-b", "pyo3", "--mixed"], cwd=path)
