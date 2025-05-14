from abc import ABC


class BaseRunner(ABC):

    def ready(self) -> bool:
        """Is this runtime available for execution

        If False, running ``setup()`` should solve the situation, if it completes
        """
        raise NotImplementedError

    def setup(self, **kwargs) -> None:
        """Many any environment and temporaries needed for execution"""
        raise NotImplementedError

    def run(self, **kwargs):
        """Execute a given runnable"""
        raise NotImplementedError

    def clean(self) -> None:
        """Remove any temporary runtime or state"""
        raise NotImplementedError

    def __repr__(self):
        return f"{type(self).__name__}()"
