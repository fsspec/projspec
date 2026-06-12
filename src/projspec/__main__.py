#!/usr/bin/env python
"""Simple example executable for this library"""

import json
import pydoc
import sys

import click

import projspec.proj
from projspec.config import temp_conf


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
@click.option(
    "--wait",
    default=True,
    is_flag=True,
    help="Wait for artifact to finish, for Process type artifacts only (default True)",
)
def make(artifact, path, storage_options, types, xtypes, wait):
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
    with temp_conf(capture_artifact_output=False):
        art = proj.make(artifact)
        print("Created:", art)
    if wait and art.proc:
        art.proc.wait()
        print("Finished with code:", art.proc.returncode)


@main.command()
def version():
    """Show version and quit"""
    print(f"projspec version: {projspec.__version__}")


@main.command("scan")
@click.argument("patterns", nargs=-1)
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
    "--json-out",
    is_flag=True,
    default=False,
    help="JSON output, for projects only",
)
@click.option(
    "--html-out",
    is_flag=True,
    default=False,
    help="HTML output, for projects only",
)
@click.option(
    "--walk", is_flag=True, help="Descend into child directories of each match"
)
@click.option("--summary", is_flag=True, help="Show abbreviated output")
@click.option("--library", is_flag=True, help="Add each result to the library")
def scan(
    patterns,
    storage_options,
    types,
    xtypes,
    json_out,
    html_out,
    walk,
    summary,
    library,
):
    """Scan directories and display results.

    PATTERNS is one or more directory paths or glob expressions.  When the
    shell expands a glob before invoking projspec, each expanded path is
    passed as a separate argument.  Glob expressions containing wildcards
    (e.g. '~/projects/*') are expanded by projspec itself via fsspec.
    If no PATTERNS are given, the current directory is scanned.
    """
    from projspec.utils import scan_glob

    if types in {"ALL", ""}:
        types = None
    else:
        types = types.split(",")

    for pattern in patterns or (".",):
        for proj in scan_glob(
            pattern,
            types=types,
            xtypes=xtypes,
            walk=walk,
            storage_options=storage_options,
            add_to_library=library,
        ):
            if summary:
                print(proj.text_summary())
            else:
                if json_out:
                    print(json.dumps(proj.to_dict(compact=False)))
                elif html_out:
                    print(proj._repr_html_())
                else:
                    print(proj)


@main.command("info")
@click.argument(
    "types",
    default="ALL",
)
def info(types=None):
    """Documentation about all the classes within projspec

    types: a specific class name, in Camel or snake_case; if not given,
        lists all types as JSON.
    """
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


@main.command("create")
@click.argument("type")
@click.argument("path", default=".")
def create(type, path):
    """Create a new project of the given type in the given path.

    Returns the list of files created.

    (Path must be local, no storage_options)
    """
    from projspec.proj import Project
    from projspec.proj.base import ProjectSpec, registry

    if type not in registry:
        print(f"Unknown spec type: {type}")
        sys.exit(1)
    proj = Project(path)
    if type not in proj:
        try:
            files = proj.create(type)
        except NotImplementedError:
            supported = sorted(
                name
                for name, cls in registry.items()
                if cls._create is not ProjectSpec._create
            )
            print(
                f"Spec type '{type}' does not support creation.\n"
                f"Types that support creation: {', '.join(supported)}"
            )
            sys.exit(1)
        for afile in files:
            print(afile)
    else:
        print(f"Project already has a {type} spec")


@main.group("library")
def library():
    """Interact with the project library.

    Library file location is defined by config value "library_path".
    """


@library.command("list")
@click.option(
    "--json-out",
    is_flag=True,
    default=False,
    help="JSON output, for projects only",
)
def list(json_out):
    """Show contents of the library"""
    from projspec.library import ProjectLibrary

    library = ProjectLibrary()
    if json_out:
        print(
            json.dumps(
                {k: v.to_dict(compact=False) for k, v in library.entries.items()}
            )
        )
    else:
        for url in sorted(library.entries):
            proj = library.entries[url]
            print(f"{proj.text_summary(bare=True)}")


@library.command("clear")
def clear():
    """Clear all contents of the library"""
    from projspec.library import ProjectLibrary

    ProjectLibrary().clear()


@library.command("delete")
@click.argument("url")
def delete(url):
    """Delete the project at the given URL from the library.

    URL must be given as shows in `list`.
    """
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
    """Get a value from the config."""
    from projspec.config import get_conf

    print(get_conf(key))


@config.command("show")
def show():
    """Show all contents of the config."""
    from projspec.config import conf

    # TODO: show docs and defaults for each key, from projspec.config.config_doc?
    # TODO: allow JSON output
    print(conf)


@config.command("defaults")
def defaults():
    """Show default config settings for all available values and their definitions"""
    from projspec.config import defaults, config_doc
    import os

    print("PROJSPEC_CONFIG_DIR", os.environ.get("PROJSPEC_CONFIG_DIR", "unset"))
    print()
    for k, v, d in zip(defaults(), defaults().values(), config_doc.values()):
        print(f"{k}: {v} -- {d}")


@config.command("create")
def create():
    """Create the config file with default values, if it doesn't exist"""
    from projspec.config import populate_if_empty

    print(populate_if_empty())


@config.command("unset")
@click.argument("key")
def unset(key):
    """Remove a value from the config (returns to default)"""
    from projspec.config import set_conf

    set_conf(key, None)


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_(key, value):
    """Set a config value"""
    from projspec.config import set_conf

    set_conf(key, value)


if __name__ == "__main__":
    main()
