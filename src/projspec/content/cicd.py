"""Run definitions that are part of code productionalisation"""

from dataclasses import dataclass, field

from projspec.content import BaseContent


@dataclass
class CIWorkflow(BaseContent):
    """A CI/CD workflow or pipeline definition.

    Captures the name, triggering events, and high-level job/stage names from
    CI configuration files (GitHub Actions, GitLab CI, CircleCI, etc.).
    """

    name: str = ""
    triggers: list = field(default_factory=list)
    jobs: list = field(default_factory=list)
    provider: str = ""  # e.g. "github", "gitlab", "circleci"


# Keep legacy stub under old name for backwards compatibility
GithubAction = CIWorkflow


@dataclass
class PipelineStage(BaseContent):
    """A named stage or step in a data/ML/workflow pipeline.

    Used by dbt, Snakemake, Prefect, Airflow, Kedro, DVC, etc.
    """

    name: str = ""
    cmd: list = field(default_factory=list)
    depends_on: list = field(default_factory=list)


@dataclass
class ServiceDependency(BaseContent):
    """An external service that a project depends on at runtime.

    Extracted from Docker Compose service definitions, Helm values, etc.
    Examples: postgres, redis, kafka, elasticsearch.
    """

    name: str = ""
    service_type: str = ""  # e.g. "postgres", "redis", "kafka"
    version: str = ""
    image: str = ""
