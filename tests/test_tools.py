"""Tests for projspec.tools.choose_install_method and install_tool."""

import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

import projspec.tools as tools
from projspec.tools import (
    ToolInfo,
    TOOLS,
    _is_url,
    _is_shell_string,
    _leading_executable,
    _method_is_viable,
    _rank_install_string,
    _preferred_install_methods,
    choose_install_method,
    install_tool,
)
from projspec.config import temp_conf


# ---------------------------------------------------------------------------
# Helpers for patching is_installed
# ---------------------------------------------------------------------------


@contextmanager
def installed(*executables: str):
    """Context manager: make is_installed report only *executables* as present."""
    exe_set = set(executables)
    with patch.object(
        tools.is_installed, "exists", side_effect=lambda x, **kw: x in exe_set
    ):
        yield


@contextmanager
def nothing_installed():
    """Context manager: make is_installed report nothing as present."""
    with patch.object(tools.is_installed, "exists", return_value=False):
        yield


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


class TestIsUrl:
    def test_https(self):
        assert _is_url("https://example.com/install.sh")

    def test_http(self):
        assert _is_url("http://example.com")

    def test_pip_not_url(self):
        assert not _is_url("pip install foo")

    def test_curl_not_url(self):
        assert not _is_url("curl -sSL https://example.com | sh")


class TestIsShellString:
    def test_pipe(self):
        assert _is_shell_string("curl -sSL https://x.sh | sh")

    def test_redirect(self):
        assert _is_shell_string("echo y > /tmp/x")

    def test_and_and(self):
        assert _is_shell_string("cd /tmp && ./install.sh")

    def test_plain_pip(self):
        assert not _is_shell_string("pip install uv")

    def test_plain_brew(self):
        assert not _is_shell_string("brew install uv")


class TestLeadingExecutable:
    def test_pip(self):
        assert _leading_executable("pip install foo") == "pip"

    def test_curl(self):
        assert _leading_executable("curl -sSL https://example.com | sh") == "curl"

    def test_empty(self):
        assert _leading_executable("") == ""


# ---------------------------------------------------------------------------
# _method_is_viable
# ---------------------------------------------------------------------------


class TestMethodIsViable:
    def test_url_never_viable(self):
        assert not _method_is_viable("https://example.com/install")

    def test_winget_only_on_windows(self):
        with patch.object(tools, "_IS_POSIX", True):
            assert not _method_is_viable("winget install --id=foo.Bar")
        with patch.object(tools, "_IS_POSIX", False):
            with installed("winget"):
                assert _method_is_viable("winget install --id=foo.Bar")

    def test_shell_string_requires_posix(self):
        with patch.object(tools, "_IS_POSIX", False):
            with installed("curl"):
                assert not _method_is_viable("curl -sSL https://x.sh | sh")

    def test_shell_string_requires_leading_executable_present(self):
        with patch.object(tools, "_IS_POSIX", True):
            with nothing_installed():
                assert not _method_is_viable("curl -sSL https://x.sh | sh")
            with installed("curl"):
                assert _method_is_viable("curl -sSL https://x.sh | sh")

    def test_plain_command_needs_executable_on_path(self):
        with nothing_installed():
            assert not _method_is_viable("pip install foo")
        with installed("pip"):
            assert _method_is_viable("pip install foo")

    def test_brew_needs_brew_present(self):
        with nothing_installed():
            assert not _method_is_viable("brew install foo")
        with installed("brew"):
            assert _method_is_viable("brew install foo")


# ---------------------------------------------------------------------------
# _rank_install_string
# ---------------------------------------------------------------------------


class TestRankInstallString:
    def test_early_preference_ranks_lower(self):
        prefs = ["uv", "conda", "pip"]
        assert _rank_install_string("uv add foo", prefs) < _rank_install_string(
            "pip install foo", prefs
        )
        assert _rank_install_string("conda install foo", prefs) < _rank_install_string(
            "pip install foo", prefs
        )

    def test_unknown_executable_ranks_last(self):
        prefs = ["uv", "pip"]
        rank_unknown = _rank_install_string("obscure-tool install foo", prefs)
        assert rank_unknown == len(prefs)

    def test_same_installer_same_rank(self):
        prefs = ["pip", "conda"]
        r1 = _rank_install_string("pip install foo", prefs)
        r2 = _rank_install_string("pip install bar --extra-index-url x", prefs)
        assert r1 == r2


# ---------------------------------------------------------------------------
# _preferred_install_methods
# ---------------------------------------------------------------------------


class TestPreferredInstallMethods:
    def test_returns_list(self):
        result = _preferred_install_methods()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_config_override(self):
        with temp_conf(preferred_install_methods=["conda", "pip"]):
            result = _preferred_install_methods()
        assert result[:2] == ["conda", "pip"]

    def test_empty_config_uses_defaults(self):
        with temp_conf(preferred_install_methods=[]):
            result = _preferred_install_methods()
        assert "pip" in result
        assert "uv" in result

    def test_posix_excludes_winget_by_default(self):
        with patch.object(tools, "_IS_POSIX", True):
            result = _preferred_install_methods()
        assert "winget" not in result

    def test_windows_includes_winget_by_default(self):
        with patch.object(tools, "_IS_POSIX", False):
            result = _preferred_install_methods()
        assert "winget" in result


# ---------------------------------------------------------------------------
# choose_install_method
# ---------------------------------------------------------------------------


class TestChooseInstallMethod:
    def test_unknown_tool_returns_none(self):
        assert choose_install_method("nonexistent-tool-xyz") is None

    def test_returns_string_for_known_tool_with_viable_method(self):
        with installed("pip"):
            result = choose_install_method("uv")
        assert result is not None
        assert isinstance(result, str)

    def test_prefers_configured_installer_when_present(self):
        # mlflow has "uv add mlflow" — with uv on PATH and uv preferred,
        # that suggestion should be chosen over pip
        with temp_conf(preferred_install_methods=["uv", "pip"]):
            with installed("uv", "pip"):
                result = choose_install_method("mlflow")
        assert result is not None
        assert result.startswith("uv")

    def test_falls_back_to_pip_when_uv_absent(self):
        with temp_conf(preferred_install_methods=["uv", "pip"]):
            with installed("pip"):
                result = choose_install_method("uv")
        assert result is not None
        assert result.startswith("pip")

    def test_shell_string_chosen_when_only_curl_available(self):
        """When only curl is on PATH, a curl|sh one-liner should be chosen."""
        info = ToolInfo(
            name="test-shell-tool",
            description="Test tool",
            install_suggestions=[
                "pip install test-shell-tool",
                "curl -sSL https://example.com/install.sh | sh",
            ],
        )
        with patch.dict(tools.TOOLS, {"test-shell-tool": info}):
            with temp_conf(preferred_install_methods=["pip", "curl"]):
                with (
                    installed("curl"),
                    patch.object(tools, "_IS_POSIX", True),
                ):
                    result = choose_install_method("test-shell-tool")
        assert result is not None
        assert "curl" in result
        assert "|" in result

    def test_url_never_chosen(self):
        info = ToolInfo(
            name="url-only-tool",
            description="Only has a URL install",
            install_suggestions=["https://example.com/install"],
        )
        with patch.dict(tools.TOOLS, {"url-only-tool": info}):
            result = choose_install_method("url-only-tool")
        assert result is None

    def test_preference_order_respected(self):
        info = ToolInfo(
            name="multi-method-tool",
            description="Has several install methods",
            install_suggestions=[
                "pip install multi-method-tool",
                "conda install -c conda-forge multi-method-tool",
                "brew install multi-method-tool",
            ],
        )
        with patch.dict(tools.TOOLS, {"multi-method-tool": info}):
            with temp_conf(preferred_install_methods=["conda", "pip", "brew"]):
                with installed("pip", "conda", "brew"):
                    result = choose_install_method("multi-method-tool")
        assert result is not None
        assert result.startswith("conda")

    def test_winget_not_chosen_on_posix(self):
        info = ToolInfo(
            name="win-tool",
            description="Windows-only tool",
            install_suggestions=["winget install --id=foo.Bar"],
        )
        with patch.dict(tools.TOOLS, {"win-tool": info}):
            with patch.object(tools, "_IS_POSIX", True):
                result = choose_install_method("win-tool")
        assert result is None


# ---------------------------------------------------------------------------
# install_tool
# ---------------------------------------------------------------------------


class TestInstallTool:
    def test_raises_for_unknown_tool(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            install_tool("nonexistent-tool-xyz")

    def test_raises_when_no_viable_method(self):
        with (
            nothing_installed(),
            patch.object(tools, "_IS_POSIX", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="No viable install method"):
                install_tool("uv")

    def test_plain_command_uses_subprocess_call_with_list(self):
        """Non-shell install strings are called as a list (no shell=True)."""
        with (
            installed("pip"),
            patch("subprocess.call", return_value=0) as mock_call,
        ):
            with temp_conf(preferred_install_methods=["pip"]):
                rc = install_tool("uv")
        assert rc == 0
        mock_call.assert_called_once()
        call_args, call_kwargs = mock_call.call_args
        assert isinstance(call_args[0], list)
        assert call_kwargs.get("shell") is not True

    def test_shell_string_uses_shell_true(self):
        """Shell one-liners are run with shell=True."""
        info = ToolInfo(
            name="shell-install-tool",
            description="Installed via curl pipe",
            install_suggestions=["curl -sSL https://example.com/install.sh | sh"],
        )
        with patch.dict(tools.TOOLS, {"shell-install-tool": info}):
            with (
                installed("curl"),
                patch.object(tools, "_IS_POSIX", True),
                patch("subprocess.call", return_value=0) as mock_call,
                temp_conf(preferred_install_methods=["curl"]),
            ):
                rc = install_tool("shell-install-tool")
        assert rc == 0
        mock_call.assert_called_once()
        call_args, call_kwargs = mock_call.call_args
        assert call_kwargs.get("shell") is True
        assert isinstance(call_args[0], str)

    def test_returns_exit_code(self):
        with (
            installed("pip"),
            patch("subprocess.call", return_value=42),
            temp_conf(preferred_install_methods=["pip"]),
        ):
            rc = install_tool("uv")
        assert rc == 42

    def test_non_zero_exit_code_is_propagated(self):
        with (
            installed("pip"),
            patch("subprocess.call", return_value=1),
            temp_conf(preferred_install_methods=["pip"]),
        ):
            rc = install_tool("uv")
        assert rc == 1
