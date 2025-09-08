"""Contents specifying datasets"""

from projspec.content import BaseContent


class FrictionlessData(BaseContent):
    """A datapackage spec, as defined by frictionlessdata

    This lists loadable tabular files with defined schema, typically from formats such as
    JSON, CSV, and parquet.

    See https://specs.frictionlessdata.io/data-package/
    """

    # typically in a datapackage.json spec


class IntakeCatalog(BaseContent):
    """A catalog of data assets, including basic properties (location) and how to load/process them.

    See https://intake.readthedocs.io/en/latest/
    """

    # typically in a catalog.yaml free-floating file
