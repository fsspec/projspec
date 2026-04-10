import yaml

from projspec.proj.base import ProjectExtra


class Cited(ProjectExtra):
    """A github-specified format to say how this project should be cited."""

    spec_doc = "https://citation-file-format.github.io/"

    def match(self):
        return "CITATION.cff" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.metadata import Citation

        with self.proj.fs.open(self.proj.basenames["CITATION.cff"], "rt") as f:
            meta = yaml.safe_load(f)
        self.contents["descriptive_metadata"] = Citation(proj=self.proj, meta=meta)


class Zenodo(ProjectExtra):
    """This project has been published on Zenodo"""

    spec_doc = "https://help.zenodo.org/docs/github/describe-software/zenodo-json/"

    def match(self):
        # NB: zenodo picks up CITATION.cff too, but this format is more specific
        return ".zenodo.json" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.metadata import Citation

        with self.proj.fs.open(self.proj.basenames[".zenodo.json"], "rt") as f:
            meta = yaml.safe_load(f)
        # TODO: extract known contents such as license.
        self.contents["descriptive_metadata"] = Citation(proj=self.proj, meta=meta)
