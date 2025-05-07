from projspec.content import BaseContent


class Command(BaseContent):
    """The simplest runnable thing: """
    name = "command"

    def __init__(self, runner, path, *args, **kwargs):
        self.runner = runner
        self.path = path
        self.args = args
        self.kwargs = kwargs

