from io import StringIO

from projspec.proj import ProjectSpec, ParseFailed

# Metadata keys that are specific to dataset cards and never appear on model cards.
# Used to distinguish the two repo types when both have a README.md.
_DATASET_DISCRIMINATORS = frozenset(
    [
        "task_categories",
        "task_ids",
        "dataset_info",
        "size_categories",
        "annotations_creators",
        "language_creators",
        "source_datasets",
        "configs",
    ]
)


class HuggingFaceRepo(ProjectSpec):
    spec_doc = "https://huggingface.co/docs/hub/en/model-cards"

    # full_spec = ("https://github.com/huggingface/huggingface_hub/blob/"
    #              "main/src/huggingface_hub/templates/modelcard_template.md")

    # fields: language, library_name, tags, base_model, new_version, datasets
    #  license, license_name, license_link, model-index (results)
    # Dataset names are the same as the repo names in HF.

    def match(self) -> bool:
        return "README.md" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.metadata import DescriptiveMetadata, License, Citation
        import yaml

        with self.get_file("README.md") as f:
            txt = f.read()
        if txt.count("---\n") < 2:
            raise ParseFailed
        meta = txt.split("---\n")[1]
        try:
            meta = yaml.safe_load(StringIO(meta))
        except Exception as e:
            raise ParseFailed from e
        if not isinstance(meta, dict):
            raise ParseFailed
        if {
            "dataset_info",
            "source_datasets",
            "task_categories",
            "task_ids",
        }.intersection(meta):
            raise ParseFailed("README.md is a dataset card")

        if "licence" in meta:
            self.contents["license"] = License(
                proj=self.proj,
                shortname=meta["licence"],
                fullname=meta.get("license_name"),
                url=meta.get("license_link"),
            )
        for tag in meta.get("tags", []):
            if tag.startswith("arxiv:"):
                self._contents.setdefault("citations", []).append(
                    Citation(
                        proj=self.proj, meta=dict(arxiv=tag.removeprefix("arxiv:"))
                    )
                )
        # TODO: datasets are links to other repos
        self.contents["descriptive_metadata"] = DescriptiveMetadata(
            proj=self.proj,
            meta={
                k: meta[k]
                for k in [
                    "language",
                    "library_name",
                    "tags",
                    "base_model",
                    "new_version",
                ]
                if k in meta
            },
        )

    @staticmethod
    def _create(path: str) -> None:
        with open(f"{path}/README.md", "w") as f:
            f.write(
                """---
license: other
license_name: coqui-public-model-license
license_link: https://coqui.ai/cpml
library_name: flair
tags:
- flair
base_model: HuggingFaceH4/zephyr-7b-beta
new_version: 0.1
datasets:
- stanfordnlp/imdb
- HuggingFaceFW/fineweb
---
"""
            )


class HuggingFaceDataset(ProjectSpec):
    """A dataset repository hosted on the Hugging Face Hub.

    A HuggingFace dataset repo is identified by a ``README.md`` whose YAML
    front-matter contains at least one dataset-specific key (e.g.
    ``task_categories``, ``dataset_info``, ``size_categories``).

    Parsed contents
    ---------------
    descriptive_metadata
        Carries ``pretty_name``, ``language``, ``tags``, ``task_categories``,
        ``size_categories``, ``source_datasets``, ``annotations_creators``,
        and ``language_creators`` — whichever are present in the card.
    license *(optional)*
        Present when a ``license`` key is found in the front-matter.
    """

    # detailed spec: https://raw.githubusercontent.com/huggingface/hub-docs/refs/heads/main/datasetcard.md
    spec_doc = "https://huggingface.co/docs/hub/datasets-cards"

    def match(self) -> bool:
        return "README.md" in self.proj.basenames

    def parse(self) -> None:
        import yaml
        from projspec.content.metadata import DescriptiveMetadata, License, Citation
        from projspec.content.data import TabularData

        try:
            with self.get_file("README.md") as f:
                txt = f.read()
        except OSError as exc:
            raise ParseFailed(f"Could not read README.md: {exc}") from exc

        if txt.count("---\n") < 2:
            raise ParseFailed("README.md has no YAML front-matter")
        try:
            meta = yaml.safe_load(StringIO(txt.split("---\n")[1]))
        except yaml.YAMLError as exc:
            raise ParseFailed(f"Invalid YAML front-matter: {exc}") from exc
        if not isinstance(meta, dict):
            raise ParseFailed("YAML front-matter did not parse to a mapping")
        if {"library_name", "base_model", "new_version"}.intersection(meta):
            raise ParseFailed("README.md is a dataset card")

        if "license" in meta:
            self._contents["license"] = License(
                proj=self.proj,
                shortname=meta["license"],
                fullname=meta.get("license_name", "unknown"),
                url=meta.get("license_link", ""),
            )
        for tag in meta.get("tags", []):
            if tag.startswith("arxiv:"):
                self._contents.setdefault("citations", []).append(
                    Citation(
                        proj=self.proj, meta=dict(arxiv=tag.removeprefix("arxiv:"))
                    )
                )

        # TODO: source_datasets are links to other datasets
        descriptive_keys = [
            "pretty_name",
            "language",
            "tags",
            "task_categories",
            "task_ids",
            "size_categories",
            "source_datasets",
            "annotations_creators",
            "language_creators",
            "paperswithcode_id",
        ]
        card_meta = {k: meta[k] for k in descriptive_keys if k in meta}
        self._contents["descriptive_metadata"] = DescriptiveMetadata(
            proj=self.proj,
            meta=card_meta,
        )
        if datasets := meta.get("dataset_info"):
            # only including configured tabular data for now
            if "config_name" in datasets[0]:
                self._contents["tabular_data"] = [
                    TabularData(
                        name=data["config_name"],
                        proj=self.proj,
                        schema=data["features"],
                        metadata={
                            k: data[k]
                            for k in ("splits", "download_size", "dataset_size")
                            if k in data
                        },
                    )
                    for data in datasets
                    if "features" in data
                ]
            else:
                if "features" in datasets:
                    self._contents["tabular_data"] = TabularData(
                        name="data",
                        proj=self.proj,
                        schema=datasets["features"],
                        metadata={
                            k: datasets[k]
                            for k in ("splits", "download_size", "dataset_size")
                            if k in datasets
                        },
                    )

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal but valid HuggingFace dataset card."""
        with open(f"{path}/README.md", "w") as f:
            f.write(
                """\
---
pretty_name: My Dataset
license: apache-2.0
language:
- en
tags:
- text
task_categories:
- text-classification
size_categories:
- n<1K
---

# My Dataset

A short description of the dataset.
"""
            )
