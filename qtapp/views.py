"""HTML view generators for the Qt application.

These are ports of the TypeScript HTML panel generators in vsextension/src/extension.ts.
The Qt app calls Python directly instead of shelling out to subprocesses.
"""

import json
import html as _html_mod
from typing import Any

from projspec.utils import class_infos


def _escape(s: str) -> str:
    return _html_mod.escape(str(s), quote=True)


def _get_info_data() -> dict:
    """Return {specs, content, artifact} info dict (equivalent to getInfoData())."""
    return class_infos()


# ---------------------------------------------------------------------------
# Shared CSS strings
# ---------------------------------------------------------------------------

_TREE_SHARED_CSS = """
    * { box-sizing: border-box; }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 13px;
        color: #cccccc;
        background-color: #1e1e1e;
        margin: 0;
        padding: 0;
        position: relative;
    }

    .tree { list-style: none; margin: 0; padding: 0; }
    .tree-item { margin: 0; padding: 0; }

    .tree-node {
        display: flex;
        align-items: center;
        padding: 4px 8px;
        cursor: pointer;
        border-radius: 4px;
        transition: background-color 0.1s ease;
    }

    .tree-node:hover { background-color: #2a2d2e; }

    .tree-node.selected {
        background-color: #094771;
        color: #ffffff;
    }

    .tree-icon {
        width: 16px; height: 16px; margin-right: 4px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; flex-shrink: 0;
    }

    .tree-icon.expandable::before { content: "▶"; font-size: 10px; transition: transform 0.1s ease; }
    .tree-icon.expanded::before { transform: rotate(90deg); }
    .tree-icon.leaf::before {
        content: ""; width: 6px; height: 6px;
        background: #888; border-radius: 50%; display: block;
    }

    .tree-label { flex: 1; padding: 2px 4px; }

    .tree-children { list-style: none; margin: 0; padding-left: 20px; display: none; }
    .tree-children.expanded { display: block; }

    .project-node { font-weight: bold; color: #dcb67a; }
    .content-node { color: #4ec9b0; }
    .artifact-node { color: #ce9178; }
    .spec-node { color: #dcdcaa; }
    .folder-node { color: #dcb67a; font-weight: 500; }
    .field-node { color: #cccccc; }

    .field-value { color: #9cdcfe; font-style: italic; }

    .info-button {
        width: 20px; height: 20px; border-radius: 50%;
        background: #0e639c; color: #ffffff;
        border: none; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        font-size: 12px; font-weight: bold; margin-left: 8px;
        opacity: 0.7; transition: all 0.2s ease; flex-shrink: 0;
    }
    .info-button:hover { opacity: 1; background: #1177bb; transform: scale(1.1); }

    .make-button {
        padding: 2px 8px;
        background-color: #0e639c; color: #ffffff;
        border: 1px solid #0e639c; border-radius: 2px; cursor: pointer;
        font-size: 10px; font-family: inherit; margin-left: 8px;
        opacity: 0.8; transition: all 0.2s ease; flex-shrink: 0;
    }
    .make-button:hover { opacity: 1; background-color: #1177bb; }

    .info-popup {
        position: absolute;
        background: #252526; border: 1px solid #454545; border-radius: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        padding: 16px; max-width: 400px; min-width: 250px;
        z-index: 1000; font-size: 13px; line-height: 1.5; display: none;
    }
    .info-popup.visible { display: block; }
    .popup-header {
        display: flex; align-items: center; margin-bottom: 12px;
        padding-bottom: 8px; border-bottom: 1px solid #454545;
    }
    .popup-icon {
        width: 20px; height: 20px; margin-right: 8px; border-radius: 50%;
        background-color: #0e639c; color: #fff;
        display: flex; align-items: center; justify-content: center;
        font-weight: bold; font-size: 12px; flex-shrink: 0;
    }
    .popup-title { font-weight: bold; margin: 0; color: #cccccc; }
    .popup-content { margin-bottom: 8px; }
    .popup-section { margin-bottom: 12px; }
    .popup-section:last-child { margin-bottom: 0; }
    .section-title {
        font-weight: bold; margin-bottom: 4px; color: #9e9e9e;
        font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .section-content { white-space: pre-wrap; word-wrap: break-word; }
    .popup-link { color: #3794ff; text-decoration: none; word-break: break-all; }
    .popup-link:hover { text-decoration: underline; }
    .popup-link-btn {
        background: none; border: none; padding: 0; cursor: pointer;
        color: #3794ff; font-family: inherit; font-size: inherit;
        text-align: left; word-break: break-all; white-space: normal;
    }
    .popup-link-btn:hover { text-decoration: underline; }
    .no-info { color: #9e9e9e; font-style: italic; }
    .info-popup::before { content: none; }
    .info-popup::after  { content: none; }

    .control-button {
        padding: 2px 8px;
        background-color: #3c3c3c; color: #cccccc;
        border: 1px solid #454545; border-radius: 2px;
        cursor: pointer; font-size: 11px; font-family: inherit;
    }
    .control-button:hover { background-color: #494949; }
    .control-button.active { background-color: #0e639c; color: #fff; }

    .loading-overlay {
        position: fixed; inset: 0;
        background: rgba(0,0,0,0.35);
        display: none; align-items: center; justify-content: center;
        z-index: 4000; cursor: wait;
    }
    .loading-overlay.visible { display: flex; }
    .loading-spinner {
        width: 28px; height: 28px;
        border: 3px solid #cccccc; border-top-color: transparent;
        border-radius: 50%; animation: spin 0.7s linear infinite; opacity: 0.8;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .html-preview {
        display: block;
        width: 100%;
        border: none;
        margin-top: 4px;
        margin-left: 20px;
        min-height: 40px;
        max-height: 600px;
    }
"""

_INFO_POPUP_JS = """
    function showInfoPopup(button, itemData) {
        const popup = document.getElementById('info-popup');
        const popupTitle = document.getElementById('popup-title');
        const popupContent = document.getElementById('popup-content');
        const rect = button.getBoundingClientRect();
        const container = document.getElementById('tree-container');
        const containerRect = container.getBoundingClientRect();
        popup.style.top = (rect.top - containerRect.top - 10) + 'px';
        popupTitle.textContent = itemData.key || itemData.label || '';

        let contentHtml = '';
        if (itemData.infoData && itemData.infoData.trim() !== '') {
            let doc = '', link = '';
            try {
                const info = JSON.parse(itemData.infoData);
                doc = info.doc || ''; link = info.link || '';
            } catch(e) {
                const parts = itemData.infoData.split('\\n\\n');
                doc = parts[0] || ''; link = parts[1] || '';
            }
            const docParts = doc.split('\\n').map(p => p.trim()).filter(p => p.length > 0);
            const summary = docParts[0] || '';
            const extra = docParts.slice(1);
            if (summary) contentHtml += '<div class="popup-section"><div class="section-content" style="font-weight:bold;margin-bottom:8px;">' + summary + '</div></div>';
            if (extra.length > 0) contentHtml += '<div class="popup-section"><div class="section-content">' + extra.map(p => '<p style="margin-top:0;margin-bottom:8px;">' + p + '</p>').join('') + '</div></div>';
            if (link) contentHtml += '<div class="popup-section"><div class="section-title">More Information</div><div class="section-content"><button class="popup-link-btn" onclick="postMessage({command:\\'openUrl\\',url:\\'' + link.replace(/'/g, '%27') + '\\'})">&#x1F517; ' + link + '</button></div></div>';
        }
        if (!contentHtml) {
            contentHtml = '<div class="no-info">Information for ' + (itemData.itemType || 'item') + ' type "' + (itemData.key || itemData.label || '') + '" is not currently available.</div>';
        }
        popupContent.innerHTML = contentHtml;
        // Position to the left of the button; measure after making visible so width is known
        popup.style.left = '-9999px';
        popup.classList.add('visible');
        const popupRect = popup.getBoundingClientRect();
        popup.style.left = (rect.left - containerRect.left - popupRect.width - 10) + 'px';
        // If that goes off the left edge, fall back to right of the button
        if (rect.left - popupRect.width - 10 < 0) {
            popup.style.left = (rect.right - containerRect.left + 10) + 'px';
        }
        if (popupRect.bottom > window.innerHeight) popup.style.top = (rect.bottom - containerRect.top - popupRect.height + 10) + 'px';
    }

    function hideInfoPopup() {
        document.getElementById('info-popup').classList.remove('visible');
    }
"""

_INFO_POPUP_HTML = """
    <div id="info-popup" class="info-popup">
        <div class="popup-header">
            <div class="popup-icon">i</div>
            <h3 class="popup-title" id="popup-title"></h3>
        </div>
        <div class="popup-content" id="popup-content"></div>
    </div>
"""


# ---------------------------------------------------------------------------
# Library / tree panel
# ---------------------------------------------------------------------------


def _build_tree_nodes(project_url: str, project: dict, info_data: dict) -> list:
    """Equivalent to buildTreeNodes() in extension.ts."""
    children = []

    def _build_tooltip(doc, link):
        return json.dumps({"doc": doc or "", "link": link or ""})

    # Top-level contents
    for name in (project.get("contents") or {}).keys():
        basename = name.split("/")[-1]
        content_type = basename.split(".")[0]
        info = (info_data.get("content") or {}).get(content_type)
        info_text = (
            _build_tooltip(info.get("doc"), info.get("link", "")) if info else None
        )
        children.append(
            {
                "key": basename,
                "infoData": info_text,
                "projectUrl": project_url,
                "itemType": "content",
            }
        )

    # Top-level artifacts
    for artifact_type, artifact_data in (project.get("artifacts") or {}).items():
        info = (info_data.get("artifact") or {}).get(artifact_type)
        info_text = (
            _build_tooltip(info.get("doc"), info.get("link", "")) if info else None
        )
        if isinstance(artifact_data, str):
            children.append(
                {
                    "key": artifact_type,
                    "infoData": info_text,
                    "projectUrl": project_url,
                    "itemType": "artifact",
                    "qname": artifact_type,
                }
            )
        elif isinstance(artifact_data, dict):
            for name in artifact_data.keys():
                children.append(
                    {
                        "key": f"{artifact_type}.{name}",
                        "infoData": info_text,
                        "projectUrl": project_url,
                        "itemType": "artifact",
                        "qname": f"{artifact_type}.{name}",
                    }
                )

    # Specs
    for spec_name, spec_data in (project.get("specs") or {}).items():
        info = (info_data.get("specs") or {}).get(spec_name)
        info_text = (
            _build_tooltip(info.get("doc"), info.get("link", "")) if info else None
        )
        spec_children = []
        for artifact_type, artifact_data in (spec_data.get("_artifacts") or {}).items():
            art_info = (info_data.get("artifact") or {}).get(artifact_type)
            art_info_text = (
                _build_tooltip(art_info.get("doc"), art_info.get("link", ""))
                if art_info
                else None
            )
            if isinstance(artifact_data, str):
                spec_children.append(
                    {
                        "key": artifact_type,
                        "infoData": art_info_text,
                        "projectUrl": project_url,
                        "itemType": "artifact",
                        "qname": f"{spec_name}.{artifact_type}",
                    }
                )
            elif isinstance(artifact_data, dict):
                for name in artifact_data.keys():
                    spec_children.append(
                        {
                            "key": f"{artifact_type}.{name}",
                            "infoData": art_info_text,
                            "projectUrl": project_url,
                            "itemType": "artifact",
                            "qname": f"{spec_name}.{artifact_type}.{name}",
                        }
                    )
        node = {
            "key": spec_name,
            "infoData": info_text,
            "projectUrl": project_url,
            "itemType": "spec",
        }
        if spec_children:
            node["children"] = spec_children
        children.append(node)

    return children


def _generate_tree_html(node: dict, level: int = 0) -> str:
    """Equivalent to generateTreeHTML() in extension.ts."""
    html = ""
    for child in node.get("children") or []:
        has_children = bool(child.get("children"))
        node_class = _get_node_class(child)
        icon_class = "tree-icon expandable" if has_children else "tree-icon leaf"
        has_info = child.get("itemType") in ("content", "artifact", "spec")
        is_artifact = child.get("itemType") == "artifact"
        item_data_json = _escape(json.dumps(child))
        key_text = _escape(str(child.get("key", "")))
        make_btn = (
            f'<button class="make-button" data-item="{item_data_json}" title="Make artifact">Make</button>'
            if is_artifact
            else ""
        )
        info_btn = (
            f'<button class="info-button" data-item="{item_data_json}" title="Show information">i</button>'
            if has_info
            else ""
        )
        children_html = ""
        if has_children:
            children_html = f'<ul class="tree-children">{_generate_tree_html(child, level + 1)}</ul>'
        html += f"""
            <li class="tree-item">
                <div class="tree-node {node_class}" data-item="{item_data_json}">
                    <span class="{icon_class}"></span>
                    <span class="tree-label">{key_text}</span>
                    {make_btn}
                    {info_btn}
                </div>
                {children_html}
            </li>"""
    return html


def _get_node_class(node: dict) -> str:
    if node.get("isProject"):
        return "project-node"
    elif node.get("itemType") == "content":
        return "content-node"
    elif node.get("itemType") == "artifact":
        return "artifact-node"
    elif node.get("itemType") == "spec":
        return "spec-node"
    elif node.get("children"):
        return "folder-node"
    return ""


def get_library_html(
    library_data: dict,
    spec_names: list[str],
    scroll_to_project_url: str | None = None,
) -> str:
    """Generate the Library panel HTML.

    Equivalent to getTreeWebviewContent() in extension.ts.

    Parameters
    ----------
    library_data:
        ``{project_url: project_dict}`` — the full library JSON.
    spec_names:
        List of known spec type names for the Create project autocomplete.
    scroll_to_project_url:
        If given, this project will be expanded and selected on load.
    """
    info_data = _get_info_data()

    # Build tree data
    project_children = []
    for project_url, project in library_data.items():
        pchildren = _build_tree_nodes(project_url, project, info_data)
        project_basename = project_url.split("/")[-1] or project_url
        node = {
            "key": f"{project_basename} ({project_url})",
            "infoData": project_url,
            "children": pchildren,
            "data": project,
            "isProject": True,
        }
        project_children.append(node)

    tree_root = {"key": "projects", "children": project_children}
    tree_html = _generate_tree_html(tree_root)

    spec_names_json = json.dumps(spec_names)
    scroll_url_js = (
        f"'{_escape(scroll_to_project_url)}'" if scroll_to_project_url else "null"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Library</title>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <style>
{_TREE_SHARED_CSS}

        .search-container {{
            padding: 8px;
            position: sticky; top: 0;
            background-color: #1e1e1e; z-index: 10;
            border-bottom: 1px solid #454545; margin-bottom: 8px;
        }}
        .search-input-wrapper {{ position: relative; display: flex; align-items: center; }}
        #search-input {{
            width: 100%; padding: 4px 24px 4px 8px; box-sizing: border-box;
            background-color: #3c3c3c; color: #cccccc; border: 1px solid #555;
            border-radius: 2px; font-family: inherit; font-size: inherit;
        }}
        #search-input:focus {{ outline: 1px solid #007acc; border-color: #007acc; }}
        #search-clear {{
            position: absolute; right: 4px; background: none; border: none;
            padding: 0 2px; cursor: pointer; color: #cccccc; opacity: 0.6;
            font-size: 14px; line-height: 1; display: none;
        }}
        #search-clear:hover {{ opacity: 1; }}

        .controls-top-container {{
            padding: 8px; display: flex; gap: 8px;
            border-bottom: 1px solid #454545; margin-bottom: 8px;
        }}
        .controls-bottom-container {{
            padding: 8px; display: flex; gap: 8px;
            border-bottom: 1px solid #454545; margin-bottom: 8px;
        }}

        /* Modal */
        .modal-overlay {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.5); display: none;
            align-items: center; justify-content: center; z-index: 2000;
        }}
        .modal-overlay.visible {{ display: flex; }}
        .modal-dialog {{
            background: #252526; border: 1px solid #454545; border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5); padding: 20px;
            width: 350px; max-width: 90%;
        }}
        .modal-title {{ margin-top: 0; margin-bottom: 16px; font-size: 16px; font-weight: bold; color: #cccccc; }}
        .modal-content {{ margin-bottom: 20px; }}
        .modal-label {{ display: block; margin-bottom: 8px; color: #cccccc; }}
        .modal-input {{
            width: 100%; padding: 6px;
            background: #3c3c3c; color: #cccccc; border: 1px solid #555;
            border-radius: 2px; font-family: inherit; box-sizing: border-box;
        }}
        .autocomplete-container {{ position: relative; width: 100%; }}
        .autocomplete-suggestions {{
            position: absolute; top: 100%; left: 0; right: 0;
            background: #252526; border: 1px solid #454545; border-top: none;
            max-height: 150px; overflow-y: auto; z-index: 2100;
            display: none; box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }}
        .autocomplete-suggestions.visible {{ display: block; }}
        .suggestion-item {{ padding: 6px 10px; cursor: pointer; transition: background-color 0.1s ease; }}
        .suggestion-item:hover, .suggestion-item.active {{ background-color: #2a2d2e; }}
        .modal-buttons {{ display: flex; justify-content: flex-end; gap: 8px; }}
        .modal-button {{
            padding: 6px 16px; border-radius: 2px; border: 1px solid #555;
            cursor: pointer; font-family: inherit; font-size: 13px;
        }}
        .modal-button-primary {{ background: #0e639c; color: #fff; }}
        .modal-button-primary:hover {{ background: #1177bb; }}
        .modal-button-secondary {{ background: #3c3c3c; color: #cccccc; }}
        .modal-button-secondary:hover {{ background: #494949; }}

        /* Context menu */
        .context-menu {{
            position: fixed; background: #252526;
            border: 1px solid #454545; border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            padding: 4px 0; z-index: 3000; display: none; min-width: 140px;
        }}
        .context-menu.visible {{ display: block; }}
        .context-menu-item {{
            padding: 6px 16px; cursor: pointer; color: #cccccc;
            font-family: inherit; font-size: 13px; white-space: nowrap;
        }}
        .context-menu-item:hover {{ background: #094771; color: #fff; }}
    </style>
</head>
<body>
    <div class="controls-top-container">
        <button id="scan-project" class="control-button">Scan</button>
        <button id="create-project" class="control-button">Create</button>
    </div>
    <div class="search-container">
        <div class="search-input-wrapper">
            <input type="text" id="search-input" placeholder="Search projects..." aria-label="Search projects">
            <button id="search-clear" title="Clear search">&#x2715;</button>
        </div>
    </div>
    <div class="controls-bottom-container">
        <button id="expand-all" class="control-button">Expand All</button>
        <button id="collapse-all" class="control-button">Collapse All</button>
    </div>
    <div id="tree-container">
        <ul class="tree">
            {tree_html}
        </ul>
    </div>

    <div id="loading-overlay" class="loading-overlay">
        <div class="loading-spinner"></div>
    </div>

    {_INFO_POPUP_HTML}

    <div id="context-menu" class="context-menu">
        <div class="context-menu-item" id="context-open">Set browser path</div>
        <div class="context-menu-item" id="context-file-browser">Open in system file browser</div>
        <div class="context-menu-item" id="context-vscode">Open in VSCode</div>
        <div class="context-menu-item" id="context-jupyter">Open in Jupyter</div>
        <div class="context-menu-item" id="context-remove">Remove from library</div>
    </div>

    <div id="create-modal" class="modal-overlay">
        <div class="modal-dialog">
            <h3 class="modal-title">Create Project</h3>
            <div class="modal-content">
                <label for="project-type-input" class="modal-label">Project Type:</label>
                <div class="autocomplete-container">
                    <input type="text" id="project-type-input" class="modal-input" placeholder="Search or select type..." autocomplete="off">
                    <div id="autocomplete-suggestions" class="autocomplete-suggestions"></div>
                </div>
            </div>
            <div class="modal-buttons">
                <button id="modal-cancel" class="modal-button modal-button-secondary">Cancel</button>
                <button id="modal-create" class="modal-button modal-button-primary">Create</button>
            </div>
        </div>
    </div>

    <script>
        // Qt WebChannel bridge
        let bridge = null;
        function postMessage(msg) {{
            if (bridge) {{
                bridge.handleMessage(JSON.stringify(msg));
            }}
        }}

        new QWebChannel(qt.webChannelTransport, function(channel) {{
            bridge = channel.objects.bridge;
        }});

        const specNames = {spec_names_json};
        let activeSuggestionIndex = -1;
        let contextMenuItem = null;
        const scrollToProjectUrl = {scroll_url_js};

        function setLoading(active) {{
            document.getElementById('loading-overlay').classList.toggle('visible', active);
        }}

        // ── Scroll to project on load ──────────────────────────────────────
        if (scrollToProjectUrl) {{
            window.addEventListener('DOMContentLoaded', () => {{
                for (const node of document.querySelectorAll('.tree-node.project-node')) {{
                    const itemData = JSON.parse(node.dataset.item || '{{}}');
                    if (itemData.infoData === scrollToProjectUrl) {{
                        const treeItem = node.closest('.tree-item');
                        const children = treeItem && treeItem.querySelector('.tree-children');
                        const icon = treeItem && treeItem.querySelector('.tree-icon');
                        if (children) children.classList.add('expanded');
                        if (icon) icon.classList.add('expanded');
                        node.classList.add('selected');
                        node.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        break;
                    }}
                }}
            }});
        }}

        // ── Scan ───────────────────────────────────────────────────────────
        document.getElementById('scan-project').addEventListener('click', () => {{
            setLoading(true);
            postMessage({{ command: 'scan' }});
        }});

        // ── Create ─────────────────────────────────────────────────────────
        document.getElementById('create-project').addEventListener('click', () => {{
            document.getElementById('create-modal').classList.add('visible');
            const inp = document.getElementById('project-type-input');
            inp.value = '';
            inp.focus();
            renderSuggestions('');
        }});

        // ── Autocomplete ───────────────────────────────────────────────────
        function renderSuggestions(filter) {{
            const sc = document.getElementById('autocomplete-suggestions');
            const filtered = specNames.filter(s => s.toLowerCase().includes(filter.toLowerCase()));
            sc.innerHTML = '';
            activeSuggestionIndex = -1;
            if (filtered.length > 0) {{
                filtered.forEach(spec => {{
                    const item = document.createElement('div');
                    item.className = 'suggestion-item';
                    item.textContent = spec;
                    item.addEventListener('click', () => selectSuggestion(spec));
                    sc.appendChild(item);
                }});
                sc.classList.add('visible');
            }} else {{
                sc.classList.remove('visible');
            }}
        }}
        function updateActiveSuggestion(suggestions) {{
            suggestions.forEach((s, i) => {{
                s.classList.toggle('active', i === activeSuggestionIndex);
                if (i === activeSuggestionIndex) s.scrollIntoView({{ block: 'nearest' }});
            }});
        }}
        function selectSuggestion(spec) {{
            document.getElementById('project-type-input').value = spec;
            document.getElementById('autocomplete-suggestions').classList.remove('visible');
            activeSuggestionIndex = -1;
        }}

        const typeInput = document.getElementById('project-type-input');
        typeInput.addEventListener('input', e => renderSuggestions(e.target.value));
        typeInput.addEventListener('keydown', e => {{
            const sugs = document.getElementById('autocomplete-suggestions').querySelectorAll('.suggestion-item');
            if (e.key === 'ArrowDown') {{ activeSuggestionIndex = Math.min(activeSuggestionIndex + 1, sugs.length - 1); updateActiveSuggestion(sugs); e.preventDefault(); }}
            else if (e.key === 'ArrowUp') {{ activeSuggestionIndex = Math.max(activeSuggestionIndex - 1, -1); updateActiveSuggestion(sugs); e.preventDefault(); }}
            else if (e.key === 'Enter' && activeSuggestionIndex >= 0) {{ selectSuggestion(sugs[activeSuggestionIndex].textContent); e.preventDefault(); }}
        }});

        // ── Search ─────────────────────────────────────────────────────────
        document.getElementById('search-input').addEventListener('input', e => {{
            const term = e.target.value.toLowerCase();
            document.getElementById('search-clear').style.display = e.target.value ? 'block' : 'none';
            document.querySelectorAll('.tree > .tree-item').forEach(item => {{
                const labels = item.querySelectorAll('.tree-label');
                let found = false;
                for (const lbl of labels) {{
                    if (lbl.textContent.toLowerCase().includes(term)) {{ found = true; break; }}
                }}
                item.style.display = found ? '' : 'none';
            }});
        }});
        document.getElementById('search-clear').addEventListener('click', () => {{
            document.getElementById('search-input').value = '';
            document.getElementById('search-clear').style.display = 'none';
            document.querySelectorAll('.tree > .tree-item').forEach(i => i.style.display = '');
            document.getElementById('search-input').focus();
        }});

        // ── Expand / Collapse ──────────────────────────────────────────────
        document.getElementById('expand-all').addEventListener('click', () => {{
            document.querySelectorAll('.tree-children').forEach(c => c.classList.add('expanded'));
            document.querySelectorAll('.tree-icon.expandable').forEach(i => i.classList.add('expanded'));
        }});
        document.getElementById('collapse-all').addEventListener('click', () => {{
            document.querySelectorAll('.tree-children').forEach(c => c.classList.remove('expanded'));
            document.querySelectorAll('.tree-icon.expandable').forEach(i => i.classList.remove('expanded'));
        }});

        // ── Modal lifecycle ────────────────────────────────────────────────
        document.getElementById('modal-cancel').addEventListener('click', () =>
            document.getElementById('create-modal').classList.remove('visible'));
        document.getElementById('modal-create').addEventListener('click', () => {{
            const pt = document.getElementById('project-type-input').value;
            if (pt) {{
                postMessage({{ command: 'createProject', projectType: pt }});
                document.getElementById('create-modal').classList.remove('visible');
            }} else {{
                document.getElementById('project-type-input').focus();
            }}
        }});
        document.addEventListener('click', e => {{
            if (!typeInput.contains(e.target) && !document.getElementById('autocomplete-suggestions').contains(e.target))
                document.getElementById('autocomplete-suggestions').classList.remove('visible');
        }});

        // ── Tree clicks ────────────────────────────────────────────────────
        document.addEventListener('click', e => {{
            // Expand/collapse arrow
            if (e.target.classList.contains('tree-icon') && e.target.classList.contains('expandable')) {{
                const treeItem = e.target.closest('.tree-item');
                const children = treeItem.querySelector('.tree-children');
                const expanded = children.classList.toggle('expanded');
                e.target.classList.toggle('expanded', expanded);
                return;
            }}
            // Info button
            if (e.target.classList.contains('info-button')) {{
                e.stopPropagation();
                showInfoPopup(e.target, JSON.parse(e.target.dataset.item));
                return;
            }}
            // Make button
            if (e.target.classList.contains('make-button')) {{
                e.stopPropagation();
                postMessage({{ command: 'makeArtifact', item: JSON.parse(e.target.dataset.item) }});
                return;
            }}
            // Close info popup
            const popup = document.getElementById('info-popup');
            if (!popup.contains(e.target) && !e.target.classList.contains('info-button')) hideInfoPopup();
            // Hide context menu
            if (!document.getElementById('context-menu').contains(e.target)) hideContextMenu();
            // Node selection
            if (e.target.classList.contains('tree-node') || e.target.classList.contains('tree-label')) {{
                const treeNode = e.target.closest('.tree-node');
                const itemData = JSON.parse(treeNode.dataset.item || '{{}}');
                document.querySelectorAll('.tree-node.selected').forEach(n => n.classList.remove('selected'));
                treeNode.classList.add('selected');
                if (!itemData.isProject && itemData.projectUrl) {{
                    postMessage({{ command: 'selectItem', item: itemData }});
                }}
            }}
        }});

        // ── Context menu ───────────────────────────────────────────────────
        document.addEventListener('contextmenu', e => {{
            const treeNode = e.target.closest && e.target.closest('.tree-node');
            if (treeNode) {{
                const itemData = JSON.parse(treeNode.dataset.item || '{{}}');
                if (itemData.isProject) {{
                    e.preventDefault();
                    contextMenuItem = itemData;
                    document.querySelectorAll('.tree-node.selected').forEach(n => n.classList.remove('selected'));
                    treeNode.classList.add('selected');
                    const cm = document.getElementById('context-menu');
                    cm.style.left = e.clientX + 'px';
                    cm.style.top = e.clientY + 'px';
                    cm.classList.add('visible');
                    return;
                }}
            }}
            hideContextMenu();
        }});
        document.getElementById('context-open').addEventListener('click', () => {{
            if (contextMenuItem) postMessage({{ command: 'setBrowserPath', item: contextMenuItem }});
            hideContextMenu();
        }});
        document.getElementById('context-file-browser').addEventListener('click', () => {{
            if (contextMenuItem) postMessage({{ command: 'openInFileBrowser', item: contextMenuItem }});
            hideContextMenu();
        }});
        document.getElementById('context-vscode').addEventListener('click', () => {{
            if (contextMenuItem) postMessage({{ command: 'openInVSCode', item: contextMenuItem }});
            hideContextMenu();
        }});
        document.getElementById('context-jupyter').addEventListener('click', () => {{
            if (contextMenuItem) postMessage({{ command: 'openInJupyter', item: contextMenuItem }});
            hideContextMenu();
        }});
        document.getElementById('context-remove').addEventListener('click', () => {{
            if (contextMenuItem) {{
                setLoading(true);
                postMessage({{ command: 'removeProject', item: contextMenuItem }});
            }}
            hideContextMenu();
        }});
        function hideContextMenu() {{
            document.getElementById('context-menu').classList.remove('visible');
            contextMenuItem = null;
        }}

        document.addEventListener('keydown', e => {{
            if (e.key === 'Escape') {{
                hideInfoPopup();
                document.getElementById('create-modal').classList.remove('visible');
            }}
        }});

{_INFO_POPUP_JS}
    </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Details panel
# ---------------------------------------------------------------------------

_SKIP_KEYS = {"klass", "proc", "storage_options", "children", "url", "_html"}


def _build_tooltip(doc, link):
    return json.dumps({"doc": doc or "", "link": link or ""})


def _build_detail_nodes(
    obj: Any, role: str, qname_path: str, project_url: str, info_data: dict
) -> list:
    """Equivalent to buildNodes() in extension.ts."""
    if obj is None:
        return []

    def scalar_label(v):
        if v is None:
            return "null"
        return str(v)

    if isinstance(obj, list):
        result = []
        for i, item in enumerate(obj):
            if item is not None and isinstance(item, dict):
                result.append(
                    {
                        "label": str(i),
                        "role": role,
                        "children": _build_detail_nodes(
                            item,
                            role,
                            f"{qname_path}.{i}",
                            project_url,
                            info_data,
                        ),
                    }
                )
            else:
                result.append({"label": scalar_label(item), "role": "field"})
        return result

    if not isinstance(obj, dict):
        return [{"label": scalar_label(obj), "role": "field"}]

    nodes = []
    for key, value in obj.items():
        if key in _SKIP_KEYS:
            continue
        child_path = f"{qname_path}.{key}" if qname_path else key

        # Container keys — inline children with correct role
        if key in ("specs", "_contents", "contents", "_artifacts", "artifacts"):
            child_role = (
                "spec"
                if key == "specs"
                else "content"
                if key in ("_contents", "contents")
                else "artifact"
            )
            nodes.extend(
                _build_detail_nodes(
                    value, child_role, qname_path, project_url, info_data
                )
            )
            continue

        # Artifact special handling
        if role == "artifact":
            art_info = (info_data.get("artifact") or {}).get(key)
            art_info_data = (
                _build_tooltip(art_info.get("doc"), art_info.get("link", ""))
                if art_info
                else None
            )

            if isinstance(value, str) or value is None:
                nodes.append(
                    {
                        "label": key,
                        "role": "artifact",
                        "qname": child_path,
                        "projectUrl": project_url,
                        "infoData": art_info_data,
                        "itemType": "artifact",
                    }
                )
            elif isinstance(value, dict):
                entries = list(value.items())
                all_strings = all(isinstance(v, (str, type(None))) for _, v in entries)
                if all_strings:
                    named_children = [
                        {
                            "label": name,
                            "role": "artifact",
                            "qname": f"{child_path}.{name}",
                            "projectUrl": project_url,
                            "itemType": "artifact",
                        }
                        for name, _ in entries
                    ]
                    nodes.append(
                        {
                            "label": key,
                            "role": "artifact",
                            "children": named_children or None,
                            "infoData": art_info_data,
                            "itemType": "artifact",
                        }
                    )
                else:
                    children = _build_detail_nodes(
                        value, "field", child_path, project_url, info_data
                    )
                    nodes.append(
                        {
                            "label": key,
                            "role": "artifact",
                            "qname": child_path,
                            "projectUrl": project_url,
                            "children": children or None,
                            "infoData": art_info_data,
                            "itemType": "artifact",
                        }
                    )
            continue

        # Scalar leaf
        if value is None or not isinstance(value, (dict, list)):
            effective_role = (
                "content"
                if role == "content"
                else ("spec" if role == "spec" else "field")
            )
            nodes.append(
                {
                    "label": key,
                    "value": scalar_label(value),
                    "role": effective_role,
                }
            )
            continue
        if isinstance(value, list):
            if all(not isinstance(v, dict) for v in value):
                array_children = [
                    {"label": scalar_label(v), "role": "field"} for v in value
                ]
                effective_role = (
                    "content"
                    if role == "content"
                    else ("spec" if role == "spec" else "field")
                )
                nodes.append(
                    {
                        "label": key,
                        "role": effective_role,
                        "children": array_children or None,
                    }
                )
            else:
                nodes.append(
                    {
                        "label": key,
                        "role": role,
                        "children": _build_detail_nodes(
                            value, role, child_path, project_url, info_data
                        ),
                    }
                )
            continue

        # Object value
        children = _build_detail_nodes(value, role, child_path, project_url, info_data)
        node_info_data = None
        if role == "spec":
            info = (info_data.get("specs") or {}).get(key)
            if info:
                node_info_data = _build_tooltip(info.get("doc"), info.get("link", ""))
        elif role == "content":
            info = (info_data.get("content") or {}).get(key)
            if info:
                node_info_data = _build_tooltip(info.get("doc"), "")
        nodes.append(
            {
                "label": key,
                "role": role,
                "children": children or None,
                "infoData": node_info_data,
                "itemType": role if role not in ("none", "field") else None,
                "htmlContent": (
                    value["_html"]
                    if role == "content"
                    and isinstance(value, dict)
                    and isinstance(value.get("_html"), str)
                    else None
                ),
            }
        )

    return nodes


def _is_leaf_artifact(node: dict) -> bool:
    if node.get("role") != "artifact" or not node.get("qname"):
        return False
    children = node.get("children")
    if not children:
        return True
    return not any(c.get("role") == "artifact" for c in children)


# Dark console-green stylesheet injected into every html-preview srcdoc.
_HTML_PREVIEW_CSS = (
    "<style>"
    ":root{--bg:#0d1117;--bg-hd:#161b22;--bg-alt:#111820;--grn:#39d353;--grn-d:#26a641;"
    "--grn-m:#196127;--bd:#21262d;--bd-d:#161b22;--fg:#c9d1d9;--fg-d:#8b949e;"
    "--bb:#1f6feb;--bg2:#30363d;--fn:ui-monospace,'Cascadia Code','Fira Mono',monospace}"
    "*{box-sizing:border-box}"
    "body{background:var(--bg);color:var(--fg);margin:0;font-family:var(--fn);font-size:12px}"
    ".ps-data-card{border:1px solid var(--bd);border-radius:6px;overflow:hidden;"
    "background:var(--bg);color:var(--fg)}"
    ".ps-data-card-header{background:var(--bg-hd);padding:7px 12px;display:flex;"
    "align-items:center;gap:8px;border-bottom:1px solid var(--bd)}"
    ".ps-data-card-header .ps-icon{font-size:16px}"
    ".ps-data-card-header .ps-name{font-weight:bold;font-size:13px;color:var(--grn)}"
    ".ps-data-card-header .ps-badge{background:var(--bb);color:#fff;border-radius:10px;"
    "padding:1px 7px;font-size:10px}"
    ".ps-data-card-header .ps-badge-gray{background:var(--bg2);color:var(--fg);"
    "border-radius:10px;padding:1px 7px;font-size:10px}"
    ".ps-data-meta{padding:8px 12px;border-bottom:1px solid var(--bd-d)}"
    ".ps-data-meta table{border-collapse:collapse;width:100%}"
    ".ps-data-meta td{padding:2px 8px 2px 0;vertical-align:top}"
    ".ps-data-meta td:first-child{color:var(--fg-d);white-space:nowrap;width:110px}"
    "details>summary{list-style:none;cursor:pointer;color:var(--grn-d);font-size:11px;margin-top:4px}"
    "details>summary::-webkit-details-marker{display:none}"
    ".ps-schema-table{font-size:11px;border-collapse:collapse;margin-top:4px;width:100%}"
    ".ps-schema-table th{background:var(--bg-hd);color:var(--grn-d);padding:2px 8px;"
    "text-align:left;border:1px solid var(--bd)}"
    ".ps-schema-table td{padding:2px 8px;border:1px solid var(--bd-d);font-family:var(--fn);color:var(--fg)}"
    ".ps-schema-table td strong{color:var(--grn)}"
    ".ps-preview{padding:8px 12px}"
    ".ps-preview-title{font-weight:bold;font-size:10px;color:var(--grn-m);margin-bottom:5px;"
    "text-transform:uppercase;letter-spacing:.8px}"
    ".ps-df-wrap{overflow-x:auto}"
    ".ps-df-wrap table,.dataframe{font-size:11px!important;border-collapse:collapse!important;"
    "width:100%!important;color:var(--fg)!important;background:var(--bg)!important}"
    ".ps-df-wrap th,.dataframe thead th{background:var(--bg-hd)!important;color:var(--grn-d)!important;"
    "padding:3px 10px!important;border:1px solid var(--bd)!important;white-space:nowrap;text-align:left!important}"
    ".ps-df-wrap td,.dataframe tbody td{padding:2px 10px!important;border:1px solid var(--bd-d)!important;"
    "color:var(--fg)!important;background:var(--bg)!important;white-space:nowrap;"
    "max-width:200px;overflow:hidden;text-overflow:ellipsis}"
    ".dataframe tbody tr:nth-child(even) td{background:var(--bg-alt)!important}"
    ".ps-img-preview{max-width:100%;max-height:200px;border-radius:4px}"
    "</style>"
)


def _render_detail_node(node: dict, depth: int) -> str:
    has_children = bool(node.get("children"))
    can_make = _is_leaf_artifact(node)
    has_info_popup = node.get("infoData") is not None and node.get("role") not in (
        "field",
        "none",
    )

    role = node.get("role", "")
    node_class = "tree-node"
    if role == "spec":
        node_class += " spec-node"
    elif role == "content":
        node_class += " content-node"
    elif role == "artifact":
        node_class += " artifact-node"
    elif role == "field":
        node_class += " field-node"

    icon_class = "tree-icon expandable" if has_children else "tree-icon leaf"

    node_data = _escape(
        json.dumps(
            {
                "key": node.get("label", ""),
                "label": node.get("label", ""),
                "qname": node.get("qname"),
                "projectUrl": node.get("projectUrl"),
                "itemType": node.get("itemType"),
                "infoData": node.get("infoData"),
            }
        )
    )

    label = node.get("label", "")
    value = node.get("value")
    if value is not None:
        label_html = (
            f'{_escape(label)}: <span class="field-value">{_escape(value)}</span>'
        )
    else:
        label_html = _escape(label)

    children_html = ""
    if has_children:
        inner = "".join(_render_detail_node(c, depth + 1) for c in node["children"])
        children_html = (
            f'<ul class="tree-children" data-depth="{depth + 1}">{inner}</ul>'
        )

    html_content = node.get("htmlContent")
    if html_content:
        srcdoc = (
            (_HTML_PREVIEW_CSS + html_content)
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html_preview = f'<iframe class="html-preview" sandbox="allow-scripts" srcdoc="{srcdoc}"></iframe>'
    else:
        html_preview = ""

    make_btn = (
        f'<button class="make-button" data-item="{node_data}" title="Make artifact">Make</button>'
        if can_make
        else ""
    )
    info_btn = (
        f'<button class="info-button" data-item="{node_data}" title="Show information">i</button>'
        if has_info_popup
        else ""
    )

    return f"""<li class="tree-item">
        <div class="{node_class}" data-item="{node_data}">
            <span class="{icon_class}"></span>
            <span class="tree-label">{label_html}</span>
            {make_btn}
            {info_btn}
        </div>
        {html_preview}
        {children_html}
    </li>"""


def get_details_html(
    project_basename: str,
    project_url: str,
    project: dict,
    highlight_key: str | None = None,
) -> str:
    """Generate the Details panel HTML for a single project.

    Equivalent to getDetailsWebviewContent() in extension.ts.

    Parameters
    ----------
    project_basename:
        Display name of the project (last path component).
    project_url:
        Full URL/path of the project.
    project:
        The project dict (from ``Project.to_dict()``).
    highlight_key:
        Dot-separated key path to scroll to and highlight on load.
    """
    info_data = _get_info_data()
    detail_nodes = _build_detail_nodes(project, "none", "", project_url, info_data)
    tree_html = "".join(_render_detail_node(n, 0) for n in detail_nodes)
    initial_key_js = json.dumps(highlight_key) if highlight_key else "null"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape(project_basename)} — details</title>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <style>
{_TREE_SHARED_CSS}

        body {{
            display: flex; flex-direction: column; height: 100vh; overflow: hidden;
            padding: 0; margin: 0;
        }}
        .project-header {{
            padding: 8px 10px; border-bottom: 1px solid #454545; flex-shrink: 0;
        }}
        .project-title {{ font-weight: bold; font-size: 14px; color: #dcb67a; margin-bottom: 2px; }}
        .project-url {{ font-size: 11px; color: #9e9e9e; word-break: break-all; }}
        .controls-container {{
            padding: 6px 8px; display: flex; gap: 6px;
            border-bottom: 1px solid #454545; flex-shrink: 0;
        }}
        #tree-container {{ flex: 1; overflow-y: auto; padding: 6px 10px; position: relative; }}
    </style>
</head>
<body>
    <div class="project-header">
        <div class="project-title">{_escape(project_basename)}</div>
        <div class="project-url">{_escape(project_url)}</div>
    </div>
    <div class="controls-container">
        <button id="btn-default" class="control-button active">Default view</button>
        <button id="btn-expand" class="control-button">Expand All</button>
        <button id="btn-collapse" class="control-button">Collapse All</button>
    </div>
    <div id="tree-container">
        <ul class="tree">{tree_html}</ul>
    </div>

    {_INFO_POPUP_HTML}

    <script>
        // Qt WebChannel bridge
        let bridge = null;
        function postMessage(msg) {{
            if (bridge) bridge.handleMessage(JSON.stringify(msg));
        }}
        new QWebChannel(qt.webChannelTransport, function(channel) {{
            bridge = channel.objects.bridge;
        }});

        // ── Expand / collapse ──────────────────────────────────────────────
        function setExpanded(ul, expanded) {{
            ul.classList.toggle('expanded', expanded);
            const icon = ul.closest('.tree-item')?.querySelector(':scope > .tree-node > .tree-icon.expandable');
            if (icon) icon.classList.toggle('expanded', expanded);
        }}
        function expandAll() {{ document.querySelectorAll('.tree-children').forEach(ul => setExpanded(ul, true)); }}
        function collapseAll() {{ document.querySelectorAll('.tree-children').forEach(ul => setExpanded(ul, false)); }}
        function defaultView() {{
            document.querySelectorAll('.tree-children').forEach(ul => {{
                const depth = parseInt(ul.dataset.depth || '1', 10);
                setExpanded(ul, depth <= 1);
            }});
        }}
        function setActiveButton(btn) {{
            document.querySelectorAll('.control-button').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        }}
        document.getElementById('btn-expand').addEventListener('click', e => {{ expandAll(); setActiveButton(e.target); }});
        document.getElementById('btn-collapse').addEventListener('click', e => {{ collapseAll(); setActiveButton(e.target); }});
        document.getElementById('btn-default').addEventListener('click', e => {{ defaultView(); setActiveButton(e.target); }});

        // ── Scroll to key ──────────────────────────────────────────────────
        function scrollToKey(key) {{
            if (!key) return;
            const segments = key.split('.');
            let searchRoot = document.querySelector('.tree');
            let targetNode = null;
            for (const seg of segments) {{
                if (!searchRoot) break;
                let found = null;
                for (const node of searchRoot.querySelectorAll(':scope > .tree-item > .tree-node')) {{
                    try {{
                        const data = JSON.parse(node.dataset.item || '{{}}');
                        if (data.key === seg) {{ found = node; break; }}
                    }} catch(e) {{}}
                }}
                if (!found) break;
                targetNode = found;
                const treeItem = found.closest('.tree-item');
                const childList = treeItem ? treeItem.querySelector(':scope > .tree-children') : null;
                if (childList) setExpanded(childList, true);
                searchRoot = childList;
            }}
            if (targetNode) {{
                document.querySelectorAll('.tree-node.selected').forEach(n => n.classList.remove('selected'));
                targetNode.classList.add('selected');
                targetNode.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}

        const initialKey = {initial_key_js};
        window.addEventListener('DOMContentLoaded', () => {{
            defaultView();
            if (initialKey) scrollToKey(initialKey);
        }});

        // ── Tree interaction ───────────────────────────────────────────────
        document.addEventListener('click', e => {{
            if (e.target.classList.contains('tree-icon') && e.target.classList.contains('expandable')) {{
                const treeItem = e.target.closest('.tree-item');
                const children = treeItem.querySelector(':scope > .tree-children');
                setExpanded(children, !children.classList.contains('expanded'));
                return;
            }}
            if (e.target.classList.contains('info-button')) {{
                e.stopPropagation();
                showInfoPopup(e.target, JSON.parse(e.target.dataset.item));
                return;
            }}
            if (e.target.classList.contains('make-button')) {{
                e.stopPropagation();
                postMessage({{ command: 'makeArtifact', item: JSON.parse(e.target.dataset.item) }});
                return;
            }}
            const popup = document.getElementById('info-popup');
            if (!popup.contains(e.target) && !e.target.classList.contains('info-button')) hideInfoPopup();
        }});
        document.addEventListener('keydown', e => {{ if (e.key === 'Escape') hideInfoPopup(); }});

{_INFO_POPUP_JS}
    </script>
</body>
</html>"""
