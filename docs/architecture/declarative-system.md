# Declarative System Manifest — system.yaml

## Overview

`/etc/ouroboros/system.yaml` is the declarative manifest for the installed system. It is written by the installer at the end of the `FINISH` state and updated by `our-pac` when packages are explicitly installed or removed.

It acts as the source of truth for:
- `ouroboros-health` — verifying system state matches expectations
- `ouroboros-reinstall` — reproducing the installation from scratch
- `ouroboros-rebase` — OTA channel migration
- `our-pac` — tracking user-installed packages separately from base packages

---

## Schema

```yaml
version: "0.5.4"          # Manifest format version
channel: "stable"         # OTA channel: stable | edge
channel_url: "https://raw.githubusercontent.com/Arkh-Ur/ouroborOS/main/channels/stable.yaml"
installed: "2025-06-01T12:00:00Z"

system:
  hostname: ouroboros
  locale: en_US.UTF-8
  timezone: America/Argentina/Buenos_Aires
  desktop:
    profile: hyprland      # minimal | hyprland | niri | gnome | kde | cosmic
    dm: sddm               # gdm | sddm | plm | greetd | none
  shell: /bin/bash

base_packages:             # All packages installed by installer (pacstrap + profile)
  - base
  - linux-zen
  - networkmanager
  # ...sorted list of all base packages...

user_packages: []          # Packages explicitly added by user via our-pac -S
aur_packages: []           # AUR packages installed via our-aur (future use)

users:
  - username: admin
    real_name: "Administrator"
    groups: [wheel, audio, video, input]
    shell: /bin/bash
    homed_storage: subvolume   # subvolume | luks | directory | classic

security:
  secure_boot: false
  tpm2_unlock: false
  fido2_pam: false

disk:
  device: /dev/sda
  use_luks: false
  btrfs_label: ouroborOS
  swap_type: zram
```

---

## How It Is Written

### At install time (`FINISH` state)

The installer calls `InstallerConfig.to_system_yaml()` to generate the manifest and writes it to `/etc/ouroboros/system.yaml` on the installed target. This happens after all packages are installed and the system is configured.

`base_packages` is populated from `InstallerConfig.installed_packages`, which captures the output of `pacman -Qq` inside the chroot immediately after `pacstrap` + profile installation completes.

### After explicit package installs (`our-pac -S`)

`our-pac` calls `update_system_yaml_packages "add" <pkg>` after a successful `pacman -S`. The package is appended to `user_packages` (sorted). This distinguishes user-chosen packages from the base set.

### After explicit package removes (`our-pac -R`)

`our-pac` calls `update_system_yaml_packages "remove" <pkg>`. The package is removed from `user_packages`.

### What is NOT updated automatically

- `-Syu` upgrades — no `user_packages` change (packages already present)
- `our-aur` installs — `aur_packages` is reserved but not yet auto-populated
- Flatpak installs — not tracked in system.yaml (Flatpak manages its own state)

---

## base_packages vs user_packages

| List | What it contains | Updated by |
|------|-----------------|------------|
| `base_packages` | Everything installed by `pacstrap` + desktop profile | Installer (once) |
| `user_packages` | Packages explicitly added by the user after install | `our-pac -S` / `-R` |

This split allows `ouroboros-health` to distinguish "expected system state" from "user customization" and enables `ouroboros-reinstall` to reproduce the installation then replay user packages.

---

## OTA Channels

The `channel` and `channel_url` fields drive the OTA update mechanism:

```yaml
# channels/stable.yaml (in the public repo)
version: "0.5.7"
iso_url: "https://github.com/Arkh-Ur/ouroborOS/releases/download/v0.5.7/ouroborOS-v0.5.7.iso"
iso_sha256: "..."
```

`ouroboros-rebase` compares the running version against the channel's published version. If an update is available, it downloads the ISO, extracts the root tarball, and rebuilds `@` via snapshot + promote.

---

## File Location

| Path | Purpose |
|------|---------|
| `/etc/ouroboros/system.yaml` | The live manifest (on `@etc`, always writable) |
| `templates/install-config.yaml` | User-facing install config template (separate schema) |
| `src/installer/config.py` | `to_system_yaml()` — manifest generator |
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-pac` | `update_system_yaml_packages()` |

---

## Constraints

- `system.yaml` lives in `/etc/ouroboros/` on the `@etc` subvolume — always writable, not part of the immutable `@`
- Rolling back `@` via `our-rollback promote` does NOT revert `system.yaml` (it is on `@etc`)
- The manifest is not validated at runtime — `ouroboros-health` reads it but does not enforce it
- `aur_packages` is reserved in the schema but not yet auto-populated by `our-aur`
