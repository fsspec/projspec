# Compatibility shim — GitRepo now lives in projspec.proj.vcs.
# This module is kept so that existing pickled objects and any code that
# does ``from projspec.proj.git import GitRepo`` continues to work.
from projspec.proj.vcs import GitRepo

__all__ = ["GitRepo"]
