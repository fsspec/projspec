from typing import TypeVar

import re

T = TypeVar('T', bound='Parent')


class AttrDict(dict):
    """Contains a dict but allows attribute read access for compliant keys"""

    def __init__(self, *data, **kw):
        dic = False
        if len(data) == 1 and isinstance(data[0], (tuple, list)):
            types = set(type(_) for _ in data[0])
            if isinstance(data[0], dict):
                super().__init__(data[0])
            elif isinstance(data[0], list):
                super().__init__({camel_to_snake(list(types)[0].__name__): data[0]})
            else:
                dic = True
        else:
            dic = True
        if dic:
            super().__init__({camel_to_snake(type(v).__name__): v for v in data})
        self.update(kw)

    def __getattr__(self, item):
        if item in self:
            return self[item]
        raise AttributeError(item)


cam_patt = re.compile(r'(?<!^)(?=[A-Z])')


def camel_to_snake(camel: str) -> str:
    # https://stackoverflow.com/a/1176023/3821154
    return re.sub(cam_patt, '_', camel).lower()


def to_camel_case(snake_str: str) -> str:
    # https://stackoverflow.com/a/19053800/3821154
    return "".join(x.capitalize() for x in snake_str.lower().split("_"))

