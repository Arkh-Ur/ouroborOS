# ouroborOS

[![Build ISO](https://github.com/Arkhur-Vo/ouroborOS/actions/workflows/build.yml/badge.svg)](https://github.com/Arkhur-Vo/ouroborOS/actions/workflows/build.yml)
[![Test Suite](https://github.com/Arkhur-Vo/ouroborOS/actions/workflows/test.yml/badge.svg)](https://github.com/Arkhur-Vo/ouroborOS/actions/workflows/test.yml)
[![Lint](https://github.com/Arkhur-Vo/ouroborOS/actions/workflows/lint.yml/badge.svg)](https://github.com/Arkhur-Vo/ouroborOS/actions/workflows/lint.yml)

An ArchLinux-based Linux distribution with an **immutable root filesystem**, a fully **systemd-native** stack, and a built-in **snapshot-based upgrade system**.

> **Status:** v0.1.0 — early release. Core functionality complete and tested. See [Known Limitations](#known-limitations).

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

Download the latest ISO from the [Releases page](https://github.com/Arkhur-Vo/ouroborOS/releases).

Verify the checksum:

```bash
sha256sum -c ouroborOS-SHA256SUMS.txt
```

### Build from source

```bash
git clone https://github.com/Arkhur-Vo/ouroborOS.git
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

The root filesystem is read-only. Use `ouroboros-upgrade` instead of `pacman` directly — it creates a pre-upgrade snapshot and remounts the root read-write before calling pacman:

```bash
# Install or update packages (snapshot created automatically before changes)
sudo ouroboros-upgrade -S neovim tmux

# Full system upgrade
sudo ouroboros-upgrade -Syu

# Roll back: reboot and select the pre-upgrade snapshot from the boot menu
```

---

## Rolling back

Every upgrade creates a timestamped Btrfs snapshot with a matching boot entry. To roll back:

1. Reboot the machine.
2. At the systemd-boot menu, select `ouroborOS snapshot (YYYY-MM-DDTHHMMSS)`.
3. The system boots into the read-only snapshot — your previous state, intact.

---

## Key Design Constraints

- **UEFI only** — no GRUB, no Legacy BIOS
- **Read-only root** — `/etc`, `/var`, `/home` are writable subvolumes; `/` is not
- **No NetworkManager** — systemd-networkd + iwd only
- **No swap partition** — zram swap at boot
- **UUID references** — never `/dev/sdX` in fstab

---

## Known Limitations

| Limitation | v0.1 status |
|-----------|-------------|
| UEFI only | By design — no plans to change |
| x86_64 only | ARM/aarch64 deferred |
| No GUI installer | TUI + unattended YAML only |
| No AUR helper | Use `makepkg` manually |
| No Secure Boot | TPM2/MOK deferred to v0.2 |
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

## License

To be defined.
