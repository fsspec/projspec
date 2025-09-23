import os

import pytest

import projspec.utils

here = os.path.dirname(__file__)


@pytest.fixture
def proj():
    return projspec.Project(os.path.dirname(here), walk=True)
