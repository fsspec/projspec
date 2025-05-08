"""Executable contents produce artifacts

Artifacts can include interactive or batch processes, files, infrastructure and services.

Every runnable thing has an associated artifact prescription.
"""

from projspec.content import BaseContent


class Command(BaseContent):
    """The simplest runnable thing"""
    name = "command"

    def __init__(self, runner, path, *args, **kwargs):
        self.runner = runner
        self.path = path
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):
        return f"{self.runner} {self.path}"

    def run(self):
        return self.runner.run(self.path, *self.args, **self.kwargs)
