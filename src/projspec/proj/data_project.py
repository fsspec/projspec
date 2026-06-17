"""The :class:`DataProject` project type.

A *data project* is a directory that is wholly or substantially made up of
data files (as opposed to source code, docs or config).  Examples:

* a directory of CSV/parquet/JSON files exported from a database,
* a folder of images or arrays,
* a code project that *also* ships a significant amount of bundled data.

Detection policy
----------------
Scanning data is comparatively expensive (intake reads magic bytes / samples),
so we only do it when the data is *worth* describing.  Data is considered
significant when **any** of the following holds:

* the candidate data files make up at least ``data_min_fraction`` of the
  project's total bytes, **and** their combined size is at least
  ``data_min_total_size`` (guards against a project of tiny files);
* at least one individual data file is at least ``data_min_file_size``
  (a single big file is always worth describing);
* the directory matched no other project type at all (a bare data dump), as
  long as the data clears ``data_min_total_size``.

Consolidation
-------------
Before handing files to intake, obviously-related files are grouped into a
single dataset (see :mod:`projspec.proj._consolidate`):

* numbered series – ``001.csv``, ``002.csv`` → ``*.csv``
* spark/dask parts – ``part-00000.parquet`` … → ``part-*.parquet``
* token series – ``green.gif``, ``red.gif`` → ``*.gif``

Intake's own directory-dataset recognition (hive parquet, zarr, delta, …) is
preserved: such directories are inspected as a whole rather than file-by-file.

Per-dataset significance
------------------------
Just as the whole directory must clear the significance bar above, the
individual datasets within a data project are filtered too: a dataset whose
size is less than ``data_min_fraction`` of the largest dataset is treated as
incidental and dropped (see :meth:`DataProject._filter_small_datasets`).  This
mirrors the project-level fraction test so that a project dominated by one big
dataset doesn't also report a handful of tiny, unrelated ones.
"""

from __future__ import annotations

import logging

from projspec.config import get_conf
from projspec.proj.base import ProjectSpec, ParseFailed
from projspec.proj._consolidate import consolidate, FileGroup
from projspec.utils import AttrDict

logger = logging.getLogger("projspec.data_project")

# Extensions that are *not* data: source code, build/config, docs.  Anything
# else (or no extension) is a candidate data file.  Kept conservative on
# purpose - intake makes the final call on whether something is real data.
_NON_DATA_EXT = {
    # python / compiled
    ".py",
    ".pyc",
    ".pyi",
    ".pyx",
    ".pxd",
    ".so",
    ".pyd",
    ".ipynb",
    # other languages
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".scala",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".rb",
    ".php",
    ".swift",
    ".m",
    ".sh",
    ".bash",
    ".lua",
    ".pl",
    ".r",
    ".jl",
    # config / build / project metadata
    ".toml",
    ".cfg",
    ".ini",
    ".lock",
    ".mk",
    ".cmake",
    ".gradle",
    ".bazel",
    ".dockerfile",
    ".env",
    ".editorconfig",
    ".gitignore",
    ".gitattributes",
    # docs / web
    ".md",
    ".rst",
    ".txt",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".tex",
    # these are ambiguous - yaml/json are often config but also data; we treat
    # them as candidate data only when they dominate (handled by thresholds).
}

# Directory-based dataset markers intake understands; if present we inspect the
# whole directory rather than enumerating files.
_DIR_DATASET_MARKERS = (
    "_metadata",
    "_common_metadata",
    "_delta_log",
    ".zgroup",
    ".zarray",
    "zarr.json",
    "_latest.manifest",
)


class DataProject(ProjectSpec):
    """A project that is wholly or substantially composed of data files.

    Produces one :class:`projspec.content.data.Dataset` content object per
    consolidated dataset found, populated from
    :func:`intake.readers.inspect.inspect_dataset` where intake is available.
    """

    icon = "🗃️"
    spec_doc = (
        "https://intake.readthedocs.io/en/latest/api2.html"
        "#intake.readers.inspect.inspect_dataset"
    )

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _is_data_ext(name: str) -> bool:
        """Whether a basename looks like a data file (not code/docs/config)."""
        lower = name.lower()
        if lower.startswith("."):
            return False  # dotfiles are metadata, not data
        if "." not in lower:
            return False  # no extension - usually not a recognisable dataset
        for double in (".csv.gz", ".json.gz", ".tsv.gz"):
            if lower.endswith(double):
                return True
        ext = "." + lower.rsplit(".", 1)[-1]
        return ext not in _NON_DATA_EXT

    def _candidate_files(self) -> list[tuple[str, int | None]]:
        """``(basename, size)`` for data-like files directly in the root."""
        out = []
        for info in self.proj.filelist:
            if info.get("type") == "directory":
                continue
            name = info["name"].rsplit("/", 1)[-1]
            if self._is_data_ext(name):
                out.append((name, info.get("size")))
        return out

    def _has_dir_dataset(self) -> bool:
        """True if the root itself is an intake directory-dataset (hive, zarr…)."""
        return any(m in self.proj.basenames for m in _DIR_DATASET_MARKERS)

    # ── match ─────────────────────────────────────────────────────────────
    def match(self) -> bool:
        """Cheap check: are there any candidate data files (or a dir-dataset)?

        Significance (size/fraction) is enforced in :meth:`parse` so that
        ``match`` stays cheap and never reads file contents.
        """
        if self._has_dir_dataset():
            return True
        return bool(self._candidate_files())

    # ── significance policy ────────────────────────────────────────────────
    def _other_type_matches(self) -> bool:
        """Cheaply test whether any *other* project type matches this directory.

        ``parse`` runs in registry order, so ``self.proj.specs`` is not yet
        complete when ``DataProject`` is parsed.  Instead we re-run the cheap
        ``match()`` of every other registered spec.  ``match`` is contractually
        cheap (basename checks), so this adds little cost and only happens once
        per directory that has candidate data.
        """
        from projspec.proj.base import registry, ProjectExtra

        for name, cls in registry.items():
            if name == "data_project":
                continue
            # ProjectExtra specs (licences, CI, intake catalogs, …) are
            # cross-cutting add-ons, not standalone project types, so a match
            # from one of them should not suppress a data project.
            if issubclass(cls, ProjectExtra):
                continue
            try:
                inst = cls(self.proj)  # __init__ runs match(), raises if no match
            except Exception:
                continue
            else:
                logger.debug("DataProject deferring to %s for %s", name, self.proj.url)
                return True
        return False

    def _is_significant(self, data_bytes: int, max_file: int) -> bool:
        """Apply the detection policy described in the module docstring."""
        min_file = get_conf("data_min_file_size")
        min_total = get_conf("data_min_total_size")
        min_frac = get_conf("data_min_fraction")
        min_play = get_conf("data_min_play_size")

        # 1. a single big file is always worth describing
        if max_file >= min_file:
            return True

        total = self.proj.total_size or data_bytes
        # 2. data dominates the project by byte fraction (and isn't trivially small)
        if total and data_bytes / total >= min_frac and data_bytes >= min_total:
            return True

        # 3. nothing else matched -> treat any non-play data dump as a project.
        #    Here the bar is only "more than play data", not the full
        #    data_min_total_size used for the also-a-data-project case above.
        if data_bytes >= min_play and not self._other_type_matches():
            return True

        return False

    def _filter_small_datasets(self, datasets: list) -> list:
        """Drop datasets that are a small fraction of the largest one.

        Operates on a list of ``(name, Dataset)`` pairs (the form used while
        assembling :meth:`parse`'s output).

        Just as :meth:`_is_significant` decides whether the directory as a
        whole is data-y enough to report, this applies the same spirit to the
        individual datasets within a data project: a dataset whose size is
        less than ``data_min_fraction`` of the biggest dataset is treated as
        incidental and discarded.

        The comparison is by byte size relative to the largest dataset.  If
        fewer than two datasets are present, or any dataset's size is unknown
        (``None``), no filtering is applied (we can't reason about fractions).
        """
        if len(datasets) < 2:
            return datasets
        sizes = [getattr(ds, "total_size", None) for _, ds in datasets]
        if any(s is None for s in sizes):
            return datasets
        largest = max(s for s in sizes if s is not None)
        if largest <= 0:
            return datasets
        min_frac = get_conf("data_min_fraction")
        kept = [
            pair
            for pair, s in zip(datasets, sizes)
            if s is not None and s / largest >= min_frac
        ]
        # never drop everything: if the threshold somehow excludes all (e.g.
        # min_frac > 1), fall back to keeping the original set.
        return kept or datasets

    # ── parse ──────────────────────────────────────────────────────────────
    def parse(self) -> None:
        candidates = self._candidate_files()
        has_dir_dataset = self._has_dir_dataset()

        data_bytes = sum(s or 0 for _, s in candidates)
        max_file = max((s or 0 for _, s in candidates), default=0)

        if not has_dir_dataset and not self._is_significant(data_bytes, max_file):
            raise ParseFailed("Data present but not a significant data project")

        groups: list[FileGroup]
        if has_dir_dataset:
            # Let intake describe the whole directory as one dataset.
            name = self.proj.url.rstrip("/").rsplit("/", 1)[-1] or "dataset"
            groups = [
                FileGroup(
                    members=[],
                    total_size=self.proj.total_size,
                    pattern=name,
                    consolidated=True,
                )
            ]
            dir_dataset = True
        else:
            min_group = get_conf("data_consolidate_min_group")
            groups = consolidate(candidates, min_group=min_group)
            dir_dataset = False

        if len(groups) > get_conf("data_inspect_max_datasets"):
            logger.debug(
                "Too many datasets (%d) in %s; describing without intake",
                len(groups),
                self.proj.url,
            )
            described = [self._describe_without_intake(g) for g in groups]
        else:
            described = [self._describe(g, dir_dataset=dir_dataset) for g in groups]

        # Each entry is a (name, Dataset) pair. Only keep datasets that intake
        # could assign a datatype to; datasets whose type could not be
        # identified are not useful as data content.
        described = [(name, ds) for name, ds in described if ds.datatype is not None]

        # Drop datasets that are only a small fraction of the largest one,
        # analogous to the project-level significance test.
        described = self._filter_small_datasets(described)

        if not described:
            raise ParseFailed("No datasets with an identified datatype found")

        # Datasets are keyed by their (unique) name; the name is therefore not
        # duplicated as a field on the Dataset objects themselves.
        datasets = AttrDict()
        for name, ds in described:
            key = name
            # guard against the (rare) case of duplicate names
            n = 2
            while key in datasets:
                key = f"{name}#{n}"
                n += 1
            datasets[key] = ds
        self._contents = AttrDict(dataset=datasets)

    # ── dataset description ─────────────────────────────────────────────────
    def _root_url(self) -> str:
        """Protocol-qualified root URL for handing to intake / building dataset
        URLs.

        ``self.proj.url`` is the filesystem-specific path with the protocol
        stripped (e.g. ``bucket/key`` for ``s3://bucket/key``).  Intake needs
        the protocol to pick the right filesystem, so we restore it here.
        """
        return self.proj.fs.unstrip_protocol(self.proj.url)

    def _dataset_url(self, group: FileGroup, dir_dataset: bool):
        if dir_dataset:
            return self._root_url()
        return group.url(self._root_url())

    def _describe_without_intake(self, group: FileGroup):
        """Build a Dataset content object using only filename info (no I/O).

        Returns a ``(name, Dataset)`` pair; the name becomes the key in the
        project's ``contents.dataset`` mapping.
        """
        from projspec.content.data import Dataset

        return group.name, Dataset(
            proj=self.proj,
            url=group.url(self._root_url()),
            datatype=None,
            structure=[],
            schema={},
            n_files=len(group.members) or 1,
            total_size=group.total_size,
            metadata={},
        )

    def _describe(self, group: FileGroup, dir_dataset: bool = False):
        """Describe a single file-group as a Dataset, using intake if available."""
        from projspec.content.data import Dataset

        url = self._dataset_url(group, dir_dataset)
        info: dict | None = None
        try:
            from intake.readers.inspect import inspect_dataset

            # storage_options keep remote access working; the size guard and
            # timeout protect against pathological inputs.
            info = inspect_dataset(
                url,
                storage_options=self.proj.storage_options or None,
            )
        except ImportError:
            logger.debug("intake not installed; describing %s by name only", url)
        except Exception as exc:  # never let a bad file abort the whole parse
            logger.debug("inspect_dataset failed for %s: %s", url, exc)

        if not info:
            return self._describe_without_intake(group)

        n_files = info.get("n_files") or (len(group.members) or 1)
        total = info.get("file_size_bytes")
        if total is None:
            total = group.total_size

        meta = {
            k: info[k]
            for k in (
                "shape",
                "npartitions",
                "reader_used",
                "description",
                "html_repr",
                "thumbnail",
            )
            if info.get(k) is not None
        }
        # report which readers intake thinks can load this, if any
        readers = info.get("readers") or {}
        if readers:
            meta["readers"] = sorted(readers)

        structure = info.get("structure") or set()
        name = group.pattern if dir_dataset else group.name
        return name, Dataset(
            proj=self.proj,
            url=url,
            datatype=info.get("detected_type"),
            structure=sorted(structure)
            if isinstance(structure, set)
            else list(structure),
            schema=info.get("datashape") or {},
            n_files=n_files,
            total_size=total,
            metadata=meta,
        )
