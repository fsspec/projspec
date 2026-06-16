"""Content classes describing datasets found within a project.

These describe data assets in a formal way, without loading the data. Most
of them mirror the things that ``intake`` (v2, ``intake.readers``) can tell us
about a URL/glob/list of files via :func:`intake.readers.inspect.inspect_dataset`.
"""

from dataclasses import dataclass, field

from projspec.content import BaseContent


@dataclass
class TabularData(BaseContent):
    """A tabular (columnar) dataset, e.g. CSV/parquet/SQL.

    ``schema`` is a free-form mapping describing the columns; its exact form
    depends on where it was sourced (FrictionlessData resource schema, a
    HuggingFace ``features`` block, or intake's ``datashape``).
    """

    icon = "📊"

    name: str
    schema: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class FrictionlessData(BaseContent):
    """A data resource described by the FrictionlessData standard.

    See https://datapackage.org/standard/data-resource/ .
    """

    icon = "🪪"

    name: str
    schema: dict = field(default_factory=dict)


@dataclass
class IntakeSource(BaseContent):
    """A named entry in an intake catalog."""

    icon = "📖"

    name: str


@dataclass
class Dataset(BaseContent):
    """A generic dataset discovered on disk and described by intake.

    This is produced by :class:`projspec.proj.data_project.DataProject` after
    scanning files/globs with :func:`intake.readers.inspect.inspect_dataset`.

    Attributes
    ----------
    name:
        Short identifying name (usually the consolidated file/glob basename).
    url:
        The URL, glob or list of URLs that make up this dataset, relative to
        (or rooted at) the project directory.
    datatype:
        The intake ``BaseData`` subclass name detected (e.g. ``"CSV"``,
        ``"Parquet"``), or ``None`` if intake could not identify the type.
    structure:
        Structural tags reported by intake (e.g. ``{"table"}``,
        ``{"array", "image"}``).
    schema:
        The ``datashape`` mapping returned by intake (columns/dtypes, dims,
        etc.); empty if no reader could describe the data.
    n_files:
        Number of files that make up the dataset (after glob expansion).
    total_size:
        Total bytes across all files in the dataset, if known.
    metadata:
        Any other useful summary information from intake (shape, npartitions,
        recommended readers, description, …).
    """

    icon = "🗃️"

    name: str
    url: str | list[str] = ""
    datatype: str | None = None
    structure: list[str] = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    n_files: int = 1
    total_size: int | None = None
    metadata: dict = field(default_factory=dict)
