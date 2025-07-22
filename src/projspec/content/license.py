from projspec.content import BaseContent


class License(BaseContent):
    # https://opensource.org/licenses

    shortname: str  # aka SPDX
    fullname: str
    url: str  # relative in the project or remote HTTP
