"""test_our_container.py — Comprehensive pytest suite for the our-container bash script.

Tests the our-container systemd-nspawn container wrapper by invoking the real
bash script with mocked external tools (machinectl, btrfs, pacstrap, etc.).
All state is managed via temp directories — no root or Btrfs required.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


def _run_our_container(
    script: Path,
    machines_root: Path,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    script_content = script.read_text(encoding="utf-8")
    script_content = script_content.replace(
        'MACHINES_ROOT="/var/lib/machines"',
        f'MACHINES_ROOT="{machines_root}"',
    )
    script_content = script_content.replace(
        'exec sudo /usr/local/bin/our-container "$@"',
        'true  # sudo bypassed for testing',
    )
    patched = machines_root / ".our-container.test.sh"
    patched.write_text(script_content, encoding="utf-8")

    cmd = ["bash", str(patched)] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _create_container_on_disk(
    machines_root: Path,
    name: str,
) -> None:
    container_dir = machines_root / name
    container_dir.mkdir(parents=True, exist_ok=True)
    (container_dir / "etc").mkdir(exist_ok=True)
    (container_dir / "etc" / "passwd").write_text("root:x:0:0::/root:/bin/bash\n", encoding="utf-8")
    (container_dir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (container_dir / "usr" / "bin" / "bash").touch()


def _set_container_state(state_dir: Path, name: str, state: str) -> None:
    (state_dir / f"{name}.state").write_text(state, encoding="utf-8")


def _register_machine(state_dir: Path, name: str, state: str) -> None:
    with open(state_dir / "machines.list", "a", encoding="utf-8") as f:
        f.write(f"{name}         {state}\n")


# ===========================================================================
# 1. USAGE / HELP
# ===========================================================================


class TestUsage:
    def test_no_args_shows_help(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, [])
        assert result.returncode == 0
        assert "our-container" in result.stdout
        assert "USAGE" in result.stdout

    def test_help_flag(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["--help"])
        assert result.returncode == 0
        assert "systemd-nspawn container wrapper" in result.stdout

    def test_h_flag(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["-h"])
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_help_subcommand(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["help"])
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_unknown_command_exits_one(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["explode"])
        assert result.returncode == 1
        assert "unknown command" in result.stderr

    def test_usage_lists_all_commands(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["--help"])
        for cmd in ["create", "enter", "start", "stop", "list", "remove"]:
            assert cmd in result.stdout, f"missing command '{cmd}' in help output"


# ===========================================================================
# 2. COMMAND: create
# ===========================================================================


class TestCreate:
    def test_create_arch_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "test-arch", "arch"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "test-arch").is_dir()
        assert (machines_root / "test-arch" / "etc" / "passwd").exists()

    def test_create_default_distro_is_arch(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "test-default"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "test-default" / "etc" / "passwd").exists()

    def test_create_debian_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "test-debian", "debian"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "test-debian" / "etc" / "passwd").exists()

    def test_create_ubuntu_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "test-ubuntu", "ubuntu"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "test-ubuntu" / "etc" / "passwd").exists()

    def test_create_btrfs_subvolume(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, state_dir = mock_env
        result = _run_our_container(script, machines_root, ["create", "test-btrfs", "arch"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "test-btrfs").is_dir()
        assert "Btrfs subvolume" in result.stderr

    def test_create_non_btrfs_fallback(self, mock_env_no_btrfs: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env_no_btrfs
        result = _run_our_container(script, machines_root, ["create", "test-no-btrfs", "arch"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "test-no-btrfs").is_dir()
        assert "non-Btrfs" in result.stderr

    def test_create_missing_name(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create"])
        assert result.returncode == 1
        assert "usage" in result.stderr

    def test_create_duplicate_fails(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        _run_our_container(script, machines_root, ["create", "dup-test", "arch"])
        result = _run_our_container(script, machines_root, ["create", "dup-test", "arch"])
        assert result.returncode == 1
        assert "already exists" in result.stderr

    def test_create_unsupported_distro(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "test-fedora", "fedora"])
        assert result.returncode == 1
        assert "unsupported" in result.stderr

    def test_create_pacstrap_failure(self, mock_env_fail_pacstrap: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env_fail_pacstrap
        result = _run_our_container(script, machines_root, ["create", "fail-test", "arch"])
        assert result.returncode != 0

    def test_create_name_with_spaces(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "my box", "arch"])
        assert result.returncode == 1
        assert "invalid container name" in result.stderr

    def test_create_name_with_special_chars(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "box@v2!", "arch"])
        assert result.returncode == 1
        assert "invalid container name" in result.stderr


# ===========================================================================
# 3. COMMAND: enter
# ===========================================================================


class TestEnter:
    def test_enter_nonexistent_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["enter", "ghost"])
        assert "ghost" in (result.stdout + result.stderr)

    def test_enter_missing_name(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["enter"])
        assert result.returncode == 1
        assert "usage" in result.stderr

    def test_enter_existing_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        _create_container_on_disk(machines_root, "enter-test")
        result = _run_our_container(script, machines_root, ["enter", "enter-test"])
        assert result.returncode == 0, f"stderr: {result.stderr}"


# ===========================================================================
# 4. COMMAND: start
# ===========================================================================


class TestStart:
    def test_start_missing_name(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["start"])
        assert result.returncode == 1
        assert "usage" in result.stderr

    def test_start_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, state_dir = mock_env
        _create_container_on_disk(machines_root, "start-test")
        _register_machine(state_dir, "start-test", "offline")
        result = _run_our_container(script, machines_root, ["start", "start-test"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_start_machinectl_failure(self, mock_env_fail_tools: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env_fail_tools
        _create_container_on_disk(machines_root, "fail-start")
        result = _run_our_container(script, machines_root, ["start", "fail-start"])
        assert result.returncode != 0


# ===========================================================================
# 5. COMMAND: stop
# ===========================================================================


class TestStop:
    def test_stop_missing_name(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["stop"])
        assert result.returncode == 1
        assert "usage" in result.stderr

    def test_stop_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, state_dir = mock_env
        _create_container_on_disk(machines_root, "stop-test")
        _set_container_state(state_dir, "stop-test", "running")
        _register_machine(state_dir, "stop-test", "running")
        result = _run_our_container(script, machines_root, ["stop", "stop-test"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_stop_machinectl_failure(self, mock_env_fail_tools: tuple[Path, Path, Path]) -> None:
        script, machines_root, state_dir = mock_env_fail_tools
        _create_container_on_disk(machines_root, "fail-stop")
        _set_container_state(state_dir, "fail-stop", "running")
        _register_machine(state_dir, "fail-stop", "running")
        result = _run_our_container(script, machines_root, ["stop", "fail-stop"])
        assert result.returncode != 0


# ===========================================================================
# 6. COMMAND: list
# ===========================================================================


class TestList:
    def test_list_empty_storage(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["list"])
        assert result.returncode == 0

    def test_list_alias_ls(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["ls"])
        assert result.returncode == 0

    def test_list_with_containers(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        _create_container_on_disk(machines_root, "list-box1")
        _create_container_on_disk(machines_root, "list-box2")
        result = _run_our_container(script, machines_root, ["list"])
        assert result.returncode == 0
        assert "list-box1" in result.stdout
        assert "list-box2" in result.stdout

    def test_list_shows_storage_path(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["list"])
        assert result.returncode == 0
        assert "Container storage" in result.stdout


# ===========================================================================
# 7. COMMAND: remove
# ===========================================================================


class TestRemove:
    def test_remove_nonexistent(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["remove", "ghost"])
        assert result.returncode == 1
        assert "does not exist" in result.stderr

    def test_remove_missing_name(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["remove"])
        assert result.returncode == 1
        assert "usage" in result.stderr

    def test_remove_existing_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        _create_container_on_disk(machines_root, "rm-test")
        result = _run_our_container(script, machines_root, ["remove", "rm-test"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (machines_root / "rm-test").exists()

    def test_remove_running_container(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, state_dir = mock_env
        _create_container_on_disk(machines_root, "rm-running")
        _set_container_state(state_dir, "rm-running", "running")
        _register_machine(state_dir, "rm-running", "running")
        result = _run_our_container(script, machines_root, ["remove", "rm-running"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (machines_root / "rm-running").exists()

    def test_remove_btrfs_subvolume(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, state_dir = mock_env
        name = "rm-btrfs"
        _create_container_on_disk(machines_root, name)
        with open(state_dir / "subvolumes.list", "a", encoding="utf-8") as f:
            f.write(f"{machines_root}/{name}\n")
        result = _run_our_container(script, machines_root, ["remove", name])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (machines_root / name).exists()

    def test_remove_plain_directory(self, mock_env_no_btrfs: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env_no_btrfs
        name = "rm-dir"
        _create_container_on_disk(machines_root, name)
        result = _run_our_container(script, machines_root, ["remove", name])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (machines_root / name).exists()

    def test_remove_alias_rm(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        _create_container_on_disk(machines_root, "rm-alias")
        result = _run_our_container(script, machines_root, ["rm", "rm-alias"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (machines_root / "rm-alias").exists()


# ===========================================================================
# 8. LOGGING
# ===========================================================================


class TestLogging:
    def test_log_contains_program_name(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "log-test", "arch"])
        assert result.returncode == 0
        assert "our-container" in result.stderr

    def test_error_log_on_failure(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["bogus"])
        assert result.returncode == 1
        assert result.stderr != ""

    def test_die_exits_with_code_one(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["bogus"])
        assert result.returncode == 1


# ===========================================================================
# 9. EDGE CASES
# ===========================================================================


class TestEdgeCases:
    def test_create_name_with_dots(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "my.container.v2", "arch"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (machines_root / "my.container.v2").is_dir()

    def test_create_name_single_char(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        result = _run_our_container(script, machines_root, ["create", "a", "arch"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_remove_twice_fails(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        _create_container_on_disk(machines_root, "double-rm")
        _run_our_container(script, machines_root, ["remove", "double-rm"])
        result = _run_our_container(script, machines_root, ["remove", "double-rm"])
        assert result.returncode == 1
        assert "does not exist" in result.stderr

    def test_create_many_containers(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        for i in range(5):
            name = f"batch-{i:03d}"
            result = _run_our_container(script, machines_root, ["create", name, "arch"])
            assert result.returncode == 0, f"failed creating '{name}': {result.stderr}"

        result = _run_our_container(script, machines_root, ["list"])
        assert result.returncode == 0
        for i in range(5):
            assert f"batch-{i:03d}" in result.stdout


# ===========================================================================
# 10. INTEGRATION: full lifecycle
# ===========================================================================


class TestIntegration:
    def test_full_lifecycle(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        name = "lifecycle-test"

        result = _run_our_container(script, machines_root, ["create", name, "arch"])
        assert result.returncode == 0, f"create failed: {result.stderr}"
        assert (machines_root / name).is_dir()

        result = _run_our_container(script, machines_root, ["list"])
        assert name in result.stdout

        result = _run_our_container(script, machines_root, ["remove", name])
        assert result.returncode == 0, f"remove failed: {result.stderr}"
        assert not (machines_root / name).exists()

    def test_multiple_containers_independent(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        names = ["alpha", "beta", "gamma"]
        for n in names:
            result = _run_our_container(script, machines_root, ["create", n, "arch"])
            assert result.returncode == 0

        for n in names:
            assert (machines_root / n).is_dir()

        for n in names:
            result = _run_our_container(script, machines_root, ["remove", n])
            assert result.returncode == 0, f"remove {n} failed: {result.stderr}"

        for n in names:
            assert not (machines_root / n).exists()


# ===========================================================================
# 11. PERFORMANCE
# ===========================================================================


class TestPerformance:
    def test_help_responds_fast(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        start = time.monotonic()
        result = _run_our_container(script, machines_root, ["--help"])
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert elapsed < 5.0, f"help took {elapsed:.2f}s (expected < 5s)"

    def test_list_responds_fast(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        start = time.monotonic()
        result = _run_our_container(script, machines_root, ["list"])
        elapsed = time.monotonic() - start
        assert result.returncode == 0
        assert elapsed < 5.0, f"list took {elapsed:.2f}s (expected < 5s)"

    def test_error_response_fast(self, mock_env: tuple[Path, Path, Path]) -> None:
        script, machines_root, _ = mock_env
        start = time.monotonic()
        result = _run_our_container(script, machines_root, ["bogus"])
        elapsed = time.monotonic() - start
        assert result.returncode == 1
        assert elapsed < 5.0, f"error response took {elapsed:.2f}s (expected < 5s)"
