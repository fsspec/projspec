import json
import os

import pytest

import projspec
from projspec.content.data import DataResource
from projspec.utils import from_dict


def _data_project(tmp_path):
    """Return a projspec.Project rooted at *tmp_path* (no walk needed)."""
    return projspec.Project(str(tmp_path))


class TestDataDetection:
    def test_csv_detected(self, tmp_path):
        (tmp_path / "data.csv").write_text("x,y\n1,2\n3,4\n")
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    def test_parquet_detected(self, tmp_path):
        pytest.importorskip("pyarrow")
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.table({"a": [1, 2]}), str(tmp_path / "t.parquet"))
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    def test_no_data_files_not_detected(self, tmp_path):
        (tmp_path / "README.md").write_text("hello")
        (tmp_path / "config.json").write_text("{}")
        proj = _data_project(tmp_path)
        assert "data" not in proj.specs


class TestDataParse:
    def test_single_csv_resource(self, tmp_path):
        (tmp_path / "sales.csv").write_text("col1,col2\n1,a\n2,b\n")
        proj = _data_project(tmp_path)
        dr = proj.specs["data"].contents["data_resource"]
        assert isinstance(dr, DataResource)
        assert dr.path == "sales.csv"
        assert dr.format == "csv"
        assert dr.modality == "tabular"
        assert dr.file_count == 1

    def test_series_collated_to_glob_path(self, tmp_path):
        """part0.csv + part1.csv → path == 'part*.csv'"""
        for i in range(3):
            (tmp_path / f"part{i}.csv").write_text("x\n1\n")
        proj = _data_project(tmp_path)
        dr = proj.specs["data"].contents["data_resource"]
        assert isinstance(dr, DataResource)
        assert dr.path == "part*.csv"
        assert dr.file_count == 3

    def test_distinct_csv_files_separate_resources(self, tmp_path):
        """users.csv and orders.csv differ alphabetically → two resources."""
        (tmp_path / "users.csv").write_text("id\n1\n")
        (tmp_path / "orders.csv").write_text("id\n1\n")
        proj = _data_project(tmp_path)
        dr_map = proj.specs["data"].contents["data_resource"]
        # Two separate DataResource objects, keyed in an AttrDict
        assert len(dr_map) == 2
        paths = {dr_map[k].path for k in dr_map}
        assert "users.csv" in paths
        assert "orders.csv" in paths

    def test_sample_path_is_full_path(self, tmp_path):
        csv = tmp_path / "data.csv"
        csv.write_text("x\n1\n")
        proj = _data_project(tmp_path)
        dr = proj.specs["data"].contents["data_resource"]
        assert dr.sample_path == str(csv)

    def test_total_size_nonzero(self, tmp_path):
        content = "x,y\n" + "\n".join(f"{i},{i}" for i in range(20))
        (tmp_path / "nums.csv").write_text(content)
        proj = _data_project(tmp_path)
        dr = proj.specs["data"].contents["data_resource"]
        assert dr.total_size > 0


class TestDataResourceToDict:
    def _make_dr(self, tmp_path):
        (tmp_path / "items.csv").write_text("id,val\n1,a\n2,b\n")
        proj = _data_project(tmp_path)
        return proj.specs["data"].contents["data_resource"]

    def test_compact_omits_klass(self, tmp_path):
        dr = self._make_dr(tmp_path)
        d = dr.to_dict(compact=True)
        assert "klass" not in d

    def test_compact_omits_html(self, tmp_path):
        """compact=True is for human/console output — _html must be absent."""
        dr = self._make_dr(tmp_path)
        d = dr.to_dict(compact=True)
        assert "_html" not in d


class TestDataResourceRoundTrip:
    def _roundtrip(self, dr):
        """Serialise to JSON and rehydrate, returning the new DataResource."""
        d = dr.to_dict(compact=False)
        js = json.dumps(d)
        d2 = json.loads(js)
        return from_dict(d2, proj=dr.proj)

    def _make_dr(self, tmp_path):
        (tmp_path / "orders.csv").write_text("order_id,amount\n1,99\n2,42\n")
        proj = _data_project(tmp_path)
        return proj.specs["data"].contents["data_resource"]

    def test_roundtrip_returns_dataresource(self, tmp_path):
        dr2 = self._roundtrip(self._make_dr(tmp_path))
        assert isinstance(dr2, DataResource)

    def test_roundtrip_preserves_path(self, tmp_path):
        dr2 = self._roundtrip(self._make_dr(tmp_path))
        assert dr2.path == "orders.csv"

    def test_roundtrip_preserves_format(self, tmp_path):
        dr2 = self._roundtrip(self._make_dr(tmp_path))
        assert dr2.format == "csv"

    def test_roundtrip_preserves_modality(self, tmp_path):
        dr2 = self._roundtrip(self._make_dr(tmp_path))
        assert dr2.modality == "tabular"

    def test_roundtrip_preserves_file_count(self, tmp_path):
        dr2 = self._roundtrip(self._make_dr(tmp_path))
        assert dr2.file_count == 1

    def test_roundtrip_preserves_total_size(self, tmp_path):
        dr = self._make_dr(tmp_path)
        dr2 = self._roundtrip(dr)
        assert dr2.total_size == dr.total_size

    def test_roundtrip_preserves_schema(self, tmp_path):
        pytest.importorskip("pyarrow")
        import pyarrow as pa, pyarrow.parquet as pq

        pq.write_table(
            pa.table({"col_a": [1, 2, 3], "col_b": ["x", "y", "z"]}),
            str(tmp_path / "data.parquet"),
        )
        proj = _data_project(tmp_path)
        dr = proj.specs["data"].contents["data_resource"]
        dr2 = self._roundtrip(dr)
        assert dr2.schema == dr.schema

    def test_roundtrip_html_matches_original(self, tmp_path):
        """_repr_html_() on the rehydrated object must equal the original render."""
        dr = self._make_dr(tmp_path)
        html_original = dr._repr_html_()
        dr2 = self._roundtrip(dr)
        assert dr2._repr_html_() == html_original

    def test_roundtrip_html_cached_without_rerender(self, tmp_path):
        """After from_dict the HTML is already in _html — no re-render occurs."""
        dr = self._make_dr(tmp_path)
        html_original = dr._repr_html_()
        d = dr.to_dict(compact=False)
        d2 = json.loads(json.dumps(d))
        dr2 = from_dict(d2, proj=dr.proj)

        # Confirm _html is set directly on the instance (not via lazy render)
        assert (
            "_html" in dr2.__dict__
        ), "_html should be in instance __dict__ after from_dict"
        assert dr2.__dict__["_html"] == html_original

    def test_roundtrip_html_survives_missing_sample_path(self, tmp_path):
        """After rehydration, _repr_html_() must work even if sample_path
        no longer resolves (e.g. moved to a different machine)."""
        dr = self._make_dr(tmp_path)
        # Trigger render with a real file, then remove the file
        html_original = dr._repr_html_()
        os.remove(dr.sample_path)

        dr2 = self._roundtrip(dr)
        # sample_path is gone — but HTML was cached in the dict
        assert dr2._repr_html_() == html_original


class TestDataConditionalParse:
    """Tests for the 'other project types present' guard in Data.parse()."""

    def _big_csv(self, path, rows=500):
        """Write a CSV large enough to dominate byte counts."""
        content = "id,value\n" + "\n".join(f"{i},{i * 2}" for i in range(rows))
        path.write_text(content)

    def test_pure_data_dir_no_sentinel(self, tmp_path):
        """No sentinel → Data always parsed regardless of byte ratios."""
        (tmp_path / "data.csv").write_text("x\n1\n")
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    def test_datapackage_companion_not_a_sentinel(self, tmp_path):
        """datapackage.json is a compatible companion — not a sentinel."""
        self._big_csv(tmp_path / "data.csv")
        (tmp_path / "datapackage.json").write_text('{"resources": []}')
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    def test_dvc_companion_not_a_sentinel(self, tmp_path):
        """catalog.yaml (IntakeCatalog / DVCRepo companion) is not a sentinel."""
        self._big_csv(tmp_path / "data.csv")
        (tmp_path / "catalog.yaml").write_text("sources: {}")
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    def test_sentinel_present_data_majority(self, tmp_path):
        """Sentinel is present, but data files are the majority of bytes → Data parsed."""
        self._big_csv(tmp_path / "data.csv")  # large data file
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nname='x'\n"
        )  # tiny sentinel
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    def test_sentinel_present_data_majority_parquet(self, tmp_path):
        pytest.importorskip("pyarrow")
        import pyarrow as pa, pyarrow.parquet as pq

        pq.write_table(
            pa.table({"x": list(range(1000)), "y": list(range(1000))}),
            str(tmp_path / "data.parquet"),
        )
        (tmp_path / "Cargo.toml").write_text('[package]\nname="x"\n')
        proj = _data_project(tmp_path)
        assert "data" in proj.specs

    # -- mixed dirs where non-data dominates --

    def test_sentinel_present_code_majority(self, tmp_path):
        """Sentinel present and code files dominate → Data spec suppressed."""
        # Large Python source file
        (tmp_path / "main.py").write_text("x = 1\n" * 5000)
        # Tiny CSV
        (tmp_path / "tiny.csv").write_text("a,b\n1,2\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        proj = _data_project(tmp_path)
        assert "data" not in proj.specs

    def test_sentinel_present_equal_split_not_majority(self, tmp_path):
        """Exactly 50/50 bytes is not a majority — Data suppressed."""
        payload = "x" * 1000
        (tmp_path / "code.py").write_text(payload)
        (tmp_path / "data.csv").write_text(payload)
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        proj = _data_project(tmp_path)
        assert "data" not in proj.specs

    # -- helpers / unit tests for the private methods --

    def test_has_non_data_sentinels_true(self, tmp_path):
        from projspec.proj.data_dir import Data

        (tmp_path / "data.csv").write_text("x\n1\n")
        (tmp_path / "pyproject.toml").write_text("")
        proj = object.__new__(projspec.Project)
        import fsspec

        proj.fs = fsspec.filesystem("file")
        proj.url = str(tmp_path)
        proj.__dict__["basenames"] = {
            e["name"].rsplit("/", 1)[-1]: e["name"]
            for e in proj.fs.ls(str(tmp_path), detail=True)
        }
        proj.__dict__["filelist"] = proj.fs.ls(str(tmp_path), detail=True)
        inst = Data.__new__(Data)
        inst.proj = proj
        assert inst._has_non_data_sentinels() is True

    def test_has_non_data_sentinels_false(self, tmp_path):
        from projspec.proj.data_dir import Data

        (tmp_path / "data.csv").write_text("x\n1\n")
        proj = object.__new__(projspec.Project)
        import fsspec

        proj.fs = fsspec.filesystem("file")
        proj.url = str(tmp_path)
        proj.__dict__["basenames"] = {
            e["name"].rsplit("/", 1)[-1]: e["name"]
            for e in proj.fs.ls(str(tmp_path), detail=True)
        }
        proj.__dict__["filelist"] = proj.fs.ls(str(tmp_path), detail=True)
        inst = Data.__new__(Data)
        inst.proj = proj
        assert inst._has_non_data_sentinels() is False

    def test_data_bytes_majority_true(self, tmp_path):
        from projspec.proj.data_dir import Data

        self._big_csv(tmp_path / "data.csv")
        (tmp_path / "small.py").write_text("x = 1\n")
        proj = object.__new__(projspec.Project)
        import fsspec

        proj.fs = fsspec.filesystem("file")
        proj.url = str(tmp_path)
        proj.__dict__["filelist"] = proj.fs.ls(str(tmp_path), detail=True)
        inst = Data.__new__(Data)
        inst.proj = proj
        assert inst._data_bytes_majority() is True

    def test_data_bytes_majority_false(self, tmp_path):
        from projspec.proj.data_dir import Data

        (tmp_path / "main.py").write_text("x = 1\n" * 5000)
        (tmp_path / "tiny.csv").write_text("a\n1\n")
        proj = object.__new__(projspec.Project)
        import fsspec

        proj.fs = fsspec.filesystem("file")
        proj.url = str(tmp_path)
        proj.__dict__["filelist"] = proj.fs.ls(str(tmp_path), detail=True)
        inst = Data.__new__(Data)
        inst.proj = proj
        assert inst._data_bytes_majority() is False
