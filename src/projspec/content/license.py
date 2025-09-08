from projspec.content import BaseContent


class License(BaseContent):
    """A legal description of what the given project (code and other assets) can be used for.

    This could be one of the typical open-source permissive licenses (see https://spdx.org/licenses/),
    specified either just by its name or by a link. Some projects will have custom or restrictive
    conditions on their replication and use.
    """

    # https://opensource.org/licenses

    shortname: str  # aka SPDX
    fullname: str
    url: str  # relative in the project or remote HTTP
