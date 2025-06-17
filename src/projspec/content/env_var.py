from dataclasses import dataclass, field

from projspec.content.base import BaseContent


@dataclass
class EnvuironmentVariables(BaseContent):
    variables: dict[str, str | None] = field(default_factory=dict)
