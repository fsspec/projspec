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

User Classes
~~~~~~~~~~~~

.. autosummary::
    proj.conda_package.CondaRecipe
    proj.conda_package.RattlerRecipe
    proj.conda_project.CondaProject
    proj.documentation.MDBook
    proj.documentation.RTD
    proj.git.GitRepo
    proj.pixi.Pixi
    proj.python_code.PythonCode
    proj.python_code.PythonLibrary
    proj.poetry.Poetry
    proj.pyscript.PyScript
    proj.rust.Rust
    proj.rust.RustPython
    proj.uv.UvScript
    proj.uv.Uv


.. autoclass:: projspec.proj.conda_package.CondaRecipe
.. autoclass:: projspec.proj.conda_package.RattlerRecipe
.. autoclass:: projspec.proj.conda_project.CondaProject
.. autoclass:: projspec.proj.documentation.MDBook
.. autoclass:: projspec.proj.documentation.RTD
.. autoclass:: projspec.proj.git.GitRepo
.. autoclass:: projspec.proj.pixi.Pixi
.. autoclass:: projspec.proj.python_code.PythonCode
.. autoclass:: projspec.proj.python_code.PythonLibrary
.. autoclass:: projspec.proj.poetry.Poetry
.. autoclass:: projspec.proj.pyscript.PyScript
.. autoclass:: projspec.proj.rust.Rust
.. autoclass:: projspec.proj.rust.RustPython
.. autoclass:: projspec.proj.uv.UvScript
.. autoclass:: projspec.proj.uv.Uv


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

User Classes
~~~~~~~~~~~~

.. autosummary::
   content.data.FrictionlessData
   content.data.IntakeCatalog
   content.env_var.EnvironmentVariables
   content.environment.Environment
   content.executable.Command
   content.license.License
   content.metadata.DescriptiveMetadata
   content.package.PythonPackage

.. autofunction:: projspec.content.data.FrictionlessData
.. autofunction:: projspec.content.data.IntakeCatalog
.. autofunction:: projspec.content.env_var.EnvironmentVariables
.. autofunction:: projspec.content.environment.Environment
.. autofunction:: projspec.content.executable.Command
.. autofunction:: projspec.content.license.License
.. autofunction:: projspec.content.metadata.DescriptiveMetadata
.. autofunction:: projspec.content.package.PythonPackage

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

User Classes
~~~~~~~~~~~~

Utilities
---------

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
