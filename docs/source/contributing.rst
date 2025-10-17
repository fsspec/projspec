Contributor guide
=================

``projspec`` is an open-source project (see the LICENSE). We welcome contributions from
the public, for code, including fixes and new features, documentation and anything else
that will help make this repo better. Even posting issues can be very useful, as they
will help others to make the necessary changes to alleviate the issue.

Development process
-------------------

Development of ``projspec`` happens on `github`_. There you will find options for
creating issues and commenting on existing issues and pull-requests (PRs). You may
wish to "watch" the repo, to be notified of changes as they occur. You must have an
account on github to be able to interact here, but this is free. By default, you
will be notified of changes (e.g., new comments) on any issue or PR you have interacted
with.

In order to propose changes to the repo itself, you will need to create a PR. This is
done by following these steps:

1. clone the repo. There are many ways to do this, but most common is the following command,
   which will create a local directory ``projspec/`` containing the code, metadata, docs and
   version control information.

.. code-block:: shell

   $ git clone https://github.com/fsspec/projspec


2. create a fork or the repo using the github web interface. Your fork will probably live in
   your private github namespace. Set this as a remote inside your local copy of the repo

.. code-block:: shell

   $ git remote add fork https://github.com/<username>/projspec

3. make changes locally in a new branch. First you create the branch, and then add commits
   to that branch. Here are suggested ways to do this. Note that git is _very_ flexible and
   there are many ways to achieve each step.

.. code-block:: shell

   $ git checkout -b <new branch name>
   $ git commit -a

4. When your branch is an a suitable state, `push` your work to your branch. github will prompt
   you with a URL to create the PR, or navigate to your fork and branch in the web interface to
   create the PR there.

.. code-block:: shell

   $ git push fork

5. After review from a maintainer, you may wish to push more commits to your branch as required,
   and your PR may be accepted ("merged") or rejected ("closed").

.. _github: https://github.com/fsspec/projspec

Guidelines
----------

To make contributing as smooth as possible, we recommend the following.

1. Always follow the project's Code of Conduct when interacting with other humans.

2. Please describe as clearly as possible what your intent is. In the case of issues, this
   might include pasting the whole traceback your have seen following an error, listing the
   versions of ``projspec`` and its dependencies that you have installed, describing the
   circumstances when you saw a problem or would like better behaviour. Ideally, you would
   include code that allows maintainers to fully reproduce your steps.

3. When submitting changes, make sure that you describe what the changes achieve and how.
   Ideally, all code should be covered by tests included in the same PR, and that run to
   completion as part of CI (see below).

4. New functions and classes should include reasonable
   `style`, e.g., appropriate labels and hierarchy, indentation and other code formatting
   matching the rest of the docs, and docstrings and comments as appropriate. A "precommit"
   set of linters is available to run against your code, and runs as part of CI to enforce
   a minimal set of style rules. To run these locally on every commit, you can run this in the
   repo root:

.. code-block:: shell

   $ pre-commit install

5. Additions to the prose documentation (under docs/source/) should be included for new
   or altered features. After the initial full release, we will be maintaining a changelog.

Testing
-------

This repo uses ``pytest`` for testing. You can install test dependencies, for example with
this command run in the repo root.

.. code-block:: shell

   $ pip install .[test]

To run the tests:

.. code-block:: shell

   $ pytest -v --cov projspec


Adding docs
-----------

Docstrings, prose text and examples/tutorials are eagerly accepted! We, as coders, often
are late to fully document our work, and all contributions are welcome. Separate instructions
can be found in the docs/README.md file.

Adding a parser
===============

The main job of ``projspec`` is to interpret project metadat files into the component
"content" and "artifact" classes a project contains, for a given spec. This job is done
by parsers, each subclasses of :class:`projspec.proj.base.ProjectSpec`.

All subclasses are added to the registry on import, and when constructing a
:class:`projspec.proj.base.Project`, each of these classes attempts to parse the
target directory. Any specs that succeed in parsing will populate the `Project`'s
`.specs` dictionary. **Important**: imports should be deferred until parsing,
there should be no module-level imports besides builtins and existing
dependencies of ``projspec``. We do not want to
add bloat to our dependencies. Most metadata should be parsable with json, yaml and toml.

.. note::

   ``projspec`` will eventually have a config system to be able to import ProjectSpec
   subclasses from other packages. For now, any new parsers added in this repo should also
   be imported in the package ``__init__.py`` file, so that they will appear in the registry.

Only two methods need to be implemented:

* ``.match()``, which answers whether this directory *might* be interpretable as the given
  project type. If returning ``True``, the ``.parse()`` method will be attempted. The check
  here should be constant time and fast. Most typically it will depend on the existence of
  some known file in the directory root or entries in the pyproject metadata
  (``.filelist``, ``.basenames`` and ``.pyproject`` are sll cached attributes of ``self.proj``).

* ``.parse()``, which populates the ``._contents`` and ``._artifacts`` attributes with
  instances of subclasses of :class:`projspec.content.base.BaseContent` and
  :class:`projspec.artifact.base.BaseArtifact`, respectively. In a minority of cases,
  simple-typed values might suffice, for example the tags in a git repo are just strings
  without further details.

  ``parse()`` should raise :class:`projspec.proj.base.ParseFailed` if
  parsing fails, which will cause the
  corresponding project spec type not to show up in the enclosing ``Project`` instance.

  This typically involves reading some metadata file, and constructing the instances. The
  attributes are instances of ``projspec.utils.AttrDict``, which behaves like a dict for
  assignment. The convention is, that keynames should be the "snake name" version of the
  class, and the values are either a single instance, a list of instances, or a dict of
  named instance. An example of the latter might be named environments:

.. code-block:: python

   {"environment": {"default": Environment()}}

Sometimes, new Content and Artifact classes will be required too.

The special case of :class:`projspec.proj.base.ProjectExtra` exists for specs where the
content/artifact is part of the overall project, but doesn't really make sense as a project
by itself. For instance, a Dockerfile will make use of the files in a directory to
create a docker image (an Artifact of the project), but in most cases that does not make
the directory a "Docker project".
