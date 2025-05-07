from abc import ABC


class BaseRunner(ABC):

    def ready(self) -> bool:
        """Is this runner available for execution

        If False, running ``setup()`` should solve the situation, if it completes
        """
        raise NotImplementedError

    def setup(self, **kwargs):
        """Many any environment and temporaries needed for execution"""
        raise NotImplementedError

    def run(self, **kwargs):
        """Execute a given runnable"""
        raise NotImplementedError

    def clean(self):
        """Remove any temporary runtime or state"""
        raise NotImplementedError

