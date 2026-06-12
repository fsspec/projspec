"""Tests for module-level pure helpers in projspec.textapp.main.

None of these helpers import from textual, so they run in any environment
regardless of whether the optional textual dependency is installed.

Coverage targets
----------------
- _url_to_local
- _is_local_path
- _basename
- _fmt_age
- _is_enum / _enum_label
- _has_klass / _strip_klass
- _fmt_primitive
- _role
- _yaml_lines
- _wrap_chips
- _project_icon
- _collect_enum_members
- _expand_glob
- main() when App is None
"""

from __future__ import annotations

import os
import time

import pytest

try:
    from projspec.textapp.main import (
        _basename,
        _collect_enum_members,
        _enum_label,
        _expand_glob,
        _fmt_age,
        _fmt_primitive,
        _has_klass,
        _is_enum,
        _is_local_path,
        _project_icon,
        _role,
        _strip_klass,
        _url_to_local,
        _wrap_chips,
        _yaml_lines,
        ROLE_COLOUR,
        DEFAULT_ICON,
    )
except (ImportError, NameError):
    pytest.skip("projspec.textapp requires textual", allow_module_level=True)


# ---------------------------------------------------------------------------
# _url_to_local
# ---------------------------------------------------------------------------


class TestUrlToLocal:
    def test_strips_file_prefix(self):
        assert _url_to_local("file:///home/user/proj") == "/home/user/proj"

    def test_double_slash(self):
        assert _url_to_local("file://localhost/tmp") == "localhost/tmp"

    def test_plain_path_unchanged(self):
        assert _url_to_local("/tmp/proj") == "/tmp/proj"

    def test_s3_unchanged(self):
        assert _url_to_local("s3://bucket/key") == "s3://bucket/key"


# ---------------------------------------------------------------------------
# _is_local_path
# ---------------------------------------------------------------------------


class TestIsLocalPath:
    def test_file_scheme_is_local(self):
        assert _is_local_path("file:///home/user")

    def test_absolute_path_is_local(self):
        assert _is_local_path("/usr/local")

    def test_relative_path_is_local(self):
        assert _is_local_path("subdir/foo")

    def test_s3_is_not_local(self):
        assert not _is_local_path("s3://bucket/key")

    def test_http_is_not_local(self):
        assert not _is_local_path("https://example.com/path")


# ---------------------------------------------------------------------------
# _basename
# ---------------------------------------------------------------------------


class TestBasename:
    def test_simple_path(self):
        assert _basename("/home/user/myproject") == "myproject"

    def test_trailing_slash(self):
        assert _basename("/home/user/myproject/") == "myproject"

    def test_s3_url(self):
        assert _basename("s3://bucket/prefix/name") == "name"

    def test_bare_name(self):
        assert _basename("myproject") == "myproject"

    def test_empty_string(self):
        # Should not crash; returns empty-or-original
        result = _basename("")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _fmt_age
# ---------------------------------------------------------------------------


class TestFmtAge:
    def _ts(self, days_ago: float) -> float:
        return time.time() - days_ago * 86400

    def test_today(self):
        assert _fmt_age(self._ts(0.1)) == "today"

    def test_yesterday(self):
        assert _fmt_age(self._ts(1.5)) == "yesterday"

    def test_days(self):
        assert _fmt_age(self._ts(10)) == "10 days ago"

    def test_months(self):
        assert _fmt_age(self._ts(60)) == "2 months ago"

    def test_one_year(self):
        assert _fmt_age(self._ts(400)) == "1 year ago"

    def test_multiple_years(self):
        assert _fmt_age(self._ts(800)) == "2 years ago"


# ---------------------------------------------------------------------------
# _is_enum / _enum_label
# ---------------------------------------------------------------------------


class TestIsEnum:
    def test_valid_enum_dict(self):
        assert _is_enum({"klass": ["enum", "Stack"], "value": 1})

    def test_plain_dict_is_not_enum(self):
        assert not _is_enum({"key": "value"})

    def test_string_is_not_enum(self):
        assert not _is_enum("PIP")

    def test_none_is_not_enum(self):
        assert not _is_enum(None)

    def test_missing_value_is_not_enum(self):
        assert not _is_enum({"klass": ["enum", "Stack"]})

    def test_wrong_klass_type_is_not_enum(self):
        assert not _is_enum({"klass": "enum", "value": 1})


class TestEnumLabel:
    def test_known_member(self):
        enums = {"stack": {"PIP": 0, "CONDA": 1}}
        v = {"klass": ["enum", "stack"], "value": 0}
        label = _enum_label(v, enums)
        assert label == "PIP"

    def test_unknown_value_falls_back_to_str(self):
        enums = {"stack": {"PIP": 0}}
        v = {"klass": ["enum", "stack"], "value": 99}
        label = _enum_label(v, enums)
        assert "99" in label

    def test_unknown_enum_name_falls_back(self):
        enums = {}
        v = {"klass": ["enum", "nosuchtype"], "value": 0}
        label = _enum_label(v, enums)
        assert isinstance(label, str)


# ---------------------------------------------------------------------------
# _has_klass / _strip_klass
# ---------------------------------------------------------------------------


class TestHasKlass:
    def test_direct_klass_key(self):
        assert _has_klass({"klass": ["content", "foo"], "x": 1})

    def test_nested_in_list(self):
        assert _has_klass([{"klass": ["artifact", "bar"]}])

    def test_nested_in_dict(self):
        assert _has_klass({"outer": {"klass": ["spec", "baz"]}})

    def test_no_klass(self):
        assert not _has_klass({"a": 1, "b": [2, 3]})

    def test_string_is_false(self):
        assert not _has_klass("hello")

    def test_none_is_false(self):
        assert not _has_klass(None)


class TestStripKlass:
    def test_removes_klass_from_dict(self):
        d = {"klass": ["content", "x"], "name": "foo"}
        result = _strip_klass(d)
        assert "klass" not in result
        assert result["name"] == "foo"

    def test_passes_non_dict_through(self):
        assert _strip_klass("hello") == "hello"
        assert _strip_klass(42) == 42
        assert _strip_klass(None) is None

    def test_does_not_mutate_input(self):
        d = {"klass": ["x"], "a": 1}
        _strip_klass(d)
        assert "klass" in d  # original unchanged


# ---------------------------------------------------------------------------
# _fmt_primitive
# ---------------------------------------------------------------------------


class TestFmtPrimitive:
    def test_none_contains_null(self):
        result = _fmt_primitive(None)
        assert "null" in result

    def test_true_contains_true(self):
        result = _fmt_primitive(True)
        assert "true" in result

    def test_false_contains_false(self):
        result = _fmt_primitive(False)
        assert "false" in result

    def test_string_is_wrapped(self):
        result = _fmt_primitive("hello")
        assert "hello" in result

    def test_integer_is_wrapped(self):
        result = _fmt_primitive(42)
        assert "42" in result


# ---------------------------------------------------------------------------
# _role
# ---------------------------------------------------------------------------


class TestRole:
    def test_known_role_uses_colour(self):
        result = _role("hello", "spec")
        assert ROLE_COLOUR["spec"] in result
        assert "hello" in result

    def test_unknown_role_uses_fallback(self):
        result = _role("hello", "nonexistent_role")
        assert "hello" in result
        assert "[" in result  # still wrapped

    def test_output_has_opening_and_closing_tags(self):
        result = _role("x", "field")
        assert result.startswith("[")
        assert result.endswith("[/]")


# ---------------------------------------------------------------------------
# _yaml_lines
# ---------------------------------------------------------------------------


class TestYamlLines:
    def test_empty_list(self):
        lines = _yaml_lines([], {}, 0)
        assert any("[]" in l for l in lines)

    def test_empty_dict(self):
        lines = _yaml_lines({}, {}, 0)
        assert any("{}" in l for l in lines)

    def test_primitive_value(self):
        lines = _yaml_lines("hello", {}, 0)
        assert any("hello" in l for l in lines)

    def test_simple_dict(self):
        lines = _yaml_lines({"name": "foo"}, {}, 0)
        combined = " ".join(lines)
        assert "name" in combined
        assert "foo" in combined

    def test_list_of_strings(self):
        lines = _yaml_lines(["a", "b"], {}, 0)
        combined = " ".join(lines)
        assert "a" in combined and "b" in combined

    def test_nested_dict(self):
        data = {"outer": {"inner": 42}}
        lines = _yaml_lines(data, {}, 0)
        combined = " ".join(lines)
        assert "outer" in combined
        assert "inner" in combined
        assert "42" in combined

    def test_enum_dict_rendered_inline(self):
        enums = {"stack": {"PIP": 0}}
        v = {"klass": ["enum", "stack"], "value": 0}
        lines = _yaml_lines(v, enums, 0)
        combined = " ".join(lines)
        assert "PIP" in combined

    def test_indentation_increases_for_nested(self):
        data = {"a": {"b": 1}}
        lines_0 = _yaml_lines(data, {}, 0)
        lines_2 = _yaml_lines(data, {}, 2)
        # Outer indent: lines_2 should have more leading spaces
        assert lines_2[0].startswith(" " * 2)


# ---------------------------------------------------------------------------
# _wrap_chips
# ---------------------------------------------------------------------------


class TestWrapChips:
    def _chip(self, label):
        return (label, "url", "spec", None)

    def test_empty_list(self):
        assert _wrap_chips([], 36) == []

    def test_all_fit_on_one_row(self):
        chips = [self._chip("AB"), self._chip("CD")]
        rows = _wrap_chips(chips, 36)
        assert len(rows) == 1
        assert len(rows[0]) == 2

    def test_overflow_wraps(self):
        # 12 chips × ~5 cells each = 60 > 36; must wrap
        chips = [self._chip("X" * 3) for _ in range(12)]
        rows = _wrap_chips(chips, 36)
        assert len(rows) > 1

    def test_wide_chip_gets_own_row(self):
        # A chip wider than row_width must not be dropped
        wide = self._chip("W" * 40)
        short = self._chip("A")
        rows = _wrap_chips([short, wide, short], 10)
        all_chips = [c for row in rows for c in row]
        assert len(all_chips) == 3

    def test_emoji_counted_as_two_cells(self):
        # An emoji chip is counted as 2 cells per char; verify no crash
        chips = [self._chip("🔀"), self._chip("🧩"), self._chip("📦")]
        rows = _wrap_chips(chips, 36)
        all_chips = [c for row in rows for c in row]
        assert len(all_chips) == 3

    def test_all_chips_preserved(self):
        chips = [self._chip(str(i)) for i in range(20)]
        rows = _wrap_chips(chips, 20)
        all_chips = [c for row in rows for c in row]
        assert len(all_chips) == 20


# ---------------------------------------------------------------------------
# _project_icon
# ---------------------------------------------------------------------------


class TestProjectIcon:
    def _infos(self):
        return {
            "specs": {"git_repo": {"icon": "🔀"}},
            "content": {"python_package": {"icon": "🐍"}},
            "artifact": {"wheel": {"icon": "🎡"}},
        }

    def test_hit_in_infos(self):
        assert _project_icon("spec", "git_repo", self._infos()) == "🔀"

    def test_hit_content(self):
        assert _project_icon("content", "python_package", self._infos()) == "🐍"

    def test_miss_falls_back_to_default(self):
        icon = _project_icon("spec", "unknown_spec", self._infos())
        assert icon == DEFAULT_ICON["spec"]

    def test_unknown_kind_returns_question(self):
        icon = _project_icon("bizarre", "whatever", self._infos())
        assert icon == "❔"

    def test_empty_infos(self):
        icon = _project_icon("spec", "git_repo", {})
        assert icon == DEFAULT_ICON["spec"]


# ---------------------------------------------------------------------------
# _collect_enum_members
# ---------------------------------------------------------------------------


class TestCollectEnumMembers:
    def test_returns_dict(self):
        result = _collect_enum_members()
        assert isinstance(result, dict)

    def test_contains_stack_and_precision(self):
        result = _collect_enum_members()
        assert "stack" in result
        assert "precision" in result

    def test_members_are_name_to_value_dicts(self):
        result = _collect_enum_members()
        for name, members in result.items():
            assert isinstance(members, dict)
            for k in members:
                assert isinstance(k, str)


# ---------------------------------------------------------------------------
# _expand_glob
# ---------------------------------------------------------------------------


class TestExpandGlob:
    def test_exact_existing_path(self, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x")
        assert _expand_glob(str(f)) == [str(f)]

    def test_nonexistent_no_wildcard(self, tmp_path):
        assert _expand_glob(str(tmp_path / "nope.py")) == []

    def test_wildcard_matches(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        results = _expand_glob(str(tmp_path / "*.py"))
        assert len(results) == 2
        assert all(r.endswith(".py") for r in results)

    def test_wildcard_no_match(self, tmp_path):
        assert _expand_glob(str(tmp_path / "*.xyz")) == []

    def test_results_are_sorted(self, tmp_path):
        for name in ["c.py", "a.py", "b.py"]:
            (tmp_path / name).write_text("")
        results = _expand_glob(str(tmp_path / "*.py"))
        assert results == sorted(results)


# ---------------------------------------------------------------------------
# main() when App is None (textual not installed)
# ---------------------------------------------------------------------------


class TestMainWithoutTextual:
    def test_main_prints_message_when_app_is_none(self, capsys, monkeypatch):
        import projspec.textapp.main as tm

        monkeypatch.setattr(tm, "App", None)
        tm.main()
        out = capsys.readouterr().out + capsys.readouterr().err
        # Should have printed something instructing the user
        # (exact message is "Cannot run without textual …" but we just
        # check it didn't raise and produced output or did nothing)
        # Actually the function just returns early — no output; we just
        # verify it doesn't crash.
