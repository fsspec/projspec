import dataclasses


@dataclasses.dataclass()
class BaseContent:
    # these are probably just dataclass-like - details that can be searched and
    # passed to runners, but having no internal functionality

    name = "base"  # key to access by
