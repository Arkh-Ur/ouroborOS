<p align="center">
  <img src="assets/ouroboros-logo.svg" alt="ouroborOS" width="480">
</p>

<p align="center">
  <em>Modern immutable Arch Linux</em>
</p>

<p align="center">
  <a href="https://github.com/Arkh-Ur/ouroborOS/releases/latest"><img src="https://img.shields.io/github/v/release/Arkh-Ur/ouroborOS?label=latest&color=067B3B" alt="Latest Release"></a>
  <img src="https://img.shields.io/github/release-date/Arkh-Ur/ouroborOS?label=published&color=419E6E" alt="Release Date">
  <br>
  <img src="https://img.shields.io/badge/platform-x86__64-083F28?logo=linux&logoColor=white" alt="Platform">
  <img src="https://img.shields.io/badge/based_on-Arch_Linux-1793D1?logo=arch-linux&logoColor=white" alt="Arch Linux">
  <img src="https://img.shields.io/github/license/Arkh-Ur/ouroborOS?color=067B3B" alt="License">
</p>

<p align="center">
  <a href="https://github.com/Arkh-Ur/ouroborOS/actions/workflows/build.yml"><img src="https://github.com/Arkh-Ur/ouroborOS/actions/workflows/build.yml/badge.svg" alt="Build ISO"></a>
  <a href="https://github.com/Arkh-Ur/ouroborOS/actions/workflows/test.yml"><img src="https://github.com/Arkh-Ur/ouroborOS/actions/workflows/test.yml/badge.svg" alt="Test Suite"></a>
  <a href="https://github.com/Arkh-Ur/ouroborOS/actions/workflows/lint.yml"><img src="https://github.com/Arkh-Ur/ouroborOS/actions/workflows/lint.yml/badge.svg" alt="Lint"></a>
</p>

<p align="center">
  <a href="https://ko-fi.com/Y8Y61XEME9"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="ko-fi"></a>
</p>

<hr>

An ArchLinux-based Linux distribution with an **immutable root filesystem**, a fully **systemd-native** stack, and a built-in **snapshot-based upgrade system**. Includes `our-aur` (containerized AUR helper) and `our-flat` (Flatpak wrapper).

> **Status:** v0.5.2 — Phase 5 in progress. OTA update daemon (`ouroboros-update`), offline install cache, and declarative `system.yaml` manifest. See [docs.ouroboros.la](https://arkh-ur.github.io/ouroborOS/) for full documentation.

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
| AUR packages | Containerized via systemd-nspawn | Manual makepkg |
| Flatpak | Built-in `our-flat` wrapper | Manual setup |
| Security | Secure Boot + FIDO2 + LUKS + TPM2 | Manual setup |
| WiFi/Bluetooth | `our-wifi` + `our-bluetooth` wrappers | Manual iwctl/bt |

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

## OTA updates

`ouroboros-update` checks daily for new versions via the stable channel manifest:

```bash
# Check manually
sudo ouroboros-update --check

# See current update status
ouroboros-update --status

# Apply an available update
sudo ouroboros-rebase --from-channel
```

The timer runs automatically after install. When an update is available, a flag is written
to `/var/lib/ouroborOS/update-available`.

---

## Offline installation

The default ISO requires internet during install. For air-gapped environments (servers, labs, secure facilities), build an offline ISO locally with a pre-downloaded package cache:

```bash
# Requires an Arch Linux host with ~20 min and ~5 GB free disk
sudo bash src/scripts/build-iso.sh --with-cache
```

The resulting ISO (~3.8 GB) includes all packages needed for a full install with no internet. The installer detects the cache automatically.

> **Why isn't the offline ISO on the Releases page?** GitHub Free limits release assets to 2 GB. The offline ISO exceeds that, so it must be built locally.

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
| Secure Boot | Supported via `sbctl` — opt-in during install |
| Multi-language | Installer: en, es_CL, de_DE · Wiki: en, es |

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
├── wiki/                    # Astro + Starlight docs site (docs.ouroboros.la)
├── docs/                    # Architecture, user guide, developer guide
├── templates/               # install-config.yaml template
├── tests/                   # Docker-based CI test suite
└── .github/workflows/       # build.yml · test.yml · lint.yml · wiki-deploy.yml
```

---

## Documentation

**Full documentation**: [docs.ouroboros.la](https://arkh-ur.github.io/ouroborOS/)

| Document | Description |
|----------|-------------|
| [Architecture Overview](docs/architecture/overview.md) | System design and layer diagram |
| [Immutability Strategy](docs/architecture/immutability-strategy.md) | Btrfs layout and snapshot flow |
| [Installer Phases](docs/architecture/installer-phases.md) | FSM states and transitions |
| [Configuration Format](docs/installer/configuration-format.md) | YAML schema reference |
| [systemd-homed](docs/architecture/systemd-homed.md) | Home directory management |

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

<p align="center">
  <a href="https://github.com/Arkh-Ur">
    <img src="assets/arkh-ur-logo.svg" alt="Arkh-Ur" width="200">
  </a>
</p>

## License

This project uses a dual-license approach:

| Component | License |
|-----------|---------|
| Code (installer, scripts, tools) | [GNU GPL v3](LICENSE) |
| Documentation & Wiki | [CC BY-SA 4.0](wiki/LICENSE) |
