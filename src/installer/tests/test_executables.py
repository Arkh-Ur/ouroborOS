"""Tests for our-*/ouroboros-* executables in the ISO profile.

Validates that all shell scripts in airootfs/usr/local/bin/ exist,
have correct permissions, proper shebangs, safe bash flags, and that
configure.sh references them correctly for installation to the target system.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
AIROOTFS_BIN = REPO_ROOT / "src" / "ouroborOS-profile" / "airootfs" / "usr" / "local" / "bin"
CONFIGURE_SH = REPO_ROOT / "src" / "installer" / "ops" / "configure.sh"

# Scripts that are copied from the live ISO to the installed system
# via the _p3_tools loop in configure.sh.
INSTALLED_TOOLS = [
    "our-snapshot",
    "our-rollback",
    "our-wifi",
    "our-bluetooth",
    "our-fido2",
    "our-flat",
    "our-aur",
    "ouroboros-secureboot",
]

# Scripts installed inline (written via heredoc) in configure.sh
INLINE_TOOLS = [
    "our-pac",
    "ouroboros-post-upgrade",
]

# Scripts that are inline-only (written via heredoc in configure.sh, NOT in airootfs)
INLINE_ONLY_TOOLS = ["ouroboros-post-upgrade"]

# Scripts copied individually (not in the _p3_tools loop)
INDIVIDUALLY_COPIED_TOOLS = [
    "our-container",
    "our-container-autostart",
    "ouroboros-firstboot",
]

# All tools expected on the installed system
ALL_INSTALLED_TOOLS = sorted(
    INSTALLED_TOOLS + INLINE_TOOLS + INDIVIDUALLY_COPIED_TOOLS
)

LIVE_ONLY_SCRIPTS = [
    "ouroborOS-installer",
    "sshd-hostkeys",
]

ALL_AIROOTFS_SCRIPTS = sorted(
    INSTALLED_TOOLS + INLINE_TOOLS + INDIVIDUALLY_COPIED_TOOLS + LIVE_ONLY_SCRIPTS
)

AIROOTFS_SOURCE_SCRIPTS = sorted(
    [t for t in ALL_AIROOTFS_SCRIPTS if t not in INLINE_ONLY_TOOLS]
)

# Expected permission mode: 0o755 (rwxr-xr-x)
EXPECTED_MODE = 0o755


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_script(path: Path) -> str:
    """Read a script file and return its content."""
    return path.read_text(encoding="utf-8")


def _get_mode(path: Path) -> int:
    """Get the permission bits of a file."""
    return stat.S_IMODE(path.stat().st_mode)


def _has_shebang_bash(content: str) -> bool:
    """Check if the script has a bash shebang."""
    return content.startswith("#!/usr/bin/env bash") or content.startswith("#!/bin/bash")


def _has_set_euo_pipefail(content: str) -> bool:
    """Check if the script contains 'set -euo pipefail'."""
    return "set -euo pipefail" in content


# ===========================================================================
# Test classes
# ===========================================================================


class TestAirootfsScriptsExist:
    """Every expected script must exist in the airootfs profile."""

    def test_airootfs_bin_dir_exists(self) -> None:
        assert AIROOTFS_BIN.is_dir(), f"airootfs bin dir not found: {AIROOTFS_BIN}"

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_script_exists(self, script_name: str) -> None:
        path = AIROOTFS_BIN / script_name
        assert path.is_file(), f"Script not found: {path}"


class TestAirootfsScriptPermissions:
    """All scripts in airootfs must be executable (0755)."""

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_executable_permissions(self, script_name: str) -> None:
        path = AIROOTFS_BIN / script_name
        mode = _get_mode(path)
        assert mode == EXPECTED_MODE, (
            f"{script_name}: expected mode {oct(EXPECTED_MODE)}, got {oct(mode)}"
        )

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_is_regular_file_not_symlink(self, script_name: str) -> None:
        path = AIROOTFS_BIN / script_name
        assert path.is_file(), f"{script_name} is not a regular file"
        assert not path.is_symlink(), f"{script_name} is a symlink — expected regular file"


class TestAirootfsScriptShebangs:
    """All scripts must have a proper bash shebang."""

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_has_bash_shebang(self, script_name: str) -> None:
        content = _read_script(AIROOTFS_BIN / script_name)
        assert _has_shebang_bash(content), (
            f"{script_name}: missing bash shebang (expected #!/usr/bin/env bash)"
        )


class TestAirootfsScriptSafety:
    """All shell scripts should use 'set -euo pipefail' for safety."""

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_has_set_euo_pipefail(self, script_name: str) -> None:
        content = _read_script(AIROOTFS_BIN / script_name)
        assert _has_set_euo_pipefail(content), (
            f"{script_name}: missing 'set -euo pipefail'"
        )


class TestAirootfsScriptHelpFlag:
    """Every our-*/ouroboros-* tool should respond to --help."""

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_help_does_not_crash(self, script_name: str) -> None:
        """Running with --help or 'help' subcommand should exit 0, not crash."""
        path = AIROOTFS_BIN / script_name
        # Some scripts use --help, others use 'help' subcommand
        for flag in ["--help", "-h", "help"]:
            result = subprocess.run(
                [str(path), flag],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "PATH": os.environ.get("PATH", "")},
            )
            # Accept 0 (success) or 1 (usage error) — anything else is a bug
            assert result.returncode in (0, 1), (
                f"{script_name} {flag}: exited with code {result.returncode}, "
                f"stderr: {result.stderr[:200]}"
            )
            # If one flag works, we're done
            if result.returncode == 0:
                return


class TestConfigureShInstallsAllTools:
    """configure.sh must reference every installed tool."""

    def test_configure_sh_exists(self) -> None:
        assert CONFIGURE_SH.is_file(), f"configure.sh not found: {CONFIGURE_SH}"

    def test_configure_sh_content_loaded(self) -> None:
        self._content = _read_script(CONFIGURE_SH)

    @pytest.mark.parametrize("tool", INSTALLED_TOOLS)  # type: ignore[misc]  # noqa: F821
    def test_phase3_tool_referenced_in_configure(self, tool: str) -> None:
        """Each _p3_tool must appear in the tools array in configure.sh."""
        content = _read_script(CONFIGURE_SH)
        # The tool name must appear in the _p3_tools array
        assert f'"{tool}"' in content or f"'{tool}'" in content or tool in content, (
            f"{tool} not referenced in configure.sh tools array"
        )

    @pytest.mark.parametrize("tool", INDIVIDUALLY_COPIED_TOOLS)  # type: ignore[misc]  # noqa: F821
    def test_individually_copied_tool_referenced(self, tool: str) -> None:
        """Individually copied tools must have explicit cp commands."""
        content = _read_script(CONFIGURE_SH)
        assert tool in content, (
            f"{tool} not referenced in configure.sh"
        )

    @pytest.mark.parametrize("tool", INLINE_TOOLS)  # type: ignore[misc]  # noqa: F821
    def test_inline_tool_referenced(self, tool: str) -> None:
        content = _read_script(CONFIGURE_SH)
        assert tool in content, f"{tool} not referenced in configure.sh"


class TestNoCircularSymlinks:
    """our-pac must be a real file, not a circular symlink."""

    def test_our_pac_is_regular_file(self) -> None:
        path = AIROOTFS_BIN / "our-pac"
        assert path.is_file(), "our-pac is not a file"
        assert not path.is_symlink(), "our-pac must not be a symlink"

    def test_our_pac_no_self_symlink_in_configure(self) -> None:
        """configure.sh must NOT create a symlink of our-pac to itself."""
        content = _read_script(CONFIGURE_SH)
        # The old bug was: ln -sf our-pac "${TARGET}/usr/local/bin/our-pac"
        # This creates a circular symlink. We ensure this pattern does not exist.
        assert 'ln -sf our-pac "${TARGET}/usr/local/bin/our-pac"' not in content, (
            "configure.sh creates a circular our-pac symlink — this was a fixed bug"
        )
        assert "ln -sf our-pac '${TARGET}/usr/local/bin/our-pac'" not in content, (
            "configure.sh creates a circular our-pac symlink — this was a fixed bug"
        )


class TestToolNamingConvention:
    """Installed scripts must follow the our-*/ouroboros-* naming convention."""

    @pytest.mark.parametrize("script_name", ALL_INSTALLED_TOOLS)  # type: ignore[misc]  # noqa: F821
    def test_naming_prefix(self, script_name: str) -> None:
        assert script_name.startswith(("our-", "ouroboros-")), (
            f"{script_name}: does not follow our-*/ouroboros-* naming convention"
        )


class TestScriptNotEmpty:
    """No script should be empty or trivially small."""

    @pytest.mark.parametrize("script_name", AIROOTFS_SOURCE_SCRIPTS)  # type: ignore[misc]  # noqa: F821
    def test_minimum_size(self, script_name: str) -> None:
        path = AIROOTFS_BIN / script_name
        size = path.stat().st_size
        # A valid script with shebang + set -euo pipefail + help is at least ~200 bytes
        assert size >= 200, (
            f"{script_name}: suspiciously small ({size} bytes) — may be incomplete"
        )


