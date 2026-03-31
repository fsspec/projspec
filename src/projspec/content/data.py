"""Contents specifying datasets"""
from dataclasses import dataclass, field

from projspec.content import BaseContent


@dataclass
class TabularData(BaseContent):
    """A tabular dataset, columns and rows

    This lists loadable tabular files with defined schema, typically from formats such as
    JSON, CSV, and parquet.

    See https://specs.frictionlessdata.io/data-package/
    """

    name: str
    metadata: dict = field(default_factory=dict)
    # allowed schema formats:
    #  - dtype-like {fieldname: string-type}
    #  - dtype-complex {fieldname: {...}}
    #  - list like [{name:, ...}]
    # We may choose to normalise to just one of these eventually
    schema: dict | list = field(default_factory=dict)


@dataclass
class IntakeSource(BaseContent):
    """A catalog of data assets, including basic properties (location) and how to load/process them.

    See https://intake.readthedocs.io/en/latest/
    """

    # TODO: add better fields: args, driver/reader, metadata, description
    name: str
