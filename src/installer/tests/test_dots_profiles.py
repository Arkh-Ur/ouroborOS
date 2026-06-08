"""test_dots_profiles.py — Unit tests for the dots_profiles module (UT-P-001 to UT-P-055)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from installer.dots_profiles import DotsPack, load_catalog, packs_for_profile

# ── UT-P-001 to UT-P-010: DotsPack dataclass ─────────────────────────────────

class TestDotsPackDataclass:
    """UT-P-001 to UT-P-005 — DotsPack dataclass."""

    def test_dotspack_required_fields(self) -> None:
        """UT-P-001: DotsPack constructs with all required fields."""
        pack = DotsPack(
            id="noctalia",
            name="Noctalia v4",
            description="Quickshell shell.",
            author="noctalia-dev team",
            homepage="https://github.com/noctalia-dev/noctalia-shell",
            compatibility="low",
            profiles=["hyprland", "niri"],
            has_stable=True,
            has_git=True,
            stable_version_hint="v4 (stable)",
        )
        assert pack.id == "noctalia"
        assert pack.compatibility == "low"
        assert "hyprland" in pack.profiles
        assert pack.has_stable is True
        assert pack.has_git is True

    def test_dotspack_git_version_hint_default_empty(self) -> None:
        """UT-P-002: git_version_hint defaults to empty string."""
        pack = DotsPack(
            id="ml4w", name="ML4W", description="d", author="a", homepage="h",
            compatibility="medium", profiles=["hyprland"],
            has_stable=True, has_git=False, stable_version_hint="v0.2.3",
        )
        assert pack.git_version_hint == ""

    def test_dotspack_git_only_has_stable_false(self) -> None:
        """UT-P-003: Git-only pack has has_stable=False and has_git=True."""
        pack = DotsPack(
            id="illogical-impulse", name="illogical-impulse", description="d",
            author="end-4", homepage="h", compatibility="critical",
            profiles=["hyprland"], has_stable=False, has_git=True,
            stable_version_hint="",
        )
        assert pack.has_stable is False
        assert pack.has_git is True

    def test_dotspack_critical_compatibility(self) -> None:
        """UT-P-004: CRITICAL pack has compatibility="critical"."""
        pack = DotsPack(
            id="omarchy", name="Omarchy", description="d", author="DHH",
            homepage="h", compatibility="critical", profiles=["hyprland"],
            has_stable=False, has_git=True, stable_version_hint="",
        )
        assert pack.compatibility == "critical"

    def test_dotspack_profiles_is_list(self) -> None:
        """UT-P-005: profiles is a list, not a string."""
        pack = DotsPack(
            id="noctalia", name="Noctalia v4", description="d",
            author="a", homepage="h", compatibility="low",
            profiles=["hyprland", "niri"], has_stable=True, has_git=True,
            stable_version_hint="v4 (stable)",
        )
        assert isinstance(pack.profiles, list)
        assert len(pack.profiles) == 2


# ── UT-P-011 to UT-P-030: load_catalog() ─────────────────────────────────────

class TestLoadCatalog:
    """UT-P-011 to UT-P-030 — load_catalog()."""

    def test_missing_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """UT-P-011: Non-existent MANIFEST_DIR → empty list, no exception."""
        result = load_catalog(tmp_path / "nonexistent")
        assert result == []

    def test_empty_dir_returns_empty_list(self, tmp_manifest_dir: Path) -> None:
        """UT-P-012: Empty directory → empty list."""
        result = load_catalog(tmp_manifest_dir)
        assert result == []

    def test_single_valid_manifest(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-013: One valid manifest → list with one DotsPack."""
        result = load_catalog(tmp_manifest_dir)
        assert len(result) == 1
        assert result[0].id == "noctalia"

    def test_returns_alphabetical_order(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-014: Manifests returned in alphabetical order by filename."""
        result = load_catalog(tmp_manifest_dir)
        ids = [p.id for p in result]
        assert ids == sorted(ids)

    def test_invalid_yaml_ignored(self, tmp_manifest_dir: Path) -> None:
        """UT-P-015: Manifest with invalid YAML is ignored; catalog continues."""
        bad = tmp_manifest_dir / "broken.yaml"
        bad.write_text("{{ invalid: yaml: content")
        result = load_catalog(tmp_manifest_dir)
        assert all(p.id != "broken" for p in result)

    def test_non_dict_yaml_ignored(self, tmp_manifest_dir: Path) -> None:
        """UT-P-016: Manifest whose root is not a dict is ignored."""
        bad = tmp_manifest_dir / "list.yaml"
        bad.write_text("- item1\n- item2\n")
        result = load_catalog(tmp_manifest_dir)
        assert result == []

    def test_reads_nested_compatibility_immutable(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-017: compatibility read from compatibility.immutable (nested schema)."""
        result = load_catalog(tmp_manifest_dir)
        assert result[0].compatibility == "low"

    def test_reads_nested_profiles(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-018: profiles read from compatibility.profiles (nested schema)."""
        result = load_catalog(tmp_manifest_dir)
        assert set(result[0].profiles) == {"hyprland", "niri"}

    def test_has_stable_true_when_variants_stable_defined(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-019: has_stable=True when variants.stable is defined."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.has_stable is True

    def test_has_git_true_when_variants_git_defined(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-020: has_git=True when variants.git is defined."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.has_git is True

    def test_git_only_pack_has_stable_false(
        self, tmp_manifest_dir: Path, illogical_yaml: Path
    ) -> None:
        """UT-P-021: Git-only pack has has_stable=False."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "illogical-impulse")
        assert pack.has_stable is False
        assert pack.has_git is True

    def test_stable_only_pack_has_git_false(
        self, tmp_manifest_dir: Path, danklinux_yaml: Path
    ) -> None:
        """UT-P-022: Stable-only pack has has_git=False."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "danklinux")
        assert pack.has_git is False
        assert pack.has_stable is True

    def test_reads_stable_version_hint(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-023: stable_version_hint read from variants.stable.version_hint."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.stable_version_hint == "v4 (stable)"

    def test_reads_git_version_hint(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-024: git_version_hint read from variants.git.version_hint."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.git_version_hint == "git (bleeding edge)"

    def test_reads_credits_author(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-025: author read from credits.author (nested schema)."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.author == "noctalia-dev team"

    def test_reads_credits_homepage(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-026: homepage read from credits.homepage."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert "noctalia-shell" in pack.homepage

    def test_critical_pack_loads_correctly(
        self, tmp_manifest_dir: Path, illogical_yaml: Path
    ) -> None:
        """UT-P-027: CRITICAL pack loads with compatibility="critical"."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "illogical-impulse")
        assert pack.compatibility == "critical"

    def test_high_pack_loads_correctly(
        self, tmp_manifest_dir: Path, danklinux_yaml: Path
    ) -> None:
        """UT-P-028: HIGH pack loads with compatibility="high"."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "danklinux")
        assert pack.compatibility == "high"

    def test_multiple_manifests_all_loaded(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-029: Multiple valid manifests all loaded."""
        result = load_catalog(tmp_manifest_dir)
        ids = {p.id for p in result}
        assert ids == {"noctalia", "danklinux", "illogical-impulse"}

    def test_mixed_valid_and_invalid_skips_invalid(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-030: Invalid manifest skipped; valid one present in result."""
        (tmp_manifest_dir / "corrupt.yaml").write_text("not: valid: yaml: [[[")
        result = load_catalog(tmp_manifest_dir)
        assert len(result) == 1
        assert result[0].id == "noctalia"


# ── UT-P-031 to UT-P-042: packs_for_profile() ────────────────────────────────

class TestPacksForProfile:
    """UT-P-031 to UT-P-042 — packs_for_profile()."""

    def test_hyprland_returns_hyprland_packs(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-031: hyprland returns all packs with hyprland in profiles."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        ids = {p.id for p in result}
        assert "noctalia" in ids
        assert "danklinux" in ids
        assert "illogical-impulse" in ids

    def test_niri_returns_only_niri_packs(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-032: niri returns only packs with niri in profiles."""
        result = packs_for_profile("niri", tmp_manifest_dir)
        ids = {p.id for p in result}
        assert "noctalia" in ids
        assert "danklinux" in ids
        assert "illogical-impulse" not in ids

    def test_unknown_profile_returns_empty(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-033: Unknown profile → empty list, no error."""
        result = packs_for_profile("gnome", tmp_manifest_dir)
        assert result == []

    def test_minimal_profile_returns_empty(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-034: 'minimal' profile → empty list (no pack supports it)."""
        result = packs_for_profile("minimal", tmp_manifest_dir)
        assert result == []

    def test_empty_string_profile_returns_empty(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-035: Empty profile string → empty list, no error."""
        result = packs_for_profile("", tmp_manifest_dir)
        assert result == []

    def test_missing_manifest_dir_returns_empty(self, tmp_path: Path) -> None:
        """UT-P-036: Non-existent MANIFEST_DIR → empty list, no exception."""
        result = packs_for_profile("hyprland", tmp_path / "nonexistent")
        assert result == []

    def test_niri_subset_of_hyprland_packs(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-037: Niri packs are a subset of hyprland packs in this catalog."""
        hyprland = {p.id for p in packs_for_profile("hyprland", tmp_manifest_dir)}
        niri = {p.id for p in packs_for_profile("niri", tmp_manifest_dir)}
        assert niri.issubset(hyprland)

    def test_profile_filter_is_exact_match(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-038: Filter is exact match — 'hypr' does not match 'hyprland'."""
        result = packs_for_profile("hypr", tmp_manifest_dir)
        assert result == []

    def test_all_hyprland_packs_in_catalog(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-039: Catalog with 3 manifests; hyprland returns all 3."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        assert len(result) == 3

    def test_result_items_are_dotspack_instances(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-040: Every result item is a DotsPack instance."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        for pack in result:
            assert isinstance(pack, DotsPack)

    def test_returns_list_not_generator(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-041: Returns list, not generator (indexable, len() works)."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        assert isinstance(result, list)
        assert len(result) >= 0

    def test_stability_across_calls(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-042: Two consecutive calls return equal results."""
        r1 = packs_for_profile("hyprland", tmp_manifest_dir)
        r2 = packs_for_profile("hyprland", tmp_manifest_dir)
        assert [p.id for p in r1] == [p.id for p in r2]


# ── UT-P-043 to UT-P-050: DotsPackConfig ─────────────────────────────────────

class TestDotsPackConfig:
    """UT-P-043 to UT-P-050 — DotsPackConfig dataclass."""

    def test_dotspackconfig_defaults(self) -> None:
        """UT-P-043: DotsPackConfig.pack=None, channel="stable" by default."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig()
        assert cfg.pack is None
        assert cfg.channel == "stable"

    def test_dotspackconfig_set_pack(self) -> None:
        """UT-P-044: DotsPackConfig accepts a pack id string."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig(pack="noctalia", channel="stable")
        assert cfg.pack == "noctalia"
        assert cfg.channel == "stable"

    def test_dotspackconfig_git_channel(self) -> None:
        """UT-P-045: DotsPackConfig accepts channel="git"."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig(pack="illogical-impulse", channel="git")
        assert cfg.channel == "git"

    def test_dotspackconfig_none_pack_default_channel(self) -> None:
        """UT-P-046: DotsPackConfig(pack=None) keeps channel="stable" by default."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig()
        assert cfg.pack is None
        assert cfg.channel == "stable"

    def test_dotspackconfig_pack_with_hyphens(self) -> None:
        """UT-P-047: DotsPackConfig accepts pack id with hyphens (canonical name)."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig(pack="illogical-impulse", channel="git")
        assert cfg.pack == "illogical-impulse"

    def test_dotspackconfig_pack_field_is_string_or_none(self) -> None:
        """UT-P-048: DotsPackConfig.pack is str or None, never another type."""
        from installer.config import DotsPackConfig
        cfg_none = DotsPackConfig()
        cfg_str = DotsPackConfig(pack="ml4w", channel="stable")
        assert cfg_none.pack is None
        assert isinstance(cfg_str.pack, str)

    def test_dotspackconfig_channel_field_is_string(self) -> None:
        """UT-P-049: DotsPackConfig.channel is always str."""
        from installer.config import DotsPackConfig
        for channel in ("stable", "git"):
            cfg = DotsPackConfig(pack="noctalia", channel=channel)
            assert isinstance(cfg.channel, str)

    def test_dotspackconfig_two_equal_instances(self) -> None:
        """UT-P-050: Two DotsPackConfig with same fields are equivalent."""
        from installer.config import DotsPackConfig
        cfg1 = DotsPackConfig(pack="noctalia", channel="stable")
        cfg2 = DotsPackConfig(pack="noctalia", channel="stable")
        assert cfg1.pack == cfg2.pack
        assert cfg1.channel == cfg2.channel


# ── UT-P-051 to UT-P-055: FSM handler _handle_dots_pack() ────────────────────

class TestHandleDotsPackFSM:
    """UT-P-051 to UT-P-055 — FSM handler _handle_dots_pack()."""

    def test_minimal_profile_skips_dots_pack(self) -> None:
        """UT-P-051: minimal profile → handler returns without installing pack."""
        from installer.config import DotsPackConfig
        from installer.state_machine import Installer

        config = MagicMock()
        config.desktop.profile = "minimal"
        config.dots_pack = DotsPackConfig()

        fsm = Installer.__new__(Installer)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._handle_dots_pack()

        assert config.dots_pack.pack is None
        fsm._update_progress.assert_called()

    def test_git_only_pack_channel_autocorrected(
        self, tmp_manifest_dir: Path, illogical_yaml: Path
    ) -> None:
        """UT-P-052: Channel auto-corrected to "git" for git-only packs (C-03)."""
        import installer.dots_profiles as dp
        from installer.config import DotsPackConfig
        from installer.state_machine import Installer

        dots_cfg = DotsPackConfig(pack="illogical-impulse", channel="stable")
        config = MagicMock()
        config.desktop.profile = "hyprland"
        config.dots_pack = dots_cfg

        fsm = Installer.__new__(Installer)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._has_internet = MagicMock(return_value=True)

        real_packs = dp.load_catalog(tmp_manifest_dir)
        orig_manifest_dir = dp.MANIFEST_DIR
        try:
            dp.MANIFEST_DIR = tmp_manifest_dir
            with patch("installer.dots_profiles.packs_for_profile", return_value=real_packs):
                fsm._handle_dots_pack()
        finally:
            dp.MANIFEST_DIR = orig_manifest_dir

        assert config.dots_pack.channel == "git"

    def test_stable_only_pack_channel_stays_stable(
        self, tmp_manifest_dir: Path, danklinux_yaml: Path
    ) -> None:
        """UT-P-053: channel="stable" unchanged for stable-only packs."""
        import installer.dots_profiles as dp
        from installer.config import DotsPackConfig
        from installer.state_machine import Installer

        dots_cfg = DotsPackConfig(pack="danklinux", channel="stable")
        config = MagicMock()
        config.desktop.profile = "hyprland"
        config.dots_pack = dots_cfg

        fsm = Installer.__new__(Installer)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._has_internet = MagicMock(return_value=True)

        real_packs = dp.load_catalog(tmp_manifest_dir)
        orig_manifest_dir = dp.MANIFEST_DIR
        try:
            dp.MANIFEST_DIR = tmp_manifest_dir
            with patch("installer.dots_profiles.packs_for_profile", return_value=real_packs):
                fsm._handle_dots_pack()
        finally:
            dp.MANIFEST_DIR = orig_manifest_dir

        assert config.dots_pack.channel == "stable"

    def test_no_pack_selected_channel_unchanged(self) -> None:
        """UT-P-054: No pack selected → channel unchanged."""
        from installer.config import DotsPackConfig
        from installer.state_machine import Installer

        dots_cfg = DotsPackConfig(pack=None, channel="stable")
        config = MagicMock()
        config.desktop.profile = "hyprland"
        config.dots_pack = dots_cfg

        fsm = Installer.__new__(Installer)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._handle_dots_pack()

        assert dots_cfg.channel == "stable"

    def test_progress_called_at_start_and_end(self) -> None:
        """UT-P-055: _update_progress called with 0 at start and 100 at end."""
        from unittest.mock import call

        from installer.config import DotsPackConfig
        from installer.state_machine import (  # type: ignore[attr-defined]
            Installer,
            State,
        )

        config = MagicMock()
        config.desktop.profile = "minimal"
        config.dots_pack = DotsPackConfig()

        fsm = Installer.__new__(Installer)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._handle_dots_pack()

        calls = fsm._update_progress.call_args_list
        assert any(c == call(State.DOTS_PACK, 0) for c in calls)
        assert any(c == call(State.DOTS_PACK, 100) for c in calls)
