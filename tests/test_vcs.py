"""Tests for the VCS specs (HgRepo, FossilRepo, GitRepo) and Project.vcs_info.

All tests use synthetic on-disk fixtures so they never require hg, fossil,
or any other VCS tool to be installed.
"""

import os
import struct
import zlib

import pytest
import projspec


# ---------------------------------------------------------------------------
# Helpers: build minimal fake VCS directories
# ---------------------------------------------------------------------------


def _write(path, *parts, content=b""):
    """Write bytes to path/parts[0]/parts[1]/..., creating parents."""
    target = os.path.join(path, *parts)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if isinstance(content, str):
        content = content.encode()
    with open(target, "wb") as f:
        f.write(content)
    return target


# ── Git ─────────────────────────────────────────────────────────────────────


def _make_git_repo(tmp_path):
    """Create a minimal fake .git directory with HEAD, ref, reflog, COMMIT_EDITMSG."""
    root = str(tmp_path)
    sha = "a" * 40
    branch = "main"

    _write(root, ".git", "HEAD", content=f"ref: refs/heads/{branch}\n")
    _write(root, ".git", "refs", "heads", branch, content=f"{sha}\n")
    _write(root, ".git", "COMMIT_EDITMSG", content="Initial commit\n# comment\n")

    reflog_line = f"{'0' * 40} {sha} Test User <test@example.com> 1700000000 +0000\tInitial commit\n"
    _write(root, ".git", "logs", "HEAD", content=reflog_line)
    return root


class TestGitVcsInfo:
    def test_branch_and_commit(self, tmp_path):
        root = _make_git_repo(tmp_path)
        proj = projspec.Project(root)
        assert "git_repo" in proj.specs
        vi = proj.vcs_info
        assert vi is not None
        assert vi["vcs"] == "git"
        assert vi["branch"] == "main"
        assert vi["commit"] == "a" * 12

    def test_author_from_reflog(self, tmp_path):
        root = _make_git_repo(tmp_path)
        proj = projspec.Project(root)
        assert proj.vcs_info["author"] == "Test User <test@example.com>"

    def test_message_from_reflog(self, tmp_path):
        root = _make_git_repo(tmp_path)
        proj = projspec.Project(root)
        assert proj.vcs_info["message"] == "Initial commit"

    def test_timestamp_from_reflog(self, tmp_path):
        root = _make_git_repo(tmp_path)
        proj = projspec.Project(root)
        assert proj.vcs_info["timestamp"] == pytest.approx(1700000000.0)

    def test_message_fallback_to_commit_editmsg(self, tmp_path):
        """When logs/HEAD is absent, message comes from COMMIT_EDITMSG."""
        root = _make_git_repo(tmp_path)
        os.unlink(os.path.join(root, ".git", "logs", "HEAD"))
        proj = projspec.Project(root)
        assert proj.vcs_info["message"] == "Initial commit"

    def test_detached_head(self, tmp_path):
        root = str(tmp_path)
        sha = "b" * 40
        _write(root, ".git", "HEAD", content=f"{sha}\n")
        proj = projspec.Project(root)
        vi = proj.vcs_info
        assert vi["branch"] == "(detached HEAD)"
        assert vi["commit"] == "b" * 12

    def test_vcs_info_object_on_spec(self, tmp_path):
        """VCSInfo content object is accessible on the spec."""
        root = _make_git_repo(tmp_path)
        proj = projspec.Project(root)
        from projspec.content.vcs import VCSInfo

        vi_obj = proj.specs["git_repo"].contents["vcs_info"]
        assert isinstance(vi_obj, VCSInfo)
        assert vi_obj.vcs == "git"
        assert vi_obj.branch == "main"

    def test_vcs_info_extra_has_branches(self, tmp_path):
        root = _make_git_repo(tmp_path)
        proj = projspec.Project(root)
        vi_obj = proj.specs["git_repo"].contents["vcs_info"]
        assert "branches" in vi_obj.extra

    def test_no_vcs_returns_none(self, tmp_path):
        proj = projspec.Project(str(tmp_path))
        assert proj.vcs_info is None


# ── Mercurial ────────────────────────────────────────────────────────────────


def _make_hg_revlog(
    author="Alice <alice@example.com>", message="Fix bug", ts=1700001000
):
    """Build a minimal fake .hg/store/00changelog.{i,d} pair."""
    manifest = "0" * 40
    date_extra = f"{ts} 0"
    entry = f"{manifest}\n{author}\n{date_extra}\n\n{message}".encode()

    compressed = b"x" + zlib.compress(entry)
    comp_len = len(compressed)

    # First (and only) record: version number in top 4 bytes, offset=0
    offset_flags = 1 << 32
    nodeid = bytes(20) + bytes(12)
    record = struct.pack(">QII", offset_flags, comp_len, len(entry))
    record += struct.pack(">IIii", 0, 0, -1, -1)  # base, link, p1, p2
    record += nodeid
    assert len(record) == 64

    return record, compressed


def _make_hg_repo(
    tmp_path,
    branch="default",
    author="Alice <alice@example.com>",
    message="Fix bug",
    ts=1700001000,
):
    root = str(tmp_path)
    _write(root, ".hg", "branch", content=f"{branch}\n")
    _write(root, ".hg", "bookmarks", content="")
    _write(
        root,
        ".hg",
        "hgrc",
        content="[paths]\ndefault = https://example.com/repo\n",
    )
    _write(root, ".hg", "requires", content="revlogv1\n")

    index, data = _make_hg_revlog(author=author, message=message, ts=ts)
    _write(root, ".hg", "store", "00changelog.i", content=index)
    _write(root, ".hg", "store", "00changelog.d", content=data)
    return root


class TestHgRepo:
    def test_match(self, tmp_path):
        root = _make_hg_repo(tmp_path)
        proj = projspec.Project(root)
        assert "hg_repo" in proj.specs

    def test_no_match_without_hg_dir(self, tmp_path):
        proj = projspec.Project(str(tmp_path))
        assert "hg_repo" not in proj.specs

    def test_branch(self, tmp_path):
        root = _make_hg_repo(tmp_path, branch="feature-x")
        proj = projspec.Project(root)
        vi = proj.specs["hg_repo"].contents["vcs_info"]
        assert vi.branch == "feature-x"

    def test_remotes(self, tmp_path):
        root = _make_hg_repo(tmp_path)
        proj = projspec.Project(root)
        vi = proj.specs["hg_repo"].contents["vcs_info"]
        assert "default" in vi.extra["remotes"]

    def test_bookmarks_in_extra(self, tmp_path):
        root = _make_hg_repo(tmp_path)
        proj = projspec.Project(root)
        vi = proj.specs["hg_repo"].contents["vcs_info"]
        assert "bookmarks" in vi.extra

    def test_vcs_info(self, tmp_path):
        root = _make_hg_repo(
            tmp_path,
            branch="stable",
            author="Bob <bob@example.com>",
            message="Release 1.0",
            ts=1700002000,
        )
        proj = projspec.Project(root)
        vi = proj.vcs_info
        assert vi is not None
        assert vi["vcs"] == "hg"
        assert vi["branch"] == "stable"
        assert vi["author"] == "Bob <bob@example.com>"
        assert vi["message"] == "Release 1.0"
        assert vi["timestamp"] == pytest.approx(1700002000.0, abs=1)

    def test_vcs_info_no_hg_dir(self, tmp_path):
        proj = projspec.Project(str(tmp_path))
        assert proj.vcs_info is None

    def test_vcs_info_is_vcsinfo_instance(self, tmp_path):
        root = _make_hg_repo(tmp_path)
        proj = projspec.Project(root)
        from projspec.content.vcs import VCSInfo

        assert isinstance(proj.specs["hg_repo"].contents["vcs_info"], VCSInfo)


# ── Fossil ───────────────────────────────────────────────────────────────────


def _make_fossil_checkout(
    tmp_path,
    branch="trunk",
    commit_hash="abc123def456",
    author="Carol <carol@example.com>",
    message="Initial import",
    ts=1700003000,
):
    """Create a minimal fake Fossil SQLite checkout DB (_FOSSIL_)."""
    import sqlite3

    db_path = os.path.join(str(tmp_path), "_FOSSIL_")
    con = sqlite3.connect(db_path)

    con.execute("CREATE TABLE vvar(name TEXT PRIMARY KEY, value CLOB)")
    con.execute("INSERT INTO vvar VALUES ('checkout', ?)", (commit_hash,))
    con.execute("INSERT INTO vvar VALUES ('branch', ?)", (branch,))

    julian = ts / 86400.0 + 2440587.5
    con.execute(
        "CREATE TABLE event("
        "type TEXT, mtime REAL, objid INT, tagid INT, uid INT, "
        "comment TEXT, user TEXT)"
    )
    con.execute(
        "INSERT INTO event VALUES ('ci', ?, 1, NULL, 1, ?, ?)",
        (julian, message, author),
    )
    con.commit()
    con.close()
    return str(tmp_path)


class TestFossilRepo:
    def test_match(self, tmp_path):
        root = _make_fossil_checkout(tmp_path)
        proj = projspec.Project(root)
        assert "fossil_repo" in proj.specs

    def test_match_fslckout_name(self, tmp_path):
        import sqlite3

        db_path = os.path.join(str(tmp_path), ".fslckout")
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE vvar(name TEXT PRIMARY KEY, value CLOB)")
        con.execute("INSERT INTO vvar VALUES ('checkout', 'abc123')")
        con.commit()
        con.close()
        proj = projspec.Project(str(tmp_path))
        assert "fossil_repo" in proj.specs

    def test_no_match(self, tmp_path):
        proj = projspec.Project(str(tmp_path))
        assert "fossil_repo" not in proj.specs

    def test_branch_and_commit(self, tmp_path):
        root = _make_fossil_checkout(
            tmp_path, branch="trunk", commit_hash="deadbeef1234"
        )
        proj = projspec.Project(root)
        vi = proj.specs["fossil_repo"].contents["vcs_info"]
        assert vi.branch == "trunk"
        assert vi.commit == "deadbeef1234"

    def test_repository_in_extra(self, tmp_path):
        """repository path stored in extra when present in vvar."""
        import sqlite3

        db_path = os.path.join(str(tmp_path), "_FOSSIL_")
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE vvar(name TEXT PRIMARY KEY, value CLOB)")
        con.execute("INSERT INTO vvar VALUES ('checkout', 'abc')")
        con.execute(
            "INSERT INTO vvar VALUES ('repository', '/home/user/myrepo.fossil')"
        )
        con.commit()
        con.close()
        proj = projspec.Project(str(tmp_path))
        vi = proj.specs["fossil_repo"].contents["vcs_info"]
        assert vi.extra.get("repository") == "/home/user/myrepo.fossil"

    def test_vcs_info(self, tmp_path):
        root = _make_fossil_checkout(
            tmp_path,
            branch="release",
            author="Dave <dave@example.com>",
            message="Tag 2.0",
            ts=1700004000,
        )
        proj = projspec.Project(root)
        vi = proj.vcs_info
        assert vi is not None
        assert vi["vcs"] == "fossil"
        assert vi["branch"] == "release"
        assert vi["author"] == "Dave <dave@example.com>"
        assert vi["message"] == "Tag 2.0"
        assert vi["timestamp"] == pytest.approx(1700004000.0, abs=2)

    def test_vcs_info_no_fossil(self, tmp_path):
        proj = projspec.Project(str(tmp_path))
        assert proj.vcs_info is None

    def test_vcs_info_is_vcsinfo_instance(self, tmp_path):
        root = _make_fossil_checkout(tmp_path)
        proj = projspec.Project(root)
        from projspec.content.vcs import VCSInfo

        assert isinstance(proj.specs["fossil_repo"].contents["vcs_info"], VCSInfo)
