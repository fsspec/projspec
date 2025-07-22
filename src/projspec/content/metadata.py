from dataclasses import field

from projspec.content import BaseContent


class DescriptiveMetadata(BaseContent):
    """Miscellaneous descriptive information"""

    meta: dict[str, str] = field(default_factory=dict)
