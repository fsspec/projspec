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

## Support

Work on this repository is supported in part by:

"Anaconda, Inc. - Advancing AI through open source."

<a href="https://anaconda.com/"><img src="https://camo.githubusercontent.com/b8555ef2222598ed37ce38ac86955febbd25de7619931bb7dd3c58432181d3b6/68747470733a2f2f626565776172652e6f72672f636f6d6d756e6974792f6d656d626572732f616e61636f6e64612f616e61636f6e64612d6c617267652e706e67" alt="anaconda logo" width="40%"/></a>
