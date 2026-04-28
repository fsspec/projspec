"""JavaScript/Node.js framework specs: Next.js, Nuxt.js, SvelteKit, Vite, Deno, Bun, pnpm."""

import os

from projspec.proj.base import ParseFailed, ProjectSpec
from projspec.proj.node import Node
from projspec.utils import AttrDict, run_subprocess


class NextJS(Node):
    """Next.js React framework project."""

    icon = "⚛️"
    spec_doc = "https://nextjs.org/docs/app/api-reference/config/next-config-js"

    _CONFIG_NAMES = {
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "next.config.cjs",
    }

    def match(self) -> bool:
        return bool(self._CONFIG_NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Server

        super().parse0()

        pkg_mgr = self._pkg_manager()
        # Development server
        self._artifacts["dev"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "dev"],
        )
        # Production build
        self._artifacts["build"] = FileArtifact(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "build"],
            fn=f"{self.proj.url}/.next/BUILD_ID",
        )
        # Production start
        self._artifacts["start"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "start"],
        )

    def _pkg_manager(self) -> str:
        if "yarn.lock" in self.proj.basenames:
            return "yarn"
        if "pnpm-lock.yaml" in self.proj.basenames:
            return "pnpm"
        if "bun.lock" in self.proj.basenames or "bun.lockb" in self.proj.basenames:
            return "bun"
        return "npm"

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(
            ["npx", "create-next-app@latest", path, "--yes"],
            cwd=os.path.dirname(path) or ".",
            output=False,
        )


class NuxtJS(Node):
    """Nuxt.js Vue framework project."""

    icon = "💚"
    spec_doc = "https://nuxt.com/docs/api/nuxt-config"

    _CONFIG_NAMES = {"nuxt.config.js", "nuxt.config.ts", "nuxt.config.mjs"}

    def match(self) -> bool:
        return bool(self._CONFIG_NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Server

        super().parse0()

        pkg_mgr = self._pkg_manager()
        self._artifacts["dev"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "dev"],
        )
        self._artifacts["build"] = FileArtifact(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "build"],
            fn=f"{self.proj.url}/.nuxt/tsconfig.json",
        )
        self._artifacts["generate"] = FileArtifact(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "generate"],
            fn=f"{self.proj.url}/.output/public/index.html",
        )

    def _pkg_manager(self) -> str:
        if "yarn.lock" in self.proj.basenames:
            return "yarn"
        if "pnpm-lock.yaml" in self.proj.basenames:
            return "pnpm"
        return "npm"

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(
            ["npx", "nuxi@latest", "init", path],
            cwd=os.path.dirname(path) or ".",
            output=False,
        )


class SvelteKit(Node):
    """SvelteKit project."""

    icon = "🔥"
    spec_doc = "https://svelte.dev/docs/kit/configuration"

    _CONFIG_NAMES = {"svelte.config.js", "svelte.config.ts"}

    def match(self) -> bool:
        return bool(self._CONFIG_NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Server

        super().parse0()

        pkg_mgr = self._pkg_manager()
        self._artifacts["dev"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "dev"],
        )
        self._artifacts["build"] = FileArtifact(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "build"],
            fn=f"{self.proj.url}/.svelte-kit/output/client/index.html",
        )
        self._artifacts["preview"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "preview"],
        )

    def _pkg_manager(self) -> str:
        if "yarn.lock" in self.proj.basenames:
            return "yarn"
        if "pnpm-lock.yaml" in self.proj.basenames:
            return "pnpm"
        if "bun.lock" in self.proj.basenames or "bun.lockb" in self.proj.basenames:
            return "bun"
        return "npm"

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(
            ["npm", "create", "svelte@latest", path],
            cwd=os.path.dirname(path) or ".",
            output=False,
        )


class Vite(Node):
    """Vite-based project (any frontend framework using Vite as the build tool).

    Note: SvelteKit also has a svelte.config, so
    SvelteKit takes priority via its more-specific match.
    """

    icon = "⚡"
    spec_doc = "https://vitejs.dev/config/"

    _CONFIG_NAMES = {
        "vite.config.js",
        "vite.config.ts",
        "vite.config.mjs",
        "vite.config.cjs",
        "vite.config.mts",
    }

    def match(self) -> bool:
        return bool(self._CONFIG_NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.infra import StaticSite
        from projspec.artifact.process import Server

        super().parse0()

        pkg_mgr = self._pkg_manager()
        self._artifacts["dev"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "dev"],
        )
        self._artifacts["build"] = StaticSite(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "build"],
            fn=f"{self.proj.url}/dist/index.html",
        )
        self._artifacts["preview"] = Server(
            proj=self.proj,
            cmd=[pkg_mgr, "run", "preview"],
        )

    def _pkg_manager(self) -> str:
        if "yarn.lock" in self.proj.basenames:
            return "yarn"
        if "pnpm-lock.yaml" in self.proj.basenames:
            return "pnpm"
        if "bun.lock" in self.proj.basenames or "bun.lockb" in self.proj.basenames:
            return "bun"
        return "npm"

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(
            [
                "npm",
                "create",
                "vite@latest",
                path,
                "--",
                "--template",
                "vanilla",
            ],
            cwd=os.path.dirname(path) or ".",
            output=False,
        )


class Pnpm(Node):
    """Node project managed with pnpm."""

    icon = "📦"
    spec_doc = "https://pnpm.io/package_json"

    def match(self) -> bool:
        return "pnpm-lock.yaml" in self.proj.basenames

    def parse(self) -> None:
        from projspec.content.environment import Environment, Stack, Precision
        from projspec.artifact.python_env import LockFile

        super().parse0()

        try:
            with self.proj.fs.open(f"{self.proj.url}/pnpm-lock.yaml", "rt") as f:
                import yaml as _yaml

                lock = _yaml.safe_load(f)
        except Exception:
            lock = {}

        self._artifacts["lock_file"] = LockFile(
            proj=self.proj,
            cmd=["pnpm", "install"],
            fn=self.proj.basenames["pnpm-lock.yaml"],
        )

        if isinstance(lock, dict):
            pkgs = list(lock.get("packages", {}).keys())
            if pkgs:
                self._contents.setdefault("environment", AttrDict())[
                    "pnpm_lock"
                ] = Environment(
                    proj=self.proj,
                    stack=Stack.NPM,
                    packages=pkgs,
                    precision=Precision.LOCK,
                )

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(["pnpm", "init"], cwd=path, output=False)


class Bun(Node):
    """Node project managed with Bun."""

    icon = "🍞"
    spec_doc = "https://bun.sh/docs/install/lockfile"

    def match(self) -> bool:
        return bool({"bun.lock", "bun.lockb"}.intersection(self.proj.basenames))

    def parse(self) -> None:
        from projspec.artifact.python_env import LockFile

        super().parse0()

        lock_name = "bun.lock" if "bun.lock" in self.proj.basenames else "bun.lockb"
        self._artifacts["lock_file"] = LockFile(
            proj=self.proj,
            cmd=["bun", "install"],
            fn=self.proj.basenames[lock_name],
        )

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(["bun", "init", "-y"], cwd=path, output=False)


class Deno(ProjectSpec):
    """Deno project.

    Note: this is a separate runtime, not a Node project.
    """

    icon = "🖧"
    spec_doc = "https://docs.deno.com/runtime/fundamentals/configuration/"

    _CONFIG_NAMES = {"deno.json", "deno.jsonc"}

    def match(self) -> bool:
        return bool(self._CONFIG_NAMES.intersection(self.proj.basenames))

    def parse(self) -> None:
        import json
        from projspec.artifact.base import FileArtifact
        from projspec.artifact.process import Process, Server
        from projspec.artifact.python_env import LockFile
        from projspec.content.executable import Command
        from projspec.content.metadata import DescriptiveMetadata

        fname = next(n for n in self._CONFIG_NAMES if n in self.proj.basenames)
        try:
            with self.proj.get_file(fname) as f:
                cfg = json.loads(f.read())
        except Exception as exc:
            raise ParseFailed(f"Could not read {fname}: {exc}") from exc

        if not isinstance(cfg, dict):
            raise ParseFailed(f"{fname} did not parse to a mapping")

        meta: dict[str, str] = {}
        for key in ("name", "version", "description"):
            if val := cfg.get(key):
                meta[key] = str(val)

        conts = AttrDict()
        if meta:
            conts["descriptive_metadata"] = DescriptiveMetadata(
                proj=self.proj, meta=meta
            )

        arts = AttrDict()
        tasks = cfg.get("tasks", {})
        cmds = AttrDict()
        for task_name, task_cmd in tasks.items():
            cmd_list = ["deno", "task", task_name]
            cmds[task_name] = Command(proj=self.proj, cmd=cmd_list)
            arts[task_name] = Process(proj=self.proj, cmd=cmd_list)

        if cmds:
            conts["command"] = cmds

        # Lock file
        if "deno.lock" in self.proj.basenames:
            arts["lock_file"] = LockFile(
                proj=self.proj,
                cmd=["deno", "cache", "--reload", "mod.ts"],
                fn=self.proj.basenames["deno.lock"],
            )

        # Main entry point
        main = cfg.get("main") or cfg.get("exports")
        if main and isinstance(main, str):
            arts["run"] = Process(
                proj=self.proj,
                cmd=["deno", "run", "--allow-all", main],
            )

        self._contents = conts
        self._artifacts = arts

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(
            ["deno", "init", path],
            cwd=os.path.dirname(path) or ".",
            output=False,
        )
