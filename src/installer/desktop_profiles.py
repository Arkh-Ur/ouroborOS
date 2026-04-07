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
# Display managers per profile
# ---------------------------------------------------------------------------
#
# Profiles not listed here leave login on tty — the user launches their
# session manually (e.g. `Hyprland`, `niri-session`). This is intentional
# for minimalist profiles; GNOME and KDE get their canonical DMs because
# running them without one is pointlessly painful.

PROFILE_DM: dict[str, str] = {
    "gnome": "gdm",
    "kde": "sddm",
}

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
