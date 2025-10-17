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
   proj.base.ProjectExtra

.. autoclass:: projspec.proj.base.Project
   :members:
.. autoclass:: projspec.proj.base.ProjectSpec
   :members:
.. autoclass:: projspec.proj.base.ProjectExtra

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

.. autoclass:: projspec.content.base.BaseContent
   :members:

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

.. autoclass:: projspec.content.data.FrictionlessData
.. autoclass:: projspec.content.data.IntakeCatalog
.. autoclass:: projspec.content.env_var.EnvironmentVariables
.. autoclass:: projspec.content.environment.Environment
.. autoclass:: projspec.content.executable.Command
.. autoclass:: projspec.content.license.License
.. autoclass:: projspec.content.metadata.DescriptiveMetadata
.. autoclass:: projspec.content.package.PythonPackage

Artifacts
---------

An artifact item is a thing that a project can do or make.

Base Classes
~~~~~~~~~~~~

.. autosummary::
   artifact.base.BaseArtifact
   artifact.base.FileArtifact

.. autoclass:: projspec.artifact.base.BaseArtifact
   :members:
.. autoclass:: projspec.artifact.base.FileArtifact
   :members:

User Classes
~~~~~~~~~~~~

.. autosummary::
    artifact.installable.CondaPackage
    artifact.installable.Wheel
    artifact.process.Process
    artifact.python_env.CondaEnv
    artifact.python_env.EnvPack
    artifact.python_env.LockFile
    artifact.python_env.VirtualEnv

.. autoclass:: projspec.artifact.installable.CondaPackage
.. autoclass:: projspec.artifact.installable.Wheel
.. autoclass:: projspec.artifact.process.Process
.. autoclass:: projspec.artifact.python_env.CondaEnv
.. autoclass:: projspec.artifact.python_env.EnvPack
.. autoclass:: projspec.artifact.python_env.LockFile
.. autoclass:: projspec.artifact.python_env.VirtualEnv


Utilities
---------

.. autosummary::
   utils.AttrDict
   utils.Enum
   utils.IsInstalled
   utils.get_cls
   proj.base.ParseFailed

.. autoclass:: projspec.utils.AttrDict
.. autoclass:: projspec.utils.Enum
.. autofunction:: projspec.utils.get_cls
.. autoclass:: projspec.utils.IsInstalled
   :members:
.. autoclass:: projspec.proj.base.ParseFailed

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
