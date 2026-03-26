# CLAUDE.md — ouroborOS Project Instructions

This file provides Claude Code with persistent context about the ouroborOS project. Read this before working on any task.

---

## Project Overview

**ouroborOS** is an ArchLinux-based Linux distribution with an immutable root filesystem, built entirely around the systemd ecosystem.

- **Base:** ArchLinux (pacman, rolling release)
- **Filesystem:** Btrfs subvolumes, root mounted read-only (`ro`)
- **Bootloader:** systemd-boot only (no GRUB, UEFI required)
- **Networking:** systemd-networkd + iwd (no NetworkManager)
- **Installer:** Python state machine + whiptail TUI + Bash ops
- **Status:** Early development (v0.1 in progress)

---

## Repository Structure

```
ouroborOS/
├── CLAUDE.md                    ← You are here
├── IMPLEMENTATION_PLAN.md       ← Full phased roadmap
├── README.md                    ← Public project README
├── src/                         ← All source code
│   ├── scripts/                 ← Build and setup scripts
│   │   ├── build-iso.sh         ← Build the live ISO
│   │   ├── setup-dev-env.sh     ← Set up the dev environment
│   │   └── flash-usb.sh         ← Write ISO to USB drive
│   ├── installer/               ← Python installer
│   │   ├── config.py            ← InstallerConfig + YAML loader
│   │   ├── state_machine.py     ← FSM with checkpoints
│   │   ├── tui.py               ← whiptail TUI layer
│   │   ├── main.py              ← CLI entrypoint
│   │   ├── ops/                 ← Bash operations
│   │   │   ├── disk.sh          ← Partitioning, Btrfs, fstab
│   │   │   ├── snapshot.sh      ← Btrfs snapshot management
│   │   │   └── configure.sh     ← Chroot post-install config
│   │   └── tests/               ← pytest test suite
│   └── ouroborOS-profile/       ← archiso profile
│       ├── profiledef.sh
│       ├── packages.x86_64
│       ├── pacman.conf
│       ├── airootfs/            ← Files copied into the live ISO
│       └── efiboot/             ← systemd-boot entries
├── docs/                        ← Documentation only (no scripts)
│   ├── architecture/            ← System design decisions
│   ├── build/                   ← ISO build process
│   ├── installer/               ← Installer architecture
│   ├── messages/                ← Project log and decisions
│   ├── build-and-flash.md       ← How to build ISO and flash USB
│   └── user-guide.md            ← End-user installation guide
├── tests/                       ← CI test scripts
├── agents/                      ← Multi-agent role definitions
└── skills/                      ← Claude Code expert skill definitions
```

---

## Branch Strategy

| Branch | Purpose | Rules |
|--------|---------|-------|
| `master` | Stable production releases | Never commit directly; only merge from `dev` via PR |
| `dev` | Active development | Main working branch |
| `feature/NAME` | Individual features | Branch from `dev`, merge back via PR |
| `fix/NAME` | Bug fixes | Branch from `dev` (or `master` for hotfixes) |

**Always develop on `dev` or a `feature/` branch. Never push directly to `master`.**

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Base OS | ArchLinux |
| Kernel | linux-zen |
| Package manager | pacman |
| Bootloader | systemd-boot |
| Filesystem | Btrfs (immutable subvolumes) |
| Network | systemd-networkd + iwd |
| DNS | systemd-resolved |
| Home dirs | systemd-homed (optional) |
| Installer logic | Python 3 |
| Installer TUI | whiptail / dialog |
| System ops | Bash |
| ISO build | archiso (mkarchiso) |
| Testing | pytest + QEMU |

---

## Expert Skills

Use these skills when working in specific domains. Invoke with `/skill-name`:

| Skill | Use for |
|-------|---------|
| `/systemd-expert` | systemd units, networkd, resolved, homed, repart, boot |
| `/immutable-systems-expert` | Btrfs snapshots, read-only root, atomic updates |
| `/archiso-builder` | ISO profile, packages, airootfs, build process |
| `/installer-developer` | State machine, TUI, config format, unattended install |
| `/filesystem-storage-expert` | Partitioning, fstab, LUKS, Btrfs setup |
| `/bootloader-uefi-expert` | systemd-boot entries, UEFI, kernel params, microcode |

---

## Commit Message Convention

Use **Conventional Commits** format:

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

**Types:**
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `build` — build system, archiso profile, scripts
- `installer` — installer code changes
- `test` — tests
- `chore` — maintenance, dependency updates
- `refactor` — code restructuring without behavior change

**Examples:**
```
feat(installer): add disk selection TUI screen
fix(btrfs): correct subvolume mount order in installer
docs(architecture): add Btrfs snapshot naming convention
build(archiso): add python-rich to packages.x86_64
```

---

## Key Design Constraints

1. **Root filesystem is read-only.** Any write operation must target `/var`, `/etc`, `/tmp`, or `/home`.
2. **UEFI only.** No BIOS/legacy boot support. GRUB is not used.
3. **No NetworkManager.** Use systemd-networkd + iwd.
4. **systemd-boot only.** Boot entries are `.conf` files, not grub.cfg.
5. **Btrfs for root.** No ext4 or XFS for the root partition.
6. **Python for logic, Bash for ops.** No mixing of roles.
7. **All scripts must pass `shellcheck`.** No exceptions.
8. **UUID references only in fstab.** Never `/dev/sdX`.

---

## Development Workflow

### Setting up
```bash
bash src/scripts/setup-dev-env.sh
```

### Building the ISO
```bash
sudo bash src/scripts/build-iso.sh --clean
```

### Flashing to USB
```bash
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso
```

### Testing in QEMU
```bash
qemu-system-x86_64 -enable-kvm -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso -boot d
```

### Running installer tests
```bash
pytest src/installer/tests/ -v
```

---

## Current Phase

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for the full roadmap.

**Current phase:** Phase 3 complete — Installer TUI and State Machine

---

## Important Files to Know

| File | Description |
|------|-------------|
| `docs/architecture/overview.md` | System architecture, layer diagram, component table |
| `docs/architecture/immutability-strategy.md` | Btrfs layout, fstab, snapshot flow |
| `docs/architecture/installer-phases.md` | All installer states, actions, rollback |
| `docs/installer/state-machine.md` | FSM spec and Python skeleton |
| `docs/installer/configuration-format.md` | YAML schema for unattended install |
| `docs/build-and-flash.md` | How to build the ISO and write to USB |
| `docs/user-guide.md` | End-user installation and usage guide |
| `src/scripts/build-iso.sh` | ISO build script (mkarchiso wrapper) |
| `src/scripts/flash-usb.sh` | Safe dd wrapper for USB flashing |
| `src/installer/state_machine.py` | FSM implementation with checkpoints |
| `src/installer/config.py` | InstallerConfig dataclass + YAML validation |
| `src/ouroborOS-profile/profiledef.sh` | archiso profile definition |
| `IMPLEMENTATION_PLAN.md` | Phased roadmap with milestones |

---

## What NOT to Do

- Do not install or configure GRUB under any circumstances
- Do not add NetworkManager to any package list
- Do not use `/dev/sdX` paths in any configuration (always UUID)
- Do not mount root read-write in production (only during updates, via hook)
- Do not commit directly to `master`
- Do not add packages to the ISO without justification (bloat)
