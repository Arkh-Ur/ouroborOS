"""conftest.py — Shared fixtures for our-container tests.

Provides mock binaries (machinectl, btrfs, pacstrap, debootstrap, systemd-nspawn)
that simulate the real tools via a state directory.  This lets us test the our-container
bash script end-to-end without requiring root, Btrfs, or systemd.
"""

from __future__ import annotations

import os
import stat
import textwrap
from collections.abc import Generator
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Mock binary generators
# ---------------------------------------------------------------------------


def _write_mock_bin(dirpath: Path, name: str, script: str) -> Path:
    """Write an executable mock script into *dirpath* and return its path."""
    binfile = dirpath / name
    binfile.write_text(textwrap.dedent(script), encoding="utf-8")
    binfile.chmod(stat.S_IRWXU)
    return binfile


def _write_machinectl(mock_dir: Path, state_dir: Path) -> Path:
    """Create a mock machinectl that uses files in *state_dir* for state."""
    script = f"""\
    #!/usr/bin/env bash
    # mock machinectl for our-container tests
    STATE_DIR="{state_dir}"
    case "$1" in
        list)
            echo "MACHINE         SERVICE"
            # Read registered machines from state dir
            if [[ -f "$STATE_DIR/machines.list" ]]; then
                cat "$STATE_DIR/machines.list"
            fi
            ;;
        show)
            NAME="${{2:-}}"
            if [[ -z "$NAME" ]]; then exit 1; fi
            STATE_FILE="$STATE_DIR/$NAME.state"
            if [[ -f "$STATE_FILE" ]]; then
                echo "State=$(cat "$STATE_FILE")"
            else
                echo "State=unknown"
            fi
            exit 0
            ;;
        start)
            NAME="${{2:-}}"
            if [[ -z "$NAME" ]]; then exit 1; fi
            echo "$NAME" > "$STATE_DIR/$NAME.state" || exit 1
            if [[ -f "$STATE_DIR/machines.list" ]]; then
                grep -v "^$NAME " "$STATE_DIR/machines.list" > "$STATE_DIR/machines.list.tmp" 2>/dev/null || true
            fi
            echo "$NAME         running" >> "$STATE_DIR/machines.list"
            exit 0
            ;;
        stop)
            NAME="${{2:-}}"
            if [[ -z "$NAME" ]]; then exit 1; fi
            echo "offline" > "$STATE_DIR/$NAME.state" || exit 1
            if [[ -f "$STATE_DIR/machines.list" ]]; then
                sed -i "s/^$NAME .*/$NAME         offline/" "$STATE_DIR/machines.list" 2>/dev/null || true
            fi
            exit 0
            ;;
        shell)
            # Just echo that we would shell in
            echo "machinectl shell called for ${{2:-}}"
            exit 0
            ;;
        terminate)
            NAME="${{2:-}}"
            echo "offline" > "$STATE_DIR/$NAME.state" 2>/dev/null || true
            exit 0
            ;;
        *)
            echo "unknown machinectl command: $1" >&2
            exit 1
            ;;
    esac
    """
    return _write_mock_bin(mock_dir, "machinectl", script)


def _write_btrfs(mock_dir: Path, state_dir: Path) -> Path:
    """Create a mock btrfs that tracks subvolumes in *state_dir*."""
    script = f"""\
    #!/usr/bin/env bash
    STATE_DIR="{state_dir}"
    SUBVOLS_FILE="$STATE_DIR/subvolumes.list"
    case "$1 $2" in
        "subvolume create")
            SUBVOL="${{3:-}}"
            if [[ -z "$SUBVOL" ]]; then exit 1; fi
            mkdir -p "$SUBVOL"
            echo "$SUBVOL" >> "$SUBVOLS_FILE"
            exit 0
            ;;
        "subvolume show")
            SUBVOL="${{3:-}}"
            if [[ -z "$SUBVOL" ]]; then exit 1; fi
            if grep -qxF "$SUBVOL" "$SUBVOLS_FILE" 2>/dev/null; then
                # Print plausible btrfs subvolume show output
                echo "Name:           $(basename "$SUBVOL")"
                echo "UUID:           mock-uuid-$(basename "$SUBVOL")"
                exit 0
            else
                exit 1
            fi
            ;;
        "subvolume delete")
            SUBVOL="${{3:-}}"
            if [[ -z "$SUBVOL" ]]; then exit 1; fi
            if grep -qxF "$SUBVOL" "$SUBVOLS_FILE" 2>/dev/null; then
                sed -i "/^$(echo "$SUBVOL" | sed 's/[&/\\]/\\\\&/g')$/d" "$SUBVOLS_FILE"
                rm -rf "$SUBVOL"
                exit 0
            else
                exit 1
            fi
            ;;
        *)
            echo "unknown btrfs command" >&2
            exit 1
            ;;
    esac
    """
    return _write_mock_bin(mock_dir, "btrfs", script)


def _write_pacstrap(mock_dir: Path) -> Path:
    """Create a mock pacstrap that creates a minimal root filesystem."""
    script = """\
    #!/usr/bin/env bash
    TARGET="${2:-}"
    if [[ -z "$TARGET" ]]; then echo "Usage: pacstrap -c <target> <packages>" >&2; exit 1; fi
    mkdir -p "$TARGET"/{etc,usr/bin,usr/lib/systemd,var,tmp,proc,sys,dev}
    echo "root:x:0:0:root:/root:/bin/bash" > "$TARGET/etc/passwd"
    echo "root::0:0:99999:7:::" > "$TARGET/etc/shadow"
    echo "# mock pacman.conf" > "$TARGET/etc/pacman.conf"
    touch "$TARGET/usr/bin/bash"
    touch "$TARGET/usr/lib/systemd/systemd"
    exit 0
    """
    return _write_mock_bin(mock_dir, "pacstrap", script)


def _write_debootstrap(mock_dir: Path) -> Path:
    """Create a mock debootstrap that creates a minimal root filesystem."""
    script = """\
    #!/usr/bin/env bash
    DISTRO="${2:-}"
    TARGET="${3:-}"
    if [[ -z "$TARGET" ]]; then echo "Usage: debootstrap <distro> <target>" >&2; exit 1; fi
    mkdir -p "$TARGET"/{etc,usr/bin,usr/lib/systemd,var,tmp,proc,sys,dev}
    echo "root:x:0:0:root:/root:/bin/bash" > "$TARGET/etc/passwd"
    echo "root::0:0:99999:7:::" > "$TARGET/etc/shadow"
    touch "$TARGET/usr/bin/bash"
    touch "$TARGET/usr/lib/systemd/systemd"
    exit 0
    """
    return _write_mock_bin(mock_dir, "debootstrap", script)


def _write_systemd_nspawn(mock_dir: Path) -> Path:
    """Create a mock systemd-nspawn that handles passwd and direct container access."""
    script = """\
    #!/usr/bin/env bash
    # Parse -D flag to find container root, then handle subcommands
    TARGET=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -D) TARGET="$2"; shift 2 ;;
            --pipe) shift ;;
            passwd)
                # Simulate passwd -d root (delete password for root)
                shift
                # Just succeed silently
                exit 0
                ;;
            *)
                # Direct nspawn access — just succeed
                exit 0
                ;;
        esac
    done
    exit 0
    """
    return _write_mock_bin(mock_dir, "systemd-nspawn", script)


def _write_sudo(mock_dir: Path) -> Path:
    """Create a mock sudo that just executes the command as-is (no real elevation)."""
    script = """\
    #!/usr/bin/env bash
    # mock sudo: just execute the command directly
    exec "$@"
    """
    return _write_mock_bin(mock_dir, "sudo", script)


def _write_date(mock_dir: Path) -> Path:
    script = '#!/usr/bin/env bash\necho "2026-04-07 12:00:00"\n'
    return _write_mock_bin(mock_dir, "date", script)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_env(
    tmp_path: Path,
) -> Generator[tuple[Path, Path, Path], None, None]:
    """Set up a complete mock environment for testing our-container.

    Returns:
        Tuple of (our_container_script, mock_machines_root, state_dir).

    - Installs mock binaries into a temp PATH dir.
    - Creates a fake /var/lib/machines directory.
    - Creates a state directory for mock tool state tracking.
    - Yields with PATH set so our-container picks up the mocks.
    """
    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir()

    machines_root = tmp_path / "var_lib_machines"
    machines_root.mkdir()

    state_dir = tmp_path / "mock_state"
    state_dir.mkdir()
    (state_dir / "machines.list").write_text("", encoding="utf-8")
    (state_dir / "subvolumes.list").write_text("", encoding="utf-8")

    # Install all mock binaries
    _write_machinectl(mock_bin, state_dir)
    _write_btrfs(mock_bin, state_dir)
    _write_pacstrap(mock_bin)
    _write_debootstrap(mock_bin)
    _write_systemd_nspawn(mock_bin)
    _write_sudo(mock_bin)
    _write_date(mock_bin)

    # Path to the real our-container script
    repo_root = Path(__file__).resolve().parent.parent.parent
    our_container_script = (
        repo_root / "src" / "ouroborOS-profile" / "airootfs" / "usr" / "local" / "bin" / "our-container"
    )

    # Prepend mock bin to PATH
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{mock_bin}:{old_path}"

    yield our_container_script, machines_root, state_dir

    # Restore PATH
    os.environ["PATH"] = old_path


@pytest.fixture()
def mock_env_no_btrfs(tmp_path: Path) -> Generator[tuple[Path, Path, Path], None, None]:
    """Like mock_env but with a btrfs mock that always fails (simulates non-Btrfs).

    Returns:
        Tuple of (our_container_script, mock_machines_root, state_dir).
    """
    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir()

    machines_root = tmp_path / "var_lib_machines"
    machines_root.mkdir()

    state_dir = tmp_path / "mock_state"
    state_dir.mkdir()
    (state_dir / "machines.list").write_text("", encoding="utf-8")
    (state_dir / "subvolumes.list").write_text("", encoding="utf-8")

    _write_machinectl(mock_bin, state_dir)
    # btrfs mock that always fails
    _write_mock_bin(
        mock_bin,
        "btrfs",
        "#!/usr/bin/env bash\nexit 1\n",
    )
    _write_pacstrap(mock_bin)
    _write_debootstrap(mock_bin)
    _write_systemd_nspawn(mock_bin)
    _write_sudo(mock_bin)
    _write_date(mock_bin)

    repo_root = Path(__file__).resolve().parent.parent.parent
    our_container_script = (
        repo_root / "src" / "ouroborOS-profile" / "airootfs" / "usr" / "local" / "bin" / "our-container"
    )

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{mock_bin}:{old_path}"

    yield our_container_script, machines_root, state_dir

    os.environ["PATH"] = old_path


@pytest.fixture()
def mock_env_fail_tools(tmp_path: Path) -> Generator[tuple[Path, Path, Path], None, None]:
    """Like mock_env but with machinectl that fails on start/stop (error simulation).

    Returns:
        Tuple of (our_container_script, mock_machines_root, state_dir).
    """
    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir()

    machines_root = tmp_path / "var_lib_machines"
    machines_root.mkdir()

    state_dir = tmp_path / "mock_state"
    state_dir.mkdir()
    (state_dir / "machines.list").write_text("", encoding="utf-8")
    (state_dir / "subvolumes.list").write_text("", encoding="utf-8")

    # machinectl that fails on start/stop
    script = f"""\
    #!/usr/bin/env bash
    STATE_DIR="{state_dir}"
    case "$1" in
        list)
            if [[ -f "$STATE_DIR/machines.list" ]]; then
                cat "$STATE_DIR/machines.list"
            fi
            ;;
        show)
            NAME="${{2:-}}"
            STATE_FILE="$STATE_DIR/$NAME.state"
            if [[ -f "$STATE_FILE" ]]; then
                echo "State=$(cat "$STATE_FILE")"
            else
                exit 1
            fi
            ;;
        start|stop)
            exit 1
            ;;
        *)
            exit 1
            ;;
    esac
    """
    _write_mock_bin(mock_bin, "machinectl", script)
    _write_btrfs(mock_bin, state_dir)
    _write_pacstrap(mock_bin)
    _write_debootstrap(mock_bin)
    _write_systemd_nspawn(mock_bin)
    _write_sudo(mock_bin)
    _write_date(mock_bin)

    repo_root = Path(__file__).resolve().parent.parent.parent
    our_container_script = (
        repo_root / "src" / "ouroborOS-profile" / "airootfs" / "usr" / "local" / "bin" / "our-container"
    )

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{mock_bin}:{old_path}"

    yield our_container_script, machines_root, state_dir

    os.environ["PATH"] = old_path


@pytest.fixture()
def mock_env_fail_pacstrap(tmp_path: Path) -> Generator[tuple[Path, Path, Path], None, None]:
    """Like mock_env but with pacstrap that fails (bootstrap failure simulation).

    Returns:
        Tuple of (our_container_script, mock_machines_root, state_dir).
    """
    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir()

    machines_root = tmp_path / "var_lib_machines"
    machines_root.mkdir()

    state_dir = tmp_path / "mock_state"
    state_dir.mkdir()
    (state_dir / "machines.list").write_text("", encoding="utf-8")
    (state_dir / "subvolumes.list").write_text("", encoding="utf-8")

    _write_machinectl(mock_bin, state_dir)
    _write_btrfs(mock_bin, state_dir)
    # pacstrap that fails
    _write_mock_bin(
        mock_bin,
        "pacstrap",
        "#!/usr/bin/env bash\nexit 1\n",
    )
    _write_debootstrap(mock_bin)
    _write_systemd_nspawn(mock_bin)
    _write_sudo(mock_bin)
    _write_date(mock_bin)

    repo_root = Path(__file__).resolve().parent.parent.parent
    our_container_script = (
        repo_root / "src" / "ouroborOS-profile" / "airootfs" / "usr" / "local" / "bin" / "our-container"
    )

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{mock_bin}:{old_path}"

    yield our_container_script, machines_root, state_dir

    os.environ["PATH"] = old_path
