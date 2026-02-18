"""Contents specifying datasets"""
from dataclasses import dataclass, field

from projspec.content import BaseContent


@dataclass
class FrictionlessData(BaseContent):
    """A datapackage spec, as defined by frictionlessdata

    This lists loadable tabular files with defined schema, typically from formats such as
    JSON, CSV, and parquet.

    See https://specs.frictionlessdata.io/data-package/
    """

    name: str
    schema: dict = field(default_factory=dict)


@dataclass
class IntakeSource(BaseContent):
    """A catalog of data assets, including basic properties (location) and how to load/process them.

    See https://intake.readthedocs.io/en/latest/
    """

    # TODO: add better fields: args, driver/reader, metadata, description
    name: str
