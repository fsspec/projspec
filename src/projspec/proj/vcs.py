"""Version-control system specs: GitRepo, HgRepo, FossilRepo.

All three specs produce a single :class:`~projspec.content.vcs.VCSInfo`
content object under the ``"vcs_info"`` key, giving a uniform interface
regardless of which VCS is in use.  ``Project.vcs_info`` delegates directly
to that object's :attr:`~projspec.content.vcs.VCSInfo.summary` property.
"""

from __future__ import annotations

import re
import struct
import zlib

from projspec.content.vcs import VCSInfo
from projspec.proj.base import ParseFailed, ProjectSpec
from projspec.utils import AttrDict, run_subprocess


# ===========================================================================
# GitRepo
# ===========================================================================


class GitRepo(ProjectSpec):
    """A version-controlled repository using git.

    git is the most widely used distributed VCS.  Branch, commit, author,
    and message are extracted from the ``.git/`` directory without requiring
    the ``git`` binary.
    """

    icon = "🔀"
    spec_doc = "https://git-scm.com/docs/git-config#_configuration_file"

    def match(self) -> bool:
        return ".git" in self.proj.basenames

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(["git", "init"], cwd=path, output=False)

    def parse(self) -> None:
        info = _read_git_info(self.proj)
        extra: dict = {}

        # Collect refs lists (branches, tags, remote names)
        try:
            extra["remote_names"] = [
                p.rsplit("/", 1)[-1]
                for p in self.proj.fs.ls(
                    f"{self.proj.url}/.git/refs/remotes", detail=False
                )
            ]
        except FileNotFoundError:
            pass
        extra["tags"] = []
        try:
            extra["tags"] = [
                p.rsplit("/", 1)[-1]
                for p in self.proj.fs.ls(
                    f"{self.proj.url}/.git/refs/tags", detail=False
                )
            ]
        except FileNotFoundError:
            pass
        extra["branches"] = []
        try:
            extra["branches"] = [
                p.rsplit("/", 1)[-1]
                for p in self.proj.fs.ls(
                    f"{self.proj.url}/.git/refs/heads", detail=False
                )
            ]
        except FileNotFoundError:
            pass

        self._contents = AttrDict(
            vcs_info=VCSInfo(
                proj=self.proj,
                vcs="git",
                branch=info.get("branch"),
                commit=info.get("commit"),
                author=info.get("author"),
                message=info.get("message"),
                timestamp=info.get("timestamp"),
                extra=extra,
            )
        )


# ===========================================================================
# HgRepo
# ===========================================================================


class HgRepo(ProjectSpec):
    """A version-controlled repository using Mercurial (hg).

    Mercurial is a distributed VCS used heavily at Meta, Mozilla, and in
    enterprise environments.  Metadata is extracted from the ``.hg/``
    directory without requiring the ``hg`` binary.
    """

    icon = "🪢"
    spec_doc = "https://www.mercurial-scm.org/wiki/Repository"

    def match(self) -> bool:
        return ".hg" in self.proj.basenames

    @staticmethod
    def _create(path: str) -> None:
        run_subprocess(["hg", "init"], cwd=path, output=False)

    def parse(self) -> None:
        extra: dict = {}
        branch: str | None = None

        # ── branch ──────────────────────────────────────────────────────────
        try:
            with self.proj.get_file(".hg/branch") as f:
                branch = f.read().strip() or None
        except (OSError, UnicodeDecodeError):
            pass

        # ── bookmarks ────────────────────────────────────────────────────────
        try:
            with self.proj.get_file(".hg/bookmarks") as f:
                lines = f.read().splitlines()
            extra["bookmarks"] = [ln.split()[-1] for ln in lines if ln.strip()]
        except OSError:
            extra["bookmarks"] = []

        # ── remotes ──────────────────────────────────────────────────────────
        try:
            import configparser

            cp = configparser.RawConfigParser()
            with self.proj.get_file(".hg/hgrc") as f:
                cp.read_string(f.read())
            if cp.has_section("paths"):
                extra["remotes"] = dict(cp.items("paths"))
        except Exception:
            extra["remotes"] = {}

        # ── most-recent commit ───────────────────────────────────────────────
        commit_meta: dict = {}
        try:
            result = _read_last_hg_commit(self.proj)
            if result:
                commit_meta = result
        except Exception:
            pass

        if not branch and not commit_meta and not extra.get("bookmarks"):
            raise ParseFailed("No usable Mercurial metadata found")

        self._contents = AttrDict(
            vcs_info=VCSInfo(
                proj=self.proj,
                vcs="hg",
                branch=branch,
                commit=commit_meta.get("commit"),
                author=commit_meta.get("author"),
                message=commit_meta.get("message"),
                timestamp=commit_meta.get("timestamp"),
                extra=extra,
            )
        )


# ===========================================================================
# FossilRepo
# ===========================================================================

_CHECKOUT_NAMES = ("_FOSSIL_", ".fslckout")


class FossilRepo(ProjectSpec):
    """A version-controlled repository using Fossil SCM.

    Fossil is an integrated VCS + bug-tracker + wiki used by the SQLite
    project and others.  The checkout database is a standard SQLite3 file,
    so metadata is extracted without requiring the ``fossil`` binary.
    """

    icon = "🦴"
    spec_doc = "https://fossil-scm.org/home/doc/trunk/www/fileformat.wiki"

    def match(self) -> bool:
        return any(name in self.proj.basenames for name in _CHECKOUT_NAMES)

    @staticmethod
    def _create(path: str) -> None:
        import os

        repo_file = os.path.join(path, "repo.fossil")
        run_subprocess(["fossil", "init", repo_file], output=False)
        run_subprocess(["fossil", "open", repo_file], cwd=path, output=False)

    def parse(self) -> None:
        import sqlite3
        import tempfile
        import os

        db_name = next((n for n in _CHECKOUT_NAMES if n in self.proj.basenames), None)
        if db_name is None:
            raise ParseFailed("No Fossil checkout database found")

        db_path = self.proj.basenames[db_name]
        if self.proj.is_local():
            local_path = db_path
            cleanup = False
        else:
            with self.proj.get_file(db_name, text=False) as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".fossil")
            tmp.write(data)
            tmp.close()
            local_path = tmp.name
            cleanup = True

        try:
            try:
                con = sqlite3.connect(local_path)
            except Exception:
                raise ParseFailed("Could not open Fossil checkout database")
            try:
                raw = _query_fossil_db(con)
            finally:
                con.close()
        finally:
            if cleanup:
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

        if not raw:
            raise ParseFailed("No usable Fossil metadata found")

        extra: dict = {}
        if "repository" in raw:
            extra["repository"] = raw["repository"]

        self._contents = AttrDict(
            vcs_info=VCSInfo(
                proj=self.proj,
                vcs="fossil",
                branch=raw.get("branch"),
                commit=raw.get("commit"),
                author=raw.get("author"),
                message=raw.get("message"),
                timestamp=raw.get("timestamp"),
                extra=extra,
            )
        )


# ===========================================================================
# Private helpers
# ===========================================================================


def _read_git_info(proj) -> dict:
    """Extract HEAD commit metadata from a .git directory.

    Returns a dict with any subset of ``branch``, ``commit``, ``author``,
    ``message``, ``timestamp``.  Never raises.
    """
    info: dict = {}
    try:
        with proj.get_file(".git/HEAD") as f:
            head = f.read().strip()
        if head.startswith("ref:"):
            ref = head.split("ref:", 1)[1].strip()
            info["branch"] = ref.split("refs/heads/", 1)[-1]
            try:
                with proj.get_file(f".git/{ref}") as f:
                    info["commit"] = f.read().strip()[:12]
            except OSError:
                pass
        else:
            info["branch"] = "(detached HEAD)"
            info["commit"] = head[:12]
    except OSError:
        return info

    # Author + message + timestamp from reflog
    try:
        with proj.get_file(".git/logs/HEAD") as f:
            lines = f.read().splitlines()
        if lines:
            last = lines[-1]
            m = re.match(r"[0-9a-f]+ [0-9a-f]+ (.*?) \d+ [+-]\d+\t(.*)", last)
            if m:
                info["author"] = m.group(1).strip()
                info["message"] = m.group(2).strip().splitlines()[0]
            ts_m = re.search(r"\s(\d{10})\s[+-]\d{4}\t", last)
            if ts_m:
                info["timestamp"] = float(ts_m.group(1))
    except OSError:
        pass

    # Fallback message from COMMIT_EDITMSG
    if "message" not in info:
        try:
            with proj.get_file(".git/COMMIT_EDITMSG") as f:
                raw = f.read()
            msg_lines = [l for l in raw.splitlines() if not l.startswith("#")]
            if msg_lines:
                info["message"] = msg_lines[0].strip()
        except OSError:
            pass

    return info


# ── Mercurial revlog ────────────────────────────────────────────────────────

_RECORD_SIZE = 64  # bytes per revlog index entry


def _read_last_hg_commit(proj) -> dict | None:
    """Parse the last entry from .hg/store/00changelog.{i,d}.

    Revlog v1 index record layout (big-endian, 64 bytes):
      offset+flags  8 B  — high 6 bytes: offset in .d file, low 2: flags
      comp_len      4 B  — compressed length
      uncomp_len    4 B
      base_rev      4 B
      link_rev      4 B
      parent1       4 B  (signed)
      parent2       4 B  (signed)
      nodeid       32 B  — 20-byte SHA1 + 12 bytes padding
    """
    try:
        with proj.get_file(".hg/store/00changelog.i", text=False) as f:
            index_data = f.read()
    except OSError:
        return None

    n = len(index_data) // _RECORD_SIZE
    if n == 0:
        return None

    last = index_data[(n - 1) * _RECORD_SIZE : n * _RECORD_SIZE]
    if len(last) < _RECORD_SIZE:
        return None

    offset_flags, comp_len = struct.unpack_from(">QI", last, 0)
    offset = 0 if n == 1 else (offset_flags >> 16)
    nodeid = last[32:52].hex()

    try:
        with proj.get_file(".hg/store/00changelog.d", text=False) as f:
            f.seek(offset)
            raw = f.read(comp_len)
    except (OSError, AttributeError):
        return {"commit": nodeid[:12]}

    entry = _decompress_revlog_entry(raw)
    if entry is None:
        return {"commit": nodeid[:12]}
    return _parse_changelog_entry(entry, nodeid)


def _decompress_revlog_entry(raw: bytes) -> bytes | None:
    if not raw:
        return None
    tag = raw[0:1]
    if tag == b"u":
        return raw[1:]
    if tag == b"x":
        try:
            return zlib.decompress(raw[1:])
        except zlib.error:
            return None
    return None  # zstd or delta — not handled


def _parse_changelog_entry(data: bytes, nodeid: str) -> dict:
    """Parse a decompressed Mercurial changelog entry.

    Format: ``<manifest>\\n<author>\\n<date> <extra>\\n<files>\\n\\n<message>``
    """
    result: dict = {"commit": nodeid[:12]}
    try:
        text = data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        if len(lines) >= 2:
            result["author"] = lines[1].strip()
        if len(lines) >= 3:
            result["timestamp"] = float(lines[2].split()[0])
        if "\n\n" in text:
            result["message"] = text.split("\n\n", 1)[-1].strip()
    except Exception:
        pass
    return result


# ── Fossil SQLite ───────────────────────────────────────────────────────────


def _query_fossil_db(con) -> dict:
    """Query a Fossil checkout SQLite database for metadata."""
    result: dict = {}
    try:
        cur = con.execute(
            "SELECT name, value FROM vvar WHERE name IN "
            "('checkout','checkout-hash','branch','repository')"
        )
        for name, value in cur.fetchall():
            if name in ("checkout", "checkout-hash"):
                result["commit"] = str(value)[:12]
            elif name == "branch":
                result["branch"] = str(value)
            elif name == "repository":
                result["repository"] = str(value)
    except Exception:
        pass

    try:
        row = con.execute(
            "SELECT user, comment, mtime FROM event "
            "WHERE type='ci' ORDER BY mtime DESC LIMIT 1"
        ).fetchone()
        if row:
            result["author"] = str(row[0])
            result["message"] = str(row[1]).strip()
            result["timestamp"] = (float(row[2]) - 2440587.5) * 86400
    except Exception:
        pass

    return result
