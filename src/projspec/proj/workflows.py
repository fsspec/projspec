import yaml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict


class MLFlow(ProjectSpec):
    spec_doc = (
        "https://mlflow.org/docs/latest/ml/projects/#mlproject-file-configuration"
    )

    def match(self) -> bool:
        return "MLFlow" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.environment import Environment, Precision, Stack
        from projspec.artifact.process import Process
        from projspec.content.executable import Command

        with self.proj.fs.open(self.proj.basenames["MLFlow"], "rt") as f:
            meta = yaml.safe_load(f)
        if "python_env" in meta:
            with self.get_file(meta["python_env"], text=True) as f:
                env = yaml.safe_load(f)
                self.contents["environment"] = Environment(
                    stack=Stack.PIP,
                    precision=Precision.SPEC,
                    packages=env.get("dependencies", [])
                    + [f"python {env.get('python', " ")}"],
                    proj=self.proj,
                )
        elif "conda_env" in meta:
            with self.get_file(meta["conda_env"], text=True) as f:
                env = yaml.safe_load(f)
                self.contents["environment"] = Environment(
                    stack=Stack.CONDA,
                    precision=Precision.SPEC,
                    packages=env.get("dependencies", []),
                    channels=env.get("channels"),
                    proj=self.proj,
                )
        for name, cmd in meta.get("entry_points", {}).items():
            self.contents.setdefault("command", AttrDict())[name] = Command(
                proj=self.proj, cmd=cmd["command"]
            )
            self.artifacts.setdefault("process", AttrDict())[name] = Process(
                proj=self.proj, cmd=["mlflow", "run", ".", "-e", name]
            )

    @staticmethod
    def _create(path: str) -> None:
        with open(f"{path}/MLFlow", "w") as f:
            # https://github.com/mlflow/mlflow-example
            f.write(
                """
name: tutorial

conda_env: conda.yaml

entry_points:
  main:
    parameters:
      alpha: {type: float, default: 0.5}
      l1_ratio: {type: float, default: 0.1}
    command: "python train.py {alpha} {l1_ratio}"
"""
            )
        with open(f"{path}/conda.yaml", "w") as f:
            f.write(
                """
name: ml-project
channels:
  - conda-forge
dependencies:
  - python=3.9
"""
            )
        with open(f"{path}/train.py", "w") as f:
            f.write(
                """
# MLFlow code
"""
            )


# TODO: prefect https://docs.prefect.io/v3/how-to-guides/configuration/
#  manage-settings#configure-settings-for-a-project

# TODO: apache airflow? (is complex!)

# TODO: dbt https://docs.getdbt.com/reference/dbt_project.yml
