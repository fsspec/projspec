# https://helm.sh/docs/topics/charts/#the-chartyaml-file
import os

import yaml

from projspec.proj.base import ParseFailed, ProjectSpec
from projspec.utils import AttrDict


class HelmChart(ProjectSpec):
    """A Kubernetes application packaged as a Helm chart.

    A Helm chart is a directory tree containing a ``Chart.yaml`` manifest,
    a ``templates/`` directory of Kubernetes resource manifests, and an
    optional ``values.yaml`` file with default configuration values.
    Dependency charts may be declared in ``Chart.yaml`` under the
    ``dependencies`` key; pinned versions are recorded in ``Chart.lock``.
    """

    spec_doc = "https://helm.sh/docs/topics/charts/#the-chartyaml-file"

    def match(self) -> bool:
        return "Chart.yaml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Process
        from projspec.content.metadata import DescriptiveMetadata

        # ------------------------------------------------------------------ #
        # Chart.yaml — required by the Helm spec
        # ------------------------------------------------------------------ #
        try:
            with self.proj.fs.open(self.proj.basenames["Chart.yaml"], "rt") as f:
                chart = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as exc:
            raise ParseFailed(f"Could not read Chart.yaml: {exc}") from exc

        if not isinstance(chart, dict):
            raise ParseFailed("Chart.yaml did not parse to a mapping")

        name = chart.get("name", "")
        version = chart.get("version", "")

        # ------------------------------------------------------------------ #
        # Contents
        # ------------------------------------------------------------------ #
        meta: dict[str, str] = {}
        for key in (
            "name",
            "version",
            "appVersion",
            "description",
            "type",
            "home",
            "icon",
        ):
            val = chart.get(key)
            if val is not None:
                meta[key] = str(val)

        keywords = chart.get("keywords", [])
        if keywords:
            meta["keywords"] = ", ".join(keywords)

        maintainers = chart.get("maintainers", [])
        if maintainers:
            # Each entry: {name, email, url} — flatten to a readable string
            meta["maintainers"] = ", ".join(
                m.get("name", "") for m in maintainers if isinstance(m, dict)
            )

        self._contents = AttrDict(
            descriptive_metadata=DescriptiveMetadata(proj=self.proj, meta=meta)
        )

        # ------------------------------------------------------------------ #
        # Artifacts
        # ------------------------------------------------------------------ #
        arts = AttrDict()

        # helm package . → produces <name>-<version>.tgz
        tgz_pattern = (
            f"{self.proj.url}/{name}-{version}.tgz"
            if name and version
            else f"{self.proj.url}/*.tgz"
        )
        arts["packaged_chart"] = FileArtifact(
            proj=self.proj,
            cmd=["helm", "package", "."],
            fn=tgz_pattern,
        )

        # helm dependency update → populates charts/ and writes Chart.lock
        arts["chart_lock"] = FileArtifact(
            proj=self.proj,
            cmd=["helm", "dependency", "update", "."],
            fn=f"{self.proj.url}/Chart.lock",
        )

        # helm install / upgrade → deploys to the active k8s cluster
        release = name or "release"
        arts["release"] = Process(
            proj=self.proj,
            cmd=["helm", "upgrade", "--install", release, "."],
        )

        # helm lint — validates chart structure and values
        arts["lint"] = Process(
            proj=self.proj,
            cmd=["helm", "lint", "."],
        )

        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        """Scaffold a minimal but valid Helm chart directory."""
        name = os.path.basename(path)

        # Chart.yaml — required manifest
        with open(f"{path}/Chart.yaml", "wt") as f:
            f.write(
                f"apiVersion: v2\n"
                f"name: {name}\n"
                f"description: A Helm chart for {name}\n"
                f"type: application\n"
                f"version: 0.1.0\n"
                f'appVersion: "1.0.0"\n'
            )

        # values.yaml — default configuration values
        with open(f"{path}/values.yaml", "wt") as f:
            f.write(
                "replicaCount: 1\n"
                "\n"
                "image:\n"
                f"  repository: {name}\n"
                "  tag: latest\n"
                "  pullPolicy: IfNotPresent\n"
                "\n"
                "service:\n"
                "  type: ClusterIP\n"
                "  port: 80\n"
            )

        # templates/ directory with a minimal Deployment manifest
        os.makedirs(f"{path}/templates", exist_ok=True)
        with open(f"{path}/templates/deployment.yaml", "wt") as f:
            f.write(
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                f"  name: {name}\n"
                "spec:\n"
                "  replicas: {{ .Values.replicaCount }}\n"
                "  selector:\n"
                "    matchLabels:\n"
                f"      app: {name}\n"
                "  template:\n"
                "    metadata:\n"
                "      labels:\n"
                f"        app: {name}\n"
                "    spec:\n"
                "      containers:\n"
                f"        - name: {name}\n"
                '          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"\n'
                "          imagePullPolicy: {{ .Values.image.pullPolicy }}\n"
                "          ports:\n"
                "            - containerPort: {{ .Values.service.port }}\n"
            )
