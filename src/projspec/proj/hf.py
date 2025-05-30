from io import StringIO

from projspec.proj import ProjectSpec


class HuggingFaceRepo(ProjectSpec):

    def match(self) -> bool:
        import yaml
        readme = f"{self.root.url}/README.md"
        try:
            with self.root.fs.open(readme) as f:
                txt = f.read()
        except (FileNotFoundError, IOError, UnicodeDecodeError):
            return False
        if txt.count("---\n") < 2:
            return False
        meta = txt.split("---\n")[1]
        try:
            yaml.safe_load(StringIO(meta))
            return True
        except yaml.YAMLError:
            return False
