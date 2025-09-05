API Reference
=============

.. currentmodule:: projspec

Projects
--------

A "project" is a directory of stuff, with associated metadata to tell you
what that stuff is and how to use it.


Base Classes
~~~~~~~~~~~~

.. autosummary::
   proj.base.Project
   proj.base.ProjectSpec

.. autoclass:: projspec.proj.base.Project
   :members:
.. autoclass:: projspec.proj.base.ProjectSpec
   :members:

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>

Contents
--------

A contents item is something defined by a project spec, a core component of what
that project is.

Base Classes
~~~~~~~~~~~~

.. autosummary::
   content.base.BaseContent
   content.base.get_content_cls

.. autoclass:: projspec.content.base.BaseContent
   :members:
.. autofunction:: projspec.content.base.get_content_cls

Artifacts
---------

An artifact item is a thing that a project can do or make.

Base Classes
~~~~~~~~~~~~

.. autosummary::
   artifact.base.BaseArtifact
   artifact.base.FileArtifact
   artifact.base.get_artifact_cls

.. autoclass:: projspec.artifact.base.BaseArtifact
   :members:
.. autoclass:: projspec.artifact.base.FileArtifact
   :members:
.. autofunction:: projspec.artifact.base.get_artifact_cls

Utilities
---------
