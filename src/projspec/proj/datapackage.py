from projspec.proj import ProjectSpec


class DataPackage(ProjectSpec):
    # by frictionless data

    spec_doc = "https://datapackage.org/standard/data-package/#structure"
    # e.g., as exported by zenodo
    # only tabular data; docs suggest csv, xls, json filetypes; JSON
    # can be inline in the metadata. sqlite and yaml are also mentioned.

    def match(self) -> bool:
        return "datapackage.json" in self.proj.basenames

    # pythonic API
    # https://framework.frictionlessdata.io/docs/framework/actions.html


class DVCRepo(ProjectSpec):
    """Git management of data assets within a repo"""

    spec_doc = "https://doc.dvc.org/command-reference/config"

    def match(self) -> bool:
        return ".dvc" in self.proj.basenames

    def parse(self) -> None:
        import configparser

        conf = {}
        for fn in ["config", "config.local"]:
            # latter config wins, if both exist
            parser = configparser.ConfigParser()
            try:
                with self.proj.fs.open(f"{self.proj.url}/.dvc/{fn}", "rt") as f:
                    parser.read_file(f)
                    conf.update(parser._sections)
            except (IOError, ValueError):
                pass
        self.contents["remotes"] = [
            _.split(" ", 1)[1][1:-2] for _ in conf if _.startswith("'remote ")
        ]
