from projspec.content import BaseContent


class License(BaseContent):
    # https://opensource.org/licenses
    # (fields may change)

    # although a repo may well have a freestanding LICENSE file, many project metadata
    # formats also specify this by name or URL.
    shortname: str
    fullname: str
    url: str
