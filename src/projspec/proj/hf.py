from io import StringIO

from projspec.proj import ProjectSpec


class HuggingFaceRepo(ProjectSpec):
    def match(self) -> bool:
        readme = f"{self.root.url}/README.md"
        return self.root.fs.exists(readme)

    def parse(self) -> None:
        # for now, we just stash the metadata declaration
        import yaml

        readme = f"{self.root.url}/README.md"

        with self.root.fs.open(readme) as f:
            txt = f.read()
        meta = txt.split("---\n")[1]
        self.meta = yaml.safe_load(StringIO(meta))
