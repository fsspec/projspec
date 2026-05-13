"""Backwards-compatibility shim.

The canonical chrome emoji map and category defaults now live in
:mod:`projspec.webui`.  This module re-exports them for any existing
imports of ``qtapp.emoji``.
"""

from __future__ import annotations

from projspec.webui import chrome_icons

CHROME = chrome_icons()

# Category fallbacks used when a spec/content/artifact class has no
# ``icon`` attribute.  These match the ``DEFAULT_ICONS`` values baked into
# ``projspec/webui/panel.js``.
_CATEGORY_DEFAULT = {
    "spec": "\U0001f9e9",  # 🧩
    "content": "\U0001f4c4",  # 📄
    "artifact": "\U0001f4e6",  # 📦
}

_UNKNOWN = "\u2754"  # ❔


def icon_for(icon: str | None, category: str | None = None) -> str:
    """Resolve a projspec icon value to a display glyph.

    ``icon`` is whatever ``class_infos()[category][name]["icon"]`` returned.
    Since projspec now stores emoji directly in those attributes, this
    function is a thin passthrough that supplies a sensible fallback when
    the attribute is empty.
    """
    if icon:
        return icon
    if category:
        return _CATEGORY_DEFAULT.get(category, _UNKNOWN)
    return _UNKNOWN


__all__ = ["CHROME", "icon_for"]
