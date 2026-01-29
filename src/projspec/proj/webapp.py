from projspec.proj import ProjectSpec


class StreamlitApp(ProjectSpec):
    spec_doc = "https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization"
    # see also "https://docs.streamlit.io/develop/api-reference/configuration/config.toml", which is
    # mainly theme and server config.

    def match(self) -> bool:
        return bool(
            {".streamlit", "streamlit_app.py"}.intersection(self.proj.basenames)
        )

    def parse(self) -> None:
        from projspec.content.environment import PythonRequirements, CondaEnv
        from projspec.artifact.process import Server

        # a requirements.txt file is the most common and suggested way, but uv, pipenv and poetry are
        # also supported - but they will get picked up as separate project types.
        # Furthermore, the spec can live alongside the code in subdirectories, the apps in this
        # project do not share an environment.
        if "environment" not in self.proj.contents:
            # just because of ordering
            for cls in (PythonRequirements, CondaEnv):
                if cls.match(self):
                    p = cls(self.proj)
                    p.parse()
                    self._contents["environment"] = p.contents["environment"]
                    break

        # the common case is a single .py file
        pyfiles = [v for v in self.proj.basenames if v.endswith(".py")]
        if len(pyfiles) == 1:
            self.artifacts["server"] = Server(
                proj=self.proj, cmd=["streamlit", "run", pyfiles[0]]
            )
        else:
            pyfiles = self.proj.fs.glob(f"{self.proj.url}/**/*.py")
            pycontent = self.proj.fs.cat(pyfiles)
            self.artifacts["server"] = {}
            for path, content in pycontent.items():
                if "import streamlit as st" and "\nst." in content.decode():
                    name = path.rsplit("/", 1)[-1].replace(".py", "")
                    self.artifacts["server"][name] = Server(
                        proj=self.proj,
                        cmd=["streamlit", "run", path.replace(self.proj.url, "")],
                    )
