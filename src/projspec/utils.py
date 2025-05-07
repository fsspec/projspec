from typing import TypeVar

import re

T = TypeVar('T', bound='Parent')


class AttrDict(dict):

    def __init__(self, *data):
        if len(data) == 1 and isinstance(data[0], dict):
            super().__init__(dict)
        else:
            super().__init__({camel_to_snake(type(v).__name__): v for v in data})

    def __getattr__(self, item):
        if item in self:
            return self[item]
        raise AttributeError(item)


cam_patt = re.compile(r'(?<!^)(?=[A-Z])')


def camel_to_snake(camel):
    # https://stackoverflow.com/a/1176023/3821154
    return re.sub(cam_patt, '_', camel).lower()


def to_camel_case(snake_str):
    # https://stackoverflow.com/a/19053800/3821154
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))

