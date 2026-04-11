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


@dataclass
class DataResource(BaseContent):
    """A data resource found inside a data-only directory.

    Describes one logical dataset — which may be a flat collection of files, a
    Hive-partitioned tree, an Iceberg/Delta table, a Zarr store, or any other
    recognised on-disk layout.  The ``schema`` field is format-specific:

    - Tabular (Parquet, Arrow, CSV, …): ``{column_name: dtype_str, …}``
    - Image collection: ``{"width": int, "height": int, "channels": int, "mode": str}``
    - Audio collection: ``{"sample_rate": int, "channels": int, "frames": int}``
    - HDF5 / Zarr / NetCDF: ``{"variables": [...], "dims": {...}, "attrs": {...}}``
    - Unknown / library not available: ``{}``
    """

    name: str
    format: str  # canonical format string, e.g. "parquet", "csv", "png", "hdf5"
    layout: str = ""  # "flat" | "hive" | "iceberg" | "delta" | "zarr_store" | ""
    file_count: int = 0
    total_size: int = 0  # bytes; 0 when unknown (e.g. remote FS without size info)
    schema: dict | list = field(default_factory=dict)
    sample_paths: list = field(default_factory=list)  # up to 3 representative paths
    metadata: dict = field(default_factory=dict)  # catch-all extras
