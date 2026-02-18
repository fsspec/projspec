from projspec.proj import ProjectSpec, ParseFailed, ProjectExtra


class DataPackage(ProjectSpec):
    # by frictionless data

    spec_doc = "https://datapackage.org/standard/data-package/#structure"
    # e.g., as exported by zenodo
    # only tabular data; docs suggest csv, xls, json filetypes; JSON
    # can be inline in the metadata. sqlite and yaml are also mentioned.

    def match(self) -> bool:
        return "datapackage.json" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content import DescriptiveMetadata, License, FrictionlessData

        import json

        with self.proj.fs.open(self.proj.basenames["datapackage.json"], "rt") as f:
            conf = json.load(f)
        self.contents["descriptive_metadata"] = DescriptiveMetadata(
            proj=self.proj,
            meta={
                k: v for k, v in conf.items() if k in {"name", "title", "description"}
            },
            artifacts=set(),
        )
        if "licenses" in conf:
            lic = conf["licenses"][0]
            self.contents["license"] = License(
                proj=self.proj,
                shortname=lic["name"],
                url=lic.get("path"),
                artifacts=set(),
            )
        if "resources" in conf:
            self.contents["frictionless_data"] = [
                FrictionlessData(
                    proj=self.proj,
                    name=_["name"],
                    schema=_.get("schema", {}),
                    artifacts=set(),
                )
                for _ in conf["resources"]
            ]


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
        # The `dvc` CLI has many possible actions


class IntakeCatalog(ProjectExtra):
    spec_doc = (
        "https://intake.readthedocs.io/en/latest/api2.html#intake.readers.entry.Catalog"
    )

    def match(self) -> bool:
        return "catalog.yaml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.data import IntakeSource

        import yaml

        with self.proj.fs.open(self.proj.basenames["catalog.yaml"], "rt") as f:
            meta = yaml.safe_load(f)

        if not "entries" in meta:
            raise ParseFailed("No entries found in catalog")

        if meta.get("version") == 2:
            self.contents["intake_source"] = [
                IntakeSource(proj=self.proj, name=_, artifacts=set())
                for _ in meta.get("entries", [])
            ]
        else:
            self.contents["intake_source"] = [
                IntakeSource(proj=self.proj, name=_, artifacts=set())
                for _ in meta.get("sources", [])
            ]
