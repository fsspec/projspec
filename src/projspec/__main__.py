#!/usr/bin/env python
"""Simple example executable for this library"""

import json
import pydoc
import sys

import click

import projspec.proj


@click.command()
@click.argument("path", default=".")
@click.option(
    "--types",
    default="ALL",
    help='Type names to scan for (comma-separated list in camel or snake case); defaults to "ALL"',
)
@click.option(
    "--xtypes",
    default="NONE",
    help="List of spec types to ignore (comma-separated list in camel or snake case)",
)
@click.option("--walk", is_flag=True, help="To descend into all child directories")
@click.option("--summary", is_flag=True, help="Show abbreviated output")
@click.option("--version", is_flag=True, default=False, help="Print version and quit")
@click.option(
    "--json-out", is_flag=True, default=False, help="JSON output, for projects only"
)
@click.option(
    "--html-out", is_flag=True, default=False, help="HTML output, for projects only"
)
@click.option(
    "--make",
    help="(Re)Create the first artifact found matching this type name; matches [spec.]artifact[.name]",
)
@click.option(
    "--info",
    help="Give information about a names entity type (spec, contents or artifact)",
)
@click.option(
    "--storage_options",
    default="",
    help="storage options dict for the given URL, as JSON",
)
def main(
    path,
    types,
    xtypes,
    walk,
    summary,
    version,
    json_out,
    html_out,
    make,
    info,
    storage_options,
):
    if version:
        print(projspec.__version__)
        return
    if types in {"ALL", ""}:
        types = None
    else:
        types = types.split(",")
    if info:
        info = projspec.utils.camel_to_snake(info)
        cls = (
            projspec.proj.base.registry.get(info)
            or projspec.content.base.registry.get(info)
            or projspec.artifact.base.registry.get(info)
        )
        if cls:
            pydoc.doc(cls, output=sys.stdout)
        else:
            print("Name not found")
        return
    if xtypes in {"NONE", ""}:
        xtypes = None
    else:
        xtypes = xtypes.split(",")
    if storage_options:
        storage_options = json.loads(storage_options)
    else:
        storage_options = None
    proj = projspec.Project(
        path, storage_options=storage_options, types=types, xtypes=xtypes, walk=walk
    )
    if make:
        proj.make(make)
    elif summary:
        print(proj.text_summary())
    elif json_out:
        print(json.dumps(proj.to_dict(compact=True)))
    elif html_out:
        print(proj._repr_html_())
    else:
        print(proj)


if __name__ == "__main__":
    main()
