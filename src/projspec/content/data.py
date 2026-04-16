"""Contents specifying datasets"""

from dataclasses import dataclass, field

from projspec.content import BaseContent


@dataclass
class TabularData(BaseContent):
    """A tabular dataset, columns and rows

    This lists loadable tabular files with defined schema, typically from formats such as
    JSON, CSV, and parquet.
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
    recognised on-disk layout.

    The `path` field is a human-readable basename that identifies the resource:

    - Single file: `"data.csv"`
    - Multi-file series: `"part*.parquet"` (glob-style, common prefix + `*` + ext)
    - Directory-as-dataset (Hive partition, Zarr store, …): `"year=2024/"`

    The `modality` field classifies the broad nature of the data using the
    vocabulary established by intake's `structure` tags and napari's layer
    type system:

    - `"tabular"`    — row/column data (CSV, Parquet, ORC, Excel, …)
    - `"array"`      — N-dimensional arrays (NumPy, HDF5, NetCDF, Zarr, …)
    - `"image"`      — 2-D/3-D images (PNG, JPEG, TIFF, DICOM, NIfTI, …)
    - `"timeseries"` — time-indexed signals (WAV, GRIB, …)
    - `"geospatial"` — vector/raster geodata (Shapefile, GeoJSON, GeoTIFF, …)
    - `"model"`      — ML model weights (GGUF, SafeTensors, PyTorch, …)
    - `"nested"`     — hierarchical / JSON-like (Avro, YAML, XML, …)
    - `"document"`   — human-readable documents (PDF, DOCX, …)
    - `"video"`      — video streams (MP4, AVI, …)
    - `"archive"`    — compressed bundles (ZIP, tar.gz, …)
    - `""`           — unknown / mixed

    The `schema` field is format-specific:

    - Tabular (Parquet, Arrow, CSV, …): `{column_name: dtype_str, …}`
    - Image / array: `{"width": int, "height": int, "channels": int, "mode": str}`
    - Audio: `{"sample_rate": int, "channels": int, "frames": int}`
    - HDF5 / Zarr / NetCDF: `{"variables": [...], "dims": {...}, "attrs": {...}}`
    - Unknown / library not available: `{}`
    """

    path: str  # basename (or glob pattern / dir/ ) identifying this resource
    format: str  # canonical format string, e.g. "parquet", "csv", "png", "hdf5"
    modality: str = ""  # broad data nature; see docstring for vocabulary
    layout: str = ""  # "flat"|"hive"|"iceberg"|"delta"|"zarr_store"|"tiledarray"|""
    file_count: int = 0
    total_size: int = 0  # bytes; 0 when unknown (e.g. remote FS without size info)
    schema: dict | list = field(default_factory=dict)
    # full path to one representative file, for use by preview loaders
    sample_path: str = ""
    metadata: dict = field(default_factory=dict)  # catch-all extras
    _html = None

    def __repr__(self) -> str:
        from projspec.content.data_html import repr_text

        return repr_text(self)

    def _repr_html_(self) -> str:
        """Jupyter rich display — returns cached HTML, rendering on first call."""
        if self._html is None:
            from projspec.content.data_html import repr_html

            self._html = repr_html(self)
        return self._html

    def to_dict(self, compact=False):
        d = super().to_dict(compact=compact)
        if not compact:
            d["_html"] = self._repr_html_()
        return d
