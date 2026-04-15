"""Tests for projspec.content.data_html — repr_text and repr_html.

These tests use a mock DataResource to avoid needing real data files on disk
for basic formatting checks, then run format-specific loader tests when the
required optional libraries are available.
"""

from __future__ import annotations

import io
import os
import tempfile
from unittest.mock import MagicMock

import pytest

import projspec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dr(
    path="mytable.parquet",
    fmt="parquet",
    modality="tabular",
    layout="flat",
    file_count=3,
    total_size=1024 * 512,
    schema=None,
    sample_path="",
    metadata=None,
):
    """Build a DataResource backed by a real Project (the repo root) but with
    controlled field values."""
    from projspec.content.data import DataResource

    mock_proj = MagicMock(spec=projspec.Project)
    # Use a real local filesystem via fsspec
    import fsspec

    mock_proj.fs = fsspec.filesystem("file")
    mock_proj.url = "/tmp"

    return DataResource(
        proj=mock_proj,
        path=path,
        format=fmt,
        modality=modality,
        layout=layout,
        file_count=file_count,
        total_size=total_size,
        schema=schema or {},
        sample_path=sample_path,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# repr_text tests
# ---------------------------------------------------------------------------


class TestReprText:
    def test_basic_fields_present(self):
        dr = _make_dr()
        text = repr(dr)
        assert "mytable.parquet" in text
        assert "parquet" in text
        assert "tabular" in text
        assert "files=3" in text

    def test_size_formatting(self):
        dr = _make_dr(total_size=1024)
        text = repr(dr)
        assert "KB" in text or "B" in text

    def test_size_zero(self):
        dr = _make_dr(total_size=0)
        text = repr(dr)
        assert "unknown" in text

    def test_schema_hint_dict(self):
        dr = _make_dr(schema={"col_a": "int64", "col_b": "float32", "col_c": "str"})
        text = repr(dr)
        assert "col_a" in text

    def test_schema_hint_many_fields(self):
        schema = {f"col_{i}": "int64" for i in range(10)}
        dr = _make_dr(schema=schema)
        text = repr(dr)
        assert "+7 more" in text

    def test_schema_hint_list(self):
        dr = _make_dr(schema=[{"name": "a"}, {"name": "b"}])
        text = repr(dr)
        assert "2 fields" in text

    def test_non_flat_layout_shown(self):
        dr = _make_dr(layout="hive")
        text = repr(dr)
        assert "hive" in text

    def test_flat_layout_hidden(self):
        dr = _make_dr(layout="flat")
        text = repr(dr)
        assert "layout" not in text

    def test_no_modality(self):
        dr = _make_dr(modality="")
        text = repr(dr)
        assert "modality" not in text

    def test_single_line(self):
        dr = _make_dr()
        text = repr(dr)
        assert "\n" not in text

    def test_path_shown(self):
        """repr_text must show the path field, not a separate name."""
        dr = _make_dr(path="part*.csv")
        text = repr(dr)
        assert "part*.csv" in text

    def test_dir_path_shown(self):
        dr = _make_dr(path="year=2024/")
        text = repr(dr)
        assert "year=2024/" in text


# ---------------------------------------------------------------------------
# repr_html tests
# ---------------------------------------------------------------------------


class TestReprHtml:
    def test_returns_string(self):
        dr = _make_dr()
        html = dr._repr_html_()
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_path(self):
        dr = _make_dr(path="my_dataset.parquet")
        html = dr._repr_html_()
        assert "my_dataset.parquet" in html

    def test_contains_glob_path(self):
        dr = _make_dr(path="part*.parquet")
        html = dr._repr_html_()
        assert "part*.parquet" in html

    def test_contains_dir_path(self):
        dr = _make_dr(path="year=2024/")
        html = dr._repr_html_()
        assert "year=2024/" in html

    def test_contains_format_badge(self):
        dr = _make_dr(fmt="parquet")
        html = dr._repr_html_()
        assert "parquet" in html

    def test_contains_modality_badge(self):
        dr = _make_dr(modality="tabular")
        html = dr._repr_html_()
        assert "tabular" in html

    def test_contains_file_count(self):
        dr = _make_dr(file_count=7)
        html = dr._repr_html_()
        assert "7" in html

    def test_contains_size(self):
        dr = _make_dr(total_size=2048)
        html = dr._repr_html_()
        assert "KB" in html or "B" in html

    def test_schema_dict_rendered(self):
        dr = _make_dr(schema={"id": "int64", "name": "string"})
        html = dr._repr_html_()
        assert "id" in html
        assert "int64" in html

    def test_schema_list_of_dicts_rendered(self):
        dr = _make_dr(
            schema=[
                {"name": "id", "type": "integer"},
                {"name": "val", "type": "number"},
            ]
        )
        html = dr._repr_html_()
        assert "id" in html
        assert "integer" in html

    def test_schema_empty_no_details(self):
        dr = _make_dr(schema={})
        html = dr._repr_html_()
        assert "Schema" not in html

    def test_no_preview_section_without_sample_path(self):
        dr = _make_dr(sample_path="")
        html = dr._repr_html_()
        assert "Preview" not in html

    def test_layout_badge_shown_for_hive(self):
        dr = _make_dr(layout="hive")
        html = dr._repr_html_()
        assert "hive" in html

    def test_layout_badge_hidden_for_flat(self):
        dr = _make_dr(layout="flat")
        html = dr._repr_html_()
        assert 'ps-badge-gray">flat<' not in html

    def test_html_structure(self):
        dr = _make_dr()
        html = dr._repr_html_()
        assert "ps-data-card" in html
        assert "ps-data-card-header" in html
        assert "ps-data-meta" in html

    def test_icon_present_for_known_modality(self):
        dr = _make_dr(modality="image")
        html = dr._repr_html_()
        # Image icon is 🖼 (&#x1F5BC;)
        assert "&#x1F5BC;" in html

    def test_icon_fallback_for_unknown_modality(self):
        dr = _make_dr(modality="")
        html = dr._repr_html_()
        # Fallback icon &#x1F5C2;
        assert "&#x1F5C2;" in html

    def test_large_schema_collapsed(self):
        schema = {f"col_{i}": "int64" for i in range(20)}
        dr = _make_dr(schema=schema)
        html = dr._repr_html_()
        # details element should NOT have open attribute when >8 fields
        assert (
            "<details  style" in html
            or 'details  style="margin-top:6px"' in html
            or 'details style="margin-top:6px">' in html
        )

    def test_small_schema_open(self):
        schema = {f"col_{i}": "int64" for i in range(4)}
        dr = _make_dr(schema=schema)
        html = dr._repr_html_()
        assert "<details open" in html


# ---------------------------------------------------------------------------
# Live preview tests — skipped when optional dependencies are absent
# ---------------------------------------------------------------------------


class TestLivePreviews:
    """Tests that write real files and verify the preview HTML is produced."""

    def _dr_for_file(self, path, fmt, modality):
        """Create a DataResource pointing at a real local file."""
        from projspec.content.data import DataResource
        import fsspec

        mock_proj = MagicMock(spec=projspec.Project)
        mock_proj.fs = fsspec.filesystem("file")
        mock_proj.url = os.path.dirname(path)
        return DataResource(
            proj=mock_proj,
            path=os.path.basename(path),
            format=fmt,
            modality=modality,
            layout="flat",
            file_count=1,
            total_size=os.path.getsize(path),
            schema={},
            sample_path=path,
        )

    def test_csv_preview(self, tmp_path):
        pd = pytest.importorskip("pandas")
        import pandas as pd

        path = str(tmp_path / "data.csv")
        pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]}).to_csv(path, index=False)
        dr = self._dr_for_file(path, "csv", "tabular")
        html = dr._repr_html_()
        assert "Preview" in html
        assert "<table" in html
        assert "x" in html
        assert "y" in html

    def test_csv_preview_uses_repr_html(self, tmp_path):
        """Preview HTML should come from pandas html, not hand-rolled."""
        pytest.importorskip("pandas")
        import pandas as pd

        path = str(tmp_path / "data.csv")
        pd.DataFrame({"x": range(20), "y": range(20)}).to_csv(path, index=False)
        dr = self._dr_for_file(path, "csv", "tabular")
        html = dr._repr_html_()
        # pandas wraps its table in a <div> with a dataframe class
        assert "dataframe" in html or "ps-df-wrap" in html

    def test_csv_preview_row_limit(self, tmp_path):
        """Only _PREVIEW_ROWS rows of data should appear, not all 50."""
        pytest.importorskip("pandas")
        import pandas as pd

        path = str(tmp_path / "big.csv")
        pd.DataFrame({"v": range(50)}).to_csv(path, index=False)
        dr = self._dr_for_file(path, "csv", "tabular")
        html = dr._repr_html_()
        # Extract just the preview section so CSS text doesn't interfere
        preview_start = html.find('<div class="ps-preview">')
        assert preview_start != -1, "no preview section found"
        preview_html = html[preview_start:]
        # The last row value (49) should not appear as a table cell
        assert "<td>49</td>" not in preview_html

    def test_parquet_preview(self, tmp_path):
        pytest.importorskip("pyarrow")
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = str(tmp_path / "data.parquet")
        table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        pq.write_table(table, path)
        dr = self._dr_for_file(path, "parquet", "tabular")
        html = dr._repr_html_()
        assert "Preview" in html
        assert "<table" in html
        assert "a" in html

    def test_parquet_preview_uses_pandas_repr(self, tmp_path):
        """Parquet preview must go through pandas html, not raw arrow HTML."""
        pytest.importorskip("pyarrow")
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = str(tmp_path / "data.parquet")
        table = pa.table({"col_a": range(10), "col_b": list("abcdefghij")})
        pq.write_table(table, path)
        dr = self._dr_for_file(path, "parquet", "tabular")
        html = dr._repr_html_()
        # pandas DataFrame.html includes class="dataframe"
        assert "dataframe" in html

    def test_parquet_preview_row_limit(self, tmp_path):
        """Parquet preview reads only one row group and slices to _PREVIEW_ROWS."""
        pytest.importorskip("pyarrow")
        import pyarrow as pa
        import pyarrow.parquet as pq
        from projspec.content.data_html import _PREVIEW_ROWS

        n_rows = 100
        path = str(tmp_path / "large.parquet")
        # Use a column whose values are unique strings unlikely to appear in CSS
        values = [f"row_{i:04d}" for i in range(n_rows)]
        pq.write_table(pa.table({"label": values}), path)
        dr = self._dr_for_file(path, "parquet", "tabular")
        html = dr._repr_html_()
        assert "row_0000" in html  # first row present
        assert "row_0099" not in html  # last row absent

    def test_arrow_ipc_preview(self, tmp_path):
        """Arrow IPC file: reads only the first batch, converts via pandas."""
        pytest.importorskip("pyarrow")
        import pyarrow as pa
        import pyarrow.ipc as ipc

        path = str(tmp_path / "data.arrow")
        table = pa.table({"x": [10, 20, 30], "y": ["a", "b", "c"]})
        with pa.OSFile(path, "wb") as sink:
            with ipc.new_file(sink, table.schema) as writer:
                writer.write_table(table)
        dr = self._dr_for_file(path, "arrow", "tabular")
        html = dr._repr_html_()
        assert "Preview" in html
        assert "dataframe" in html
        assert "x" in html

    def test_image_preview(self, tmp_path):
        pytest.importorskip("PIL")
        from PIL import Image

        path = str(tmp_path / "test.png")
        img = Image.new("RGB", (64, 64), color=(128, 0, 200))
        img.save(path)
        dr = self._dr_for_file(path, "png", "image")
        html = dr._repr_html_()
        assert "Preview" in html
        assert "data:image/png;base64," in html

    def test_numpy_preview(self, tmp_path):
        np = pytest.importorskip("numpy")
        import numpy as np

        path = str(tmp_path / "arr.npy")
        np.save(path, np.arange(20).reshape(4, 5))
        dr = self._dr_for_file(path, "numpy", "array")
        html = dr._repr_html_()
        assert "Preview" in html
        assert "shape" in html

    def test_numpy_preview_reads_header_shape(self, tmp_path):
        """The shape reported in the preview must match the actual array shape."""
        np = pytest.importorskip("numpy")
        import numpy as np

        path = str(tmp_path / "arr.npy")
        arr = np.zeros((7, 3), dtype="float32")
        np.save(path, arr)
        dr = self._dr_for_file(path, "numpy", "array")
        html = dr._repr_html_()
        assert "(7, 3)" in html
        assert "float32" in html

    def test_numpy_large_array_no_full_load(self, tmp_path):
        """Arrays above the 1 MB threshold should show shape/dtype without a data slice."""
        np = pytest.importorskip("numpy")
        import numpy as np

        path = str(tmp_path / "big.npy")
        # 512 * 512 * float64 = 2 MB > 1 MB threshold
        np.save(path, np.zeros((512, 512), dtype="float64"))
        dr = self._dr_for_file(path, "numpy", "array")
        html = dr._repr_html_()
        assert "(512, 512)" in html  # shape shown
        assert "float64" in html  # dtype shown
        # The data slice key ("preview") should NOT appear in the info table;
        # check the table cell content rather than the CSS class names
        assert ">preview<" not in html  # no <td>preview</td> row


# ---------------------------------------------------------------------------
# fmt_size helper
# ---------------------------------------------------------------------------


def test_fmt_size():
    from projspec.content.data_html import _fmt_size

    assert _fmt_size(0) == "unknown"
    assert _fmt_size(512) == "512 B"
    assert "KB" in _fmt_size(2048)
    assert "MB" in _fmt_size(2 * 1024 * 1024)
    assert "GB" in _fmt_size(3 * 1024**3)
