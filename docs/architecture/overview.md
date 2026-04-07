# ouroborOS — Architecture Overview

## Philosophy

ouroborOS takes its name from the ouroboros, the ancient symbol of a serpent consuming its own tail — representing **continuous self-renewal, self-containment, and cyclical evolution**. These principles guide every architectural decision:

- **Immutability**: The root filesystem is read-only. Changes are deliberate, atomic, and reversible.
- **Self-renewal**: Updates are atomic snapshots, not in-place mutations. Rollback is always one command away.
- **Minimal bloat**: Only what is needed is included. Every component must justify its presence.
- **systemd-native**: The entire user-space lifecycle — boot, networking, storage, identity — is managed through the systemd ecosystem.
- **ArchLinux base**: Rolling release model, bleeding-edge packages, pacman for package management.

---

## System Layer Diagram

```mermaid
graph TB
    subgraph UserSpace["🧑 User Space"]
        Apps["User Applications\nFlatpak / pacman packages"]
        Home["/home\n@home subvolume"]
    end

    subgraph Mutable["✏️ Writable System Layer  (Btrfs subvolumes)"]
        Var["/var\n@var subvolume · rw"]
        Etc["/etc\n@etc subvolume · rw"]
        Tmp["/tmp\ntmpfs · cleared on reboot"]
    end

    subgraph ImmutableRoot["🔒 Read-Only Immutable Root  /"]
        Root["Btrfs @ subvolume\nmounted with ro,noatime,compress=zstd"]
        Snap["/.snapshots\n@snapshots · rollback targets"]
    end

    subgraph BootLayer["⚡ Boot Layer"]
        UEFI["UEFI Firmware"]
        SDBoot["systemd-boot\n/boot/loader/entries/*.conf"]
        Kernel["linux-zen + initramfs\nmkinitcpio · btrfs hook"]
    end

    Apps --> Home
    Home --> Var & Etc & Tmp
    Var & Etc --> Root
    Root --> Snap
    UEFI --> SDBoot --> Kernel --> Root
```

---

## Component Relationships

```mermaid
graph LR
    archiso["archiso\nISO build"] -->|produces| ISO["ouroborOS.iso"]
    ISO -->|boots| Live["Live Environment\ntty1 autologin"]
    Live -->|launches| Installer["TUI Installer\nPython + Bash"]

    Installer -->|partitions| SGDISK["sgdisk\nGPT layout"]
    Installer -->|formats| BTRFS["Btrfs\nsubvolumes"]
    Installer -->|installs| PACSTRAP["pacstrap\nbase packages"]
    Installer -->|configures| ARCHCHROOT["arch-chroot\nchroot operations"]

    ARCHCHROOT -->|bootloader| SDBOOT["systemd-boot\nbootctl install"]
    ARCHCHROOT -->|network| NETWORKD["systemd-networkd\n+ iwd"]
    ARCHCHROOT -->|dns| RESOLVED["systemd-resolved\nDoT + DNSSEC"]
    ARCHCHROOT -->|users| USERADD["useradd\nstandard Linux users"]
    ARCHCHROOT -->|snapshot| SNAP["Btrfs snapshot\n@snapshots/install"]

    SDBOOT -->|boot entry| RO_ROOT["/ mounted ro\nBtrfs @ subvol"]
```

---

## Core Components

| Component | Role |
|-----------|------|
| **archiso** | Live ISO build framework |
| **systemd-boot** | UEFI bootloader (replaces GRUB) |
| **Btrfs** | Filesystem with snapshots and subvolumes |
| **sgdisk** | GPT partitioning during install |
| **systemd-networkd** | Network configuration (wired + wireless) |
| **systemd-resolved** | DNS resolution with DoT support |
| **arch-chroot** | Chroot operations during installation |
| **systemd-firstboot** | First-boot configuration wizard |
| **mkinitcpio** | Initramfs generation with custom hooks |
| **systemd-repart** | *Future evaluation* — declarative partition layout |
| **systemd-homed** | *Future evaluation* — portable, encrypted home directories |

---

## Key Design Decisions

### 1. Immutability via Btrfs (not OSTree)
OSTree was evaluated but rejected due to poor pacman integration. Btrfs subvolumes + read-only root mount provides equivalent immutability with native ArchLinux tooling. See [immutability-strategy.md](./immutability-strategy.md).

### 2. systemd-boot over GRUB
GRUB adds complexity (grub.cfg, update-grub, theme management). systemd-boot is minimal, UEFI-native, and integrates with `bootctl` and kernel install hooks. Only UEFI systems are supported.

### 3. Installer written in Bash + Python
- **Bash**: Low-level operations (partitioning, mounting, pacstrap, chroot)
- **Python**: TUI logic (state machine, user input validation, config serialization)
- **Rich**: Terminal UI rendering (primary), whiptail as fallback

### 4. No NetworkManager
`systemd-networkd` + `iwd` (for WiFi) covers all networking needs without the overhead of NetworkManager.

---

## Repository Structure

```
ouroborOS/
├── CLAUDE.md                  # Claude Code project instructions
├── AGENTS.md                  # Agent knowledge base
├── IMPLEMENTATION_PLAN.md     # Phased implementation roadmap
├── README.md                  # Public project README
├── src/
│   ├── installer/             # Python FSM installer + Bash ops (core app)
│   ├── scripts/               # Build, flash, dev-env shell scripts
│   └── ouroborOS-profile/     # archiso profile (airootfs, efiboot, packages)
├── templates/                 # Default install config template for interactive mode
├── docs/                      # Architecture, build, installer documentation
├── tests/                     # Docker-based test infra + shell scripts
├── agents/                    # Agent role definitions (qa-tester, developer, etc.)
├── skills/                    # Domain skill docs (systemd, archiso, filesystem, etc.)
└── .github/workflows/         # CI workflows (lint, test, code-review, opencode)
```

---

## Related Documents

- [Immutability Strategy](./immutability-strategy.md)
- [systemd Integration](./systemd-integration.md)
- [Installer Phases](./installer-phases.md)
- [Build Process](../build/build-process.md)
- [Implementation Plan](../../IMPLEMENTATION_PLAN.md)
