Configuration
=============

``projspec`` supports setting certain values via a configuration file,
or environment variables. Where an environment variable is set, it takes
precedence. Where neither is set, the following defaults are used. The
CLI subcommand ``config`` can be used to get/set/clear config values in the
config file. The location of the config file is f"{conf_dir}/projspec.json" where
``conf_dir`` is ``PROJSPEC_CONFIG_DIR``, if set, or "~/.config/projspec".

Default config, defined in ``projspec.config.defaults()``:

.. code-block:: python

    {
        "library_path": f"{conf_dir}/library.json",
        "scan_types": [".py", ".yaml", ".yml", ".toml", ".json", ".md"],
        "scan_max_files": 100,
        "scan_max_size": 5 * 2**10,
        "remote_artifact_status": False,
        "capture_artifact_output": True,
        "preferred_install_methods": ["conda", "pip"],
    }

The key definitions are as follows.

.. code-block::

    library_path : location of persisted project objects
    scan_types : files extensions automatically read for scanning
    scan_max_files : don't scan files if more than this number in the project
    scan_max_size : don't scan files bigger than this (in bytes)
    remote_artifact_status : whether to check status for remote artifacts
    capture_artifact_output : if True, capture and enqueue output from spawned Process
      artifacts. Otherwise, output appears on stdout/err.
    preferred_install_methods : ordered list of preferred installer names for
      install_tool(), e.g. ['uv', 'conda', 'pip']. Empty list uses the platform default.

You can get this same information from the CLI command ``projspec config defaults``.
Note, that config values which do no exist in the the defaults or cannot be
coerced to the same time will be skipped, with a warning.
