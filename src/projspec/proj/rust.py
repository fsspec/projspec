import toml
from projspec.proj import ProjectSpec, PythonLibrary


class Rust(ProjectSpec):
    """A directory, which can build a binary executable or library with Cargo."""

    spec_doc = "https://doc.rust-lang.org/cargo/reference/manifest.html"

    def match(self) -> bool:
        return "Cargo.toml" in self.proj.basenames

    def parse(self):
        from projspec.content.metadata import DescriptiveMetadata

        with self.proj.fs.open(f"{self.proj.url}/Cargo.toml", "rt") as f:
            meta = toml.load(f)
        self.contents["desciptive_metadata"] = DescriptiveMetadata(
            proj=self.proj, meta=meta["package"], artifacts=set()
        )
        1


class RustPython(Rust, PythonLibrary):
    """A rust project designed for importing with python, perhaps with mixed rust/python code trees.

    This version assumes the build tool is ``maturin``, which may not be the only possibility.
    """

    spec_doc = "https://www.maturin.rs/config.html"

    def match(self) -> bool:
        # The second condition here is not necessarily required, it is enough to
        # have a python package directory with the same name as the rust library.

        # You can also have metadata.maturin in the Cargo.toml
        return (
            Rust.match(self)
            and "maturin" in self.proj.pyproject.get("tool", {})
            and self.proj.pyproject.get("build-backend", "") == "maturin"
        )

    # this builds a python-installable wheel in addition to rust artifacts.
