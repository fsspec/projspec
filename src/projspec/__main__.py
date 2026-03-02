#!/usr/bin/env python
"""Simple example executable for this library"""

import json
import pydoc
import sys

import click

import projspec.proj


# global runtime config
context = {}


@click.group()
def main():
    pass


@main.command("make")
@click.argument("artifact", type=str)
@click.argument("path", default=".", type=str)
@click.option(
    "--storage_options",
    default="",
    help="storage options dict for the given URL, as JSON",
)
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
def make(artifact, path, storage_options, types, xtypes):
    """Make the given artifact in the project at the given path.

    artifact: str , of the form [<spec>.]<artifact-type>[.<name>]

    path: str, path to the project directory, defaults to "."
    """
    if types in {"ALL", ""}:
        types = None
    else:
        types = types.split(",")
    proj = projspec.Project(
        path, storage_options=storage_options, types=types, xtypes=xtypes
    )
    proj.make(artifact)


@main.command()
def version():
    print(f"projspec version: {projspec.__version__}")


@main.command("scan")
@click.argument("path", default=".")
@click.option(
    "--storage_options",
    default="",
    help="storage options dict for the given URL, as JSON",
)
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
@click.option(
    "--json-out", is_flag=True, default=False, help="JSON output, for projects only"
)
@click.option(
    "--html-out", is_flag=True, default=False, help="HTML output, for projects only"
)
@click.option("--walk", is_flag=True, help="To descend into all child directories")
@click.option("--summary", is_flag=True, help="Show abbreviated output")
@click.option("--library", is_flag=True, help="Add to library")
def scan(
    path, storage_options, types, xtypes, json_out, html_out, walk, summary, library
):
    """Scan the given path for projects, and display

    path: str, path to the project directory, defaults to "."
    """
    if types in {"ALL", ""}:
        types = None
    else:
        types = types.split(",")
    proj = projspec.Project(
        path, storage_options=storage_options, types=types, xtypes=xtypes, walk=walk
    )
    if summary:
        print(proj.text_summary())
    else:
        if json_out:
            print(json.dumps(proj.to_dict(compact=True)))
        elif html_out:
            print(proj._repr_html_())
        else:
            print(proj)
    if library:
        proj.add_to_library()


@main.command("info")
@click.argument(
    "types",
    default="ALL",
)
def info(types=None):
    if types in {"ALL", "", None}:
        from projspec.utils import class_infos

        print(json.dumps(class_infos()))
    else:
        name = projspec.utils.camel_to_snake(types)
        cls = (
            projspec.proj.base.registry.get(name)
            or projspec.content.base.registry.get(name)
            or projspec.artifact.base.registry.get(name)
        )
        if cls:
            pydoc.doc(cls, output=sys.stdout)
        else:
            print("Name not found")


@main.group("library")
def library():
    """Interact with the project library.

    Library file location is defined by config value "library_path".
    """


@library.command("list")
@click.option(
    "--json-out", is_flag=True, default=False, help="JSON output, for projects only"
)
def list(json_out):
    from projspec.library import ProjectLibrary

    library = ProjectLibrary()
    if json_out:
        print(json.dumps({k: v.to_dict() for k, v in library.entries.items()}))
    else:
        for url, proj in library.entries.items():
            print(f"{proj.text_summary(bare=True)}")


@library.command("delete")
@click.argument("url")
def delete(url):
    from projspec.library import ProjectLibrary

    library = ProjectLibrary()
    library.entries.pop(url)
    library.save()


@main.group("config")
def config():
    """Interact with the projspec config."""
    pass


@config.command("get")
@click.argument("key")
def get(key):
    from projspec.config import get_conf

    print(get_conf(key))


@config.command("show")
def show():
    from projspec.config import conf

    print(conf)


@config.command("unset")
@click.argument("key")
def unset(key):
    from projspec.config import set_conf

    set_conf(key, None)


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_(key, value):
    from projspec.config import set_conf

    # TODO: consider types
    set_conf(key, value)


if __name__ == "__main__":
    main()
