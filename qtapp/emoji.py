"""Emoji icons for projspec UIs.

The spec / content / artifact classes in ``projspec`` itself already carry
emoji in their ``icon`` class attribute, so the three UIs can render those
as-is.  This module only supplies the small fixed set of *chrome* icons
(toolbar buttons, search box, kebab trigger, etc.) that are specific to
the UI and a category fallback for icons ``projspec`` doesn't name.
"""

from __future__ import annotations


CHROME = {
    "add": "➕",
    "reload": "🔄",
    "configure": "⚙️",
    "search": "🔍",
    "clear": "✖️",
    "spinner": "⏳",
    "chevron_up": "🔼",
    "chevron_down": "🔽",
    "kebab": "⋮",
    "play": "▶️",
    "info": "ℹ️",
    "reveal": "➡️",
}

_CATEGORY_DEFAULT = {
    "spec": "🧩",
    "content": "📄",
    "artifact": "📦",
}

_UNKNOWN = "❔"


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
