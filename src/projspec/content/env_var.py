from dataclasses import dataclass, field

from projspec.content.base import BaseContent


@dataclass
class EnvironmentVariables(BaseContent):
    """A set of environment variable key/value pairs, typically used with new processes."""

    variables: dict[str, str | None] = field(default_factory=dict)
