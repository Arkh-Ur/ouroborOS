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
        Home["/home\nsystemd-homed · per-user LUKS encryption"]
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

    Installer -->|partitions| REPART["systemd-repart\nGPT layout"]
    Installer -->|formats| BTRFS["Btrfs\nsubvolumes"]
    Installer -->|installs| PACSTRAP["pacstrap\nbase packages"]
    Installer -->|configures| NSPAWN["systemd-nspawn\nchroot"]

    NSPAWN -->|bootloader| SDBOOT["systemd-boot\nbootctl install"]
    NSPAWN -->|network| NETWORKD["systemd-networkd\n+ iwd"]
    NSPAWN -->|dns| RESOLVED["systemd-resolved\nDoT + DNSSEC"]
    NSPAWN -->|users| HOMED["systemd-homed\nencrypted homes"]
    NSPAWN -->|snapshot| SNAP["Btrfs snapshot\n@snapshots/install"]

    SDBOOT -->|boot entry| RO_ROOT["/ mounted ro\nBtrfs @ subvol"]
```

---

## Core Components

| Component | Role |
|-----------|------|
| **archiso** | Live ISO build framework |
| **systemd-boot** | UEFI bootloader (replaces GRUB) |
| **Btrfs** | Filesystem with snapshots and subvolumes |
| **overlayfs** | Writable layer over read-only root |
| **systemd-repart** | Declarative partition layout at install time |
| **systemd-networkd** | Network configuration (wired + wireless) |
| **systemd-resolved** | DNS resolution with DoT support |
| **systemd-homed** | Portable, encrypted home directories |
| **systemd-firstboot** | First-boot configuration wizard |
| **systemd-nspawn** | Isolated chroot during installation |
| **mkinitcpio** | Initramfs generation with custom hooks |

---

## Key Design Decisions

### 1. Immutability via Btrfs (not OSTree)
OSTree was evaluated but rejected due to poor pacman integration. Btrfs subvolumes + read-only root mount provides equivalent immutability with native ArchLinux tooling. See [immutability-strategy.md](./immutability-strategy.md).

### 2. systemd-boot over GRUB
GRUB adds complexity (grub.cfg, update-grub, theme management). systemd-boot is minimal, UEFI-native, and integrates with `bootctl` and kernel install hooks. Only UEFI systems are supported.

### 3. Installer written in Bash + Python
- **Bash**: Low-level operations (partitioning, mounting, pacstrap, chroot)
- **Python**: TUI logic (state machine, user input validation, config serialization)
- **whiptail/dialog**: Terminal UI rendering

### 4. No NetworkManager
`systemd-networkd` + `iwd` (for WiFi) covers all networking needs without the overhead of NetworkManager.

---

## Repository Structure

```
ouroborOS/
├── CLAUDE.md                  # Claude Code project instructions
├── IMPLEMENTATION_PLAN.md     # Phased implementation roadmap
├── README.md                  # Public project README
├── docs/                      # Technical documentation
│   ├── architecture/          # System design decisions
│   ├── build/                 # ISO build process
│   ├── installer/             # Installer architecture
│   ├── messages/              # Project log and decisions
│   └── scripts/               # Build and setup scripts
└── skills/                    # Claude Code expert skill definitions
```

---

## Related Documents

- [Immutability Strategy](./immutability-strategy.md)
- [systemd Integration](./systemd-integration.md)
- [Installer Phases](./installer-phases.md)
- [Build Process](../build/build-process.md)
- [Implementation Plan](../../IMPLEMENTATION_PLAN.md)
