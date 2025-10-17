from dataclasses import dataclass, field

from projspec.content import BaseContent


@dataclass
class DescriptiveMetadata(BaseContent):
    """Miscellaneous descriptive information"""

    meta: dict[str, str] = field(default_factory=dict)
