import re

from projspec.proj.base import ProjectSpec
from projspec.content.package import NodePackage
from projspec.artifact.process import Process
from projspec.content.executable import Command
from projspec.utils import AttrDict


class Node(ProjectSpec):
    """Node.js project, managed by NPM

    This is a project that contains a package.json file.
    """

    spec_doc = "https://docs.npmjs.com/cli/v11/configuring-npm/package-json"

    def match(self):
        return "package.json" in self.proj.basenames

    def parse0(self):
        from projspec.content.environment import Environment, Stack, Precision
        from projspec.content.metadata import DescriptiveMetadata
        from projspec.artifact.python_env import LockFile

        import json

        with self.proj.fs.open(f"{self.proj.url}/package.json", "rt") as f:
            pkg_json = json.load(f)
        self.meta = pkg_json

        # Metadata
        name = pkg_json.get("name")
        version = pkg_json.get("version")
        description = pkg_json.get("description")
        # Dependencies
        dependencies = pkg_json.get("dependencies")
        dev_dependencies = pkg_json.get("devDependencies")
        # Entry points for runtime execution: CLI
        scripts = pkg_json.get("scripts", {})
        bin = pkg_json.get("bin")
        # Entry points for importable code: library
        main = pkg_json.get("main")
        module = pkg_json.get("module")
        # TBD: exports?
        # Package manager
        package_manager = pkg_json.get("packageManager", "npm@latest")
        if isinstance(package_manager, str):
            package_manager_name = package_manager.split("@")[0]
        else:
            package_manager_name = package_manager.get("name", "npm")

        # Commands
        bin_entry = {}
        if bin and isinstance(bin, str):
            bin_entry = {name: bin}
        elif bin and isinstance(bin, dict):
            bin_entry = bin

        # Contents
        conts = AttrDict(
            {
                "descriptive_metadata": DescriptiveMetadata(
                    proj=self.proj,
                    meta={
                        "name": name,
                        "version": version,
                        "description": description,
                        "main": main,
                        "module": module,
                    },
                    artifacts=set(),
                ),
            },
        )

        cmd = AttrDict()
        for name, path in bin_entry.items():
            cmd[name] = Command(
                proj=self.proj, cmd=["node", f"{self.proj.url}/{path}"], artifacts=set()
            )

        # Artifacts
        arts = AttrDict()
        for script_name, script_cmd in scripts.items():
            if script_name == "build":
                arts["build"] = Process(
                    proj=self.proj, cmd=[package_manager_name, "run", script_name]
                )
            else:
                cmd[script_name] = Command(
                    proj=self.proj,
                    cmd=[package_manager_name, "run", script_name],
                    artifacts=set(),
                )

        if "package-lock.json" in self.proj.basenames:
            arts["lock_file"] = LockFile(
                proj=self.proj,
                artifacts={},
                cmd=["npm", "install"],
                fn=self.proj.basenames["package-lock.json"],
            )
            # TODO: load lockfile and make environment
        conts.setdefault("environment", {})["node"] = Environment(
            proj=self.proj,
            artifacts=set(),
            stack=Stack.NPM,
            packages=dependencies,
            precision=Precision.SPEC,
        )
        conts.setdefault("environment", {})["node_dev"] = Environment(
            proj=self.proj,
            artifacts=set(),
            stack=Stack.NPM,
            packages=dev_dependencies,  # + dependencies?
            precision=Precision.SPEC,
        )

        conts["node_package"] = (
            NodePackage(name=name, proj=self.proj, artifacts=set()),
        )
        conts["command"] = (cmd,)
        self._artifacts = arts
        self._contents = conts

    def parse(self):
        self.parse0()


class Yarn(Node):
    """A node project that uses `yarn` for building"""

    spec_doc = "https://yarnpkg.com/configuration/yarnrc"

    def match(self):
        return ".yarnrc.yml" in self.proj.basenames

    def parse(self):
        from projspec.content.environment import Environment, Stack, Precision
        from projspec.artifact.python_env import LockFile

        super().parse0()

        with self.proj.fs.open(f"{self.proj.url}/yarn.lock", "rt") as f:
            txt = f.read()
        hits = re.findall(r'resolution: "(.*?)"', txt, flags=re.MULTILINE)

        self.artifacts["lock_file"] = LockFile(
            proj=self.proj,
            cmd=["yarn", "install"],
            fn=self.proj.basenames["yarn.lock"],
        )
        self.contents.setdefault("environment", {})["yarn_lock"] = Environment(
            proj=self.proj,
            artifacts=set(),
            stack=Stack.NPM,
            packages=hits,
            precision=Precision.LOCK,
        )


class JLabExtension(Yarn):
    """A node variant specific to JLab

    https://jupyterlab.readthedocs.io/en/latest/developer/contributing.html
      #installing-node-js-and-jlpm
    """

    # TODO: this should match even if yarn.lock is missing, so long as package.json
    #  does exist, and uses jlpm to build

    def parse(self):
        from projspec.artifact.python_env import LockFile

        super().parse()
        if not self.meta["scripts"]["build"].startswith("jlpm"):
            raise ValueError
        self.artifacts["lock_file"] = LockFile(
            proj=self.proj,
            cmd=["jlpm", "install"],
            fn=self.proj.basenames["yarn.lock"],
        )
