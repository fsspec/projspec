"""Text and HTML representations for DataResource.

``repr_text``  — plain-text one-liner for ``__repr__``.
``repr_html``  — rich HTML card for Jupyter's ``_repr_html_`` protocol.

The HTML card has two sections:

1. **Metadata table** — name, format, modality, layout, file count, total size,
   schema (collapsed by default when it has many entries).

2. **Preview** (optional) — a lightweight peek at the actual data using
   whichever optional library is available for the format.  The section is
   silently omitted when no suitable loader can be imported.

All loader imports are guarded with ``try/except ImportError`` so that the
representation degrades gracefully when optional dependencies are absent.
"""

from __future__ import annotations

import base64
import html as _html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from projspec.content.data import DataResource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODALITY_ICON: dict[str, str] = {
    "tabular": "&#x1F4CA;",  # 📊
    "image": "&#x1F5BC;",  # 🖼
    "array": "&#x1F9EE;",  # 🧮
    "timeseries": "&#x1F4C8;",  # 📈
    "geospatial": "&#x1F30D;",  # 🌍
    "model": "&#x1F9E0;",  # 🧠
    "nested": "&#x1F4C2;",  # 📂
    "document": "&#x1F4C4;",  # 📄
    "video": "&#x1F3AC;",  # 🎬
    "archive": "&#x1F4E6;",  # 📦
    "": "&#x1F5C2;",  # 🗂
}


def _fmt_size(n: int) -> str:
    """Human-readable byte count."""
    if n <= 0:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def _esc(s: object) -> str:
    return _html.escape(str(s))


# ---------------------------------------------------------------------------
# Plain-text repr
# ---------------------------------------------------------------------------


def repr_text(dr: "DataResource") -> str:
    """One-line text representation of a DataResource."""
    size = _fmt_size(dr.total_size)
    schema_hint = ""
    if isinstance(dr.schema, dict) and dr.schema:
        keys = list(dr.schema)[:3]
        extra = f", +{len(dr.schema) - 3} more" if len(dr.schema) > 3 else ""
        schema_hint = f" [{', '.join(str(k) for k in keys)}{extra}]"
    elif isinstance(dr.schema, list) and dr.schema:
        schema_hint = f" [{len(dr.schema)} fields]"

    parts = [
        f"DataResource({dr.path!r}",
        f"format={dr.format!r}",
    ]
    if dr.modality:
        parts.append(f"modality={dr.modality!r}")
    if dr.layout and dr.layout not in ("flat", ""):
        parts.append(f"layout={dr.layout!r}")
    parts.append(f"files={dr.file_count}")
    parts.append(f"size={size}")
    if schema_hint:
        parts.append(f"schema={schema_hint.strip()}")
    return ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# HTML repr
# ---------------------------------------------------------------------------

# No inline styles — class names are present for external styling by the
# host environment (Jupyter, VS Code webview, etc.).
_CARD_CSS = ""


def repr_html(dr: "DataResource") -> str:
    """Rich HTML card representation of a DataResource."""
    icon = _MODALITY_ICON.get(dr.modality, _MODALITY_ICON[""])
    size_str = _fmt_size(dr.total_size)

    # ---- header ----
    modality_badge = (
        f'<span class="ps-badge">{_esc(dr.modality)}</span>' if dr.modality else ""
    )
    format_badge = f'<span class="ps-badge-gray">{_esc(dr.format)}</span>'
    layout_badge = (
        f'<span class="ps-badge-gray">{_esc(dr.layout)}</span>'
        if dr.layout and dr.layout not in ("flat", "")
        else ""
    )

    header = (
        f'<div class="ps-data-card-header">'
        f'<span class="ps-icon">{icon}</span>'
        f'<span class="ps-name">{_esc(dr.path)}</span>'
        f"{modality_badge}{format_badge}{layout_badge}"
        f"</div>"
    )

    # ---- metadata table ----
    meta_rows = [
        ("Files", str(dr.file_count)),
        ("Total size", size_str),
    ]

    meta_html_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td>{v}</td></tr>" for k, v in meta_rows
    )
    schema_html = _render_schema(dr.schema)

    meta_section = (
        f'<div class="ps-data-meta">'
        f"<table>{meta_html_rows}</table>"
        f"{schema_html}"
        f"</div>"
    )

    # ---- preview ----
    preview_html = _build_preview(dr)
    preview_section = ""
    if preview_html:
        preview_section = (
            f'<div class="ps-preview">'
            f'<div class="ps-preview-title">Preview</div>'
            f"{preview_html}"
            f"</div>"
        )

    return (
        _CARD_CSS
        + f'<div class="ps-data-card">'
        + header
        + meta_section
        + preview_section
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Schema rendering
# ---------------------------------------------------------------------------


def _render_schema(schema: dict | list) -> str:
    """Render schema as a collapsible HTML block."""
    if not schema:
        return ""

    if isinstance(schema, dict):
        # Tabular-style {col: dtype} or structural {"variables": [...], ...}
        rows = ""
        for k, v in schema.items():
            rows += f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>"
        table = (
            f'<table class="ps-schema-table">'
            f"<tr><th>Field</th><th>Type / Value</th></tr>"
            f"{rows}"
            f"</table>"
        )
        n = len(schema)
        open_attr = "open" if n <= 8 else ""
        return (
            f'<details {open_attr} style="margin-top:6px">'
            f'<summary class="ps-schema-toggle">Schema ({n} {"field" if n == 1 else "fields"})</summary>'
            f"{table}</details>"
        )

    if isinstance(schema, list):
        # List-of-dicts (frictionless style) or plain list
        if schema and isinstance(schema[0], dict):
            # Render each dict as a row; use union of all keys as columns
            all_keys: list[str] = []
            for item in schema:
                for k in item:
                    if k not in all_keys:
                        all_keys.append(k)
            header_row = "".join(f"<th>{_esc(k)}</th>" for k in all_keys)
            body_rows = ""
            for item in schema:
                cells = "".join(f"<td>{_esc(item.get(k, ''))}</td>" for k in all_keys)
                body_rows += f"<tr>{cells}</tr>"
            table = (
                f'<table class="ps-schema-table">'
                f"<tr>{header_row}</tr>{body_rows}</table>"
            )
        else:
            items_html = "".join(f"<li>{_esc(s)}</li>" for s in schema)
            table = f"<ul style='margin:4px 0;padding-left:18px'>{items_html}</ul>"

        n = len(schema)
        open_attr = "open" if n <= 8 else ""
        return (
            f'<details {open_attr} style="margin-top:6px">'
            f'<summary class="ps-schema-toggle">Schema ({n} {"field" if n == 1 else "fields"})</summary>'
            f"{table}</details>"
        )

    return ""


# ---------------------------------------------------------------------------
# Preview builders — one function per modality family, all return HTML str
# or None when no loader is available.
# ---------------------------------------------------------------------------

#: How many rows to show in tabular previews.
_PREVIEW_ROWS = 5


def _obj_to_preview_html(obj) -> str:
    """Return the richest HTML string available for *obj*.

    Tries ``_repr_html_()`` first (pandas DataFrame, polars DataFrame, xarray
    Dataset, …), then falls back to ``__repr__``.  The result is always
    wrapped in a ``<div>`` so callers can rely on valid HTML.
    """
    if hasattr(obj, "_repr_html_"):
        try:
            h = obj._repr_html_()
            if h:
                return f'<div class="ps-df-wrap">{h}</div>'
        except Exception:
            pass
    return f'<div class="ps-df-wrap"><pre>{_esc(repr(obj))}</pre></div>'


def _build_preview(dr: "DataResource") -> str | None:
    """Return an HTML preview fragment, or None if not possible."""
    fmt = dr.format
    modality = dr.modality
    sample = dr.sample_path if dr.sample_path else None

    if sample is None:
        return None

    if modality == "tabular":
        return _preview_tabular(dr, sample)
    if modality == "image":
        return _preview_image(dr, sample)
    if modality == "array":
        return _preview_array(dr, sample)
    if modality == "timeseries" and fmt in ("wav", "flac", "mp3", "ogg"):
        return _preview_audio(dr, sample)
    return None


# --- tabular ---


def _preview_tabular(dr: "DataResource", path: str) -> str | None:
    fmt = dr.format
    fs = dr.proj.fs

    try:
        if fmt == "parquet":
            return _preview_parquet(fs, path)
        if fmt == "csv":
            return _preview_csv(fs, path)
        if fmt in ("tsv", "psv"):
            sep = "\t" if fmt == "tsv" else "|"
            return _preview_csv(fs, path, sep=sep)
        if fmt == "arrow":
            return _preview_arrow(fs, path)
        if fmt == "jsonlines":
            return _preview_jsonlines(fs, path)
        if fmt == "excel":
            return _preview_excel(fs, path)
        if fmt in ("sqlite", "duckdb"):
            return _preview_sql(fs, path, fmt)
        if fmt == "orc":
            return _preview_orc(fs, path)
    except Exception:
        pass
    return None


def _preview_parquet(fs, path: str) -> str | None:
    """Read only the first row group (or N rows from it) — no full file scan."""
    try:
        import pyarrow.parquet as pq

        with fs.open(path, "rb") as fh:
            pf = pq.ParquetFile(fh)
            # read_row_group reads one row group's pages, not the whole file
            batch = pf.read_row_group(0)
            if batch.num_rows > _PREVIEW_ROWS:
                batch = batch.slice(0, _PREVIEW_ROWS)
        # Convert to pandas so we get _repr_html_() for free
        df = batch.to_pandas()
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    try:
        # polars can read a row-count-limited slice without decoding the rest
        import polars as pl

        with fs.open(path, "rb") as fh:
            df = pl.read_parquet(fh, n_rows=_PREVIEW_ROWS)
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    return None


def _preview_csv(fs, path: str, sep: str = ",") -> str | None:
    # pandas nrows= stops parsing after N data lines — minimal I/O
    try:
        import pandas as pd

        with fs.open(path, "r", encoding="utf-8", errors="replace") as fh:
            df = pd.read_csv(fh, sep=sep, nrows=_PREVIEW_ROWS)
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    try:
        import polars as pl

        with fs.open(path, "rb") as fh:
            df = pl.read_csv(fh, n_rows=_PREVIEW_ROWS, separator=sep)
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    return None


def _preview_arrow(fs, path: str) -> str | None:
    """Read only the first record batch — no full file deserialisation."""
    try:
        import pyarrow.ipc as ipc

        with fs.open(path, "rb") as fh:
            try:
                # IPC file format: random-access; read just batch 0
                reader = ipc.open_file(fh)
                batch = reader.get_batch(0)
            except Exception:
                fh.seek(0)
                # IPC stream format: sequential; read just the first batch
                reader = ipc.open_stream(fh)
                batch = reader.read_next_batch()
        if batch.num_rows > _PREVIEW_ROWS:
            batch = batch.slice(0, _PREVIEW_ROWS)
        df = batch.to_pandas()
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    return None


def _preview_jsonlines(fs, path: str) -> str | None:
    # pandas nrows= stops reading after N lines
    try:
        import pandas as pd

        with fs.open(path, "r", encoding="utf-8", errors="replace") as fh:
            df = pd.read_json(fh, lines=True, nrows=_PREVIEW_ROWS)
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    return None


def _preview_excel(fs, path: str) -> str | None:
    # nrows= limits rows read from the sheet
    try:
        import pandas as pd

        with fs.open(path, "rb") as fh:
            df = pd.read_excel(fh, nrows=_PREVIEW_ROWS)
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    return None


def _preview_sql(fs, path: str, fmt: str) -> str | None:
    # SQLite/DuckDB: only works with a local path (not a remote FS)
    try:
        if getattr(fs, "protocol", "file") not in ("file", "local", ""):
            return None
        if fmt == "duckdb":
            try:
                import duckdb

                con = duckdb.connect(path, read_only=True)
                tables = con.execute("SHOW TABLES").fetchall()
                if not tables:
                    return None
                tname = tables[0][0]
                df = con.execute(
                    f'SELECT * FROM "{tname}" LIMIT {_PREVIEW_ROWS}'
                ).fetchdf()
                return _obj_to_preview_html(df)
            except ImportError:
                pass
        else:
            import sqlite3
            import pandas as pd

            con = sqlite3.connect(path)
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            if not tables:
                return None
            tname = tables[0][0]
            df = pd.read_sql(f'SELECT * FROM "{tname}" LIMIT {_PREVIEW_ROWS}', con)
            return _obj_to_preview_html(df)
    except Exception:
        pass
    return None


def _preview_orc(fs, path: str) -> str | None:
    try:
        import pyarrow.orc as orc

        with fs.open(path, "rb") as fh:
            table = orc.ORCFile(fh).read().slice(0, _PREVIEW_ROWS)
        df = table.to_pandas()
        return _obj_to_preview_html(df)
    except ImportError:
        pass
    return None


# --- image ---


def _preview_image(dr: "DataResource", path: str) -> str | None:
    try:
        from PIL import Image
        import io

        fs = dr.proj.fs
        with fs.open(path, "rb") as fh:
            raw: bytes = fh.read()

        img = Image.open(io.BytesIO(raw))
        img.thumbnail((600, 200))

        buf = io.BytesIO()
        # Save as PNG for lossless display regardless of source format
        rgb = img.convert("RGB") if img.mode not in ("RGB", "L", "RGBA") else img
        rgb.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        w, h = img.size
        schema = dr.schema if isinstance(dr.schema, dict) else {}
        info = f"{schema.get('width', w)}×{schema.get('height', h)}"
        if "mode" in schema:
            info += f", mode={schema['mode']}"

        return (
            f'<div><img class="ps-img-preview" src="data:image/png;base64,{b64}" '
            f'alt="{_esc(dr.path)}" />'
            f'<div style="font-size:11px;color:#666;margin-top:3px">{_esc(info)}</div></div>'
        )
    except ImportError:
        pass
    except Exception:
        pass
    return None


# --- array ---


def _preview_array(dr: "DataResource", path: str) -> str | None:
    fmt = dr.format
    fs = dr.proj.fs

    if fmt == "numpy":
        return _preview_numpy(fs, path)
    if fmt == "hdf5":
        return _preview_hdf5(fs, path)
    if fmt == "netcdf":
        return _preview_netcdf(fs, path)
    if fmt == "zarr":
        return _preview_zarr(dr)
    return None


def _array_info_html(info: dict) -> str:
    rows = "".join(
        f"<tr><td><strong>{_esc(k)}</strong></td><td>{_esc(v)}</td></tr>"
        for k, v in info.items()
    )
    return f'<table class="ps-schema-table" style="margin-top:0">{rows}</table>'


def _preview_numpy(fs, path: str) -> str | None:
    """Read only the .npy header to get shape/dtype, then load a minimal slice."""
    try:
        import numpy as np
        import numpy.lib.format as nf
        import io

        with fs.open(path, "rb") as fh:
            raw_header = fh.read(512)  # header is always ≤ 512 bytes

        buf = io.BytesIO(raw_header)
        nf.read_magic(buf)
        # read_array_header_1_0 is the stable API across numpy versions;
        # newer numpy also exposes read_array_header — try both.
        try:
            shape, _, dtype = nf.read_array_header_1_0(buf)
        except AttributeError:
            shape, _, dtype = nf.read_array_header(buf)  # type: ignore[attr-defined]

        info: dict = {"shape": str(shape), "dtype": str(dtype)}

        # Load the full array only when it's small enough (≤ 1 MB heuristic)
        # or when we can cheaply slice the first N rows.
        try:
            total_elements = 1
            for s in shape:
                total_elements *= s
            item_size = np.dtype(dtype).itemsize
            if total_elements * item_size <= 1_048_576:
                with fs.open(path, "rb") as fh:
                    arr = np.load(io.BytesIO(fh.read()), allow_pickle=False)
                sliced = arr[:_PREVIEW_ROWS] if arr.ndim >= 1 else arr
                info["preview"] = repr(sliced)
        except Exception:
            pass

        return _array_info_html(info)
    except Exception:
        pass
    return None


def _preview_hdf5(fs, path: str) -> str | None:
    """Open the HDF5 file and read only metadata — no array data loaded."""
    try:
        import h5py

        with fs.open(path, "rb") as fh:
            with h5py.File(fh, "r") as f:
                keys = list(f.keys())[:8]
                info: dict = {"top-level keys": ", ".join(keys) or "(none)"}
                for k in keys[:3]:
                    obj = f[k]
                    if hasattr(obj, "shape"):
                        info[k] = f"shape={obj.shape}, dtype={obj.dtype}"
                    else:
                        info[k] = f"group ({len(obj)} members)"
        return _array_info_html(info)
    except ImportError:
        pass
    return None


def _preview_netcdf(fs, path: str) -> str | None:
    """Open the dataset lazily (no data loaded) and render its repr."""
    try:
        import xarray as xr

        with fs.open(path, "rb") as fh:
            # engine="scipy" reads lazily; no array data is decoded here
            ds = xr.open_dataset(fh, engine="scipy")
        # xarray Dataset has a rich _repr_html_()
        return _obj_to_preview_html(ds)
    except ImportError:
        pass
    return None


def _preview_zarr(dr: "DataResource") -> str | None:
    """Use the schema cached at parse time — zero extra I/O."""
    schema = dr.schema
    if not schema or not isinstance(schema, dict):
        return None
    info = {}
    if "arrays" in schema:
        info["arrays"] = ", ".join(str(a) for a in schema["arrays"][:8]) or "(none)"
    if "groups" in schema:
        info["groups"] = ", ".join(str(g) for g in schema["groups"][:8]) or "(none)"
    if "attrs" in schema:
        info["attrs"] = str(dict(list(schema["attrs"].items())[:4]))
    return _array_info_html(info) if info else None


# --- audio ---


def _preview_audio(dr: "DataResource", path: str) -> str | None:
    """Read only the audio file header — no sample data loaded."""
    try:
        import soundfile as sf

        fs = dr.proj.fs
        with fs.open(path, "rb") as fh:
            info = sf.info(fh)
        details = {
            "sample rate": f"{info.samplerate} Hz",
            "channels": str(info.channels),
            "duration": f"{info.frames / info.samplerate:.2f} s",
            "format": info.format,
            "subtype": info.subtype,
        }
        return _array_info_html(details)
    except ImportError:
        pass
    return None
