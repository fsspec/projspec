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
    artifact.container.Docker
    artifact.linter.PreCommitted
    content.environment.CondaEnv
    content.environment.PythonRequirements
    content.metadata.Licensed
    proj.base.ProjectExtra
    proj.briefcase.Briefcase
    proj.conda_package.CondaRecipe
    proj.conda_package.RattlerRecipe
    proj.conda_project.CondaProject
    proj.datapackage.DVCRepo
    proj.datapackage.DataPackage
    proj.documentation.MDBook
    proj.documentation.RTD
    proj.git.GitRepo
    proj.ide.JetbrainsIDE
    proj.ide.NvidiaAIWorkbench
    proj.ide.VSCode
    proj.ide.Zed
    proj.node.JLabExtension
    proj.node.Node
    proj.node.Yarn
    proj.pixi.Pixi
    proj.poetry.Poetry
    proj.pyscript.PyScript
    proj.python_code.PythonCode
    proj.python_code.PythonLibrary
    proj.rust.Rust
    proj.rust.RustPython
    proj.uv.Uv
    proj.uv.UvScript
    proj.webapp.Django
    proj.webapp.Marimo
    proj.webapp.Streamlit


.. autoclass:: projspec.artifact.container.Docker
.. autoclass:: projspec.artifact.linter.PreCommitted
.. autoclass:: projspec.content.environment.CondaEnv
.. autoclass:: projspec.content.environment.PythonRequirements
.. autoclass:: projspec.content.metadata.Licensed
.. autoclass:: projspec.proj.base.ProjectExtra
.. autoclass:: projspec.proj.briefcase.Briefcase
.. autoclass:: projspec.proj.conda_package.CondaRecipe
.. autoclass:: projspec.proj.conda_package.RattlerRecipe
.. autoclass:: projspec.proj.conda_project.CondaProject
.. autoclass:: projspec.proj.datapackage.DVCRepo
.. autoclass:: projspec.proj.datapackage.DataPackage
.. autoclass:: projspec.proj.documentation.MDBook
.. autoclass:: projspec.proj.documentation.RTD
.. autoclass:: projspec.proj.git.GitRepo
.. autoclass:: projspec.proj.ide.JetbrainsIDE
.. autoclass:: projspec.proj.ide.NvidiaAIWorkbench
.. autoclass:: projspec.proj.ide.VSCode
.. autoclass:: projspec.proj.ide.Zed
.. autoclass:: projspec.proj.node.JLabExtension
.. autoclass:: projspec.proj.node.Node
.. autoclass:: projspec.proj.node.Yarn
.. autoclass:: projspec.proj.pixi.Pixi
.. autoclass:: projspec.proj.poetry.Poetry
.. autoclass:: projspec.proj.pyscript.PyScript
.. autoclass:: projspec.proj.python_code.PythonCode
.. autoclass:: projspec.proj.python_code.PythonLibrary
.. autoclass:: projspec.proj.rust.Rust
.. autoclass:: projspec.proj.rust.RustPython
.. autoclass:: projspec.proj.uv.Uv
.. autoclass:: projspec.proj.uv.UvScript
.. autoclass:: projspec.proj.webapp.Django
.. autoclass:: projspec.proj.webapp.Marimo
.. autoclass:: projspec.proj.webapp.Streamlit


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
    content.data.IntakeSource
    content.env_var.EnvironmentVariables
    content.environment.Environment
    content.executable.Command
    content.metadata.DescriptiveMetadata
    content.metadata.License
    content.package.NodePackage
    content.package.PythonPackage
    content.package.RustModule

.. autoclass:: projspec.content.data.FrictionlessData
.. autoclass:: projspec.content.data.IntakeSource
.. autoclass:: projspec.content.env_var.EnvironmentVariables
.. autoclass:: projspec.content.environment.Environment
.. autoclass:: projspec.content.executable.Command
.. autoclass:: projspec.content.metadata.DescriptiveMetadata
.. autoclass:: projspec.content.metadata.License
.. autoclass:: projspec.content.package.NodePackage
.. autoclass:: projspec.content.package.PythonPackage
.. autoclass:: projspec.content.package.RustModule

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
    artifact.container.DockerImage
    artifact.container.DockerRuntime
    artifact.installable.CondaPackage
    artifact.installable.SystemInstallablePackage
    artifact.installable.Wheel
    artifact.linter.PreCommit
    artifact.process.Process
    artifact.process.Server
    artifact.python_env.CondaEnv
    artifact.python_env.EnvPack
    artifact.python_env.LockFile
    artifact.python_env.VirtualEnv

.. autoclass:: projspec.artifact.container.DockerImage
.. autoclass:: projspec.artifact.container.DockerRuntime
.. autoclass:: projspec.artifact.installable.CondaPackage
.. autoclass:: projspec.artifact.installable.SystemInstallablePackage
.. autoclass:: projspec.artifact.installable.Wheel
.. autoclass:: projspec.artifact.linter.PreCommit
.. autoclass:: projspec.artifact.process.Process
.. autoclass:: projspec.artifact.process.Server
.. autoclass:: projspec.artifact.python_env.CondaEnv
.. autoclass:: projspec.artifact.python_env.EnvPack
.. autoclass:: projspec.artifact.python_env.LockFile
.. autoclass:: projspec.artifact.python_env.VirtualEnv


Utilities
---------

.. autosummary::
   library.ProjectLibrary
   utils.AttrDict
   utils.Enum
   utils.IsInstalled
   utils.class_infos
   utils.get_cls
   utils.make_and_copy
   proj.base.ParseFailed
   config.get_conf

.. autoclass:: projspec.library.ProjectLibrary
.. autoclass:: projspec.utils.AttrDict
.. autoclass:: projspec.utils.Enum
.. autofunction:: projspec.utils.class_infos
.. autofunction:: projspec.utils.get_cls
.. autofunction:: projspec.utils.make_and_copy
.. autoclass:: projspec.utils.IsInstalled
   :members:
.. autoclass:: projspec.proj.base.ParseFailed
.. autofunction:: projspec.config.get_conf

.. raw:: html

    <script data-goatcounter="https://projspec.goatcounter.com/count"
        async src="//gc.zgo.at/count.js"></script>
