# ``projspec``

A common interface to code projects.

### What is a project?

From the point of view of this library, any directory of stuff with metadata
describing what that stuff is (contents), what to do with it (artifacts) is
a project. This includes things that might be called in other contexts
an "application" or "work-space."

This is implemented first in the context of the python-data ecosystem, so we
will be concerned with project types that are common in this field, but in
principle a wide range of things.

### Niche

There are a large number of project-oriented tools already in existence,
describing a similarly large number of things about those projects. The
tools have a lot of overlap with one-another but also unique use cases.

The following diagram shows an aspirational set of things we wish to
consider initially:

![project diagram](https://raw.githubusercontent.com/martindurant/projspec/refs/heads/main/projspec.jpg)

Where we define:
- project spec: a way to define a project type, often tied to a particular tool.
- contents: the things that exist within the project, either as concrete files,
 as specs (in YAML, toml or other metadata) or links to other projects.
- artifacts: the things a project makes, outputs or tasks that the project
 can execute.

### Why

The following are the principal features we aim to provide, with the simplest
first:

##### Unified interface

You can interact with all project types the same way. If you only ever use one
project management tool, this is not so exciting. However, if you have multiple
project types, switching between them can be annoying, especially for rarely used
ones (helm is a good example of this in my personal experience).

This should integrate nicely with any project browsing IDE, where you don't
necessarily even know what project type a given directory is: no need any
more to trawl through README files to figure out how to execute a project.

##### Programmatic introspection

Unlike most, or maybe all, of the tools references by this library, we will
provide not just a CLI, but a python API. You can find all the information
about a project, make logical decisions and call the third-party tools
automatically.

Also, where a project is principally executed using a particular tool, it
might still wish to describe contents/artifacts that are not dealt with by
that tool. For instance, you might create environments using ``uv``, but
also want to declare data dependencies using ``intake``. The code within
the project can then find these assets by introspection.

##### Index & search

If you have a lot of projects or interact with a project storage service,
it can be a task just to figure out which is the right one to solve the task
of the day. If we can index them (even remotely, without downloading),
you can rapidly query for particular project contents or outputs.

Naturally, this becomes more powerful as more project types and artifacts
become indexable, and more projects are stored/shared with you.

### Layout of a Project

(some technical details follow, which will migrate to documentation pages when they are
prepared)

#### Specs

In this library, a ``Project`` object contains various specifications that
have been parsed from the path given or its children. All of these specs are
subclasses of ``projspec.proj.base.ProjSpec`` and answer "what kind of project is
this path." Of course, a given directory tree can be many different types of projects.
For instance, the existence of ``pixi`` metadata is totally independent of whether
the directory is a ``git`` repo or not or whether it contains dataset specifications.
The tools using these metadata do not directly interact with
one-another, but work quite happily alongside.

Each given spec will have various descriptive metadata, and be associated with come
contents and artifacts, see below. ``projspec`` will attempt to match a directory
will _every known_ project type at instantiation.

It is a common pattern for a project to contain potentially several subprojects
in nodes of the directory tree (e.g., "monorepos").
By default, ``projspec`` will only walk the tree
if the top-level directory found no project spec hits, unless you pass ``walk=True``.

#### Content

These are things that you can know about a project from its metadata files or file listings
alone. They are inherent, integral parts of what the project is "at rest."

Contents are essentially descriptive, and serve to define the project, so that you
can understand what it is and potentially find the right project among many when
querying. Contents do not support any actions, but may (and often do) associate with
particular artifacts.

All contents
can be inferred by reading (small) files directly from remote, without downloading the
whole project or running any external tool.

#### Artifacts

An artifact in the context of this library is an action or output of a project. To actually
execute the action, the project must exist locally, and the appropriate tool be available in
the runtime.

For example, if a project is matched to be of type ``uv``, we can infer what environment(s)
it might contain, but to build those environments the project must be copied to a local
location, and ``uv``, the executable, be available to run.

Artifacts will, in general, know whether they have been already run,
and point to an output if it exists.
In some cases, we may be able to tell if the artifact has been produced already even
in the remote version of the project. An instance of this would be a lockfile, which
is the outcome of running an environment resolution on the project, but common is still
stored alongside the code in the repo; as opposed to the environment's runtime, which
will not be stored and only exist locally.

It is possible for a single entity to be both a "contents" and "artifact" item. The
example of a lockfile, again, fits this description, since it may be in the repo and
represent a constrained environment, but also it is the product of running an action
against a looser environment specification in the project.

## Support

Work on this repository is supported in part by:

"Anaconda, Inc. - Advancing AI through open source."

<a href="https://anaconda.com/"><img src="https://camo.githubusercontent.com/b8555ef2222598ed37ce38ac86955febbd25de7619931bb7dd3c58432181d3b6/68747470733a2f2f626565776172652e6f72672f636f6d6d756e6974792f6d656d626572732f616e61636f6e64612f616e61636f6e64612d6c617267652e706e67" alt="anaconda logo" width="40%"/></a>
