# ouroborOS

[![Build ISO](https://github.com/Arkh-Ur/ouroborOS/actions/workflows/build.yml/badge.svg)](https://github.com/Arkh-Ur/ouroborOS/actions/workflows/build.yml)
[![Test Suite](https://github.com/Arkh-Ur/ouroborOS/actions/workflows/test.yml/badge.svg)](https://github.com/Arkh-Ur/ouroborOS/actions/workflows/test.yml)
[![Lint](https://github.com/Arkh-Ur/ouroborOS/actions/workflows/lint.yml/badge.svg)](https://github.com/Arkh-Ur/ouroborOS/actions/workflows/lint.yml)

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/Y8Y61XEME9)

An ArchLinux-based Linux distribution with an **immutable root filesystem**, a fully **systemd-native** stack, and a built-in **snapshot-based upgrade system**. Includes `our-aur` (containerized AUR helper) and `our-flat` (Flatpak wrapper).

> **Status:** v0.4.0 — Phase 4 complete. AUR helper and Flatpak wrapper added. See [Known Limitations](#known-limitations).

---

## What makes ouroborOS different?

| Feature | ouroborOS | Typical Arch |
|---------|-----------|--------------|
| Root filesystem | Read-only (Btrfs `@` subvolume) | Read-write |
| Upgrades | Atomic snapshot → upgrade → rollback | In-place |
| Bootloader | systemd-boot only | Usually GRUB |
| Network | systemd-networkd + iwd | NetworkManager |
| Swap | zram (no swap partition) | Swap partition |
| Installer | TUI state machine + unattended YAML | Manual |

---

## Quick Start

### Requirements

- **UEFI** firmware (no Legacy BIOS)
- **x86_64** CPU (Intel or AMD — microcode auto-detected)
- 2 GB RAM minimum, 20 GB disk
- USB drive ≥ 2 GB for flashing

### Download

Download the latest ISO from the [Releases page](https://github.com/Arkh-Ur/ouroborOS/releases).

Verify the checksum:

```bash
sha256sum -c ouroborOS-SHA256SUMS.txt
```

### Build from source

```bash
git clone https://github.com/Arkh-Ur/ouroborOS.git
cd ouroborOS

# Install build dependencies (Arch Linux host required)
bash src/scripts/setup-dev-env.sh

# Build the ISO
sudo bash src/scripts/build-iso.sh --clean
```

### Flash to USB

```bash
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso
```

### Test in QEMU (UEFI)

```bash
qemu-system-x86_64 -enable-kvm -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -cdrom out/ouroborOS-*.iso -boot d
```

---

## Installation

Boot the ISO and the installer starts automatically. See the [User Guide](docs/user-guide.md) for the full walkthrough.

**Interactive mode** (TUI):
```bash
ouroborOS-installer
```

**Unattended mode** (YAML config):
```bash
ouroborOS-installer --config /path/to/config.yaml
```

A ready-to-edit config template is at [`templates/install-config.yaml`](templates/install-config.yaml).

---

## Upgrading packages

The root filesystem is read-only. Use `our-pac` instead of `pacman` directly — it creates a pre-upgrade snapshot and remounts the root read-write before calling pacman:

```bash
# Install or update packages (snapshot created automatically before changes)
sudo our-pac -S neovim tmux

# Full system upgrade
sudo our-pac -Syu

# Roll back: reboot and select the pre-upgrade snapshot from the boot menu
```

---

## Rolling back

Every upgrade creates a timestamped Btrfs snapshot with a matching boot entry. To roll back:

1. Reboot the machine.
2. At the systemd-boot menu, select `ouroborOS snapshot (YYYY-MM-DDTHHMMSS)`.
3. The system boots into the read-only snapshot — your previous state, intact.

---

## AUR packages

Use `our-aur` to install packages from the Arch User Repository without touching the immutable root. Builds run inside ephemeral `systemd-nspawn` containers and install via `systemd-sysext`:

```bash
# Search AUR
our-aur -Ss hyprlock

# Install from AUR
our-aur -S quickshell

# Update installed AUR packages
our-aur -Su
```

---

## Flatpak applications

Use `our-flat` for Flatpak applications with a pacman-style interface:

```bash
# Add Flathub remote (opt-in)
sudo our-flat remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Install an app
sudo our-flat -S com.spotify.Client

# Update all Flatpak apps
sudo our-flat -Su
```

---

## Key Design Constraints

- **UEFI only** — no GRUB, no Legacy BIOS
- **Read-only root** — `/etc`, `/var`, `/home` are writable subvolumes; `/` is not
- **No NetworkManager** — systemd-networkd + iwd only
- **No swap partition** — zram swap at boot
- **UUID references** — never `/dev/sdX` in fstab

---

## Known Limitations

| Limitation | Status |
|-----------|--------|
| UEFI only | By design — no plans to change |
| x86_64 only | By design — no plans to add ARM |
| No GUI installer | TUI + unattended YAML only |
| No Secure Boot by default | TPM2/MOK deferred to Phase 5 |
| English only | Multi-language deferred |

---

## Project Structure

```
ouroborOS/
├── src/
│   ├── installer/           # Python FSM installer + Bash ops
│   │   ├── state_machine.py # Core FSM
│   │   ├── tui.py           # Rich TUI + whiptail fallback
│   │   ├── config.py        # YAML config loader + validation
│   │   └── ops/             # disk.sh · configure.sh · snapshot.sh
│   ├── scripts/             # build-iso.sh · flash-usb.sh · setup-dev-env.sh
│   └── ouroborOS-profile/   # archiso profile (packages, airootfs, efiboot)
├── docs/                    # Architecture, user guide, developer guide
├── templates/               # install-config.yaml template
├── tests/                   # Docker-based CI test suite
└── .github/workflows/       # build.yml · test.yml · lint.yml
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/user-guide.md) | Installation, upgrades, rollback, WiFi |
| [Developer Guide](docs/developer-guide.md) | Build, test, contribute |
| [Architecture Overview](docs/architecture/overview.md) | System design and layer diagram |
| [Immutability Strategy](docs/architecture/immutability-strategy.md) | Btrfs layout and snapshot flow |
| [Installer Phases](docs/architecture/installer-phases.md) | FSM states and transitions |
| [Configuration Format](docs/installer/configuration-format.md) | YAML schema reference |

---

## Contributing

1. Fork the repository and create a `feature/your-feature` branch from `dev`.
2. Read the [Developer Guide](docs/developer-guide.md) for setup and conventions.
3. Open a pull request against `dev`.

All shell scripts must pass `shellcheck`. Python code must pass `ruff`. Tests must pass.

---

## Support the project

ouroborOS is an independent open-source project. If it saves you time or you want to see it grow, consider supporting it on Ko-Fi:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/Y8Y61XEME9)

---

## License

To be defined.
