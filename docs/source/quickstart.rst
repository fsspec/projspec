Quickstart
==========


Installation
------------

You can install from source, pip or conda or many other ways, since the
code is pure-python.
One of the following should work

.. code-block::

   $ python -m pip install projspec
   $ conda install projspec -c conda-forge

CLI
---

Having installed ``projspec``,
run the following on this library's repo directory. You may wish to clone the
repo from https://github.com/fsspec/projspec to follow along

.. code-block::

   $ projspec --summary --walk
   <Project 'file:///Users/mdurant/code/projspec'>
    /: CondaProject GitRepo Pixi Poetry PythonLibrary RTD Uv
    /recipe: CondaRecipe RattlerRecipe
    /src/projspec: PythonCode

This summary view tells you that the repo root directory contains metadata that
mean it can be considered a "conda project", a "git repo", a "pixi project",
a "poetry project", a "python library", a "readthedocs source" and a
"UV project". Don't worry if you don't know what these things are, we will explain!

While it is typical to have more than one project definition in a directory,
it is unusual to have so many definitions in a single place, but of course we
do this for demonstration and testing purposes.

You also see that some subdirectories have valid project specifications too:
two types of recipes in recipe/  and python code under src/ .

Programmatic Interface
----------------------

``Project`` objects are anchored to a particular path (local or remote), and
expose information about the various project specs that match for that
directory and their details. The simplest thing that one might do with a Project
is display it, which is also the main functionality of the CLI, above.

Extra functionality in python code includes the ability to examine the internals
of a Project; here is a simple example, run in the projspec's repo root:

.. code-block::

   >>> import projspec
   >>> proj = projspec.Project(".")
   >>> "uv" in proj
   True

This asks the question: "can this directory be interpreted as UV project", and
the answer is yes.

To execute an action on a project, one might do something like

.. code-block::

   >>> proj.uv.artifacts.wheel.make()

which will use ``uv`` to create a wheel artifact in dist/ , and the status of
``proj.uv.artifacts.wheel`` will change from "clean" to "done".

Notebook GUI
------------

When displayed in a notebook, a Project will show its contents as expandable
HTML:

.. image:: img/tree.png

(this is currently purely informational - in the future it will feature links, pop-up
documentation and artifact activation buttons.)

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
