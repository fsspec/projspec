from projspec.proj import ProjectSpec, PythonLibrary


class Rust(ProjectSpec):
    spec_doc = "https://doc.rust-lang.org/cargo/reference/manifest.html"

    def match(self) -> bool:
        return "Cargo.toml" in self.root.basenames

    # this builds a (static) library or an executable, or both.


class RustPython(Rust, PythonLibrary):
    spec_doc = "https://www.maturin.rs/config.html"

    def match(self) -> bool:
        # The second condition here is not necessarily required, it is enough to
        # have a python package directory with the same name as the rust library.
        return (
            Rust.match(self)
            and "maturin" in self.root.pyproject.get("tool", {})
            and self.root.pyproject.get("build-backend", "") == "maturin"
        )

    # this builds a python-installable wheel in addition to rust artifacts.
