"""ProjectSpec for bare data directories.

Matches directories whose contents are predominantly data files (by extension or
by a recognised on-disk layout such as Hive partitioning, Apache Iceberg, Delta
Lake, or Zarr), with no requirement for any declarative metadata file.
"""

from __future__ import annotations

import os
import re
from posixpath import basename as _basename

from projspec.proj import ProjectSpec, ParseFailed
from projspec.utils import AttrDict

# ---------------------------------------------------------------------------
# Extension → (canonical format name, modality)
#
# Modality vocabulary from intake's `structure` tags + napari's layer types:
#   "tabular"    — row/column data
#   "array"      — N-dimensional arrays
#   "image"      — 2-D/3-D images (raster)
#   "timeseries" — time-indexed signals
#   "geospatial" — vector or raster geodata
#   "model"      — ML model weights / configs
#   "nested"     — hierarchical / JSON-like
#   "document"   — human-readable documents
#   "video"      — video streams
#   "archive"    — compressed bundles
#
# .json is excluded — too common in non-data contexts (configs, manifests).
# ---------------------------------------------------------------------------
_EXT_TO_FORMAT: dict[str, tuple[str, str]] = {
    # Tabular / columnar -------------------------------------------------------
    ".csv": ("csv", "tabular"),
    ".tsv": ("tsv", "tabular"),
    ".psv": ("psv", "tabular"),
    ".parquet": ("parquet", "tabular"),
    ".parq": ("parquet", "tabular"),
    ".pq": ("parquet", "tabular"),
    ".arrow": ("arrow", "tabular"),
    ".ipc": ("arrow", "tabular"),
    ".feather": ("arrow", "tabular"),  # Feather v1/v2 (magic: FEA1 / ARROW1)
    ".orc": ("orc", "tabular"),
    ".avro": ("avro", "tabular"),
    ".xls": ("excel", "tabular"),
    ".xlsx": ("excel", "tabular"),
    ".xlsm": ("excel", "tabular"),
    ".xlsb": ("excel", "tabular"),
    ".jsonl": ("jsonlines", "tabular"),
    ".ndjson": ("jsonlines", "tabular"),
    ".db": ("sqlite", "tabular"),  # DuckDB / SQLite (disambiguated by magic)
    ".sqlite": ("sqlite", "tabular"),
    ".sqlitedb": ("sqlite", "tabular"),
    ".duckdb": ("duckdb", "tabular"),
    # Array / scientific -------------------------------------------------------
    ".npy": ("numpy", "array"),
    ".npz": ("numpy", "array"),
    ".hdf5": ("hdf5", "array"),
    ".hdf": ("hdf5", "array"),
    ".h5": ("hdf5", "array"),
    ".h4": ("hdf5", "array"),
    ".he5": ("hdf5", "array"),
    ".nc": ("netcdf", "array"),
    ".nc3": ("netcdf", "array"),
    ".nc4": ("netcdf", "array"),
    ".mat": ("matlab", "array"),
    ".fits": ("fits", "array"),
    ".grib": ("grib", "timeseries"),
    ".grb": ("grib", "timeseries"),
    ".grib2": ("grib", "timeseries"),
    ".grb2": ("grib", "timeseries"),
    ".asdf": ("asdf", "array"),
    ".zarr": ("zarr", "array"),
    # Image / biomedical imaging -----------------------------------------------
    ".png": ("png", "image"),
    ".jpg": ("jpeg", "image"),
    ".jpeg": ("jpeg", "image"),
    ".tif": ("tiff", "image"),  # also geotiff — ambiguous; image wins
    ".tiff": ("tiff", "image"),
    ".cog": ("tiff", "geospatial"),  # Cloud-Optimised GeoTIFF
    ".bmp": ("bmp", "image"),
    ".gif": ("gif", "image"),
    ".webp": ("webp", "image"),
    ".dcm": ("dicom", "image"),
    ".dicom": ("dicom", "image"),
    ".nii": ("nifti", "image"),
    ".nrrd": ("nrrd", "image"),
    ".nhdr": ("nrrd", "image"),
    ".mha": ("metaimage", "image"),
    ".mhd": ("metaimage", "image"),
    ".svs": ("svs", "image"),  # Aperio whole-slide image
    ".ndpi": ("ndpi", "image"),  # Hamamatsu whole-slide image
    ".scn": ("scn", "image"),  # Leica whole-slide image
    ".lsm": ("lsm", "image"),  # Zeiss confocal
    ".exr": ("exr", "image"),  # OpenEXR HDR
    ".qptiff": ("qptiff", "image"),  # PerkinElmer whole-slide
    # Geospatial ---------------------------------------------------------------
    ".shp": ("shapefile", "geospatial"),
    ".shx": ("shapefile", "geospatial"),
    ".dbf": ("shapefile", "geospatial"),
    ".geojson": ("geojson", "geospatial"),
    ".gpkg": ("geopackage", "geospatial"),
    ".fgb": ("flatgeobuf", "geospatial"),
    ".kml": ("kml", "geospatial"),
    ".pmtiles": ("pmtiles", "geospatial"),
    # Audio --------------------------------------------------------------------
    ".wav": ("wav", "timeseries"),
    ".flac": ("flac", "timeseries"),
    ".mp3": ("mp3", "timeseries"),
    ".ogg": ("ogg", "timeseries"),
    # Video --------------------------------------------------------------------
    ".mp4": ("mp4", "video"),
    ".avi": ("avi", "video"),
    ".mov": ("mov", "video"),
    ".mkv": ("mkv", "video"),
    ".webm": ("webm", "video"),
    # ML model weights ---------------------------------------------------------
    ".safetensors": ("safetensors", "model"),
    ".gguf": ("gguf", "model"),
    ".pt": ("pytorch", "model"),
    ".pth": ("pytorch", "model"),
    ".onnx": ("onnx", "model"),
    ".tfrec": ("tfrecord", "model"),
    # Archive / bundle ---------------------------------------------------------
    ".pkl": ("pickle", "archive"),
    ".bin": ("binary", "archive"),
}

_DATA_EXTENSIONS: frozenset[str] = frozenset(_EXT_TO_FORMAT)

# ---------------------------------------------------------------------------
# Magic-byte signatures (format, modality, offset, bytes_pattern).
#
# Each entry: (format_str, modality_str, offset, pattern)
#   offset = int  → match at that fixed byte offset
#   offset = None → scan anywhere in the first 1 KiB (re.search)
#
# Ordered from most-specific to least-specific (longer / more-offset patterns
# first so they shadow shorter ones that match the same header).
# ---------------------------------------------------------------------------
_MAGIC: list[tuple[str, str, int | None, bytes]] = [
    # Fixed-offset signatures
    ("dicom", "image", 128, b"DICM"),  # DICOM preamble
    ("nifti", "image", 344, b"ni1\x00"),  # NIfTI-1
    ("nifti", "image", 344, b"n+1\x00"),  # NIfTI-1 single file
    ("duckdb", "tabular", 8, b"DUCK"),
    ("safetensors", "model", 8, b"{"),  # SafeTensors JSON header
    ("wav", "timeseries", 8, b"WAVE"),  # RIFF…WAVE
    # Offset-0 signatures
    ("parquet", "tabular", 0, b"PAR1"),
    ("hdf5", "array", 0, b"\x89HDF"),
    ("netcdf", "array", 0, b"CDF\x01"),  # NetCDF classic
    ("netcdf", "array", 0, b"CDF\x02"),  # NetCDF-64bit
    ("orc", "tabular", 0, b"ORC"),
    ("avro", "tabular", 0, b"Obj\x01"),
    ("arrow", "tabular", 0, b"ARROW1"),  # IPC stream
    ("arrow", "tabular", 0, b"FEA1"),  # Feather v1
    ("numpy", "array", 0, b"\x93NUMPY"),
    ("matlab", "array", 0, b"MATLAB"),
    ("fits", "array", 0, b"SIMPLE"),
    ("grib", "timeseries", 0, b"GRIB"),
    ("asdf", "array", 0, b"#ASDF"),
    ("flatgeobuf", "geospatial", 0, b"fgb"),
    ("gguf", "model", 0, b"GGUF"),
    ("png", "image", 0, b"\x89PNG"),
    ("jpeg", "image", 0, b"\xff\xd8\xff"),
    ("tiff", "image", 0, b"II*\x00"),  # little-endian TIFF
    ("tiff", "image", 0, b"MM\x00*"),  # big-endian TIFF
    ("sqlite", "tabular", 0, b"SQLite format"),
    ("shapefile", "geospatial", 0, b"\x00\x00\x27\x0a"),
    ("pmtiles", "geospatial", 0, b"PMTiles"),
]

# Regex that matches Hive-style partition directory names (e.g. "year=2024").
_HIVE_DIR_RE = re.compile(r"^[^=]+=.+$")


# ---------------------------------------------------------------------------
# Schema extraction helpers — all imports inside try/except ImportError so
# that missing optional libraries never block parsing.
# ---------------------------------------------------------------------------


def _read_schema(path: str, fmt: str, fs) -> dict | list:
    """Return a best-effort schema dict/list for *path*, or {} on any failure."""
    try:
        if fmt == "parquet":
            try:
                import pyarrow.parquet as pq

                with fs.open(path, "rb") as fh:
                    pf = pq.ParquetFile(fh)
                    return {field.name: str(field.type) for field in pf.schema_arrow}
            except ImportError:
                pass

        elif fmt == "arrow":
            try:
                import pyarrow.ipc as ipc

                with fs.open(path, "rb") as fh:
                    reader = ipc.open_file(fh)
                    return {field.name: str(field.type) for field in reader.schema}
            except ImportError:
                pass

        elif fmt == "hdf5":
            try:
                import h5py

                with fs.open(path, "rb") as fh:
                    with h5py.File(fh, "r") as ds:
                        return {
                            "variables": list(ds.keys()),
                            "attrs": dict(ds.attrs),
                        }
            except ImportError:
                pass

        elif fmt == "netcdf":
            try:
                import netCDF4 as nc  # type: ignore[import]

                with fs.open(path, "rb") as fh:
                    ds = nc.Dataset("in-mem", memory=fh.read())
                    return {
                        "variables": list(ds.variables.keys()),
                        "dims": {k: len(v) for k, v in ds.dimensions.items()},
                    }
            except ImportError:
                try:
                    import xarray as xr  # type: ignore[import]

                    with fs.open(path, "rb") as fh:
                        ds = xr.open_dataset(fh, engine="scipy")
                        return {
                            "variables": list(ds.data_vars),
                            "dims": dict(ds.dims),
                        }
                except ImportError:
                    pass

        elif fmt in ("jpeg", "png", "bmp", "gif", "webp", "tiff"):
            try:
                from PIL import Image  # type: ignore[import]

                with fs.open(path, "rb") as fh:
                    img = Image.open(fh)
                    img.load()
                    mode = img.mode
                    channels = len(img.getbands())
                    return {
                        "width": img.width,
                        "height": img.height,
                        "channels": channels,
                        "mode": mode,
                    }
            except ImportError:
                pass

        elif fmt in ("wav", "flac", "mp3", "ogg"):
            try:
                import soundfile as sf  # type: ignore[import]

                with fs.open(path, "rb") as fh:
                    info = sf.info(fh)
                    return {
                        "sample_rate": info.samplerate,
                        "channels": info.channels,
                        "frames": info.frames,
                    }
            except ImportError:
                pass

    except Exception:  # — never let schema extraction abort parsing
        pass

    return {}


# ---------------------------------------------------------------------------
# Helpers that work on the already-loaded filelist / basenames
# ---------------------------------------------------------------------------


def _filelist_dirs(filelist: list[dict]) -> list[dict]:
    """Return only directory entries from a filelist."""
    return [e for e in filelist if e.get("type", "") == "directory"]


def _filelist_files(filelist: list[dict]) -> list[dict]:
    """Return only file entries from a filelist."""
    return [e for e in filelist if e.get("type", "") != "directory"]


def _fmt_from_path(path: str) -> tuple[str, str] | None:
    """Return (format, modality) for *path* by extension, or None if unknown."""
    ext = os.path.splitext(path)[1].lower()
    return _EXT_TO_FORMAT.get(ext)


def _identify_by_magic(path: str, fs) -> tuple[str, str] | None:
    """Return (format, modality) by probing *path*'s header bytes, or None.

    Reads up to 1 KiB.  Checks fixed-offset patterns first (longer offsets
    first, to avoid short patterns shadowing longer ones), then scans for
    anywhere-patterns via re.search.
    """
    try:
        with fs.open(path, "rb") as fh:
            head = fh.read(1024)
    except Exception:
        return None

    for fmt, modality, offset, pattern in _MAGIC:
        if offset is None:
            if re.search(re.escape(pattern), head):
                return fmt, modality
        else:
            if head[offset : offset + len(pattern)] == pattern:
                return fmt, modality
    return None


# Token that may vary across files in a series: digits, dashes, underscores, dots.
# Alphabetic variation (e.g. "users" vs "orders") disqualifies collation.
_SERIES_VAR_RE = re.compile(r"^[\d\-_.]+$")


def _common_affix(stems: list[str]) -> tuple[str, str]:
    """Return the longest (prefix, suffix) shared by every stem in *stems*."""
    if not stems:
        return "", ""
    prefix = os.path.commonprefix(stems)
    # Reverse each stem to find common suffix via commonprefix trick
    rev = [s[::-1] for s in stems]
    suffix = os.path.commonprefix(rev)[::-1]
    # Ensure prefix and suffix don't overlap (can happen with a single-char stem)
    if len(prefix) + len(suffix) > min(len(s) for s in stems):
        suffix = ""
    return prefix, suffix


def _group_by_naming_series(entries: list[dict]) -> list[list[dict]]:
    """Partition *entries* (same-format file list) into naming-series groups.

    Two or more files belong to the same series when their basenames (stems)
    differ only in a contiguous segment that consists solely of digits, dashes,
    underscores, or dots — i.e. a numeric counter or a date component.

    A single file is always its own series (trivially consistent).

    Returns a list of groups, each group being a non-empty list of entries that
    share a common naming pattern.
    """
    if len(entries) <= 1:
        return [entries] if entries else []

    # Compute stems once
    stems = [os.path.splitext(_basename(e["name"]))[0] for e in entries]

    prefix, suffix = _common_affix(stems)
    plen, slen = len(prefix), len(suffix)

    # Extract the variable middle segment for each stem
    variables = []
    for stem in stems:
        mid = stem[plen : len(stem) - slen if slen else len(stem)]
        variables.append(mid)

    # All files form one series if:
    #   1. There is a non-trivial shared prefix OR suffix (at least 1 char), AND
    #   2. Every variable segment is numeric/date-like (no alphabetic chars)
    has_affix = plen >= 1 or slen >= 1
    all_numeric_var = all(_SERIES_VAR_RE.match(v) or v == "" for v in variables)

    if has_affix and all_numeric_var:
        return [entries]

    # Otherwise fall back: each file is its own "series" (separate resource)
    return [[e] for e in entries]


# ---------------------------------------------------------------------------
# Data spec
# ---------------------------------------------------------------------------

# Sentinel files / directories whose presence indicates a non-data project
# type is also present in this directory.  When any of these are found,
# Data.parse() applies the byte-majority test instead of parsing
# unconditionally.
#
# Notably absent: datapackage.json, catalog.yaml/yml, .dvc/ — those belong
# to projspec.proj.datapackage and are treated as compatible companions.
_NON_DATA_SENTINELS: frozenset[str] = frozenset(
    {
        # Python
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "hatch.toml",
        # Rust
        "Cargo.toml",
        # JavaScript / Node
        "package.json",
        # Go
        "go.mod",
        # Container / infra
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        # Helm
        "Chart.yaml",
        # Ruby / Java / .NET
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "*.csproj",
        # R
        "DESCRIPTION",
        # Conda
        "environment.yml",
        "environment.yaml",
        "meta.yaml",
        # Pixi
        "pixi.toml",
        # Mkdocs / Sphinx / RTD
        "mkdocs.yml",
        "mkdocs.yaml",
        "conf.py",
        ".readthedocs.yaml",
        ".readthedocs.yml",
        # Scripts / notebooks that imply code-first dirs
        "Makefile",
    }
)


class Data(ProjectSpec):
    """A directory whose primary contents are data files.

    Matches on any of:
    - At least one file with an unambiguous data extension (CSV, Parquet, Arrow,
      HDF5, images, audio, etc.) — without requiring a metadata sidecar.
    - A recognised directory layout: Hive partitioning (`key=value/` subdirs),
      Apache Iceberg (`metadata/` directory), Delta Lake (`_delta_log/`), or
      a Zarr store (`.zattrs` / `.zgroup` at the root).

    Parsing behaviour
    -----------------
    If no non-datapackage project signals are present in the directory the spec
    parses unconditionally.  If sentinel files that indicate another project type
    (`pyproject.toml`, `Cargo.toml`, `package.json`, …) are found, parsing
    succeeds only when the majority of bytes in the root file listing belong to
    recognised data files; otherwise `ParseFailed` is raised so that the
    directory is not double-counted as both a code project and a data project.
    """

    def match(self) -> bool:
        # Fast path: structural layout signals (no file-content inspection needed)
        if self._detect_layout():
            return True
        # Slow path: any top-level file with an unambiguous data extension
        return any(
            os.path.splitext(name)[1].lower() in _DATA_EXTENSIONS
            for name in self.proj.basenames
        )

    def parse(self) -> None:
        if self._has_non_data_sentinels():
            if not self._data_bytes_majority():
                raise ParseFailed(
                    "Non-data project sentinels found and data files are not "
                    "the majority of bytes — skipping Data spec"
                )

        layout = self._detect_layout()
        resources: list

        if layout in ("hive", "iceberg", "delta"):
            resources = self._parse_layout_dirs(layout)
            # Delta/Iceberg also commonly store data files at the root level
            # alongside the log/metadata directory; collect those too.
            if layout in ("iceberg", "delta"):
                root_resources = self._parse_flat()
                resources = resources + root_resources
        elif layout in ("zarr_store", "tiledarray"):
            resources = [self._parse_zarr_root()]
        else:
            resources = self._parse_flat()

        if not resources:
            raise ParseFailed("No recognisable data files found")

        if len(resources) == 1:
            self._contents["data_resource"] = resources[0]
        else:
            self._contents["data_resource"] = AttrDict(
                {_safe_key(r.path): r for r in resources}
            )

    def _has_non_data_sentinels(self) -> bool:
        """Return True if any non-datapackage project sentinel is present."""
        basenames = self.proj.basenames
        return any(name in _NON_DATA_SENTINELS for name in basenames)

    def _data_bytes_majority(self) -> bool:
        """Return True if data files account for >50 % of root-listing bytes.

        Files with unknown / zero size are excluded from both totals so they
        do not unfairly skew the ratio.
        """
        total_bytes = 0
        data_bytes = 0
        for entry in self.proj.filelist:
            size = entry.get("size") or 0
            if size <= 0:
                continue
            total_bytes += size
            ext = os.path.splitext(entry["name"].rsplit("/", 1)[-1])[1].lower()
            if ext in _DATA_EXTENSIONS:
                data_bytes += size
        if total_bytes == 0:
            return False
        return data_bytes > total_bytes / 2

    def _detect_layout(self) -> str:
        """Return a layout string, or '' if none of the known layouts match.

        Uses the `contains` sentinel approach from intake: certain well-known
        files/directories at the root identify a directory as a logical dataset.
        """
        basenames = self.proj.basenames
        # Zarr store: .zattrs, .zgroup, or zarr.json at the root
        # (zarr.json is the Zarr v3 sentinel; .zattrs/.zgroup are v2)
        if any(s in basenames for s in (".zattrs", ".zgroup", "zarr.json")):
            return "zarr_store"
        dir_names = {_basename(e["name"]) for e in _filelist_dirs(self.proj.filelist)}
        # Delta Lake
        if "_delta_log" in dir_names:
            return "delta"
        # TileDB array directory
        if "__meta" in dir_names and "__schema" in dir_names:
            return "tiledarray"
        # Apache Iceberg: metadata/ directory present
        if "metadata" in dir_names:
            return "iceberg"
        # Partitioned Parquet: _metadata sentinel file at root (written by Spark/Dask)
        if "_metadata" in basenames:
            return "iceberg"
        # Hive: any top-level subdirectory whose name matches key=value
        if any(_HIVE_DIR_RE.match(d) for d in dir_names):
            return "hive"
        return ""

    def _resource_from_entries(
        self, entries: list[dict], fmt: str, modality: str, layout: str
    ):
        """Build a DataResource from a list of same-format file entries.

        The `path` field is set to:

        - Single file: the bare basename, e.g. `"data.csv"`.
        - Multi-file series: a glob pattern, e.g. `"part*.csv"`, built from
          the shared prefix/suffix of the basenames.
        """
        from projspec.content.data import DataResource

        full_paths = [e["name"] for e in entries]
        total_size = sum(e.get("size", 0) or 0 for e in entries)
        sample_path = full_paths[0] if full_paths else ""
        schema = _read_schema(sample_path, fmt, self.proj.fs) if sample_path else {}

        ext = os.path.splitext(_basename(full_paths[0]))[1] if full_paths else ""

        if len(entries) == 1:
            path = _basename(full_paths[0]) or fmt
        else:
            stems = [os.path.splitext(_basename(p))[0] for p in full_paths]
            prefix, suffix = _common_affix(stems)
            stem_pattern = (prefix.rstrip("-_.") or fmt) + "*" + suffix
            path = stem_pattern + ext

        return DataResource(
            proj=self.proj,
            path=path,
            format=fmt,
            modality=modality,
            layout=layout,
            file_count=len(entries),
            total_size=total_size,
            schema=schema,
            sample_path=sample_path,
        )

    def _parse_flat(self) -> list:
        """Group top-level files by format and naming series.

        Files of the same format are only collated into a single DataResource
        when they share a consistent naming schema — i.e. their stems differ
        only in a numeric or date-like segment (e.g. `part0.csv`,
        `part1.csv` or `2024-02.tiff`, `2024-03.tiff`).  Files whose
        stems vary in alphabetic content (e.g. `users.csv`, `orders.csv`)
        each become their own DataResource.
        """
        # First bucket by (fmt, modality)
        fmt_groups: dict[tuple[str, str], list[dict]] = {}
        for entry in _filelist_files(self.proj.filelist):
            fmt_info = _fmt_from_path(entry["name"])
            if fmt_info is None:
                continue
            fmt_groups.setdefault(fmt_info, []).append(entry)

        resources = []
        for (fmt, modality), entries in fmt_groups.items():
            # Split each format-group into naming series
            for series in _group_by_naming_series(entries):
                resources.append(
                    self._resource_from_entries(series, fmt, modality, "flat")
                )
        return resources

    def _parse_layout_dirs(self, layout: str) -> list:
        """One DataResource per top-level subdirectory (partition / table root).

        Within each subdirectory the dominant format is determined, then files
        are checked for a consistent naming series before collating.
        """
        dir_entries = _filelist_dirs(self.proj.filelist)
        resources = []
        for dir_entry in dir_entries:
            dir_path = dir_entry["name"]
            dir_name = _basename(dir_path)
            # Skip hidden/internal dirs for iceberg/delta
            if layout in ("iceberg", "delta") and dir_name.startswith(
                ("metadata", "_delta_log", "_")
            ):
                continue
            # Enumerate files one level inside this subdirectory
            try:
                sub_filelist = self.proj.fs.ls(dir_path, detail=True)
            except Exception:
                continue

            sub_files = _filelist_files(sub_filelist)
            # Determine dominant (fmt, modality) by file count
            fmt_counts: dict[tuple[str, str], int] = {}
            for e in sub_files:
                fmt_info = _fmt_from_path(e["name"])
                if fmt_info:
                    fmt_counts[fmt_info] = fmt_counts.get(fmt_info, 0) + 1
            if not fmt_counts:
                continue
            dominant = max(fmt_counts, key=lambda k: fmt_counts[k])
            dominant_fmt, dominant_modality = dominant
            dominant_files = [
                e for e in sub_files if _fmt_from_path(e["name"]) == dominant
            ]
            resource = self._resource_from_entries(
                dominant_files, dominant_fmt, dominant_modality, layout
            )
            # Override path with the directory basename + trailing slash
            # (partition dirs are already logically grouped by the directory)
            resource.path = dir_name + "/"
            resources.append(resource)
        return resources

    def _parse_zarr_root(self):
        """Describe the whole directory as a single array-store resource.

        Used for Zarr stores and TileDB arrays — both are directory-as-dataset
        layouts with no individual data files at the root.
        """
        from projspec.content.data import DataResource

        url = self.proj.url
        layout = self._detect_layout()
        # TileDB directories are not Zarr; distinguish the format accordingly
        if layout == "tiledarray":
            fmt, modality = "tiledb", "array"
            schema: dict | list = {}
        else:
            fmt, modality = "zarr", "array"
            schema = {}
            try:
                import zarr  # type: ignore[import]

                store = zarr.open(url, mode="r")
                schema = {
                    "arrays": list(store.array_keys()),
                    "groups": list(store.group_keys()),
                    "attrs": dict(store.attrs),
                }
            except (ImportError, Exception):
                pass

        total_size = sum(
            e.get("size", 0) or 0 for e in _filelist_files(self.proj.filelist)
        )
        return DataResource(
            proj=self.proj,
            path=(_basename(url) or fmt) + "/",
            format=fmt,
            modality=modality,
            layout=layout,
            file_count=len(_filelist_files(self.proj.filelist)),
            total_size=total_size,
            schema=schema,
            sample_path="",
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _safe_key(name: str) -> str:
    """Convert an arbitrary name to a valid Python identifier for AttrDict keys."""
    key = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if key and key[0].isdigit():
        key = "_" + key
    return key or "_unnamed"
