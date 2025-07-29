import re

from projspec.proj import ProjectSpec


class MDBook(ProjectSpec):
    spec_doc = (
        "https://rust-lang.github.io/mdBook/format/configuration/index.html"
    )

    def match(self) -> bool:
        return "book.toml" in self.root.basenames


class RTD(ProjectSpec):
    spec_doc = (
        "https://docs.readthedocs.com/platform/stable/config-file/v2.html"
    )

    def match(self) -> bool:
        return any(
            re.match("[.]?readthedocs.y[a]?ml", _) for _ in self.root.basenames
        )

    def parse(self) -> None:
        # supports mkdocs and sphinx builders
        # build env usually in `python.install[*].requirements`, which can
        # point to a requirements.txt or conda.environment for conda env.
        pass
