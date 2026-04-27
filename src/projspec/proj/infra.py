"""Infrastructure/deployment project specs: DockerCompose, Terraform, Ansible, Pulumi, CDK, Earthfile, Nixpacks, Vagrant."""

import os
import re

import yaml

from projspec.proj.base import ParseFailed, ProjectSpec
from projspec.utils import AttrDict


class DockerCompose(ProjectSpec):
    """Docker Compose multi-service project.

    Designed to launch a set of runtimes (specific images with config), volumes
    and networks, and expose ports.
    """

    icon = "layer-group"
    spec_doc = "https://docs.docker.com/reference/compose-file/"

    _NAMES = {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    }

    def match(self) -> bool:
        return bool(self._NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.infra import ComposeStack
        from projspec.content.cicd import ServiceDependency
        from projspec.content.metadata import DescriptiveMetadata

        fname = next(n for n in self._NAMES if n in self.proj.basenames)
        try:
            with self.proj.get_file(fname) as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read {fname}: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(f"{fname} did not parse to a mapping")

        services = cfg.get("services", {})
        service_deps = AttrDict()
        for svc_name, svc_cfg in services.items():
            if not isinstance(svc_cfg, dict):
                continue
            image = svc_cfg.get("image", "")
            # Guess service type from image name
            svc_type = image.split(":")[0].split("/")[-1] if image else svc_name
            service_deps[svc_name] = ServiceDependency(
                proj=self.proj,
                name=svc_name,
                service_type=svc_type,
                version=image.split(":")[-1] if ":" in image else "",
                image=image,
            )

        conts = AttrDict()
        if service_deps:
            conts["service_dependency"] = service_deps

        meta: dict[str, str] = {}
        if "name" in cfg:
            meta["name"] = str(cfg["name"])
        if services:
            meta["services"] = ", ".join(services.keys())
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        self._contents = conts
        self._artifacts = AttrDict(stack=ComposeStack(proj=self.proj, file=fname))

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal docker-compose.yml."""
        with open(os.path.join(path, "docker-compose.yml"), "wt") as f:
            f.write(
                "services:\n"
                "  app:\n"
                "    image: alpine:latest\n"
                "    command: echo 'Hello from Docker Compose!'\n"
            )


class Terraform(ProjectSpec):
    """Terraform infrastructure-as-code project."""

    icon = "cloud"
    spec_doc = "https://developer.hashicorp.com/terraform/language"

    def match(self) -> bool:
        return any(n.endswith(".tf") for n in self.proj.basenames)

    def parse(self) -> None:
        from projspec.artifact.infra import TerraformPlan
        from projspec.artifact.process import Process
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        # Extract resource types from .tf files
        resource_types: set[str] = set()
        providers: set[str] = set()
        for basename, full_path in self.proj.basenames.items():
            if not basename.endswith(".tf"):
                continue
            try:
                with self.proj.fs.open(full_path, "rt") as f:
                    content = f.read()
                resource_types.update(
                    re.findall(r'^resource\s+"([^"]+)"', content, re.MULTILINE)
                )
                providers.update(
                    re.findall(r'source\s*=\s*"[^/]+/([^"]+)"', content, re.MULTILINE)
                )
            except Exception:
                pass

        conts = AttrDict()
        meta: dict[str, str] = {}
        if providers:
            meta["providers"] = ", ".join(sorted(providers))
        if resource_types:
            meta["resource_types"] = ", ".join(sorted(resource_types))
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        tf_commands = {
            "init": ["terraform", "init"],
            "validate": ["terraform", "validate"],
            "apply": ["terraform", "apply", "-auto-approve"],
            "destroy": ["terraform", "destroy", "-auto-approve"],
            "output": ["terraform", "output"],
        }
        cmds = AttrDict()
        arts = AttrDict()
        for name, cmd in tf_commands.items():
            cmds[name] = Command(proj=self.proj, cmd=cmd)
            arts[name] = Process(proj=self.proj, cmd=cmd)

        arts["plan"] = TerraformPlan(proj=self.proj)

        conts["command"] = cmds
        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Terraform project."""
        with open(os.path.join(path, "main.tf"), "wt") as f:
            f.write(
                "terraform {\n"
                '  required_version = ">= 1.0"\n'
                "}\n"
                "\n"
                "# Add your resources here\n"
                '# resource "aws_instance" "example" {\n'
                '#   ami           = "ami-0c55b159cbfafe1f0"\n'
                '#   instance_type = "t2.micro"\n'
                "# }\n"
            )
        with open(os.path.join(path, "variables.tf"), "wt") as f:
            f.write(
                "# Define input variables here\n"
                '# variable "region" {\n'
                '#   default = "us-east-1"\n'
                "# }\n"
            )
        with open(os.path.join(path, "outputs.tf"), "wt") as f:
            f.write("# Define outputs here\n")


class Ansible(ProjectSpec):
    """Ansible automation project."""

    icon = "gears"
    spec_doc = "https://docs.ansible.com/ansible/latest/reference_appendices/playbooks_keywords.html"

    _PLAYBOOK_NAMES = {"playbook.yml", "playbook.yaml", "site.yml", "site.yaml"}

    def match(self) -> bool:
        if "ansible.cfg" in self.proj.basenames:
            return True
        if bool(self._PLAYBOOK_NAMES.intersection(self.proj.basenames)):
            return True
        # roles/ directory alongside a YAML file
        if self.proj.fs.isdir(f"{self.proj.url}/roles"):
            return any(n.endswith((".yml", ".yaml")) for n in self.proj.basenames)
        return False

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        # Find playbook files
        playbook_files = [
            n
            for n in self.proj.basenames
            if n.endswith((".yml", ".yaml"))
            and n not in {"requirements.yml", "galaxy.yml"}
        ]

        cmds = AttrDict()
        arts = AttrDict()

        for pb in playbook_files:
            name = pb.replace(".yml", "").replace(".yaml", "")
            cmd = ["ansible-playbook", pb]
            cmds[name] = Command(proj=self.proj, cmd=cmd)
            arts[name] = Process(proj=self.proj, cmd=cmd)

        if not cmds:
            cmds["run"] = Command(proj=self.proj, cmd=["ansible-playbook", "site.yml"])
            arts["run"] = Process(proj=self.proj, cmd=["ansible-playbook", "site.yml"])

        self._contents = AttrDict(command=cmds)
        self._artifacts = AttrDict(process=arts)

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Ansible project."""
        with open(os.path.join(path, "playbook.yml"), "wt") as f:
            f.write(
                "---\n"
                "- name: Example playbook\n"
                "  hosts: localhost\n"
                "  gather_facts: false\n"
                "  tasks:\n"
                "    - name: Print hello\n"
                "      ansible.builtin.debug:\n"
                "        msg: 'Hello from Ansible!'\n"
            )
        with open(os.path.join(path, "inventory"), "wt") as f:
            f.write("localhost ansible_connection=local\n")


class Pulumi(ProjectSpec):
    """Pulumi infrastructure-as-code project."""

    icon = "cloud-arrow-up"
    spec_doc = "https://www.pulumi.com/docs/reference/pulumi-yaml/"

    _NAMES = {"Pulumi.yaml", "Pulumi.yml"}

    def match(self) -> bool:
        return bool(self._NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.deployment import Deployment
        from projspec.artifact.process import Process
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        fname = next(n for n in self._NAMES if n in self.proj.basenames)
        try:
            with self.proj.get_file(fname) as f:
                cfg = yaml.safe_load(f)
        except Exception as exc:
            raise ParseFailed(f"Could not read {fname}: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(f"{fname} did not parse to a mapping")

        meta: dict[str, str] = {}
        for key in ("name", "description", "runtime"):
            if val := cfg.get(key):
                meta[key] = (
                    str(val) if not isinstance(val, dict) else str(val.get("name", val))
                )

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        stack_name = cfg.get("name", "dev")
        cmds = AttrDict(
            up=Command(proj=self.proj, cmd=["pulumi", "up", "--yes"]),
            destroy=Command(proj=self.proj, cmd=["pulumi", "destroy", "--yes"]),
            preview=Command(proj=self.proj, cmd=["pulumi", "preview"]),
        )
        arts = AttrDict(
            deploy=Deployment(
                proj=self.proj,
                cmd=["pulumi", "up", "--yes"],
                release=stack_name,
                clean_cmd=["pulumi", "destroy", "--yes"],
            ),
            preview=Process(proj=self.proj, cmd=["pulumi", "preview"]),
        )

        conts["command"] = cmds
        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Pulumi YAML project."""
        name = os.path.basename(path)
        with open(os.path.join(path, "Pulumi.yaml"), "wt") as f:
            f.write(
                f"name: {name}\n"
                "runtime: yaml\n"
                "description: A Pulumi YAML project\n"
                "\n"
                "resources: {}\n"
            )


class CDK(ProjectSpec):
    """AWS Cloud Development Kit (CDK) project."""

    icon = "aws"
    spec_doc = "https://docs.aws.amazon.com/cdk/v2/guide/projects.html"

    def match(self) -> bool:
        return "cdk.json" in self.proj.basenames

    def parse(self) -> None:
        import json
        from projspec.artifact.deployment import Deployment
        from projspec.artifact.process import Process
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        try:
            with self.proj.get_file("cdk.json") as f:
                cfg = json.loads(f.read())
        except Exception as exc:
            raise ParseFailed(f"Could not read cdk.json: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed("cdk.json did not parse to a mapping")

        app_cmd = cfg.get("app", "")
        conts = AttrDict()
        if app_cmd:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta={"app": app_cmd}
            )

        cmds = AttrDict(
            synth=Command(proj=self.proj, cmd=["cdk", "synth"]),
            deploy=Command(proj=self.proj, cmd=["cdk", "deploy", "--all"]),
            destroy=Command(proj=self.proj, cmd=["cdk", "destroy", "--all"]),
            diff=Command(proj=self.proj, cmd=["cdk", "diff"]),
        )
        arts = AttrDict(
            deploy=Deployment(
                proj=self.proj,
                cmd=["cdk", "deploy", "--all", "--require-approval", "never"],
                release="cdk",
                clean_cmd=["cdk", "destroy", "--all", "--force"],
            ),
            diff=Process(proj=self.proj, cmd=["cdk", "diff"]),
            synth=Process(proj=self.proj, cmd=["cdk", "synth"]),
        )

        conts["command"] = cmds
        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal CDK project."""
        with open(os.path.join(path, "cdk.json"), "wt") as f:
            f.write('{\n  "app": "npx ts-node --prefer-ts-exts bin/app.ts"\n}\n')


class Earthfile(ProjectSpec):
    """Earthly build project."""

    icon = "earth-americas"
    spec_doc = "https://docs.earthly.dev/docs/earthfile"

    def match(self) -> bool:
        return "Earthfile" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        # Parse targets from Earthfile
        target_names: list[str] = []
        try:
            with self.proj.get_file("Earthfile") as f:
                content = f.read()
            target_names = re.findall(
                r"^([a-zA-Z][a-zA-Z0-9_-]*):", content, re.MULTILINE
            )
        except Exception:
            pass

        cmds = AttrDict()
        arts = AttrDict()

        for target in target_names:
            if target.upper() == target:
                # All-caps are typically Earthly VERSION/ARG/etc directives, skip
                continue
            cmd = ["earthly", f"+{target}"]
            cmds[target] = Command(proj=self.proj, cmd=cmd)
            arts[target] = Process(proj=self.proj, cmd=cmd)

        if not cmds:
            cmds["build"] = Command(proj=self.proj, cmd=["earthly", "+build"])
            arts["build"] = Process(proj=self.proj, cmd=["earthly", "+build"])

        self._contents = AttrDict(command=cmds)
        self._artifacts = AttrDict(process=arts)

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Earthfile."""
        with open(os.path.join(path, "Earthfile"), "wt") as f:
            f.write(
                "VERSION 0.8\n"
                "\n"
                "build:\n"
                "    FROM alpine:latest\n"
                "    RUN echo 'Hello from Earthly!'\n"
                "\n"
                "test:\n"
                "    FROM +build\n"
                "    RUN echo 'Tests passed!'\n"
            )


class Nixpacks(ProjectSpec):
    """Nixpacks build configuration project."""

    icon = "snowflake"
    spec_doc = "https://nixpacks.com/docs/configuration/file"

    def match(self) -> bool:
        return "nixpacks.toml" in self.proj.basenames

    def parse(self) -> None:
        import toml
        from projspec.artifact.process import Process
        from projspec.content.metadata import DescriptiveMetadata
        from projspec.utils import PickleableTomlDecoder

        try:
            with self.proj.get_file("nixpacks.toml", text=False) as f:
                cfg = toml.loads(f.read().decode(), decoder=PickleableTomlDecoder())
        except Exception as exc:
            raise ParseFailed(f"Could not read nixpacks.toml: {exc}") from exc

        meta: dict[str, str] = {}
        phases = cfg.get("phases", {})
        if phases:
            meta["phases"] = ", ".join(phases.keys())
        start = cfg.get("start", {})
        if start_cmd := start.get("cmd"):
            meta["start_cmd"] = str(start_cmd)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        name = os.path.basename(self.proj.url).lower()
        arts = AttrDict(
            build=Process(
                proj=self.proj, cmd=["nixpacks", "build", ".", "--name", name]
            ),
        )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal nixpacks.toml."""
        with open(os.path.join(path, "nixpacks.toml"), "wt") as f:
            f.write(
                "[phases.setup]\n"
                "nixPkgs = ['python311']\n"
                "\n"
                "[phases.install]\n"
                "cmds = ['pip install -r requirements.txt']\n"
                "\n"
                "[start]\n"
                "cmd = 'python app.py'\n"
            )


class Vagrant(ProjectSpec):
    """Vagrant virtual machine project."""

    icon = "box-archive"
    spec_doc = "https://developer.hashicorp.com/vagrant/docs/vagrantfile"

    def match(self) -> bool:
        return "Vagrantfile" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.process import Process, Server
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        # Extract box name from Vagrantfile via simple regex
        meta: dict[str, str] = {}
        try:
            with self.proj.get_file("Vagrantfile") as f:
                content = f.read()
            boxes = re.findall(r'config\.vm\.box\s*=\s*["\']([^"\']+)["\']', content)
            if boxes:
                meta["box"] = boxes[0]
            hostname_match = re.search(
                r'config\.vm\.hostname\s*=\s*["\']([^"\']+)["\']', content
            )
            if hostname_match:
                meta["hostname"] = hostname_match.group(1)
        except Exception:
            pass

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        cmds = AttrDict(
            up=Command(proj=self.proj, cmd=["vagrant", "up"]),
            halt=Command(proj=self.proj, cmd=["vagrant", "halt"]),
            destroy=Command(proj=self.proj, cmd=["vagrant", "destroy", "-f"]),
            ssh=Command(proj=self.proj, cmd=["vagrant", "ssh"]),
        )
        arts = AttrDict(
            vm=Server(proj=self.proj, cmd=["vagrant", "up"]),
        )

        conts["command"] = cmds
        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal Vagrantfile."""
        with open(os.path.join(path, "Vagrantfile"), "wt") as f:
            f.write(
                'Vagrant.configure("2") do |config|\n'
                '  config.vm.box = "ubuntu/jammy64"\n'
                '  config.vm.provider "virtualbox" do |vb|\n'
                '    vb.memory = "1024"\n'
                "  end\n"
                "end\n"
            )
