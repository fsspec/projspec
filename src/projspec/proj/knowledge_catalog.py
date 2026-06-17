"""The :class:`KnowledgeCatalog` project spec.

Detects an *Open Knowledge Format* (OKF) bundle: a directory tree of markdown
files with YAML frontmatter, where every non-reserved ``.md`` file is a
"concept" carrying at least a ``type`` field.  Two filenames are reserved at
any level: ``index.md`` (directory listing) and ``log.md`` (update history).

See https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
"""

from __future__ import annotations

import os
from io import StringIO

from projspec.proj import ProjectSpec
from projspec.proj.base import ParseFailed
from projspec.utils import AttrDict

# Filenames with reserved meaning that are never concept documents (§3.1).
_RESERVED = {"index.md", "log.md"}


def _split_frontmatter(text: str | bytes) -> dict | None:
    """Return the parsed YAML frontmatter block of a markdown document.

    Returns ``None`` when the document has no parseable ``---``-delimited
    frontmatter mapping at its start.
    """
    import yaml

    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    # Frontmatter must be delimited by '---' on its own line at the start and a
    # closing '---'. Require at least the opening and closing fences.
    if text.count("---\n") < 2 and not text.lstrip().startswith("---"):
        return None
    parts = text.split("---\n")
    if len(parts) < 3:
        return None
    # parts[0] is whatever precedes the first fence (should be empty/whitespace)
    if parts[0].strip():
        return None
    try:
        meta = yaml.safe_load(StringIO(parts[1]))
    except Exception:
        return None
    return meta if isinstance(meta, dict) else None


class KnowledgeCatalog(ProjectSpec):
    """An Open Knowledge Format (OKF) knowledge bundle.

    An OKF bundle is a directory of markdown "concept" documents, each with a
    YAML frontmatter block declaring a ``type``.  Reserved ``index.md`` /
    ``log.md`` files provide directory listings and update history.

    Produces one :class:`projspec.content.metadata.DescriptiveMetadata` per
    concept, keyed by its *concept ID* (the file path within the bundle with
    the ``.md`` suffix removed, e.g. ``tables/orders``).
    """

    icon = "📚"
    spec_doc = (
        "https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md"
    )

    def match(self) -> bool:
        """Cheap check: a reserved ``index.md`` is present, plus either another
        markdown document or a subdirectory that might hold concepts.

        Full validation (that concepts carry a ``type`` field) is deferred to
        :meth:`parse`, which raises :class:`ParseFailed` if none qualify, so a
        plain ``index.md`` from some other tool does not register as an OKF
        bundle.
        """
        if "index.md" not in self.proj.basenames:
            return False
        # another markdown concept at the root...
        for name in self.proj.basenames:
            if name.endswith(".md") and name not in _RESERVED:
                return True
        # ...or a subdirectory that might contain concepts
        for info in self.proj.filelist:
            if info.get("type") == "directory":
                base = str(info["name"]).rstrip("/").rsplit("/", 1)[-1]
                # skip hidden/dunder dirs (handled like project walking)
                if not base.startswith((".", "_")):
                    return True
        return False

    def _concept_files(self) -> list[str]:
        """Full paths of candidate concept documents (recursive, non-reserved)."""
        root = self.proj.url.rstrip("/")
        try:
            # glob may return a list or (with detail) a dict keyed by path
            paths = list(self.proj.fs.glob(f"{root}/**/*.md"))
        except Exception:
            # fall back to the top-level listing if globbing isn't supported
            paths = [
                full
                for name, full in self.proj.basenames.items()
                if name.endswith(".md")
            ]
        out = []
        for p in paths:
            p = str(p)
            base = p.rsplit("/", 1)[-1]
            if base in _RESERVED:
                continue
            out.append(p)
        return sorted(out)

    def _concept_id(self, full_path: str) -> str:
        """The concept ID: bundle-relative path with the ``.md`` suffix removed."""
        root = self.proj.url.rstrip("/") + "/"
        rel = full_path[len(root) :] if full_path.startswith(root) else full_path
        if rel.endswith(".md"):
            rel = rel[: -len(".md")]
        return rel

    def parse(self) -> None:
        from projspec.content.metadata import DescriptiveMetadata

        concepts = AttrDict()
        for full in self._concept_files():
            try:
                with self.proj.fs.open(full, "rt") as f:
                    text = f.read()
            except OSError:
                continue
            meta = _split_frontmatter(text)
            if not meta:
                # not a conformant concept document - skip
                continue
            type_ = meta.get("type")
            if not type_ or not str(type_).strip():
                # §9: every concept frontmatter must carry a non-empty `type`
                continue

            entry: dict[str, str] = {"type": str(type_)}
            for field in ("title", "description", "resource", "timestamp"):
                val = meta.get(field)
                if val:
                    entry[field] = str(val)
            tags = meta.get("tags")
            if tags:
                if isinstance(tags, (list, tuple)):
                    entry["tags"] = ", ".join(str(t) for t in tags)
                else:
                    entry["tags"] = str(tags)

            key = self._concept_id(full)
            concepts[key] = DescriptiveMetadata(proj=self.proj, meta=entry)

        if not concepts:
            raise ParseFailed("No OKF concept documents with a 'type' field found")

        # The bundle-root index.md may declare the OKF version it targets.
        bundle_meta: dict[str, str] = {}
        if "index.md" in self.proj.basenames:
            try:
                with self.proj.get_file("index.md") as f:
                    idx = _split_frontmatter(f.read())
            except OSError:
                idx = None
            if idx and idx.get("okf_version"):
                bundle_meta["okf_version"] = str(idx["okf_version"])

        contents = AttrDict(concept=concepts)
        if bundle_meta:
            contents["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=bundle_meta
            )
        self._contents = contents
        self._artifacts = AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal but conformant OKF bundle."""
        name = os.path.basename(path.rstrip("/")) or "bundle"

        with open(f"{path}/index.md", "w") as f:
            f.write(
                "---\n"
                'okf_version: "0.1"\n'
                "---\n\n"
                f"# {name}\n\n"
                "* [Overview](overview.md) - what this bundle contains\n"
            )

        with open(f"{path}/log.md", "w") as f:
            f.write(
                "# Update Log\n\n"
                "## 2026-01-01\n"
                "* **Initialization**: Created the bundle.\n"
            )

        with open(f"{path}/overview.md", "w") as f:
            f.write(
                "---\n"
                "type: Reference\n"
                f"title: {name} overview\n"
                "description: A short description of this knowledge bundle.\n"
                "---\n\n"
                f"# {name}\n\n"
                "Free-form markdown describing the knowledge captured here.\n"
            )
