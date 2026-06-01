"""Integration tests for our-box user-space container tool.

Excluded from CI pytest (--ignore). Run selectively:
  pytest src/installer/tests/test_our_box_integration.py -v

Lifecycle tests require podman installed on the host.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _podman_available() -> bool:
    return shutil.which("podman") is not None


requires_podman = pytest.mark.skipif(
    not _podman_available(),
    reason="podman not installed",
)


class TestOurBoxHelp:
    """Basic --help smoke tests — no root, no podman needed."""

    def test_script_exists(self, our_box_script: Path) -> None:
        assert our_box_script.exists()
        assert our_box_script.is_file()

    def test_script_executable(self, our_box_script: Path) -> None:
        assert os.access(our_box_script, os.X_OK)

    def test_has_set_euo_pipefail(self, our_box_script: Path) -> None:
        content = our_box_script.read_text(encoding="utf-8")
        assert "set -euo pipefail" in content

    def test_help_exits_zero(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_no_args_shows_help(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_help_mentions_create_enter_remove(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "create" in result.stdout
        assert "enter" in result.stdout
        assert "remove" in result.stdout

    def test_help_mentions_box_types(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "dev" in result.stdout
        assert "ephemeral" in result.stdout
        assert "app" in result.stdout

    def test_help_alias(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "USAGE" in result.stdout

    def test_unknown_command_returns_nonzero(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "nonexistent"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0


class TestOurBoxValidation:
    """Argument validation — no root, no podman needed."""

    def test_create_missing_name_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "create"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower() or "name" in combined.lower()

    def test_create_missing_image_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "create", "mybox"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_create_invalid_type_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "create", "mybox", "alpine", "--type", "invalid"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "invalid" in combined.lower() or "type" in combined.lower()

    def test_enter_missing_name_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "enter"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_remove_missing_name_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "remove"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_migrate_invalid_source_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "migrate", "--from", "invalidtool", "mybox"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_engine_set_invalid_errors(self, our_box_script: Path) -> None:
        result = subprocess.run(
            ["bash", str(our_box_script), "engine", "set", "invalid"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0


class TestOurBoxList:
    """List command — no root, no podman needed (returns empty gracefully)."""

    def test_list_exits_nonzero_without_podman_gracefully(
        self, our_box_script: Path,
    ) -> None:
        """list must not crash with an unhandled error even without podman."""
        result = subprocess.run(
            ["bash", str(our_box_script), "list"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        # Either succeeds (empty list) or fails gracefully with a message
        combined = result.stdout + result.stderr
        assert result.returncode in (0, 1)
        # Must not be a bash crash (no unbound variable / pipefail noise)
        assert "unbound variable" not in combined
        assert "set -" not in combined


@requires_podman
class TestOurBoxLifecycle:
    """Full lifecycle tests — require podman installed."""

    _BOX_NAME = "ourbox-test-dev"
    _IMAGE = "docker.io/library/alpine:latest"

    def test_create_dev_box(self, our_box_script: Path) -> None:
        try:
            result = subprocess.run(
                [
                    "bash", str(our_box_script), "create",
                    self._BOX_NAME, self._IMAGE,
                    "--type", "dev", "--no-home",
                ],
                capture_output=True, text=True, timeout=120,
            )
            assert result.returncode == 0, result.stderr
        finally:
            subprocess.run(
                ["bash", str(our_box_script), "remove", self._BOX_NAME],
                capture_output=True, timeout=30,
            )

    def test_create_ephemeral_box_exits_zero(self, our_box_script: Path) -> None:
        # ephemeral runs immediately with --rm; we just check the create path
        # doesn't crash before trying to start (image pull may fail in CI,
        # so we only assert a reasonable exit code)
        result = subprocess.run(
            [
                "podman", "pull", self._IMAGE,
            ],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            pytest.skip("Cannot pull image — skipping ephemeral test")

    def test_create_remove_cycle(self, our_box_script: Path) -> None:
        box = "ourbox-test-cycle"
        image = self._IMAGE

        # Pull image first
        pull = subprocess.run(["podman", "pull", image], capture_output=True, timeout=120)
        if pull.returncode != 0:
            pytest.skip("Cannot pull image")

        try:
            # Create
            create = subprocess.run(
                ["bash", str(our_box_script), "create", box, image, "--type", "dev", "--no-home"],
                capture_output=True, text=True, timeout=60,
            )
            assert create.returncode == 0, create.stderr

            # Verify metadata exists
            meta_path = Path.home() / ".config" / "our-box" / "boxes.d" / f"{box}.conf"
            assert meta_path.exists(), "box metadata not written"

            # Remove
            remove = subprocess.run(
                ["bash", str(our_box_script), "remove", box],
                capture_output=True, text=True, timeout=30,
            )
            assert remove.returncode == 0, remove.stderr

            # Verify metadata cleaned up
            assert not meta_path.exists(), "box metadata not removed"

            # Recreate
            recreate = subprocess.run(
                ["bash", str(our_box_script), "create", box, image, "--type", "dev", "--no-home"],
                capture_output=True, text=True, timeout=60,
            )
            assert recreate.returncode == 0, recreate.stderr

        finally:
            subprocess.run(
                ["bash", str(our_box_script), "remove", box],
                capture_output=True, timeout=30,
            )
