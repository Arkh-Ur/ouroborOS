"""conftest.py — Shared fixtures for ouroborOS test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the repository root (3 levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent.parent


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repository root directory."""
    return _project_root()


@pytest.fixture(scope="session")
def our_container_script(project_root: Path) -> Path:
    """Absolute path to the our-container script."""
    return project_root / "src" / "ouroborOS-profile" / "airootfs" / "usr" / "local" / "bin" / "our-container"


# ---------------------------------------------------------------------------
# Temporary directories that mimic our-container paths
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_machines_root(tmp_path: Path) -> Path:
    """Create a temporary /var/lib/machines/ structure."""
    machines = tmp_path / "var" / "lib" / "machines"
    machines.mkdir(parents=True)
    return machines


@pytest.fixture()
def fake_snapshots_root(fake_machines_root: Path) -> Path:
    """Create a temporary .snapshots/ inside machines root."""
    snapshots = fake_machines_root / ".snapshots"
    snapshots.mkdir()
    return snapshots


@pytest.fixture()
def fake_images_root(fake_machines_root: Path) -> Path:
    """Create a temporary .images/ inside machines root."""
    images = fake_machines_root / ".images"
    images.mkdir()
    return images


@pytest.fixture()
def fake_nspawn_dir(tmp_path: Path) -> Path:
    """Create a temporary /etc/systemd/nspawn/ directory."""
    nspawn = tmp_path / "etc" / "systemd" / "nspawn"
    nspawn.mkdir(parents=True)
    return nspawn


# ---------------------------------------------------------------------------
# Container simulation (creates fake container dirs on the fake root)
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_container(fake_machines_root: Path) -> Path:
    """Create a fake container directory with minimal structure."""
    name = "test-container"
    container_dir = fake_machines_root / name
    container_dir.mkdir()
    (container_dir / "etc").mkdir()
    (container_dir / "etc" / "passwd").write_text("root:x:0:0::/root:/bin/bash\n")
    (container_dir / "usr").mkdir()
    (container_dir / "usr" / "bin").mkdir()
    (container_dir / "var").mkdir()
    return container_dir


@pytest.fixture()
def fake_container_with_subvol(fake_machines_root: Path) -> tuple[Path, str]:
    """Create a fake container with a marker file indicating Btrfs subvolume."""
    name = "test-subvol-container"
    container_dir = fake_machines_root / name
    container_dir.mkdir()
    (container_dir / "etc").mkdir()
    (container_dir / "etc" / "passwd").write_text("root:x:0:0::/root:/bin/bash\n")
    (container_dir / "usr").mkdir()
    (container_dir / "usr" / "bin").mkdir()
    # .btrfs-subvol marker indicates it's a Btrfs subvolume (for testing)
    (container_dir / ".btrfs-subvol").touch()
    return container_dir, name


# ---------------------------------------------------------------------------
# our-container command runner (subprocess wrapper)
# ---------------------------------------------------------------------------

class OurBoxRunner:
    """Thin wrapper to invoke our-container with environment overrides."""

    def __init__(
        self,
        script: Path,
        machines_root: Path | None = None,
        snapshots_root: Path | None = None,
        images_root: Path | None = None,
        nspawn_dir: Path | None = None,
    ) -> None:
        self.script = script
        self.env = dict(os.environ)
        if machines_root is not None:
            # Override MACHINES_ROOT via wrapper env (our-container reads it from constant)
            # We can't override the constant directly, so we use a temp wrapper
            self._machines_root = machines_root
        else:
            self._machines_root = None

    def _build_env(self) -> dict[str, str]:
        env = dict(self.env)
        env["OUR_BOX_TEST"] = "1"
        return env

    def _make_wrapper(self, machines_root: Path | None = None) -> Path:
        """Create a temporary wrapper script that overrides MACHINES_ROOT."""
        wrapper = Path(tempfile.mktemp(suffix=".sh"))
        mr = machines_root or self._machines_root or Path("/var/lib/machines")
        content = f'''#!/usr/bin/env bash
set -euo pipefail
readonly MACHINES_ROOT="{mr}"
readonly SNAPSHOTS_ROOT="{mr}/.snapshots"
readonly IMAGES_ROOT="{mr}/.images"
readonly PROGRAM_NAME="our-container"
'''
        # Read the original script and strip the first 3 constant lines + shebang + set
        original = self.script.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        # Skip lines up to and including "set -euo pipefail" and the 3 readonly lines
        skip_until = 0
        found_set = False
        for i, line in enumerate(lines):
            if "set -euo pipefail" in line:
                found_set = True
            if found_set and "readonly MACHINES_ROOT" in line:
                skip_until = i + 3  # skip the 3 readonly lines
                break

        content += "".join(lines[skip_until + 1:])
        wrapper.write_text(content, encoding="utf-8")
        wrapper.chmod(0o755)
        return wrapper

    def run(
        self,
        args: list[str],
        machines_root: Path | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        """Run our-container with given arguments.

        Returns the CompletedProcess. The wrapper is cleaned up after.
        """
        wrapper = self._make_wrapper(machines_root)
        try:
            return subprocess.run(
                ["sudo", str(wrapper)] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._build_env(),
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=["our-container"] + args,
                returncode=124,
                stdout="",
                stderr="timeout",
            )
        finally:
            wrapper.unlink(missing_ok=True)


@pytest.fixture()
def runner(
    our_container_script: Path,
    fake_machines_root: Path,
) -> OurBoxRunner:
    """Create an OurBoxRunner that targets the fake machines root."""
    return OurBoxRunner(
        script=our_container_script,
        machines_root=fake_machines_root,
    )


# ---------------------------------------------------------------------------
# Subprocess helpers for validation
# ---------------------------------------------------------------------------

@pytest.fixture()
def sudo_available() -> bool:
    """Check if we can run sudo without a password (CI environment)."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture()
def systemd_machined_active() -> bool:
    """Check if systemd-machined is running on this host."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "systemd-machined"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "active" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture()
def btrfs_available() -> bool:
    """Check if btrfs tools are available."""
    return shutil.which("btrfs") is not None


@pytest.fixture()
def pacstrap_available() -> bool:
    """Check if pacstrap is available."""
    return shutil.which("pacstrap") is not None
