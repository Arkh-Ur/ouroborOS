"""desktop_profiles.py — ouroborOS desktop profile definitions.

Profiles are **package sets**, not curated configurations. ouroborOS does not
ship custom themes, keybindings, or desktop settings — each profile is a
starting point that the user configures however they want.

See docs/PHASE_2_PLAN.md for the rationale behind each package choice.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Profile package sets
# ---------------------------------------------------------------------------

PROFILE_PACKAGES: dict[str, list[str]] = {
    "minimal": [],
    "hyprland": [
        "hyprland",
        "xdg-desktop-portal-hyprland",
        "waybar",
        "foot",
        "wofi",
        "hyprpolkitagent",
        "qt5-wayland",
        "qt6-wayland",
    ],
    "niri": [
        "niri",
        "xdg-desktop-portal-gnome",
        "foot",
        "fuzzel",
        "polkit-gnome",
        "qt5-wayland",
        "qt6-wayland",
    ],
    "gnome": [
        "gnome",
        "gnome-tweaks",
        "xdg-user-dirs",
    ],
    "kde": [
        "plasma",
        "plasma-wayland-session",
        "kde-applications-meta",
    ],
}

# ---------------------------------------------------------------------------
# Display manager options (Wayland-native only)
# ---------------------------------------------------------------------------
#
# Four options are offered — all Wayland-native:
#   gdm   — GNOME Display Manager.  Full Wayland compositor.
#   sddm  — Simple Desktop Display Manager.  Wayland support via Qt.
#   plm   — Plasma Login Manager.  Fork of SDDM, native KDE integration.
#   none  — TTY login.  User launches their session manually.
#
# The "auto" value (default) resolves to the canonical DM for each profile,
# falling back to "none" for profiles that don't ship one.

VALID_DMS: frozenset[str] = frozenset({"gdm", "sddm", "plm", "none"})

# Canonical DM for each profile (used when dm="auto")
_PROFILE_DEFAULT_DM: dict[str, str] = {
    "gnome": "gdm",
    "kde": "plm",
    "hyprland": "sddm",
    "niri": "sddm",
}

# Pacman package for each DM (installed by pacstrap when needed)
_DM_PACKAGE: dict[str, str] = {
    "gdm": "gdm",
    "sddm": "sddm",
    "plm": "plasma-login-manager",
}

# systemd service unit for each DM (used by configure.sh)
_DM_SERVICE: dict[str, str] = {
    "gdm": "gdm",
    "sddm": "sddm",
    "plm": "plasmalogin",
}


def dm_package(dm: str) -> str:
    """Return the pacman package name for a display manager."""
    return _DM_PACKAGE[dm]


def dm_service(dm: str) -> str:
    """Return the systemd service name (without .service) for a display manager."""
    return _DM_SERVICE[dm]


def resolve_dm(profile: str, dm_choice: str = "auto") -> str:
    """Resolve the display manager for a profile + user choice.

    Args:
        profile: Desktop profile name.
        dm_choice: 'gdm', 'sddm', 'plasmalogin', 'none', or 'auto'.

    Returns:
        The resolved DM name.
    """
    if dm_choice == "auto":
        return _PROFILE_DEFAULT_DM.get(profile, "none")
    if dm_choice not in VALID_DMS:
        raise ValueError(
            f"Unknown display manager: {dm_choice!r}. "
            f"Valid options: {sorted(VALID_DMS)} + 'auto'"
        )
    return dm_choice


# ---------------------------------------------------------------------------
# Legacy mapping (kept for backward compat — maps profile → default DM)
# ---------------------------------------------------------------------------

PROFILE_DM: dict[str, str] = dict(_PROFILE_DEFAULT_DM)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

VALID_PROFILES: frozenset[str] = frozenset(PROFILE_PACKAGES.keys())


def is_valid_profile(profile: str) -> bool:
    """Return True if *profile* is a known desktop profile name."""
    return profile in VALID_PROFILES


def packages_for(profile: str) -> list[str]:
    """Return the package list for *profile*, or raise ValueError."""
    if profile not in PROFILE_PACKAGES:
        raise ValueError(
            f"Unknown desktop profile: {profile!r}. "
            f"Valid profiles: {sorted(VALID_PROFILES)}"
        )
    return list(PROFILE_PACKAGES[profile])


def display_manager_for(profile: str) -> str:
    """Return the display manager service name for *profile*, or ''."""
    return PROFILE_DM.get(profile, "")
