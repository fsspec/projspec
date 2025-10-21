import re

from projspec.proj import ProjectSpec


class MDBook(ProjectSpec):
    """mdBook is a command line tool to create books with Markdown.

    mdBook is used by the Rust programming language project, and The Rust Programming Language book
    is an example.
    """

    # to get generated docs output for a rust lib, use `rustdoc`
    # https://doc.rust-lang.org/rustdoc/what-is-rustdoc.html

    spec_doc = "https://rust-lang.github.io/mdBook/format/configuration/index.html"

    def match(self) -> bool:
        return "book.toml" in self.proj.basenames


class RTD(ProjectSpec):
    """Documentation to be processes by ReadTheDocs

    RTD is commonly used by open-source python projects and others. Documentation is
    typically built automatically from github repos using sphinx or mkdocs.

    General description of the platform: https://docs.readthedocs.com/platform/stable/
    """

    spec_doc = "https://docs.readthedocs.com/platform/stable/config-file/v2.html"

    def match(self) -> bool:
        return any(re.match("[.]?readthedocs.y[a]?ml", _) for _ in self.proj.basenames)

    def parse(self) -> None:
        # supports mkdocs and sphinx builders
        # build env usually in `python.install[*].requirements`, which can
        # point to a requirements.txt or environment.yaml for conda env.

        # Artifact of HTML output. Classically with `make html` (in docs/ unless otherwise
        # specified), and the output goes into docs/build/html unless the conf.py file says different.
        # RTD actually does
        # > python -m sphinx -T -W --keep-going -b html -d _build/doctrees -D language=en . $READTHEDOCS_OUTPUT/html
        pass
