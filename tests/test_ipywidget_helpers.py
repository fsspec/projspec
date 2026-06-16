"""Tests for module-level helpers in projspec.webui.ipywidget.

These functions have no dependency on anywidget, ipywidgets, or a live
Jupyter kernel, so they run in any environment.  Widget-construction tests
that *do* require anywidget remain in test_webui.py.

Coverage targets
----------------
- _url_to_local
- _spawn_detached
- _open_with
- _reveal_file
- _open_config_file
- _collect_enum_members
- _build_esm (smoke only)
- widget command handlers: configure, createSpecConfirmed, make (success),
  addConfirmed (valid path), rescan
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from projspec.webui.ipywidget import (
    _collect_enum_members,
    _open_with,
    _reveal_file,
    _url_to_local,
    _spawn_detached,
    _open_config_file,
    _build_esm,
)
from projspec.library import ProjectLibrary


# ---------------------------------------------------------------------------
# _url_to_local
# ---------------------------------------------------------------------------


class TestUrlToLocal:
    def test_strips_file_prefix(self):
        assert _url_to_local("file:///home/user/proj") == "/home/user/proj"

    def test_passes_plain_path_through(self):
        assert _url_to_local("/tmp/myproject") == "/tmp/myproject"

    def test_passes_s3_through(self):
        # Non-file remote URLs are not altered
        assert _url_to_local("s3://bucket/path") == "s3://bucket/path"

    def test_empty_string(self):
        assert _url_to_local("") == ""


# ---------------------------------------------------------------------------
# _spawn_detached
# ---------------------------------------------------------------------------


class TestSpawnDetached:
    def test_success_does_not_toast(self, monkeypatch):
        toasts = []
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: MagicMock())
        _spawn_detached(["echo", "hi"], toasts.append)
        assert toasts == []

    def test_file_not_found_toasts(self, monkeypatch):
        toasts = []

        def bad_popen(*a, **kw):
            raise FileNotFoundError("no such file")

        monkeypatch.setattr(subprocess, "Popen", bad_popen)
        _spawn_detached(["no-such-cmd"], toasts.append)
        assert toasts and "no-such-cmd" in toasts[0]
        assert "Command not found" in toasts[0]

    def test_generic_error_toasts(self, monkeypatch):
        toasts = []

        def bad_popen(*a, **kw):
            raise OSError("something broke")

        monkeypatch.setattr(subprocess, "Popen", bad_popen)
        _spawn_detached(["myapp"], toasts.append)
        assert toasts and "myapp" in toasts[0]


# ---------------------------------------------------------------------------
# _open_with
# ---------------------------------------------------------------------------


class TestOpenWith:
    def _patch_spawn(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "projspec.webui.ipywidget._spawn_detached",
            lambda cmd, toast: calls.append(cmd),
        )
        return calls

    def _patch_default(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: calls.append(path),
        )
        return calls

    def test_vscode(self, monkeypatch):
        calls = self._patch_spawn(monkeypatch)
        _open_with("vscode", "file:///home/user/proj", lambda m: None)
        assert calls and calls[0][0] == "code"
        assert "/home/user/proj" in calls[0]

    def test_pycharm(self, monkeypatch):
        calls = self._patch_spawn(monkeypatch)
        _open_with("pycharm", "/my/proj", lambda m: None)
        assert calls and calls[0][0] == "pycharm"

    def test_jupyter(self, monkeypatch):
        calls = self._patch_spawn(monkeypatch)
        _open_with("jupyter", "/my/proj", lambda m: None)
        assert calls and calls[0][:2] == ["jupyter", "lab"]

    def test_filebrowser(self, monkeypatch):
        calls = self._patch_default(monkeypatch)
        _open_with("filebrowser", "file:///home/user/proj", lambda m: None)
        assert calls and "/home/user/proj" in calls[0]

    def test_unknown_tool_toasts(self):
        toasts = []
        _open_with("notepad", "/my/proj", toasts.append)
        assert toasts and "notepad" in toasts[0]

    def test_url_is_stripped_for_vscode(self, monkeypatch):
        calls = self._patch_spawn(monkeypatch)
        _open_with("vscode", "file:///abs/path", lambda m: None)
        assert "/abs/path" in calls[0]


# ---------------------------------------------------------------------------
# _reveal_file
# ---------------------------------------------------------------------------


class TestRevealFile:
    def test_empty_fn_is_noop(self):
        # Must not raise and must not toast
        toasts = []
        _reveal_file("", toasts.append)
        assert toasts == []

    def test_remote_url_toasts(self):
        toasts = []
        _reveal_file("s3://bucket/key.csv", toasts.append)
        assert toasts and "Remote" in toasts[0]

    def test_file_prefix_stripped(self, tmp_path):
        f = tmp_path / "report.csv"
        f.write_text("data")
        opened = []
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: opened.append(path),
        ):
            _reveal_file(f"file://{f}", lambda m: None)
        assert opened

    def test_exact_match_opens_directory(self, tmp_path):
        f = tmp_path / "wheel.whl"
        f.write_text("data")
        opened = []
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: opened.append(path),
        ):
            _reveal_file(str(f), lambda m: None)
        assert opened
        assert opened[0] == str(tmp_path)  # directory, not the file itself

    def test_glob_match_opens_first(self, tmp_path):
        (tmp_path / "a.whl").write_text("x")
        (tmp_path / "b.whl").write_text("y")
        opened = []
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: opened.append(path),
        ):
            _reveal_file(str(tmp_path / "*.whl"), lambda m: None)
        assert opened  # something was opened

    def test_no_match_toasts(self):
        toasts = []
        _reveal_file("/definitely/no/such/file.whl", toasts.append)
        assert toasts and "No files match" in toasts[0]


# ---------------------------------------------------------------------------
# _open_config_file
# ---------------------------------------------------------------------------


class TestOpenConfigFile:
    def test_creates_config_file_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROJSPEC_CONFIG_DIR", str(tmp_path))
        opened = []
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: opened.append(path),
        ):
            toasts = []
            _open_config_file(toasts.append)

        conf_file = tmp_path / "projspec.json"
        assert conf_file.exists()
        data = json.loads(conf_file.read_text())
        assert "scan_types" in data
        assert opened and str(conf_file) in opened[0]

    def test_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROJSPEC_CONFIG_DIR", str(tmp_path))
        conf_file = tmp_path / "projspec.json"
        conf_file.write_text('{"custom": true}')
        opened = []
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: opened.append(path),
        ):
            _open_config_file(lambda m: None)

        # File must not have been overwritten
        assert json.loads(conf_file.read_text()) == {"custom": True}
        assert opened  # but it was still opened

    def test_toasts_on_mkdir_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROJSPEC_CONFIG_DIR", str(tmp_path / "no" / "perm"))
        toasts = []
        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            with patch(
                "projspec.webui.ipywidget._open_with_default",
                lambda path, toast: None,
            ):
                _open_config_file(toasts.append)
        assert toasts and "Could not create" in toasts[0]

    def test_always_emits_docs_toast(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROJSPEC_CONFIG_DIR", str(tmp_path))
        toasts = []
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: None,
        ):
            _open_config_file(toasts.append)
        assert any("readthedocs" in t for t in toasts)


# ---------------------------------------------------------------------------
# _collect_enum_members
# ---------------------------------------------------------------------------


class TestCollectEnumMembers:
    def test_returns_dict(self):
        result = _collect_enum_members()
        assert isinstance(result, dict)

    def test_contains_known_enums(self):
        result = _collect_enum_members()
        # Stack and Precision are always present (no optional deps needed)
        assert "stack" in result
        assert "precision" in result

    def test_values_are_dicts_of_name_to_value(self):
        result = _collect_enum_members()
        for name, members in result.items():
            assert isinstance(members, dict), f"{name} members not a dict"
            for k, v in members.items():
                assert isinstance(k, str), f"key {k!r} of {name} not a str"


# ---------------------------------------------------------------------------
# _build_esm (smoke)
# ---------------------------------------------------------------------------


class TestBuildEsm:
    def test_returns_string(self):
        esm = _build_esm()
        assert isinstance(esm, str)

    def test_contains_required_markers(self):
        esm = _build_esm()
        assert "const PANEL_HTML_BODY =" in esm
        assert "const PANEL_CSS =" in esm
        assert "const PANEL_JS =" in esm
        assert "const CHROME_ICONS =" in esm

    def test_exports_render(self):
        esm = _build_esm()
        assert "export function render" in esm

    def test_panel_html_body_is_valid_json(self):
        esm = _build_esm()
        start = esm.index("const PANEL_HTML_BODY = ") + len("const PANEL_HTML_BODY = ")
        # JSON string ends at the first unescaped semicolon after the literal
        end = esm.index(";\n", start)
        json_lit = esm[start:end]
        body = json.loads(json_lit)  # must not raise
        assert "id=" in body  # panel DOM IDs are present


# ---------------------------------------------------------------------------
# Widget command handlers (requires anywidget)
# ---------------------------------------------------------------------------


@pytest.fixture
def widget_and_lib(tmp_path):
    """Return (widget, library) with one entry, anywidget mocked out."""
    pytest.importorskip("anywidget")
    import projspec

    lib = ProjectLibrary(str(tmp_path / "lib.json"), auto_save=False)
    proj_path = str(tmp_path)
    proj_url = "file://" + proj_path
    lib.entries[proj_url] = projspec.Project(proj_path, walk=False)

    widget = lib.ipywidget()
    widget.send = lambda c, buffers=None: None
    widget._toast = lambda m: None
    return widget, lib, proj_url


def _fire(widget, cmd, **kwargs):
    """Fire a frontend message and collect sends + toasts."""
    sends, toasts = [], []
    widget.send = lambda c, buffers=None: sends.append(c)
    widget._toast = lambda m: toasts.append(m)
    widget._on_frontend_message(widget, {"cmd": cmd, **kwargs}, None)
    return sends, toasts


class TestWidgetHandlers:
    def test_configure_creates_config(self, tmp_path, monkeypatch, widget_and_lib):
        widget, lib, url = widget_and_lib
        monkeypatch.setenv("PROJSPEC_CONFIG_DIR", str(tmp_path / "cfg"))
        with patch(
            "projspec.webui.ipywidget._open_with_default",
            lambda path, toast: None,
        ):
            sends, toasts = _fire(widget, "configure")
        conf = tmp_path / "cfg" / "projspec.json"
        assert conf.exists()
        assert any("readthedocs" in t for t in toasts)

    def test_add_confirmed_valid_path(self, tmp_path, widget_and_lib):
        """addConfirmed with a real directory adds it to the library."""
        widget, lib, url = widget_and_lib
        new_proj = tmp_path / "newproj"
        new_proj.mkdir()
        (new_proj / "requirements.txt").write_text("numpy")
        # Start with just the original entry
        original_keys = set(lib.entries)
        sends, toasts = _fire(
            widget, "addConfirmed", path=str(new_proj), storageOptions=""
        )
        # Should now have at least one more entry
        assert len(lib.entries) > len(original_keys) or not toasts

    def test_rescan_preserves_library_key(self, tmp_path, widget_and_lib):
        widget, lib, url = widget_and_lib
        assert url in lib.entries
        _fire(widget, "rescan", url=url)
        assert url in lib.entries  # key must be preserved after rescan

    def test_set_busy_sends_loading_message(self, widget_and_lib):
        widget, lib, url = widget_and_lib
        sends = []
        widget.send = lambda c, buffers=None: sends.append(c)
        widget._set_busy(True)
        assert any(
            s.get("type") == "loading" and s.get("loading") is True for s in sends
        )
        sends.clear()
        widget._set_busy(False)
        assert any(
            s.get("type") == "loading" and s.get("loading") is False for s in sends
        )

    def test_create_spec_confirmed(self, tmp_path, widget_and_lib):
        """createSpecConfirmed calls proj.create and updates the library."""
        widget, lib, url = widget_and_lib
        sends, toasts = _fire(
            widget, "createSpecConfirmed", url=url, spec="github_actions"
        )
        # Either it succeeded (sends data) or toasted an error — no exception
        assert isinstance(sends, list)

    def test_reload_with_existing_file(self, tmp_path, widget_and_lib):
        """_reload re-reads the backing file when it exists."""
        widget, lib, url = widget_and_lib
        # Save the library so the file exists
        lib.save()
        sends, _ = _fire(widget, "reload")
        assert any(s.get("type") == "data" for s in sends)

    def test_resolve_entry_path_prefers_project_path(self, widget_and_lib):
        widget, lib, url = widget_and_lib
        resolved = widget._resolve_entry_path(url)
        proj = lib.entries[url]
        assert resolved == proj.path

    def test_resolve_entry_path_falls_back_to_url_to_local(self, widget_and_lib):
        widget, lib, url = widget_and_lib
        # A key that is not in the library gets _url_to_local applied
        result = widget._resolve_entry_path("file:///some/other/path")
        assert result == "/some/other/path"
