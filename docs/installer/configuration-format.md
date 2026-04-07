# Installer Configuration Format

## Overview

ouroborOS supports **unattended (automated) installation** via a YAML configuration file. When the installer detects a config file at boot, it runs without interactive prompts.

This is useful for:
- Reproducible deployments
- Testing in CI/CD pipelines
- Enterprise provisioning

---

## Config File Location

The installer searches for a config file in this order:

1. Kernel cmdline parameter: `ouroborOS.config=/path/to/config.yaml`
2. `/tmp/ouroborOS-config.yaml` (e.g. injected via cloud-init or live ISO)
3. `/run/ouroborOS-config.yaml`
4. First `*.yaml` on USB drives under `/run/media/` matching filenames: `ouroborOS-config.yaml`, `ouroborOS.yaml`, or `installer-config.yaml`

---

## Full Schema

```yaml
# ouroborOS Installer Configuration
# All fields with defaults are optional.

# ─── DISK ──────────────────────────────────────────────────────────────────────
disk:
  device: "/dev/sda"             # Target disk device path (required)
  use_luks: false                # Enable LUKS2 full-disk encryption
  btrfs_label: "ouroborOS"       # Btrfs filesystem label
  swap_type: "zram"              # "zram" or "none" (no swap partition)

# ─── LOCALE ────────────────────────────────────────────────────────────────────
locale:
  locale: "en_US.UTF-8"          # Locale name (see /etc/locale.gen)
  keymap: "us"                   # Keyboard layout (see localectl list-keymaps)
  timezone: "America/New_York"   # TZ database name (required)

# ─── NETWORK ───────────────────────────────────────────────────────────────────
network:
  hostname: "ouroboros"          # System hostname (required)
  enable_networkd: true          # Enable systemd-networkd
  enable_iwd: true               # Enable iwd (WiFi)
  enable_resolved: true          # Enable systemd-resolved

# ─── USER ──────────────────────────────────────────────────────────────────────
user:
  username: "alice"              # Primary user username (required)
  password: "changeme"           # Plaintext password (auto-hashed to SHA-512)
  # password_hash: "$6$rounds=..."  # Or provide a pre-computed SHA-512 hash
  groups:                        # Groups for the primary user
    - wheel
    - audio
    - video
    - input
  shell: "/bin/bash"             # Login shell

# ─── EXTRA PACKAGES ────────────────────────────────────────────────────────────
extra_packages:                  # Additional packages beyond the base set
  - neovim
  - htop
  - tmux

# ─── POST-INSTALL ACTION ──────────────────────────────────────────────────────
post_install_action: "reboot"    # "reboot" | "shutdown" | "none"
```

---

## Minimal Config Example

Minimal configuration for a typical single-user install:

```yaml
disk:
  device: /dev/vda

locale:
  timezone: Europe/Madrid

network:
  hostname: mi-ouroboros

user:
  username: usuario
  password_hash: $6$rounds=656000$...
```

---

## Generating Password Hashes

```bash
# SHA-512 hash for use in config file
openssl passwd -6 "mypassword"
# or
python3 -c "import crypt; print(crypt.crypt('mypassword', crypt.mksalt(crypt.METHOD_SHA512)))"
```

Alternatively, use `password` (plaintext) in the config file — the installer auto-hashes it via `openssl passwd -6 -stdin` at load time.

---

## Schema Validation

The installer validates the config file before proceeding:

```bash
ouroborOS-installer --validate-config /path/to/config.yaml
```

Validation checks:
- Required top-level sections present (`disk`, `locale`, `network`, `user`)
- `disk.device` is an absolute `/dev/` path pointing to a whole disk (not a partition)
- `locale.timezone` matches a valid timezone format
- `network.hostname` is a valid RFC 1123 hostname
- `user.username` is a valid POSIX username
- `user` section includes either `password_hash` or `password`
- `post_install_action` is one of: `reboot`, `shutdown`, `none`

---

## Triggering Unattended Install

### Via kernel cmdline (ISO/PXE boot)
```
ouroborOS.config=http://server/config.yaml
ouroborOS.config=/run/archiso/bootmnt/ouroborOS-config.yaml
```

### Via USB drive
Place `ouroborOS-config.yaml` at the root of a FAT32 USB drive alongside the ISO. The live environment will auto-detect it.
