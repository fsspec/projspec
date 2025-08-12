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
        # for now, we just stash the metadata declaration
        import yaml

        readme = f"{self.proj.url}/README.md"

        with self.proj.fs.open(readme) as f:
            txt = f.read()
        meta = txt.split("---\n")[1]
        self.meta = yaml.safe_load(StringIO(meta))
