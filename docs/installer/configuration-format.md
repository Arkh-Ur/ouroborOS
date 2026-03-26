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
2. USB drive root: `/run/media/*/ouroborOS-config.yaml`
3. Live ISO root: `/ouroborOS-config.yaml`
4. `/tmp/ouroborOS-config.yaml` (written interactively during session)

---

## Full Schema

```yaml
# ouroborOS Installer Configuration
# Version: 1.0
# All fields with defaults are optional.

# ─── LOCALE ─────────────────────────────────────────────────────────────────
locale:
  language: "en_US.UTF-8"      # locale name (see /etc/locale.gen)
  keymap: "us"                  # keyboard layout (see localectl list-keymaps)
  timezone: "America/New_York"  # TZ database name (see timedatectl list-timezones)

# ─── DISK & PARTITIONS ───────────────────────────────────────────────────────
disk:
  target: "/dev/sda"            # Target disk (CAUTION: will be wiped)
  scheme: "auto"                # "auto" | "manual"
  wipe: true                    # Confirm wipe — required to be true

  # Auto scheme: ESP + Btrfs (recommended)
  auto:
    esp_size: "512M"
    swap: false                 # No swap; use zram instead
    encryption: false           # LUKS on root partition

  # Manual scheme (advanced)
  # manual:
  #   partitions:
  #     - device: "/dev/sda1"
  #       type: "esp"
  #       size: "512M"
  #       format: "vfat"
  #       mountpoint: "/boot"
  #     - device: "/dev/sda2"
  #       type: "linux"
  #       format: "btrfs"
  #       mountpoint: "/"

# ─── BTRFS SUBVOLUMES ────────────────────────────────────────────────────────
btrfs:
  subvolumes:
    root: "@"
    var: "@var"
    etc: "@etc"
    home: "@home"
    snapshots: "@snapshots"
  compression: "zstd:3"         # zstd:1–22 | lzo | zlib | none
  mountflags: "noatime"

# ─── SYSTEM ──────────────────────────────────────────────────────────────────
system:
  hostname: "ouroborOS"
  kernel: "linux-zen"           # linux | linux-zen | linux-lts | linux-hardened

# ─── USERS ───────────────────────────────────────────────────────────────────
users:
  root:
    password: ""                # Leave empty to disable root login (recommended)
    password_hash: ""           # SHA-512 hash (use `openssl passwd -6`)

  create:
    - username: "alice"
      realname: "Alice"
      groups: ["wheel", "audio", "video", "storage"]
      password_hash: "$6$rounds=..."
      shell: "/bin/bash"
      use_homed: false          # true = systemd-homed encrypted home

# ─── PACKAGES ────────────────────────────────────────────────────────────────
packages:
  extra:                        # Additional packages beyond base
    - neovim
    - htop
    - tmux
  aur: []                       # AUR packages (requires AUR helper)

# ─── NETWORK ─────────────────────────────────────────────────────────────────
network:
  manager: "systemd-networkd"   # Only option for now
  dns:
    servers: ["1.1.1.1", "9.9.9.9"]
    over_tls: true
    dnssec: true
  wifi:
    enabled: false
    ssid: ""
    passphrase: ""

# ─── BOOTLOADER ──────────────────────────────────────────────────────────────
bootloader:
  type: "systemd-boot"
  timeout: 3
  secure_boot: false

# ─── POST-INSTALL ─────────────────────────────────────────────────────────────
post_install:
  reboot: true                  # Reboot automatically after install
  scripts: []                   # Paths to custom scripts run in chroot
```

---

## Minimal Config Example

Minimal configuration for a typical single-user install:

```yaml
locale:
  language: "es_ES.UTF-8"
  keymap: "es"
  timezone: "Europe/Madrid"

disk:
  target: "/dev/vda"
  scheme: "auto"
  wipe: true

system:
  hostname: "mi-ouroboros"

users:
  root:
    password: ""
  create:
    - username: "usuario"
      password_hash: "$6$rounds=656000$..."
      groups: ["wheel", "audio", "video"]
```

---

## Generating Password Hashes

```bash
# SHA-512 hash for use in config file
openssl passwd -6 "mypassword"
# or
python3 -c "import crypt; print(crypt.crypt('mypassword', crypt.mksalt(crypt.METHOD_SHA512)))"
```

---

## Schema Validation

The installer validates the config file before proceeding:

```bash
ouroborOS-installer --validate-config /path/to/config.yaml
```

Validation checks:
- Required fields present (`disk.target`, `disk.wipe: true`)
- Disk device exists
- Password hashes are valid SHA-512 format
- Timezone is valid
- Locale is available

---

## Triggering Unattended Install

### Via kernel cmdline (ISO/PXE boot)
```
ouroborOS.config=http://server/config.yaml
ouroborOS.config=/run/archiso/bootmnt/ouroborOS-config.yaml
```

### Via USB drive
Place `ouroborOS-config.yaml` at the root of a FAT32 USB drive alongside the ISO. The live environment will auto-detect it.
