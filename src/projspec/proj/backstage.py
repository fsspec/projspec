import os

import yaml

from projspec.proj import ProjectSpec
from projspec.proj.base import ParseFailed
from projspec.utils import AttrDict


class BackstageCatalog(ProjectSpec):
    """A Backstage software catalog descriptor file (catalog-info.yaml).

    Backstage catalogs describe software components, APIs, resources, systems,
    domains and other entities using a Kubernetes-style envelope with `apiVersion`,
    `kind`, `metadata`, and `spec` sections.  A single file may contain multiple
    `---`-separated documents.
    """

    icon = "sitemap"
    spec_doc = "https://backstage.io/docs/features/software-catalog/descriptor-format/"

    def match(self) -> bool:
        return "catalog-info.yaml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.metadata import DescriptiveMetadata

        try:
            with self.proj.get_file("catalog-info.yaml") as f:
                raw = f.read()
        except OSError as exc:
            raise ParseFailed(f"Could not read catalog-info.yaml: {exc}") from exc

        # The file may contain multiple YAML documents separated by "---"
        try:
            docs = list(yaml.safe_load_all(raw))
        except yaml.YAMLError as exc:
            raise ParseFailed(f"Invalid YAML in catalog-info.yaml: {exc}") from exc

        docs = [d for d in docs if isinstance(d, dict)]
        if not docs:
            raise ParseFailed("catalog-info.yaml contains no valid entity documents")

        # Only accept documents that declare a backstage apiVersion
        backstage_docs = [
            d for d in docs if str(d.get("apiVersion", "")).startswith("backstage.io/")
        ]
        if not backstage_docs:
            raise ParseFailed(
                "catalog-info.yaml contains no backstage.io entity documents"
            )

        # Build one DescriptiveMetadata per entity, keyed by "<kind>.<name>".
        meta_entries = AttrDict()
        for doc in backstage_docs:
            kind = doc.get("kind", "unknown")
            metadata = (
                doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            )
            spec = doc.get("spec", {}) if isinstance(doc.get("spec"), dict) else {}

            name = metadata.get("name", "unnamed")
            key = f"{kind.lower()}.{name}"

            entry: dict[str, str] = {"kind": kind}
            for field in ("name", "title", "description", "namespace"):
                if val := metadata.get(field):
                    entry[field] = str(val)
            for field in ("type", "lifecycle", "owner"):
                if val := spec.get(field):
                    entry[field] = str(val)
            tags = metadata.get("tags", [])
            if tags:
                entry["tags"] = ", ".join(str(t) for t in tags)

            meta_entries[key] = DescriptiveMetadata(proj=self.proj, meta=entry)

        self._contents = AttrDict(descriptive_metadata=meta_entries)
        self._artifacts = AttrDict()

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Backstage catalog-info.yaml."""
        name = os.path.basename(path)
        doc = {
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {
                "name": name,
                "description": f"A {name} component",
            },
            "spec": {
                "type": "service",
                "lifecycle": "experimental",
                "owner": "team-default",
            },
        }
        with open(f"{path}/catalog-info.yaml", "wt") as f:
            yaml.dump(doc, f, default_flow_style=False, sort_keys=False)
