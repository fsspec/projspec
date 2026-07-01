import re

from projspec.proj import ProjectSpec, ParseFailed, ProjectExtra


class DataPackage(ProjectSpec):
    """A FrictionlessData datapackage spec"""

    icon = "📊"
    spec_doc = "https://datapackage.org/standard/data-package/#structure"
    # e.g., as exported by zenodo
    # only tabular data; docs suggest csv, xls, json filetypes; JSON
    # can be inline in the metadata. sqlite and yaml are also mentioned.

    def match(self) -> bool:
        return "datapackage.json" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content import DescriptiveMetadata, License, TabularData

        import json

        with self.proj.fs.open(self.proj.basenames["datapackage.json"], "rt") as f:
            conf = json.load(f)
        self.contents["descriptive_metadata"] = DescriptiveMetadata(
            proj=self.proj,
            meta={
                k: v for k, v in conf.items() if k in {"name", "title", "description"}
            },
        )
        if "licenses" in conf:
            lic = conf["licenses"][0]
            self.contents["license"] = License(
                proj=self.proj,
                shortname=lic["name"],
                url=lic.get("path"),
            )
        if "resources" in conf:
            self.contents["frictionless_data"] = [
                TabularData(
                    proj=self.proj,
                    name=_["name"],
                    schema=_.get("schema", {}),
                )
                for _ in conf["resources"]
            ]

    @staticmethod
    def _create(path: str) -> None:
        with open(path + "/datapackage.json", "wt") as f:
            # https://github.com/frictionlessdata/examples/tree/main/text-file
            f.write(
                """
            {
              "name": "text-file",
              "title": "Text File Data Package",
              "description": "An example of a text file in a non-tabular data package",
              "licenses": [{
                "name": "CC0-1.0",
                "path": "https://creativecommons.org/publicdomain/zero/1.0/"
              }],
              "resources": [{
                "name": "text-file",
                "path": "text-file.txt",
                "title": "Text File Data Resource",
                "format": "txt"
              }]
            }
            """
            )


class DVCRepo(ProjectSpec):
    """Git management of data assets within a repo"""

    icon = "🌿"
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
    icon = "📖"
    spec_doc = (
        "https://intake.readthedocs.io/en/latest/api2.html#intake.readers.entry.Catalog"
    )
    template = re.compile(r"^cat(alog)?\.y[a]?ml$")
    match: str

    def match(self) -> bool:
        matches = [_ for _ in self.proj.basenames if self.template.match(_)]
        if matches:
            self.match = matches[0]
            return True
        return False

    def parse(self) -> None:
        from projspec.content.data import IntakeSource

        import yaml

        with self.proj.fs.open(self.proj.basenames[self.match], "rt") as f:
            meta = yaml.safe_load(f)

        if "entries" not in meta and "sources" not in meta:
            raise ParseFailed("No entries found in catalog")

        if meta.get("version") == 2:
            self.contents["intake_source"] = [
                IntakeSource(proj=self.proj, name=_) for _ in meta.get("entries", [])
            ]
        else:
            self.contents["intake_source"] = [
                IntakeSource(proj=self.proj, name=_) for _ in meta.get("sources", [])
            ]

    @staticmethod
    def _create(path: str) -> None:
        with open(f"{path}/catalog.yaml", "w") as f:
            # doesn't actually create data
            f.write(
                """
            aliases: {}
            data:
              35b33d80d511b79c:
                datatype: intake.readers.datatypes:Text
                kwargs:
                  storage_options: null
                  url: text-file.txt
                metadata: {}
                user_parameters: {}
            entries:
              text:
                kwargs:
                  data: '{data(35b33d80d511b79c)}'
                metadata: {}
                output_instance: builtins:str
                reader: intake.readers.readers:FileTextReader
                user_parameters: {}
            metadata: {}
            user_parameters: {}
            version: 2
            """
            )


class CroissantDataset(ProjectSpec):
    """An ML Commons Croissant dataset described by a JSON-LD metadata file.

    Croissant (http://mlcommons.org/croissant/1.0) is the standard format for
    describing ML datasets using JSON-LD / schema.org vocabulary.  It captures
    dataset-level metadata (name, description, license, citation) as well as a
    structured schema of the data via ``RecordSet`` and ``Field`` objects.

    Detection heuristic
    -------------------
    1. Look for any ``.json`` / ``.jsonld`` file whose **basename** matches a
       list of common Croissant filenames (``croissant.json``,
       ``croissant_metadata.json``, ``metadata.json``, …).
    2. Open the candidate file and confirm it carries the Croissant conformance
       marker (``conformsTo`` containing ``mlcommons.org/croissant`` or a
       ``@context`` that maps ``cr`` / ``mlcommons``).

    No file I/O other than reading the single metadata file is needed, so this
    parser is compatible with remote filesystems.
    """

    icon = "🥐"
    spec_doc = "https://docs.mlcommons.org/croissant/docs/croissant-spec.html"

    # Filename matched during match(); reused in parse() to avoid re-scanning.
    _matched_file: str | None = None
    _CROISSANT_NAMES = re.compile(
        r"^(croissant.*|.*[-_]?croissant[-_]?.*|metadata)\.json(ld)?$",
        re.IGNORECASE,
    )
    _CROISSANT_CONFORMSTO = "mlcommons.org/croissant"

    def match(self) -> bool:
        """Return True when a plausible Croissant JSON-LD file is present."""
        for basename in self.proj.basenames:
            if self._CROISSANT_NAMES.match(basename):
                # Peek at the file to confirm it is really Croissant.
                # We use get_file() so the content may already be cached.
                try:
                    fobj = self.proj.get_file(basename, text=True)
                    if fobj is None:
                        continue
                    text = fobj.read()
                    if self._CROISSANT_CONFORMSTO in text:
                        self._matched_file = basename
                        return True
                except Exception:
                    continue
        return False

    def parse(self) -> None:
        import json

        from projspec.content import (
            CroissantRecordSet,
            DescriptiveMetadata,
            License,
            Citation,
        )
        from projspec.utils import AttrDict

        if self._matched_file is None:
            raise ParseFailed("No Croissant file identified")

        self._contents = AttrDict()
        self._artifacts = AttrDict()

        with self.get_file(self._matched_file, text=True) as f:
            meta = json.load(f)

        # --- dataset-level metadata ---
        dm_fields = {
            "name",
            "description",
            "url",
            "version",
            "datePublished",
            "dateCreated",
            "dateModified",
            "keywords",
            "inLanguage",
        }
        self._contents["descriptive_metadata"] = DescriptiveMetadata(
            proj=self.proj,
            meta={k: str(v) for k, v in meta.items() if k in dm_fields and v},
        )

        # --- license ---
        lic_raw = meta.get("license")
        if lic_raw:
            # license may be a string URL or a dict with @id / name
            if isinstance(lic_raw, str):
                self._contents["license"] = License(
                    proj=self.proj, shortname=lic_raw, url=lic_raw
                )
            elif isinstance(lic_raw, dict):
                self._contents["license"] = License(
                    proj=self.proj,
                    shortname=lic_raw.get("name", lic_raw.get("@id", "")),
                    url=lic_raw.get("@id", lic_raw.get("url", "")),
                )

        # --- citation ---
        cite_raw = meta.get("citeAs") or meta.get("citation")
        if cite_raw:
            self._contents["citation"] = Citation(
                proj=self.proj,
                meta={"citeAs": cite_raw} if isinstance(cite_raw, str) else cite_raw,
            )

        # --- record sets ---
        record_sets_raw = meta.get("recordSet") or meta.get("cr:recordSet") or []
        if isinstance(record_sets_raw, dict):
            record_sets_raw = [record_sets_raw]

        record_sets = {}
        for rs in record_sets_raw:
            rs_id = rs.get("name") or rs.get("@id", "")
            description = rs.get("description", "")
            fields_raw = rs.get("field") or rs.get("cr:field") or []
            if isinstance(fields_raw, dict):
                fields_raw = [fields_raw]
            field_names = [
                f.get("name") or f.get("@id", "")
                for f in fields_raw
                if isinstance(f, dict)
            ]
            record_sets[rs_id] = CroissantRecordSet(
                proj=self.proj,
                name=rs_id,
                description=description,
                fields=field_names,
            )

        # TODO: file/fileSets, transforms
        if record_sets:
            self._contents["croissant_record_set"] = AttrDict(record_sets)

    @staticmethod
    def _create(path: str) -> None:
        """Write a minimal valid Croissant metadata file."""
        import json

        doc = {
            "@context": {
                "@language": "en",
                "@vocab": "https://schema.org/",
                "cr": "http://mlcommons.org/schema/",
                "dct": "http://purl.org/dc/terms/",
            },
            "@type": "sc:Dataset",
            "name": "my-dataset",
            "description": "A short description of the dataset.",
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "url": "https://example.com/my-dataset",
            "dct:conformsTo": "http://mlcommons.org/croissant/1.0",
            "distribution": [
                {
                    "@type": "cr:FileObject",
                    "@id": "data.csv",
                    "contentUrl": "data.csv",
                    "encodingFormat": "text/csv",
                }
            ],
            "recordSet": [
                {
                    "@type": "cr:RecordSet",
                    "@id": "records",
                    "name": "records",
                    "field": [
                        {
                            "@type": "cr:Field",
                            "@id": "records/id",
                            "name": "id",
                            "dataType": "sc:Integer",
                        },
                        {
                            "@type": "cr:Field",
                            "@id": "records/value",
                            "name": "value",
                            "dataType": "sc:Text",
                        },
                    ],
                }
            ],
        }
        with open(f"{path}/croissant.json", "wt") as f:
            json.dump(doc, f, indent=2)
