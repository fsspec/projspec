import yaml

from projspec.proj import ProjectSpec
from projspec.utils import AttrDict, _yaml_no_jinja

# lockfile format is as produced by conda-lock; may be a standalone thing to find?
# https://github.com/conda/conda-lock


class CondaProject(ProjectSpec):
    # not a spec, but a howto:
    spec_doc = "https://conda-incubator.github.io/conda-project/tutorial.html"

    def match(self) -> bool:
        # TODO: a .condarc or environment.yml file is actually enough, e.g.,
        #  https://github.com/conda-incubator/conda-project/tree/main/examples/condarc-settings
        #  but we could argue that such are not really _useful_ projects; but can you
        #  ever see a .condarc otherwise?

        basenames = {_.rsplit("/", 1)[-1] for _ in self.root.filelist}
        return not basenames.isdisjoint(
            {"conda-project.yml", "conda-meta.yaml"}
        )

    def parse(self) -> None:
        from projspec.artifact.process import Process
        from projspec.artifact.python_env import CondaEnv, LockFile
        from projspec.content.environment import Environment, Precision, Stack
        from projspec.content.executable import Command

        try:
            with self.root.fs.open(f"{self.root.url}/conda-project.yml") as f:
                meta = _yaml_no_jinja(f)
        except FileNotFoundError:
            with self.root.fs.open(f"{self.root.url}/conda-project.yaml") as f:
                meta = _yaml_no_jinja(f)

        envs = AttrDict()
        locks = AttrDict()
        runtimes = AttrDict()
        cmds = AttrDict()
        procs = AttrDict()
        for env_name, fspec in meta.get("environments", {}).items():
            try:
                fnames = [fspec] if isinstance(fspec, str) else fspec
                channels = []
                packages = []
                for fname in fnames:
                    with self.root.fs.open(f"{self.root.url}/{fname}") as f:
                        env = _yaml_no_jinja(f)
                        channels.extend(
                            [
                                _
                                for _ in env.get("channels", [])
                                if _ not in channels
                            ]
                        )
                        packages.extend(
                            [
                                _
                                for _ in env.get("dependencies", [])
                                if _ not in packages
                            ]
                        )
                runtime = CondaEnv(
                    proj=self.root,
                    cmd=["conda", "project", "prepare", env_name],
                    fn=f"{self.root.url}/./envs/{env_name}/",
                )
                runtimes[env_name] = runtime
                lock_fname = f"{self.root.url}/conda-lock.{env_name}.yml"
                lock = LockFile(
                    proj=self.root,
                    cmd=["conda", "project", "lock", env_name],
                    fn=lock_fname,
                )
                locks[env_name] = lock
                if self.root.fs.exists(lock_fname):
                    with self.root.fs.open(lock_fname) as f:
                        data = yaml.load(f, Loader=yaml.SafeLoader)
                        lpackages = [
                            f"{p['name']} =={p['version']}"
                            for p in data.get("package", [])
                        ]
                    envs[f"{env_name}.lock"] = Environment(
                        proj=self.root,
                        channels=[],
                        packages=lpackages,
                        stack=Stack.CONDA,
                        precision=Precision.LOCK,
                        artifacts={runtime},
                    )
                env = Environment(
                    proj=self.root,
                    channels=channels,
                    packages=packages,
                    stack=Stack.CONDA,
                    precision=Precision.SPEC,
                    artifacts={runtime, lock},
                )
                envs[env_name] = env
            except FileNotFoundError:
                pass

        for name, cmd in meta.get("commands", {}).items():
            prc = Process(
                proj=self.root,
                cmd=["conda", "project", "run", name],
            )
            procs[name] = prc
            cmds[name] = Command(proj=self.root, cmd=cmd, artifacts={prc})

        cont = AttrDict(envs=envs, commands=cmds)
        arts = AttrDict(lock=locks, conda_env=runtimes, process=procs)

        self._contents = cont
        self._artifacts = arts
