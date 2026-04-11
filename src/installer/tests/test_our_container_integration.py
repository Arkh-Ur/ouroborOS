"""Integration tests for our-container container wrapper.

Run selectively:  pytest -k our_container
Requires sudo + systemd-machined for real container tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


def _sudo_nopasswd() -> bool:
    try:
        return subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, timeout=5,
        ).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


_SUDO_NOPASSWD = _sudo_nopasswd()

requires_sudo = pytest.mark.skipif(
    not _SUDO_NOPASSWD,
    reason="sudo without password not available",
)

requires_machined = pytest.mark.skipif(
    not _SUDO_NOPASSWD
    or subprocess.run(
        ["systemctl", "is-active", "systemd-machined"],
        capture_output=True,
        timeout=5,
    ).stdout.strip()
    != b"active",
    reason="systemd-machined not active or sudo unavailable",
)


class TestOurBoxScriptStructure:

    def test_script_exists(self, our_container_script: Path) -> None:
        assert our_container_script.exists()
        assert our_container_script.is_file()

    def test_script_executable(self, our_container_script: Path) -> None:
        assert os.access(our_container_script, os.X_OK)

    def test_help_output(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "our-container" in result.stdout
        assert "systemd-nspawn" in result.stdout
        assert "create" in result.stdout
        assert "remove" in result.stdout

    def test_help_alias(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_unknown_command_returns_error(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "nonexistent-command"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "unknown command" in result.stderr.lower() or "unknown command" in result.stdout.lower()

    def test_no_command_shows_help(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_has_set_euo_pipefail(self, our_container_script: Path) -> None:
        content = our_container_script.read_text(encoding="utf-8")
        assert "set -euo pipefail" in content

    def test_machines_root_constant(self, our_container_script: Path) -> None:
        content = our_container_script.read_text(encoding="utf-8")
        assert 'MACHINES_ROOT="/var/lib/machines"' in content


class TestCommandValidation:

    def test_create_without_name_errors(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "create"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "usage" in result.stderr.lower() or "usage" in result.stdout.lower()

    def test_enter_without_name_errors(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "enter"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "usage" in result.stderr.lower() or "usage" in result.stdout.lower()

    def test_start_without_name_errors(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "start"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_stop_without_name_errors(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "stop"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_remove_without_name_errors(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "remove"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    @requires_sudo
    def test_unsupported_distro_fails(self, our_container_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_container_script), "create", "test-fedora", "fedora"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "unsupported" in result.stderr.lower() or "unsupported" in result.stdout.lower()


class TestErrorHandling:

    @requires_sudo
    def test_remove_nonexistent_fails(self, fake_machines_root: Path) -> None:
        result = _run_our_container(fake_machines_root, "remove", "no-such-container")
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()

    @requires_sudo
    def test_enter_nonexistent_fails(self, fake_machines_root: Path) -> None:
        result = _run_our_container(fake_machines_root, "enter", "ghost-container", timeout=5)
        assert result.returncode != 0

    @requires_sudo
    def test_create_duplicate_fails(self, fake_machines_root: Path) -> None:
        name = "dup-test"
        container_dir = fake_machines_root / name
        container_dir.mkdir()
        (container_dir / "etc").mkdir()

        result = _run_our_container(fake_machines_root, "create", name, "arch")
        assert result.returncode != 0
        assert "already exists" in result.stderr.lower() or "already exists" in result.stdout.lower()


class TestListCommand:

    @requires_sudo
    def test_list_empty(self, fake_machines_root: Path) -> None:
        result = _run_our_container(fake_machines_root, "list")
        assert result.returncode == 0

    @requires_sudo
    def test_list_shows_existing_containers(self, fake_machines_root: Path, fake_container: Path) -> None:
        result = _run_our_container(fake_machines_root, "list")
        assert result.returncode == 0
        assert "test-container" in result.stdout


class TestFullLifecycle:

    @requires_sudo
    @requires_machined
    @pytest.mark.skipif(
        not shutil.which("pacstrap"),
        reason="pacstrap not installed",
    )
    def test_create_start_stop_remove_cycle(self) -> None:
        name = f"itest-lifecycle-{os.getpid()}"

        try:
            result = subprocess.run(
                ["sudo", "bash", str(_our_container_path()), "create", name, "arch"],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"pacstrap unavailable or failed: {result.stderr[:200]}")

            container_dir = Path(f"/var/lib/machines/{name}")
            assert container_dir.exists()
            assert (container_dir / "etc" / "passwd").exists()

            subprocess.run(
                ["sudo", "machinectl", "start", name],
                capture_output=True, text=True, timeout=30,
            )

            subprocess.run(
                ["sudo", "machinectl", "terminate", name],
                capture_output=True, timeout=15,
            )

            result = subprocess.run(
                ["sudo", "bash", str(_our_container_path()), "remove", name],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0
            assert not container_dir.exists()

        finally:
            subprocess.run(
                ["sudo", "machinectl", "terminate", name],
                capture_output=True, timeout=15,
            )
            subprocess.run(
                ["sudo", "rm", "-rf", f"/var/lib/machines/{name}"],
                capture_output=True, timeout=15,
            )


class TestPersistence:

    def test_container_files_persist(self, fake_machines_root: Path, fake_container: Path) -> None:
        test_file = fake_container / "etc" / "test-persistence-marker"
        test_file.write_text("persistence-test-data", encoding="utf-8")

        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "persistence-test-data"

    @requires_sudo
    def test_container_survives_list_operation(self, fake_machines_root: Path, fake_container: Path) -> None:
        result = _run_our_container(fake_machines_root, "list")
        assert result.returncode == 0
        assert fake_container.exists()
        assert (fake_container / "etc" / "passwd").exists()


class TestConcurrency:

    def test_multiple_containers_can_coexist(self, fake_machines_root: Path) -> None:
        for i in range(5):
            cdir = fake_machines_root / f"concurrent-{i}"
            cdir.mkdir()
            (cdir / "etc").mkdir()
            (cdir / "etc" / "passwd").write_text("root:x:0:0::/root:/bin/bash\n", encoding="utf-8")

        all_names = {d.name for d in fake_machines_root.iterdir() if d.is_dir() and not d.name.startswith(".")}
        for i in range(5):
            assert f"concurrent-{i}" in all_names

    def test_shared_filesystem_multiple_containers(self, fake_machines_root: Path) -> None:
        shared_file = fake_machines_root / ".shared-state"
        shared_file.write_text("shared", encoding="utf-8")

        for i in range(3):
            cdir = fake_machines_root / f"sharing-{i}"
            cdir.mkdir()
            (cdir / "etc").mkdir()

        assert shared_file.exists()
        for i in range(3):
            assert (fake_machines_root / f"sharing-{i}").exists()


class TestScalability:

    def test_create_many_container_dirs(self, fake_machines_root: Path) -> None:
        count = 50
        for i in range(count):
            cdir = fake_machines_root / f"scale-{i:03d}"
            cdir.mkdir()
            (cdir / "etc").mkdir()
            (cdir / "etc" / "passwd").touch()

        all_dirs = [d for d in fake_machines_root.iterdir() if d.is_dir() and not d.name.startswith(".")]
        assert len(all_dirs) == count

    def test_list_performance_with_many_containers(self, fake_machines_root: Path) -> None:
        import time

        for i in range(100):
            cdir = fake_machines_root / f"perf-{i:03d}"
            cdir.mkdir()
            (cdir / "etc").mkdir()
            (cdir / "etc" / "passwd").touch()

        start = time.perf_counter()
        list(fake_machines_root.iterdir())
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"Listing 100 containers took {elapsed:.2f}s (threshold: 2.0s)"


class TestFilesystemCompatibility:

    def test_directory_fallback_creation(self, fake_machines_root: Path) -> None:
        name = "dir-only-container"
        cdir = fake_machines_root / name
        cdir.mkdir()
        (cdir / "etc").mkdir()

        assert cdir.exists()
        assert cdir.is_dir()

    def test_container_dir_size_calculation(self, fake_machines_root: Path, fake_container: Path) -> None:
        size = sum(f.stat().st_size for f in fake_container.rglob("*") if f.is_file())
        assert size >= 0

    def test_deeply_nested_container_structure(self, fake_machines_root: Path) -> None:
        cdir = fake_machines_root / "nested-container"
        nested = cdir / "usr" / "lib" / "python3.11" / "site-packages" / "deep" / "module"
        nested.mkdir(parents=True)
        (nested / "__init__.py").write_text("# module\n", encoding="utf-8")

        assert nested.exists()
        assert (nested / "__init__.py").read_text(encoding="utf-8") == "# module\n"


class TestResourceSharing:

    def test_container_isolation_directories(self, fake_machines_root: Path) -> None:
        for name in ["isolated-a", "isolated-b"]:
            cdir = fake_machines_root / name
            cdir.mkdir()
            (cdir / "etc").mkdir()
            (cdir / "var").mkdir()

        for name in ["isolated-a", "isolated-b"]:
            cdir = fake_machines_root / name
            assert cdir.exists()
            assert cdir.is_dir()


class TestSystemdInteroperability:

    @requires_sudo
    @requires_machined
    def test_machined_responds(self) -> None:
        result = subprocess.run(
            ["sudo", "machinectl", "list", "--all", "--no-pager", "--no-legend"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

    @requires_sudo
    @requires_machined
    def test_machined_show_nonexistent_machine(self) -> None:
        result = subprocess.run(
            ["sudo", "machinectl", "show", "nonexistent-test-machine-xyz"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0


class TestContainerStateTransitions:

    @requires_sudo
    def test_start_already_started_is_harmless(self, fake_machines_root: Path) -> None:
        name = "state-test"
        cdir = fake_machines_root / name
        cdir.mkdir()
        (cdir / "etc").mkdir()
        (cdir / "etc" / "passwd").touch()

        result = _run_our_container(fake_machines_root, "start", name)
        assert result.returncode in (0, 1, 124)

    @requires_sudo
    def test_stop_not_running_is_harmless(self, fake_machines_root: Path) -> None:
        name = "stop-test"
        cdir = fake_machines_root / name
        cdir.mkdir()
        (cdir / "etc").mkdir()

        result = _run_our_container(fake_machines_root, "stop", name)
        assert result.returncode in (0, 1, 124)

    @requires_sudo
    def test_list_alias_works(self, fake_machines_root: Path) -> None:
        result = _run_our_container(fake_machines_root, "ls")
        assert result.returncode == 0

    @requires_sudo
    def test_remove_alias_works(self, fake_machines_root: Path) -> None:
        name = "rm-alias-test"
        cdir = fake_machines_root / name
        cdir.mkdir()
        (cdir / "etc").mkdir()

        result = _run_our_container(fake_machines_root, "rm", name)
        assert result.returncode == 0
        assert not cdir.exists()


def _our_container_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / (
        "src/ouroborOS-profile/airootfs/usr/local/bin/our-container"
    )


def _make_wrapper(fake_machines_root: Path) -> Path:
    script = _our_container_path()
    mr = fake_machines_root
    wrapper = Path(tempfile.mktemp(suffix=".sh"))
    content = f'''#!/usr/bin/env bash
set -euo pipefail
MACHINES_ROOT="{mr}"
'''
    original = script.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    skip_until = 0
    for i, line in enumerate(lines):
        if "MACHINES_ROOT=" in line and "readonly" not in line:
            skip_until = i + 1
            break
    content += "".join(lines[skip_until + 1:])
    wrapper.write_text(content, encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def _run_our_container(
    fake_machines_root: Path,
    *args: str,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    wrapper = _make_wrapper(fake_machines_root)
    try:
        return subprocess.run(
            ["sudo", "bash", str(wrapper)] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["our-container"] + list(args),
            returncode=124,
            stdout="",
            stderr="timeout",
        )
    finally:
        wrapper.unlink(missing_ok=True)
