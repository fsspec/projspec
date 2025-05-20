#! /usr/bin/env python
"""Simple example executable for this library
"""

import os
import projspec.proj


def main():
    proj = projspec.Project(os.getcwd())
    print(proj)


if __name__ == "__main__":
    main()
