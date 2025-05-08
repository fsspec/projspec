from abc import ABC


class BaseArtifact(ABC):

    def run(self):
        raise NotImplementedError
