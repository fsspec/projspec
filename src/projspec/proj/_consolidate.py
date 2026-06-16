"""Consolidate sets of related files into logical datasets.

Intake can already recognise some directory-based datasets (hive-partitioned
parquet, zarr, delta, …) by their characteristic contents.  This module covers
the complementary case where a directory holds *many individually-named files
that obviously belong together*, e.g.::

    001.csv 002.csv 003.csv          -> one CSV dataset
    part-00000.parquet part-00001…   -> one parquet dataset
    data_2019.json data_2020.json    -> one JSON dataset
    green.gif red.gif blue.gif       -> one GIF (image) dataset

The output is a list of :class:`FileGroup` objects.  Each group is either a
single standalone file or a consolidated set, and exposes a ``glob`` (or list of
members) suitable for handing straight to
:func:`intake.readers.inspect.inspect_dataset`.

The logic here is deliberately filesystem-agnostic: it operates on
``(basename, size)`` pairs so it can be unit-tested without any I/O.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# A maximal run of digits anywhere in the stem - the most common way numbered
# file series differ (001, 00001, 2020, ...).
_DIGITS = re.compile(r"\d+")
# Tokens for the "one differing token" heuristic (split on common separators).
_SEP = re.compile(r"[._\- ]+")


@dataclass
class FileGroup:
    """A standalone file or a consolidated set of related files.

    Attributes
    ----------
    members:
        Basenames belonging to this group, sorted.
    ext:
        Common file extension (lower-case, including the dot), or ``""``.
    total_size:
        Sum of the sizes of all members (bytes); ``None`` if unknown.
    pattern:
        For consolidated groups, a glob basename that matches all members
        (e.g. ``"*.csv"`` or ``"part-*.parquet"``).  For a single file this is
        just that file's basename.
    consolidated:
        ``True`` when this group represents more than one physical file.
    """

    members: list[str]
    ext: str = ""
    total_size: int | None = None
    pattern: str = ""
    consolidated: bool = False

    @property
    def name(self) -> str:
        """A short identifying name for the group."""
        if self.consolidated:
            return self.pattern
        return self.members[0]

    def url(self, root: str) -> str | list[str]:
        """Build the URL/glob (rooted at *root*) to hand to intake.

        A consolidated group whose members match a simple glob is expressed as
        a single ``root/pattern`` glob string; otherwise it is returned as an
        explicit list of member URLs.  A single file is returned as one URL.
        """
        root = root.rstrip("/")
        if not self.consolidated:
            return f"{root}/{self.members[0]}"
        if self.pattern and "*" in self.pattern:
            return f"{root}/{self.pattern}"
        return [f"{root}/{m}" for m in self.members]


def _split_ext(name: str) -> tuple[str, str]:
    """Split into ``(stem, ext)`` with a lower-cased extension.

    Handles common double extensions like ``.csv.gz`` / ``.tar.gz`` so that a
    series of compressed parts groups correctly.
    """
    lower = name.lower()
    for double in (".csv.gz", ".json.gz", ".tar.gz", ".tar.bz2", ".tsv.gz"):
        if lower.endswith(double) and len(name) > len(double):
            return name[: -len(double)], double
    stem, ext = os.path.splitext(name)
    return stem, ext.lower()


def _digit_pattern(stem: str) -> str | None:
    """Mask digit runs in *stem* with ``#``, or ``None`` if it has no digits.

    ``part-00001`` -> ``part-#``; ``data2020`` -> ``data#``.  Consecutive digit
    runs collapse to a single placeholder so that ``a1b2`` and ``a3b4`` share a
    key.
    """
    if not _DIGITS.search(stem):
        return None
    return _DIGITS.sub("#", stem)


def _glob_from_digit_pattern(pattern: str) -> str:
    """Turn a masked pattern (``part-#``) into a glob stem (``part-*``)."""
    return pattern.replace("#", "*")


def _token_signature(stem: str) -> tuple[tuple[str, ...], int] | None:
    """Return ``(tokens_with_one_blanked, blank_index)`` for the token heuristic.

    Used for non-numeric series such as ``green``/``red``/``blue``.  We only
    consider stems that split into the *same* number of tokens differing in
    exactly one position; here we just return the token tuple so the caller can
    group by "all-but-one token equal".
    """
    tokens = tuple(t for t in _SEP.split(stem) if t)
    if not tokens:
        return None
    return tokens, len(tokens)


def consolidate(
    files: list[tuple[str, int | None]],
    min_group: int = 3,
    min_token_group: int = 2,
) -> list[FileGroup]:
    """Group a flat list of files into datasets.

    Parameters
    ----------
    files:
        ``[(basename, size_or_None), ...]`` for the files directly in a
        directory (not directories, not recursive).
    min_group:
        Minimum number of files sharing a digit-masked pattern before they are
        consolidated.  Below this they are emitted as standalone files.
    min_token_group:
        Minimum size for the (weaker) "one differing token" heuristic used for
        non-numeric series like colour names.

    Returns
    -------
    list[FileGroup]
        One entry per resulting dataset, sorted by name.  Files that match no
        consolidation rule are returned as singleton, non-consolidated groups.
    """
    sizes: dict[str, int | None] = {n: s for n, s in files}
    remaining = set(sizes)
    groups: list[FileGroup] = []

    # ── Pass 1: digit-run patterns within each extension ──────────────────
    # key: (ext, digit_masked_stem) -> [names]
    digit_buckets: dict[tuple[str, str], list[str]] = {}
    for name in list(remaining):
        stem, ext = _split_ext(name)
        pat = _digit_pattern(stem)
        if pat is not None:
            digit_buckets.setdefault((ext, pat), []).append(name)

    for (ext, pat), members in digit_buckets.items():
        if len(members) >= min_group:
            members = sorted(members)
            remaining.difference_update(members)
            glob_stem = _glob_from_digit_pattern(pat)
            groups.append(
                FileGroup(
                    members=members,
                    ext=ext,
                    total_size=_sum_sizes(members, sizes),
                    pattern=f"{glob_stem}{ext}",
                    consolidated=True,
                )
            )

    # ── Pass 2: "one differing token" within each extension ───────────────
    # Group stems that share all tokens but one (same token count).
    token_buckets: dict[tuple[str, int, int, tuple[str, ...]], list[str]] = {}
    for name in list(remaining):
        stem, ext = _split_ext(name)
        sig = _token_signature(stem)
        if sig is None:
            continue
        tokens, ntok = sig
        # For each position, the key is (ext, ntok, blanked_index, other_tokens)
        for i in range(ntok):
            others = tokens[:i] + ("*",) + tokens[i + 1 :]
            token_buckets.setdefault((ext, ntok, i, others), []).append(name)

    used_in_token_pass: set[str] = set()
    # Prefer the largest buckets first so a file lands in its best group.
    for (ext, ntok, idx, others), members in sorted(
        token_buckets.items(), key=lambda kv: -len(kv[1])
    ):
        members = [m for m in members if m in remaining and m not in used_in_token_pass]
        if len(members) >= min_token_group and len(set(members)) >= min_token_group:
            members = sorted(members)
            used_in_token_pass.update(members)
            remaining.difference_update(members)
            glob_stem = "*".join("" if t == "*" else t for t in others)
            # rebuild a readable glob like "*.gif" / "frame_*_left.png"
            pattern = _normalise_token_glob(others)
            groups.append(
                FileGroup(
                    members=members,
                    ext=ext,
                    total_size=_sum_sizes(members, sizes),
                    pattern=f"{pattern}{ext}",
                    consolidated=True,
                )
            )

    # ── Pass 3: leftovers are standalone files ────────────────────────────
    for name in sorted(remaining):
        _, ext = _split_ext(name)
        groups.append(
            FileGroup(
                members=[name],
                ext=ext,
                total_size=sizes.get(name),
                pattern=name,
                consolidated=False,
            )
        )

    return sorted(groups, key=lambda g: g.name)


def _normalise_token_glob(tokens: tuple[str, ...]) -> str:
    """Join token glob pieces, collapsing the blanked position to ``*``.

    ``("*",)``                 -> ``"*"``
    ``("frame", "*", "left")`` -> ``"frame_*_left"`` (best-effort separator)
    """
    parts = [("*" if t == "*" else t) for t in tokens]
    # We lost the original separators; "_" is the most common, and the exact
    # separator does not matter for globbing since "*" spans it anyway when the
    # blank is interior. For a single trailing/leading blank this yields "*".
    glob = "_".join(parts)
    # Tidy duplicate stars produced by adjacent blanks.
    while "**" in glob:
        glob = glob.replace("**", "*")
    return glob


def _sum_sizes(members: list[str], sizes: dict[str, int | None]) -> int | None:
    total = 0
    for m in members:
        s = sizes.get(m)
        if s is None:
            return None
        total += s
    return total
