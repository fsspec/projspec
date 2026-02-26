from io import StringIO

from projspec.proj import ProjectSpec


class HuggingFaceRepo(ProjectSpec):
    spec_doc = "https://huggingface.co/docs/hub/en/model-cards"

    # full_spec = ("https://github.com/huggingface/huggingface_hub/blob/"
    #              "main/src/huggingface_hub/templates/modelcard_template.md")

    # fields: language, library_name, tags, base_model, new_version, datasets
    #  license, license_name, license_link, model-index (results)
    # Dataset names are the same as the repo names in HF.

    def match(self) -> bool:
        readme = f"{self.proj.url}/README.md"
        return self.proj.fs.exists(readme)

    def parse(self) -> None:
        from projspec.content.metadata import DescriptiveMetadata, License
        import yaml

        readme = f"{self.proj.url}/README.md"

        with self.proj.fs.open(readme, "rt") as f:
            txt = f.read()
        meta = txt.split("---\n")[1]
        meta = yaml.safe_load(StringIO(meta))
        if "licence" in meta:
            self.contents["license"] = License(
                proj=self.proj,
                shortname=meta["licence"],
                fullname=meta.get("license_name"),
                url=meta.get("license_link"),
                artifacts=set(),
            )
        self.contents["desciptive_metadata"] = DescriptiveMetadata(
            proj=self.proj,
            meta={
                k: meta[k] for k in ["language", "library_name", "tags"] if k in meta
            },
            artifacts=set(),
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
