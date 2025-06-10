#!/usr/bin/env python
"""Simple example executable for this library"""

import os
import sys

import projspec.proj


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = os.getcwd()
    proj = projspec.Project(path)
    print(proj)


if __name__ == "__main__":
    main()
