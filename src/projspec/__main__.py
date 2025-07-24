#!/usr/bin/env python
"""Simple example executable for this library"""

import click

import projspec.proj


@click.command()
@click.option(
    "--types",
    default="ALL",
    help='Type names to scan for (comma-separated list in camel or snake case); defaults to "ALL"',
)
@click.argument("path", default=".")
def main(path, types):
    if types in {"ALL", ""}:
        types = None
    else:
        types = types.split(",")
    proj = projspec.Project(path, types=types)
    print(proj)


if __name__ == "__main__":
    main()
