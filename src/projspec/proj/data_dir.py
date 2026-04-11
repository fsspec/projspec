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
# Extension → canonical format name
# Only extensions that are unambiguously data files (not config/code/docs).
# .json is excluded intentionally — it is too common in non-data contexts.
# ---------------------------------------------------------------------------
_EXT_TO_FORMAT: dict[str, str] = {
    # Tabular / columnar
    ".csv": "csv",
    ".tsv": "tsv",
    ".psv": "psv",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".arrow": "arrow",
    ".ipc": "arrow",
    ".feather": "arrow",
    ".orc": "orc",
    ".avro": "avro",
    ".xls": "excel",
    ".xlsx": "excel",
    ".xlsb": "excel",
    ".jsonl": "jsonlines",
    ".ndjson": "jsonlines",
    # Hierarchical / scientific
    ".hdf5": "hdf5",
    ".h5": "hdf5",
    ".he5": "hdf5",
    ".nc": "netcdf",
    ".nc4": "netcdf",
    # Geospatial
    ".shp": "shapefile",
    ".geojson": "geojson",
    ".gpkg": "geopackage",
    ".tif": "tiff",
    ".tiff": "tiff",
    # Image
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".bmp": "bmp",
    ".gif": "gif",
    ".webp": "webp",
    # Audio
    ".wav": "wav",
    ".flac": "flac",
    ".mp3": "mp3",
    ".ogg": "ogg",
    # Video
    ".mp4": "mp4",
    ".avi": "avi",
    ".mov": "mov",
    ".mkv": "mkv",
    # Array / ML
    ".npy": "numpy",
    ".npz": "numpy",
    ".pt": "pytorch",
    ".pth": "pytorch",
    # Opaque binary
    ".pkl": "pickle",
    ".bin": "binary",
}

_DATA_EXTENSIONS: frozenset[str] = frozenset(_EXT_TO_FORMAT)

# Magic-byte signatures for common binary formats (first 4–6 bytes).
_MAGIC: dict[bytes, str] = {
    b"PAR1": "parquet",
    b"\x89HDF": "hdf5",
    b"ORC\x00": "orc",
    b"Obj\x01": "avro",
    b"ARROW1": "arrow",
}

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


def _fmt_from_path(path: str) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    return _EXT_TO_FORMAT.get(ext)


def _confirm_magic(path: str, fmt: str, fs) -> str:
    """Try to confirm *fmt* via magic bytes; return *fmt* unchanged on failure."""
    try:
        with fs.open(path, "rb") as fh:
            header = fh.read(6)
        for magic, magic_fmt in _MAGIC.items():
            if header[: len(magic)] == magic:
                return magic_fmt
    except Exception:
        pass
    return fmt


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


class Data(ProjectSpec):
    """A directory whose primary contents are data files.

    Matches on any of:
    - At least one file with an unambiguous data extension (CSV, Parquet, Arrow,
      HDF5, images, audio, etc.) — without requiring a metadata sidecar.
    - A recognised directory layout: Hive partitioning (``key=value/`` subdirs),
      Apache Iceberg (``metadata/`` directory), Delta Lake (``_delta_log/``), or
      a Zarr store (``.zattrs`` / ``.zgroup`` at the root).
    """

    spec_doc = "https://opencode.ai/docs"  # placeholder — no single upstream spec

    # ------------------------------------------------------------------
    # match()
    # ------------------------------------------------------------------

    def match(self) -> bool:
        # Fast path: structural layout signals (no file-content inspection needed)
        if self._detect_layout():
            return True
        # Slow path: any top-level file with an unambiguous data extension
        return any(
            os.path.splitext(name)[1].lower() in _DATA_EXTENSIONS
            for name in self.proj.basenames
        )

    # ------------------------------------------------------------------
    # parse()
    # ------------------------------------------------------------------

    def parse(self) -> None:
        from projspec.content.data import (
            DataResource,
        )  # local import keeps startup fast

        layout = self._detect_layout()
        resources: list

        if layout in ("hive", "iceberg", "delta"):
            resources = self._parse_layout_dirs(layout)
            # Delta/Iceberg also commonly store data files at the root level
            # alongside the log/metadata directory; collect those too.
            if layout in ("iceberg", "delta"):
                root_resources = self._parse_flat()
                resources = resources + root_resources
        elif layout == "zarr_store":
            resources = [self._parse_zarr_root()]
        else:
            resources = self._parse_flat()

        if not resources:
            raise ParseFailed("No recognisable data files found")

        if len(resources) == 1:
            self._contents["data_resource"] = resources[0]
        else:
            self._contents["data_resource"] = AttrDict(
                {_safe_key(r.name): r for r in resources}
            )

    # ------------------------------------------------------------------
    # Layout detection
    # ------------------------------------------------------------------

    def _detect_layout(self) -> str:
        """Return a layout string, or '' if none of the known layouts match."""
        basenames = self.proj.basenames
        # Zarr store: .zattrs or .zgroup at the root
        if ".zattrs" in basenames or ".zgroup" in basenames:
            return "zarr_store"
        # Delta Lake: _delta_log/ directory
        dir_names = {_basename(e["name"]) for e in _filelist_dirs(self.proj.filelist)}
        if "_delta_log" in dir_names:
            return "delta"
        # Apache Iceberg: metadata/ directory present
        if "metadata" in dir_names:
            return "iceberg"
        # Hive: any top-level subdirectory whose name matches key=value
        if any(_HIVE_DIR_RE.match(d) for d in dir_names):
            return "hive"
        return ""

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _resource_from_entries(self, entries: list[dict], fmt: str, layout: str):
        """Build a DataResource from a list of same-format file entries.

        The resource name is the shared stem prefix when the entries form a
        multi-file series (e.g. ``part`` for ``part0.csv``, ``part1.csv``), or
        the bare filename stem for a single file, or the format string as a
        last resort.
        """
        from projspec.content.data import DataResource

        sample_paths = [e["name"] for e in entries[:3]]
        total_size = sum(e.get("size", 0) or 0 for e in entries)
        schema = (
            _read_schema(sample_paths[0], fmt, self.proj.fs) if sample_paths else {}
        )

        if len(entries) == 1:
            # Single file: use the stem as the name
            stem = os.path.splitext(_basename(entries[0]["name"]))[0]
            name = stem or fmt
        else:
            # Multi-file series: use the shared prefix (stripped of trailing
            # separator chars), falling back to the format string
            stems = [os.path.splitext(_basename(e["name"]))[0] for e in entries]
            prefix, _ = _common_affix(stems)
            name = prefix.rstrip("-_.") or fmt

        return DataResource(
            proj=self.proj,
            name=name,
            format=fmt,
            layout=layout,
            file_count=len(entries),
            total_size=total_size,
            schema=schema,
            sample_paths=sample_paths,
        )

    def _parse_flat(self) -> list:
        """Group top-level files by format and naming series.

        Files of the same format are only collated into a single DataResource
        when they share a consistent naming schema — i.e. their stems differ
        only in a numeric or date-like segment (e.g. ``part0.csv``,
        ``part1.csv`` or ``2024-02.tiff``, ``2024-03.tiff``).  Files whose
        stems vary in alphabetic content (e.g. ``users.csv``, ``orders.csv``)
        each become their own DataResource.
        """
        from projspec.content.data import DataResource

        # First bucket by format
        fmt_groups: dict[str, list[dict]] = {}
        for entry in _filelist_files(self.proj.filelist):
            fmt = _fmt_from_path(entry["name"])
            if fmt is None:
                continue
            fmt_groups.setdefault(fmt, []).append(entry)

        resources = []
        for fmt, entries in fmt_groups.items():
            # Split each format-group into naming series
            for series in _group_by_naming_series(entries):
                resources.append(self._resource_from_entries(series, fmt, "flat"))
        return resources

    def _parse_layout_dirs(self, layout: str) -> list:
        """One DataResource per top-level subdirectory (partition / table root).

        Within each subdirectory the dominant format is determined, then files
        are checked for a consistent naming series before collating.
        """
        from projspec.content.data import DataResource

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
            # Determine dominant format (most common extension)
            fmt_counts: dict[str, int] = {}
            for e in sub_files:
                fmt = _fmt_from_path(e["name"])
                if fmt:
                    fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1
            if not fmt_counts:
                continue
            dominant_fmt = max(fmt_counts, key=lambda k: fmt_counts[k])
            dominant_files = [
                e for e in sub_files if _fmt_from_path(e["name"]) == dominant_fmt
            ]
            # Use the directory name as the resource name regardless of series
            # (partition dirs are already logically grouped by the directory)
            resource = self._resource_from_entries(dominant_files, dominant_fmt, layout)
            # Override the name with the directory name
            resource.name = dir_name
            resources.append(resource)
        return resources

    def _parse_zarr_root(self):
        """Describe the whole directory as a single Zarr store resource."""
        from projspec.content.data import DataResource

        url = self.proj.url
        schema: dict | list = {}
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
            name=_basename(url) or "zarr_store",
            format="zarr",
            layout="zarr_store",
            file_count=len(_filelist_files(self.proj.filelist)),
            total_size=total_size,
            schema=schema,
            sample_paths=[],
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
