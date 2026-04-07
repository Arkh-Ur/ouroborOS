# Project Origin — ouroborOS

**Date:** 2026-03-26
**Status:** Project initialization

---

## Project Description

**ouroborOS** is a Linux distribution based on **ArchLinux**, designed with the following core tenets:

- **Immutability**: The root filesystem is read-only. System state is predictable and reproducible.
- **systemd-native**: The full systemd ecosystem (systemd-boot, systemd-networkd, systemd-resolved, systemd-homed, systemd-repart) is used instead of traditional tools.
- **Rolling release**: Inherits ArchLinux's rolling release model. Always up-to-date packages.
- **Minimal bloat**: No desktop environment pre-installed. No unnecessary daemons. Every component earns its place.
- **Self-renewal**: Named after the ouroboros — the serpent consuming its own tail — representing continuous, atomic self-improvement and renewal.

---

## Naming

The name **ouroborOS** blends:
- **Ouroboros** — the ancient symbol of eternal cyclical renewal (a serpent eating its own tail)
- **OS** — Operating System

The capital `OS` at the end is intentional, distinguishing the name visually.

---

## Target Audience

- Linux power users who want an immutable, reproducible desktop/workstation system
- Developers who need a clean, fast, minimal base
- System administrators who want declarative, auditable system state
- Users interested in immutable Linux without switching away from the Arch ecosystem

---

## Relationship to Existing Projects

| Project | Relationship |
|---------|-------------|
| ArchLinux | Base: packages, pacman, rolling release |
| EndeavourOS | Inspiration: Arch-based installer UX |
| Fedora Silverblue | Inspiration: immutable OS design |
| NixOS | Inspiration: declarative system configuration |
| systemd | Core infrastructure: full ecosystem adoption |

ouroborOS is **not** a fork of any of these. It is a clean-room ArchLinux derivative using archiso as its build foundation.

---

## Initial Goals (v0.1)

1. Bootable live ISO with a working TUI installer
2. Immutable root filesystem via Btrfs subvolumes
3. systemd-boot as the only bootloader
4. Full systemd networking stack (no NetworkManager)
5. Post-install baseline snapshot
6. Unattended install via YAML config

---

## Out of Scope (v0.1)

- GUI installer
- Desktop environment or window manager
- AUR helper integration
- Custom kernel patches
- Secure Boot support (planned for later)
