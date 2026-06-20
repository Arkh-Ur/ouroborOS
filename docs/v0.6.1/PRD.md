# PRD — ouroborOS Dotfiles/Config Packs

**Version:** v0.6.1
**Status:** Approved
**Date:** 2026-06-07
**Author:** ouroborOS dev team

---

## History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | Initial draft — post-v0.6.0 bridge feature |

---

## Problem Statement

ouroborOS delivers a fully functional, immutable Arch Linux base. After installation, the system is
technically complete but visually neutral — the user has a working Hyprland or Niri compositor with
no theming, no shell overlay, no color scheme, and no desktop widgets.

Users who want a polished desktop experience face a multi-hour manual process: researching ricing
projects, following project-specific installation guides, resolving dependency chains, and adapting
instructions written for mutable systems. This process is tedious, error-prone, and outside the
scope of what most users want to invest time in.

The Linux ricing community has produced several high-quality, actively maintained dotfiles projects
that provide exactly this polish. These projects are used by hundreds of thousands of users but have
no automated integration with any installer.

---

## Proposal

Introduce **`our-dots`** — a new member of the `our-*` tool family — and a curated catalog of
7 dotfiles/ricing packs that can be installed with a single command or selected during system
installation.

The catalog ships with the ISO and is extensible: users can add third-party repositories of pack
manifests, keeping the system open and community-driven.

Each pack in the catalog includes:
- Full description of what it provides and who created it
- Official links and attribution to the original authors
- Compatibility information for ouroborOS's immutable root
- Stable and git/development channel support where available

---

## Goals

1. **Reduce time-to-riced** from hours to minutes for users who want a polished desktop
2. **Respect immutability** — all installations go through `our-pac` and `our-aur`, never bypassing the RO/RW lifecycle
3. **Respect creator credit** — every pack installation acknowledges and links to the original author
4. **Be non-opinionated** — ouroborOS does not impose a look; the user chooses their pack (or none)
5. **Be extensible** — third-party repositories can add new packs without modifying the ISO

---

## Non-Goals

- ouroborOS does not become a distro with a default aesthetic
- `our-dots` does not modify existing Hyprland/Niri configs without consent
- ouroborOS does not maintain or fork upstream dotfiles projects
- No "ouroborOS official theme" — we curate, we do not create

---

## Target Users

| Persona | Description | Expected Usage |
|---------|-------------|----------------|
| New user | Installed ouroborOS, wants a polished desktop without manual research | `our-dots list` → `our-dots -S caelestia` |
| Power user | Knows what rice they want, wants automated install on immutable system | Unattended install with `dots_pack.pack: noctalia` |
| Developer | Wants to distribute their own dotfiles via ouroborOS | `our-dots repo-add` → custom manifest |

---

## Success Metrics

- A user can go from a freshly installed ouroborOS (any Hyprland/Niri profile) to a fully themed
  desktop in under 10 minutes, including package installation time
- All 7 curated packs can be installed on ouroborOS without manually modifying the root filesystem
- `our-dots -S <pack>` on a CRITICAL pack clearly explains what will happen before any change is made
- The catalog is extensible: adding a new pack requires only a new YAML manifest file

---

## The 7 Curated Packs

### Noctalia v4
**Creator:** noctalia-dev team
**Homepage:** https://github.com/noctalia-dev/noctalia-shell
**Docs:** https://docs.noctalia.dev/v4/getting-started/installation/#arch
**Target DE:** Niri, Hyprland
**Channels:** stable (`noctalia-shell` AUR) / git (`noctalia-shell-git` AUR)

A Quickshell-based desktop shell layer for Niri and Hyprland compositors. Features a modular
design covering the bar, notifications, clipboard history, night light, and calendar. Noctalia has
the broadest distribution support of any shell in this catalog — available in official repos for
Fedora, openSUSE, and Void, and via AUR for Arch. The explicit stable/git split makes it one of
the safest choices for an immutable system.

---

### Caelestia Shell
**Creator:** soramane
**Homepage:** https://github.com/caelestia-dots/shell
**Target DE:** Hyprland
**Channels:** stable (`caelestia-shell` AUR) / git (`caelestia-shell-git` AUR)

The highest-profile Quickshell shell in this catalog (9,800+ GitHub stars), designed as a full
Waybar replacement for Hyprland. Caelestia provides a bar, dashboard, launcher, lock screen, and
system utilities, built in QML and C++. The AUR package installs like a proper compiled application.
20+ versioned releases on GitHub, with clear stable/git separation.

*Support the creator: https://ko-fi.com/soramane*

---

### ML4W Dotfiles
**Creator:** Stephan Raabe
**Homepage:** https://ml4w.com/dotfiles-installer/getting-started/install
**Repo:** https://github.com/mylinuxforwork/ml4w-dotfiles-installer
**Target DE:** Hyprland
**Channels:** stable (0.2.3)

ML4W is a Hyprland-focused dotfiles installer framework by Stephan Raabe, well-known in the Linux
ricing community for his YouTube tutorials on desktop customization. Rather than imposing a single
look, it provides a structured installer that handles profile deployment, making it easier to
maintain and update dotfiles across systems. Pacman and AUR are explicitly supported.

---

### Ambxst
**Creator:** Axenide
**Homepage:** https://axeni.de/es/ambxst/
**Repo:** https://github.com/Axenide/Ambxst
**Target DE:** Hyprland
**Channels:** rolling

Ambxst is a Quickshell-based Hyprland shell with the explicit design goal of being non-intrusive:
it sources into your existing Hyprland config rather than replacing it, and all runtime data lives
in `~/.local/share/ambxst` and `~/.config/ambxst`. Feature set is the most comprehensive of the
shell-layer projects in this catalog: app launcher, clipboard manager, notes, wallpaper manager,
emoji picker, tmux session manager, system monitor, media control, notifications, Wi-Fi/Bluetooth
managers, audio mixer, EasyEffects integration, screen capture/recording, color picker, OCR, QR
scanner, webcam mirror, game mode, night mode, power profiles, AI assistant, weather, calendar,
power menu, and workspace management.

*Credits also due to: outfoxxed (Quickshell), end-4, soramane*

---

### DankMaterialShell
**Creator:** AvengeMedia
**Homepage:** https://danklinux.com/docs/dankinstall
**Repo:** https://github.com/AvengeMedia/DankMaterialShell
**Target DE:** Niri, Hyprland
**Channels:** versioned (1.4)

DankMaterialShell is a Material You-themed Wayland shell supporting both Niri and Hyprland
compositors, with automatic color generation from wallpapers via matugen. Includes Ghostty terminal,
Quickshell framework, dgop (system monitor), dsearch (filesystem search), and cliphist (clipboard
history). One of the few projects in this catalog with explicit first-class Niri support alongside
Hyprland.

---

### illogical-impulse
**Creator:** end-4
**Homepage:** https://ii.clsty.link/en/ii-qs/01setup/
**Repo:** https://github.com/end-4/dots-hyprland
**Target DE:** Hyprland
**Channels:** rolling (git)
**Compatibility:** ⚠ CRITICAL — requires `/etc/pacman.conf` modification

illogical-impulse is end-4's popular Hyprland rice built on Quickshell, widely recognized for its
polished aesthetic and active community. The setup script handles the full dependency chain. On
ouroborOS, installation requires temporarily remounting `/` as writable to add an `IgnoreGroup`
entry to `/etc/pacman.conf` — `our-dots` will explicitly confirm this action before proceeding.

---

### Omarchy
**Creator:** DHH (David Heinemeier Hansson) / 37signals
**Homepage:** https://learn.omacom.io/2/the-omarchy-manual/96/manual-installation
**Repo:** https://github.com/basecamp/omarchy
**Target DE:** Hyprland
**Channels:** rolling
**Compatibility:** ⚠ CRITICAL — full system configuration takeover

Omarchy is DHH's opinionated "omakase" Arch Linux configuration — you get his curated stack without
choices. It is the most comprehensive and opinionated of the seven projects, functioning more like a
distribution than a dotfiles pack: it configures the entire system from bootloader preferences to
editor setup. On ouroborOS, this pack requires the most explicit confirmation, as it makes
system-wide configuration changes. The result is a fully configured Hyprland + Neovim + Tmux
environment with 19 built-in themes.
