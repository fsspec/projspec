"""Tests for the DataProject spec and the file-consolidation helper.

The consolidation helper is filesystem-agnostic and tested directly on
``(basename, size)`` lists.  The DataProject spec is tested end-to-end by
writing files into a tmpdir and constructing a real ``projspec.Project``.

Intake may or may not be installed (and which readers are available varies),
so the DataProject assertions only check things that do not depend on a
specific reader being present: that the project is/ isn't detected, how files
are consolidated, file counts and sizes.  Where intake is available we also
spot-check ``datatype``/``structure``.
"""

import os

import pytest

import projspec
from projspec.config import temp_conf
from projspec.proj._consolidate import consolidate, FileGroup
from projspec.proj.data_project import DataProject
from projspec.content.data import Dataset, TabularData, IntakeSource

try:
    import intake.readers.inspect  # noqa: F401

    HAS_INTAKE = True
except Exception:  # pragma: no cover
    HAS_INTAKE = False

try:
    import pandas as _pd  # noqa: F401

    HAS_PANDAS = True
except Exception:  # pragma: no cover
    HAS_PANDAS = False

try:
    # importing here puts PIL in sys.modules so intake's check_imports (which
    # uses importlib.metadata.distribution and falls back to sys.modules) finds
    # it - Pillow's distribution name ("pillow") differs from the import name.
    import PIL  # noqa: F401
    import numpy as _np  # noqa: F401

    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Production-equivalent significance thresholds. Tests that depend on these
# values set them explicitly via temp_conf so they do not rely on (and are not
# broken by changes to) the config defaults.
PROD_THRESHOLDS = dict(
    data_min_fraction=0.5,
    data_min_file_size=1024 * 1024,
    data_min_total_size=10 * 1024 * 1024,
    data_min_play_size=64 * 1024,
)


def write_data(tmpdir, files: dict[str, int | bytes]) -> str:
    """Write files into *tmpdir*.

    Values are either an int (number of zero bytes to write) or raw bytes.
    """
    path = str(tmpdir)
    for rel, content in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        data = content if isinstance(content, bytes) else b"\0" * content
        with open(full, "wb") as f:
            f.write(data)
    return path


def datasets(proj) -> list[Dataset]:
    dp = proj.specs.get("data_project")
    return list(dp.contents.get("dataset", [])) if dp else []


# ---------------------------------------------------------------------------
# consolidate()
# ---------------------------------------------------------------------------


class TestConsolidate:
    def test_numbered_csv_series(self):
        files = [(f"{i:03d}.csv", 100) for i in range(1, 6)]
        groups = consolidate(files)
        assert len(groups) == 1
        g = groups[0]
        assert g.consolidated
        assert g.pattern == "*.csv"
        assert len(g.members) == 5
        assert g.total_size == 500

    def test_spark_parts(self):
        files = [(f"part-{i:05d}.parquet", 10) for i in range(4)]
        groups = consolidate(files)
        assert len(groups) == 1
        assert groups[0].pattern == "part-*.parquet"
        assert groups[0].consolidated

    def test_year_series(self):
        files = [(f"data_{y}.json", 5) for y in range(2015, 2021)]
        groups = consolidate(files)
        assert len(groups) == 1
        assert groups[0].pattern == "data_*.json"

    def test_token_series_colours(self):
        files = [("red.gif", 1), ("green.gif", 1), ("blue.gif", 1)]
        groups = consolidate(files, min_token_group=2)
        assert len(groups) == 1
        assert groups[0].pattern == "*.gif"
        assert groups[0].consolidated
        assert sorted(groups[0].members) == ["blue.gif", "green.gif", "red.gif"]

    def test_below_min_group_stays_standalone(self):
        # only two numbered files, default min_group=3 -> not consolidated
        files = [("001.csv", 10), ("002.csv", 10)]
        groups = consolidate(files, min_group=3, min_token_group=99)
        assert all(not g.consolidated for g in groups)
        assert len(groups) == 2

    def test_mixed_extensions_separate_groups(self):
        files = [(f"{i:03d}.csv", 10) for i in range(5)]
        files += [(f"{i:03d}.json", 10) for i in range(5)]
        groups = consolidate(files)
        patterns = sorted(g.pattern for g in groups)
        assert patterns == ["*.csv", "*.json"]

    def test_unrelated_files_standalone(self):
        files = [("readme_data.bin", 10), ("schema.avro", 10)]
        groups = consolidate(files, min_token_group=99)
        assert all(not g.consolidated for g in groups)
        assert {g.name for g in groups} == {"readme_data.bin", "schema.avro"}

    def test_double_extension_grouping(self):
        files = [(f"part{i}.csv.gz", 10) for i in range(5)]
        groups = consolidate(files)
        assert len(groups) == 1
        assert groups[0].ext == ".csv.gz"
        assert groups[0].consolidated

    def test_url_glob_vs_list(self, tmp_path):
        g = FileGroup(
            members=["001.csv", "002.csv", "003.csv"],
            ext=".csv",
            pattern="*.csv",
            consolidated=True,
        )
        assert g.url("/data/foo") == "/data/foo/*.csv"
        single = FileGroup(members=["only.csv"], ext=".csv", pattern="only.csv")
        assert single.url("/data/foo") == "/data/foo/only.csv"

    def test_size_unknown_propagates_none(self):
        files = [("001.csv", None), ("002.csv", 10), ("003.csv", 10)]
        groups = consolidate(files)
        assert groups[0].total_size is None


# ---------------------------------------------------------------------------
# Content classes
# ---------------------------------------------------------------------------


class TestContentClasses:
    def test_dataset_roundtrip(self, tmp_path):
        proj = projspec.Project(str(tmp_path))
        ds = Dataset(
            proj=proj,
            name="*.csv",
            url=f"{proj.url}/*.csv",
            datatype="CSV",
            structure=["table"],
            schema={"columns": ["a", "b"]},
            n_files=3,
            total_size=999,
            metadata={"readers": ["DaskCSV"]},
        )
        d = ds.to_dict(compact=False)
        assert d["klass"] == ["content", "dataset"]
        from projspec.utils import from_dict

        ds2 = from_dict(d, proj=proj)
        assert isinstance(ds2, Dataset)
        assert ds2.name == "*.csv"
        assert ds2.datatype == "CSV"
        assert ds2.n_files == 3

    def test_tabular_and_intake_source_registered(self):
        from projspec.content.base import registry

        assert registry["tabular_data"] is TabularData
        assert registry["intake_source"] is IntakeSource
        assert registry["dataset"] is Dataset


# ---------------------------------------------------------------------------
# DataProject detection / significance
# ---------------------------------------------------------------------------


class TestDataProjectSignificance:
    def test_pure_data_dir_detected(self, tmp_path):
        # three numbered csvs, well above the play-data floor
        with temp_conf(**PROD_THRESHOLDS):
            write_data(tmp_path, {f"{i:03d}.csv": 100_000 for i in range(1, 4)})
            proj = projspec.Project(str(tmp_path))
        assert "data_project" in proj.specs
        ds = datasets(proj)
        assert len(ds) == 1
        assert ds[0].n_files == 3
        assert ds[0].name == "*.csv"

    def test_tiny_play_data_rejected(self, tmp_path):
        with temp_conf(**PROD_THRESHOLDS):
            write_data(tmp_path, {f"{i:03d}.csv": 20 for i in range(1, 4)})
            proj = projspec.Project(str(tmp_path))
        assert "data_project" not in proj.specs

    def test_big_single_file_in_code_project(self, tmp_path):
        # python package + one big csv -> both python_code and data_project
        with temp_conf(**PROD_THRESHOLDS):
            write_data(
                tmp_path,
                {
                    "__init__.py": b"x = 1\n",
                    "big.csv": 2 * 1024 * 1024,  # > data_min_file_size (1MB)
                },
            )
            proj = projspec.Project(str(tmp_path))
        assert "python_code" in proj.specs
        assert "data_project" in proj.specs
        ds = datasets(proj)
        assert any(d.name == "big.csv" for d in ds)

    def test_small_data_in_code_project_ignored(self, tmp_path):
        with temp_conf(**PROD_THRESHOLDS):
            write_data(
                tmp_path,
                {
                    "__init__.py": b"x = 1\n",
                    "main.py": b"print(1)\n" * 100,
                    "sample.csv": 200,  # tiny
                },
            )
            proj = projspec.Project(str(tmp_path))
        assert "python_code" in proj.specs
        assert "data_project" not in proj.specs

    def test_fraction_rule_large_data_in_code_project(self, tmp_path):
        # small code, large data -> data dominates by fraction and total size.
        # Use a .csv so intake can identify a datatype (datasets with no
        # identified datatype are dropped from the result).
        with temp_conf(**PROD_THRESHOLDS):
            write_data(
                tmp_path,
                {
                    "__init__.py": b"x = 1\n",
                    "data.csv": b"a,b,c\n" + b"1,2,3\n" * (4 * 1024 * 1024),  # >20MB
                },
            )
            proj = projspec.Project(str(tmp_path))
        assert "python_code" in proj.specs
        assert "data_project" in proj.specs

    def test_threshold_overridable_via_config(self, tmp_path):
        write_data(tmp_path, {f"{i:03d}.csv": 20 for i in range(1, 4)})
        # with the production play-size floor: rejected
        with temp_conf(**PROD_THRESHOLDS):
            proj = projspec.Project(str(tmp_path))
            assert "data_project" not in proj.specs
        # with a tiny play-size floor it should be detected
        with temp_conf(data_min_play_size=1):
            proj = projspec.Project(str(tmp_path))
            assert "data_project" in proj.specs


# ---------------------------------------------------------------------------
# DataProject consolidation + intake integration
# ---------------------------------------------------------------------------


class TestDataProjectDatasets:
    def test_image_series_consolidated(self, tmp_path):
        with temp_conf(**PROD_THRESHOLDS):
            write_data(
                tmp_path,
                {
                    f"{c}.gif": b"GIF89a" + b"\0" * 50_000
                    for c in ("red", "green", "blue")
                },
            )
            proj = projspec.Project(str(tmp_path))
        ds = datasets(proj)
        assert len(ds) == 1
        assert ds[0].name == "*.gif"
        assert ds[0].n_files == 3

    def test_directory_dataset_marker(self, tmp_path):
        # a _metadata marker means intake treats the whole dir as one dataset
        with temp_conf(**PROD_THRESHOLDS):
            write_data(
                tmp_path,
                {
                    "_metadata": 100,
                    "part-0.parquet": b"PAR1" + b"\0" * 200_000,
                    "part-1.parquet": b"PAR1" + b"\0" * 200_000,
                },
            )
            proj = projspec.Project(str(tmp_path))
        assert "data_project" in proj.specs
        ds = datasets(proj)
        # whole directory described as a single dataset
        assert len(ds) == 1

    @pytest.mark.skipif(not HAS_INTAKE, reason="intake not installed")
    def test_intake_identifies_csv(self, tmp_path):
        with temp_conf(**PROD_THRESHOLDS):
            rows = b"a,b,c\n" + b"".join(b"1,2,3\n" for _ in range(50_000))
            write_data(tmp_path, {f"{i:03d}.csv": rows for i in range(1, 4)})
            proj = projspec.Project(str(tmp_path))
        ds = datasets(proj)
        assert len(ds) == 1
        assert ds[0].datatype == "CSV"
        assert "table" in ds[0].structure

    def test_no_data_files_no_match(self, tmp_path):
        write_data(tmp_path, {"README.md": b"# hi\n", "setup.py": b"x=1\n"})
        proj = projspec.Project(str(tmp_path))
        assert "data_project" not in proj.specs


# ---------------------------------------------------------------------------
# match() / _is_data_ext unit checks
# ---------------------------------------------------------------------------


class TestDataExt:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("data.csv", True),
            ("table.parquet", True),
            ("image.png", True),
            ("archive.csv.gz", True),
            ("module.py", False),
            ("README.md", False),
            ("pyproject.toml", False),
            (".gitignore", False),
            ("Makefile", False),  # no extension
            ("config.ini", False),
        ],
    )
    def test_is_data_ext(self, name, expected):
        assert DataProject._is_data_ext(name) is expected


# ---------------------------------------------------------------------------
# HTML repr / thumbnail captured into Dataset.metadata
# ---------------------------------------------------------------------------


def _make_csv_bytes(rows: int = 200_000) -> bytes:
    """A CSV big enough to clear the single-big-file significance threshold."""
    body = "a,b,c\n" + "\n".join(f"{i},{i * 2},val{i}" for i in range(rows))
    return body.encode()


class TestDatasetHTMLOutput:
    """The DataProject pipeline should carry intake's ``html_repr`` and
    ``thumbnail`` through into ``Dataset.metadata`` when a reader discovers the
    underlying object."""

    @pytest.mark.skipif(not (HAS_INTAKE and HAS_PANDAS), reason="needs intake + pandas")
    def test_html_repr_for_tabular(self, tmp_path):
        # single file > data_min_file_size so it is described on its own and a
        # single-file pandas reader can discover it
        with temp_conf(**PROD_THRESHOLDS):
            write_data(tmp_path, {"big.csv": _make_csv_bytes()})
            proj = projspec.Project(str(tmp_path))
        ds = datasets(proj)
        assert len(ds) == 1
        meta = ds[0].metadata
        assert "PandasCSV" in meta.get("readers")
        assert meta.get("html_repr"), "expected html_repr in Dataset.metadata"
        assert "<table" in meta["html_repr"]
        # no image thumbnail for tabular data
        assert "thumbnail" not in meta

    @pytest.mark.skipif(not (HAS_INTAKE and HAS_PIL), reason="needs intake + Pillow")
    def test_thumbnail_for_image(self, tmp_path):
        import numpy as np
        from PIL import Image

        # a single big PNG so it is significant on its own
        with temp_conf(**PROD_THRESHOLDS):
            arr = (np.random.rand(400, 400, 3) * 255).astype("uint8")
            Image.fromarray(arr).save(os.path.join(str(tmp_path), "pic.png"))

            proj = projspec.Project(str(tmp_path))
        ds = datasets(proj)
        assert len(ds) == 1
        meta = ds[0].metadata
        assert ds[0].datatype == "PNG", ds[0].datatype
        assert meta.get("reader_used") == "PILImageReader", meta.get("reader_used")
        assert meta.get("thumbnail", "").startswith("data:image/png;base64,")

    @pytest.mark.skipif(not HAS_INTAKE, reason="intake not installed")
    def test_metadata_omits_missing_html_fields(self, tmp_path):
        # a glob of tiny-but-significant files that intake can type but for
        # which no reader produces a rich repr -> html_repr/thumbnail simply
        # absent, never None-valued keys
        with temp_conf(data_min_play_size=1):
            rows = b"a,b,c\n" + b"1,2,3\n" * 10
            write_data(tmp_path, {f"{i:03d}.csv": rows for i in range(5)})
            proj = projspec.Project(str(tmp_path))
        ds = datasets(proj)
        assert ds, "expected a dataset"
        for d in ds:
            assert d.datatype is not None
            assert "html_repr" not in d.metadata or isinstance(
                d.metadata["html_repr"], str
            )
            assert "thumbnail" not in d.metadata or isinstance(
                d.metadata["thumbnail"], str
            )
