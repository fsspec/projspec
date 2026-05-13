"""Tests for the shared webui package and the ipywidget hook.

These tests don't require a browser or a real Jupyter kernel: we just
check that the static resources are self-consistent and that the
``ProjectLibrary.ipywidget`` plumbing degrades gracefully when the
optional ``anywidget`` dependency is unavailable.
"""

from __future__ import annotations

import json

import pytest

from projspec.library import ProjectLibrary
from projspec.webui import (
    chrome_icons,
    get_panel_css,
    get_panel_html,
    get_panel_js,
    resource_path,
)


def test_resources_exist():
    for name in ("panel.html", "panel.css", "panel.js", "chrome.json"):
        assert resource_path(name).exists(), name


def test_chrome_icons_keys():
    icons = chrome_icons()
    # These keys are referenced by panel.js and panel.html - if any is
    # missing the shared UI breaks across all frontends.
    required = {
        "add",
        "reload",
        "configure",
        "search",
        "clear",
        "spinner",
        "chevron_up",
        "chevron_down",
        "kebab",
        "play",
        "info",
        "reveal",
    }
    assert required <= set(icons)


def test_panel_html_resolves_placeholders():
    html = get_panel_html()
    # All icon markers should have been substituted.
    assert "<!--ICON:" not in html
    assert "<!--EXTRA_HEAD-->" not in html
    assert "<!--BOOTSTRAP-->" not in html
    assert "/*__CSS__*/" not in html
    assert "/*__JS__*/" not in html
    # Structural elements that the shared JS reaches for must be present.
    for ident in (
        'id="projects"',
        'id="search"',
        'id="details-list"',
        'id="modal-overlay"',
    ):
        assert ident in html, ident


def test_panel_html_with_bootstrap_and_extra_head():
    extra = '<script src="qrc:///foo.js"></script>'
    boot = "<script>window.projspecTransport = null;</script>"
    html = get_panel_html(extra_head=extra, bootstrap_js=boot, embedded=True)
    assert extra in html
    assert boot in html
    assert 'class="embedded"' in html


def test_panel_css_and_js_are_strings():
    assert get_panel_css().strip().startswith("/*")
    assert "projspecTransport" in get_panel_js()


# ---------------------------------------------------------------------------
#  ipywidget hook
# ---------------------------------------------------------------------------


def test_ipywidget_degrades_when_anywidget_missing(monkeypatch, tmp_path):
    """Without anywidget / ipywidgets, .ipywidget() raises ImportError
    and _ipython_display_ falls back to printing the repr."""
    try:
        import anywidget  # noqa: F401
    except ImportError:
        lib = ProjectLibrary(str(tmp_path / "lib.json"), auto_save=False)
        with pytest.raises(ImportError):
            lib.ipywidget()


def test_ipywidget_esm_builds():
    """The ESM module text must always be constructible from the static
    resources, regardless of whether anywidget is installed."""
    from projspec.webui.ipywidget import _build_esm

    esm = _build_esm()
    assert "export function render" in esm
    assert "model.send" in esm
    assert "msg:custom" in esm
    # The embedded JS / CSS should be JSON-encoded string literals.
    for marker in (
        "const PANEL_HTML_BODY =",
        "const PANEL_CSS =",
        "const PANEL_JS =",
        "const CHROME_ICONS =",
    ):
        assert marker in esm, marker


def test_ipywidget_construction_if_available(tmp_path):
    """If anywidget is available, ProjectLibrary.ipywidget() returns a
    widget with a non-empty _esm."""
    anywidget = pytest.importorskip("anywidget")
    pytest.importorskip("ipywidgets")

    lib = ProjectLibrary(str(tmp_path / "lib.json"), auto_save=False)
    widget = lib.ipywidget()
    assert isinstance(widget, anywidget.AnyWidget)
    assert widget._esm and "export function render" in widget._esm


def test_ipywidget_handlers_respond(tmp_path):
    """Every command the shared panel.js can dispatch must produce a
    response (a ``send(...)`` call or a toast) without raising.

    This catches regressions where a command silently falls through and
    the UI button appears to do nothing - the exact symptom a user would
    report as 'the button doesn't work'.
    """
    pytest.importorskip("anywidget")
    pytest.importorskip("ipywidgets")
    from projspec import Project

    lib_file = tmp_path / "lib.json"
    lib = ProjectLibrary(str(lib_file), auto_save=False)
    # Stock the library with one real entry so handlers have something to
    # operate on.  Use a key with the file:// scheme to mimic add_to_library.
    lib.entries["file:///data"] = Project("/data", walk=False)

    widget = lib.ipywidget()
    outbox: list[dict] = []
    toasts: list[str] = []
    widget.send = lambda content, buffers=None: outbox.append(content)
    widget._toast = lambda m: toasts.append(m)

    def fire(cmd: str, **kwargs) -> tuple[list[dict], list[str]]:
        outbox.clear()
        toasts.clear()
        widget._on_frontend_message(widget, {"cmd": cmd, **kwargs}, None)
        return list(outbox), list(toasts)

    # ready: must emit a data msg with the library we stocked.
    msgs, _ = fire("ready")
    assert any(m.get("type") == "data" for m in msgs)
    data = next(m for m in msgs if m.get("type") == "data")
    assert list(data["library"]) == ["file:///data"]

    # reload: must NOT wipe the library when the backing file is absent.
    # This guards the bug reported in the hand-off: ``library.load()`` sets
    # ``entries = {}`` when the file is missing, so naively calling it on
    # every Reload click destroys the widget's state.
    assert not lib_file.exists()
    msgs, _ = fire("reload")
    assert list(lib.entries) == ["file:///data"], list(lib.entries)

    # rescan: must preserve the library key (the frontend selection is
    # keyed on that URL).
    fire("rescan", url="file:///data")
    assert list(lib.entries) == ["file:///data"]

    # add: opens the text-entry modal.
    msgs, _ = fire("add")
    assert any(m.get("type") == "openAddModal" for m in msgs)

    # addConfirmed: bad path produces a toast, no send.
    msgs, tlist = fire("addConfirmed", path="/definitely/not/a/dir")
    assert tlist and "Not a directory" in tlist[0]

    # createSpec: opens the create-spec modal.
    msgs, _ = fire("createSpec", url="file:///data")
    assert any(m.get("type") == "openCreateSpecModal" for m in msgs)

    # openWith with an unknown tool: handled with a toast, no spawn.
    _, tlist = fire("openWith", tool="does-not-exist", url="file:///data")
    assert tlist and "Unknown openWith tool" in tlist[0]

    # revealFile on a non-existent path: toast, no exception.
    _, tlist = fire("revealFile", fn="/no/such/path/anywhere.whl")
    assert tlist and "No files match" in tlist[0]

    # copyToLocal: documented as not-implemented (matches other UIs).
    _, tlist = fire("copyToLocal")
    assert tlist and "not implemented" in tlist[0].lower()

    # removeFromLibrary must not call save() when auto_save is False.
    # (If it did, the assertion at the top of this test would have failed
    # for later handlers - but check explicitly.)
    fire("removeFromLibrary", url="file:///data")
    assert "file:///data" not in lib.entries
    assert not lib_file.exists(), "removeFromLibrary must respect auto_save"


def test_panel_js_is_root_scoped():
    """The shared panel.js must look up IDs via the ``$id`` helper so the
    ipywidget (which inserts the panel into a larger page) doesn't collide
    with existing #app/#projects elements in the notebook document."""
    js = get_panel_js()
    # The only remaining direct use of document.getElementById is inside
    # the ``$id`` helper itself.
    assert js.count("document.getElementById") == 1
    # And there's no unscoped document.querySelectorAll (we use $all).
    assert "document.querySelectorAll" not in js
    assert "window.projspecRoot" in js


def test_make_cwd_uses_project_path_not_library_key(tmp_path, monkeypatch):
    """Regression: Make must use the stored ``Project.path`` as the
    subprocess cwd, never the library key.

    Library keys are opaque UI identifiers.  For walked children added via
    ``_add_confirmed`` they used to be the child's basename (e.g. ``qtapp``).
    Feeding that back into ``Project(key)`` or using it as a filesystem
    path made subprocesses run in ``<kernel_cwd>/qtapp`` - the notebook's
    launch directory - instead of ``/data/qtapp``.  This test pins the
    fixed behaviour.
    """
    import subprocess

    pytest.importorskip("anywidget")
    pytest.importorskip("ipywidgets")
    from projspec import Project
    from projspec.utils import is_installed

    is_installed.cache[(is_installed.env, "code")] = True

    # Build a library where a child is keyed on its basename, mimicking the
    # pre-fix legacy shape.  The stored Project's .path is the *real*
    # absolute location (/data/vsextension).
    lib = ProjectLibrary(str(tmp_path / "lib.json"), auto_save=False)
    root = Project("/data", walk=True)
    for cname, cproj in (root.children or {}).items():
        if cname == "vsextension" and cproj.specs.get("v_s_code"):
            lib.entries[cname] = cproj
            break
    else:
        pytest.skip("vsextension child not present in /data scan")

    # Kernel cwd is deliberately somewhere else.
    monkeypatch.chdir("/")
    w = lib.ipywidget()
    w._toast = lambda m: None  # swallow
    w.send = lambda c, buffers=None: None  # swallow

    captured = {}

    class _FakePopen:
        def __init__(self, cmd, cwd=None, **kw):
            captured["cmd"] = list(cmd)
            captured["cwd"] = cwd
            raise SystemExit(0)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)

    try:
        w._on_frontend_message(
            w,
            {
                "cmd": "make",
                "url": "vsextension",
                "spec": "v_s_code",
                "artifactType": "launch",
            },
            None,
        )
    except SystemExit:
        pass

    assert captured.get("cwd") == "/data/vsextension", captured
