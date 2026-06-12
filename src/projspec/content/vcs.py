"""VCSInfo content class — normalised version-control metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from projspec.content.base import BaseContent


@dataclass
class VCSInfo(BaseContent):
    """Normalised metadata extracted from a VCS repository directory.

    All three VCS specs (``GitRepo``, ``HgRepo``, ``FossilRepo``) produce a
    single ``VCSInfo`` instance stored under the ``"vcs_info"`` key in their
    ``_contents``.

    Standard fields
    ---------------
    vcs : str
        VCS tool name: ``"git"``, ``"hg"``, or ``"fossil"``.
    branch : str or None
        Current branch / bookmark name.
    commit : str or None
        Short commit hash or revision identifier.
    author : str or None
        Author of the most recent commit.
    message : str or None
        First line of the most recent commit message.
    timestamp : float or None
        Unix timestamp of the most recent commit.

    VCS-specific extras
    -------------------
    For **git**: ``extra`` may contain ``"branches"`` (list), ``"tags"``
    (list), and ``"remote_names"`` (list).

    For **Mercurial**: ``extra`` may contain ``"bookmarks"`` (list) and
    ``"remotes"`` (dict mapping name → URL).

    For **Fossil**: ``extra`` may contain ``"repository"`` (str path to the
    ``.fossil`` database file).

    Summary
    -------
    The ``summary`` property returns a plain :class:`dict` with the subset
    of fields that have non-``None`` values — identical in shape to what
    ``Project.vcs_info`` exposes.  It is included in ``to_dict()`` output
    so it is preserved when a project is saved to the library.
    """

    icon = "🔀"

    vcs: str = ""
    branch: str | None = None
    commit: str | None = None
    author: str | None = None
    message: str | None = None
    timestamp: float | None = None
    extra: dict = field(default_factory=dict)

    @property
    def summary(self) -> dict:
        """Plain dict of all non-None standard VCS fields (including ``vcs``)."""
        out: dict = {"vcs": self.vcs}
        for key in ("branch", "commit", "author", "message", "timestamp"):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        return out
