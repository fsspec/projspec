#!/usr/bin/env python
"""Simple example executable for this library
"""

import os
import sys

import projspec.proj


def main(path=None):
    proj = projspec.Project(path or os.getcwd())
    print(proj)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
