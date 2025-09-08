Quickstart
==========

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
