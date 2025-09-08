Overview
========

From the point of view of this library, a "project" is a directory of stuff,
with associated metadata (typically in small text files) to tell you
what that stuff is and how to use it. We are not talking about a home reno project.
Each directory can be interpreted according to one or more of the implemented
specifications, and child directories may contain project structures too.

There are many types of projects meeting our definition in the wild, and we
consider particularly those of interest to python practitioners.

Layout of a Project
-------------------

We present a structured view of what a project is, after parsing the various
metadata available. You will always find some of the following components.

Specs
~~~~~

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
will every know project type at instantiation.

It is a common pattern for a project to contain potentially several subprojects
in nodes of the directory tree (e.g., "monorepos").
By default, ``projspec`` will only walk the tree
if the top-level directory found no project spec hits, unless you pass ``walk=True``.

Content
~~~~~~~

These are things that you can know about a project from its metadata files or file listings
alone. They are inherent, integral parts of what the project is "at rest."

Contents are essentially descriptive, and serve to define the project, so that you
can understand what it is and potentially find the right project among many when
querying. Contents do not support any actions, but may (and often do) associate with
particular artifacts.

All contents
can be inferred by reading (small) files directly from remote, without downloading the
whole project or running any external tool.

Artifacts
~~~~~~~~~

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

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
