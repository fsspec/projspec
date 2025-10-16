from projspec.proj.base import ProjectSpec
from projspec.content.package import NodePackage
from projspec.artifact.process import Process
from projspec.content.executable import Command
from projspec.utils import AttrDict


class Node(ProjectSpec):
    """Node.js project

    This is a project that contains a package.json file.
    """

    spec_doc = "https://docs.npmjs.com/cli/v11/configuring-npm/package-json"

    def match(self):
        return "package.json" in self.proj.basenames

    def parse(self):
        from projspec.content.environment import NodeEnvironment, Stack
        from projspec.artifact.python_env import LockFile

        import json

        with self.proj.fs.open(f"{self.proj.url}/package.json", "rt") as f:
            pkg_json = json.load(f)

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
        conts = AttrDict()
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

        # package-lock.json
        # yarn.lock
        # TBD: indicate precision?
        if "package-lock.json" in self.proj.basenames:
            arts["package-lock"] = LockFile(
                proj=self.proj,
                artifacts={},
                cmd=["npm", "install"],
                fn=self.proj.basenames["package-lock.json"],
            )
            conts["environments"] = NodeEnvironment(
                proj=self.proj,
                artifacts=set(),
                stack=Stack.NPM,
                packages=dependencies,
                dev_packages=dev_dependencies,
            )
        if "yarn.lock" in self.proj.basenames:
            arts["yarn"] = LockFile(
                proj=self.proj,
                cmd=["yarn", "install"],
                fn=self.proj.basenames["yarn.lock"],
            )
            conts["environments"] = NodeEnvironment(
                proj=self.proj,
                artifacts=set(),
                stack=Stack.YARN,
                packages=dependencies,
                dev_packages=dev_dependencies,
            )

        conts["node_package"] = node_package = (
            NodePackage(name=name, proj=self.proj, artifacts=set()),
        )
        conts["command"] = (cmd,)
        self._artifacts = arts
        self._contents = conts
