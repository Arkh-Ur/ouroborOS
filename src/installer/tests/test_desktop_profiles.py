"""test_desktop_profiles.py — Tests for installer desktop profiles module."""

from __future__ import annotations

import pytest

from installer.desktop_profiles import (
    VALID_DMS,
    VALID_PROFILES,
    VALID_SHELLS,
    display_manager_for,
    dm_package,
    dm_service,
    is_valid_profile,
    packages_for,
    resolve_dm,
    shell_package,
    shell_path,
)


# ---------------------------------------------------------------------------
# dm_package / dm_service
# ---------------------------------------------------------------------------


class TestDmPackage:
    def test_gdm_package(self) -> None:
        assert dm_package("gdm") == "gdm"

    def test_sddm_package(self) -> None:
        assert dm_package("sddm") == "sddm"

    def test_plm_package(self) -> None:
        assert dm_package("plm") == "plasma-login-manager"

    def test_dm_service_gdm(self) -> None:
        assert dm_service("gdm") == "gdm"

    def test_dm_service_sddm(self) -> None:
        assert dm_service("sddm") == "sddm"

    def test_dm_service_plm(self) -> None:
        assert dm_service("plm") == "plasmalogin"


# ---------------------------------------------------------------------------
# resolve_dm
# ---------------------------------------------------------------------------


class TestResolveDm:
    def test_auto_returns_canonical_dm_for_gnome(self) -> None:
        result = resolve_dm("gnome", "auto")
        assert result == "gdm"

    def test_auto_returns_none_for_minimal(self) -> None:
        result = resolve_dm("minimal", "auto")
        assert result == "none"

    def test_explicit_gdm(self) -> None:
        assert resolve_dm("hyprland", "gdm") == "gdm"

    def test_explicit_sddm(self) -> None:
        assert resolve_dm("minimal", "sddm") == "sddm"

    def test_unknown_dm_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown display manager"):
            resolve_dm("minimal", "lightdm")


# ---------------------------------------------------------------------------
# shell_path / shell_package
# ---------------------------------------------------------------------------


class TestShellPath:
    def test_bash_path(self) -> None:
        assert shell_path("bash") == "/bin/bash"

    def test_zsh_path(self) -> None:
        assert shell_path("zsh") == "/bin/zsh"

    def test_fish_path(self) -> None:
        assert shell_path("fish") == "/usr/bin/fish"

    def test_unknown_shell_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown shell"):
            shell_path("tcsh")

    def test_bash_package_is_none(self) -> None:
        assert shell_package("bash") is None

    def test_zsh_package(self) -> None:
        assert shell_package("zsh") == "zsh"

    def test_fish_package(self) -> None:
        assert shell_package("fish") == "fish"


# ---------------------------------------------------------------------------
# is_valid_profile / packages_for / display_manager_for
# ---------------------------------------------------------------------------


class TestProfileHelpers:
    def test_minimal_is_valid(self) -> None:
        assert is_valid_profile("minimal") is True

    def test_hyprland_is_valid(self) -> None:
        assert is_valid_profile("hyprland") is True

    def test_unknown_profile_is_invalid(self) -> None:
        assert is_valid_profile("lxqt") is False

    def test_packages_for_minimal_is_empty_list(self) -> None:
        pkgs = packages_for("minimal")
        assert isinstance(pkgs, list)

    def test_packages_for_gnome_includes_gnome(self) -> None:
        pkgs = packages_for("gnome")
        assert any("gnome" in p for p in pkgs)

    def test_packages_for_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown desktop profile"):
            packages_for("lxqt")

    def test_display_manager_for_gnome(self) -> None:
        assert display_manager_for("gnome") == "gdm"

    def test_display_manager_for_unknown_returns_empty(self) -> None:
        assert display_manager_for("lxqt") == ""
