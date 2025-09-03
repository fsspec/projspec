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
