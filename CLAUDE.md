# CLAUDE.md — Instrucciones del Proyecto ouroborOS

Este archivo proporciona contexto persistente a Claude Code sobre el proyecto ouroborOS. Lee esto antes de trabajar en cualquier tarea.

---

## Reglas de Salida (OBLIGATORIO)

1. **Idioma de salida:** Todas las respuestas, explicaciones, resúmenes y comunicaciones deben ser en **español**. El código, nombres de variables, mensajes de commit y documentación técnica del proyecto permanecen en inglés (son parte del código).
2. **Resumen final obligatorio:** Al terminar cada tarea o interacción, incluye **siempre** un resumen breve de lo último que realizaste, en este formato:

```
📋 **Resumen de lo realizado:**
- [acción concreta 1]
- [acción concreta 2]
- [estado final: completado / pendiente / error]
```

---

## Project Overview

**ouroborOS** is an ArchLinux-based Linux distribution with an immutable root filesystem, built entirely around the systemd ecosystem.

- **Base:** ArchLinux (pacman, rolling release)
- **Filesystem:** Btrfs subvolumes, root mounted read-only (`ro`)
- **Bootloader:** systemd-boot only (no GRUB, UEFI required)
- **Networking:** systemd-networkd + iwd (no NetworkManager)
- **Installer:** Python state machine + Rich TUI (primary) + Bash ops
- **Status:** v0.5.0 — Phase 5 in progress

---

## Repository Structure

**Dual-repo architecture:** `Arkh-Ur/ouroborOS-dev` (private, dev) pushes releases to `Arkh-Ur/ouroborOS` (public).

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
│   │   ├── config.py            ← InstallerConfig + YAML loader + DesktopConfig + remote URL loader
│   │   ├── desktop_profiles.py  ← Desktop profile package sets (5 profiles) + DM selection (gdm/sddm/plm/none)
│   │   ├── state_machine.py     ← FSM with checkpoints (12 states: USER + DESKTOP + SECURE_BOOT before PARTITION)
│   │   ├── tui.py               ← Rich TUI (primary) + whiptail fallback
│   │   ├── main.py              ← CLI entrypoint
│   │   ├── ops/                 ← Bash operations
│   │   │   ├── disk.sh          ← Partitioning, Btrfs, fstab, LUKS
│   │   │   ├── snapshot.sh      ← Btrfs snapshot management
│   │   │   └── configure.sh     ← Chroot post-install config (our-pac, DM enable, homed, AUR queue)
│   │   └── tests/               ← pytest test suite (347 tests, ≥93% coverage)
│   └── ouroborOS-profile/       ← archiso profile
│       ├── profiledef.sh
│       ├── packages.x86_64
│       ├── pacman.conf
│       ├── airootfs/            ← Files copied into the live ISO
│       └── efiboot/             ← systemd-boot entries
├── templates/                   ← Default install config templates
│   └── install-config.yaml      ← Interactive/unattended install config
├── docs/                        ← Documentation only (no scripts)
│   ├── PHASE_2_PLAN.md          ← Post-v0.1.0 development plan
│   ├── PHASE_4_PLAN.md          ← Phase 4 plan (our-aur, our-flat, TPM2)
│   ├── architecture/            ← System design decisions
│   ├── installer/               ← Installer architecture
│   ├── messages/                ← Project log and decisions
│   ├── developer-guide.md       ← Build, test, contribute
│   ├── user-guide.md            ← End-user installation guide
│   └── build-and-flash.md       ← How to build ISO and flash USB
├── tests/                       ← CI test scripts
├── agents/                      ← Multi-agent role definitions
├── skills/                      ← Claude Code expert skill definitions
└── .github/
    └── workflows/               ← CI workflows (build, lint, test, opencode)
```

---

## Branch Strategy — dev-first

**Regla de oro: Nada se mueve sin verde. Nada toca main sin tag. Nada es público sin pasar por privado primero.**

> Ver skill `ci-dev-first` para diagramas Mermaid completos y plan de implementación detallado.

| Branch | Purpose | Rules |
|--------|---------|-------|
| `dev` | Active development | All day-to-day work. CI runs here (lint + test + build). Tags born here. |
| `main` | Release snapshots | **NEVER push directly.** Only receives merges from release job (via tag). |
| `feature/NAME` | Individual features | Branch from `dev`, merge back to `dev` via PR. |

**Workflow:**
1. All development → `dev` (or `feature/`/`fix/` branched from `dev`)
2. Push to `dev` triggers CI: lint + test + build
3. When CI is green + manual tests pass → open PR `dev` → `main` on GitHub
4. After PR merged → tag `vX.Y.Z` from `main`
5. Tag triggers release job: build ISO → prerelease private.dev → push private.main → public release

**Claude Code rule: NEVER push to `main` directly. No exceptions, no bypass. Only PRs.**

**Pre-push hook required** (no GitHub Pro — protection is local):
```bash
# Verify hook is installed:
ls -la .git/hooks/pre-push
# Must exist and be executable. Blocks any push to main.
```

### Dual-Repo Architecture

| Repository | Visibility | Purpose |
|------------|-----------|---------|
| `Arkh-Ur/ouroborOS-dev` | Private | Development. CI runs on `dev`. Release job merges tag → `main`. |
| `Arkh-Ur/ouroborOS` | Public | Mirror of private `main`. GitHub Releases published here. |

**Flow:** `dev` push → CI → tag → release job → prerelease private → merge `main` private → mirror public

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Base OS | ArchLinux |
| Kernel | linux-zen |
| Package manager | pacman (via `our-pac` wrapper) + `our-aur` (AUR) + `our-flat` (Flatpak) |
| Bootloader | systemd-boot |
| Filesystem | Btrfs (immutable subvolumes) |
| Network | systemd-networkd + iwd |
| DNS | systemd-resolved (DoT enabled) |
| Swap | zram-generator (no swap partition) |
| Home dirs | systemd-homed (default from Phase 2) |
| Containers | systemd-nspawn (via `our-container` wrapper) |
| Installer logic | Python 3 |
| Installer TUI | Rich (primary) + whiptail (fallback) |
| System ops | Bash |
| ISO build | archiso (mkarchiso) |
| Testing | pytest + QEMU |
| CI/CD | GitHub Actions (build on tags, publish to public repo) |

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
pytest src/installer/tests/ -v       # 347 tests, ≥93% coverage
```

---

## Current Phase

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for the full roadmap.

**Phases 1-4 complete.** Release v0.4.0 published at https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.0

**Current phase:** Phase 5 in progress — `system.yaml` declarative manifest, multi-usuario, OTA. See [docs/PHASE_5_PLAN.md](./docs/PHASE_5_PLAN.md).

### Dual-Repo Architecture

| Repository | Visibility | Purpose |
|------------|-----------|---------|
| `Arkh-Ur/ouroborOS-dev` | Private | Development, CI runs on `dev`, release job merges tag → `main` |
| `Arkh-Ur/ouroborOS` | Public | Mirror of private `main`, GitHub Releases |

When a tag `v*` is pushed to `ouroborOS-dev`, the release job builds the ISO, creates a prerelease in the private repo, merges the tag to `origin/main`, then mirrors to the public repo.

---

## Important Files to Know

| File | Description |
|------|-------------|
| `docs/PHASE_2_PLAN.md` | Post-v0.1.0 development plan (our-pac, desktop profiles, our-container) |
| `docs/PHASE_4_PLAN.md` | Phase 4 plan (our-aur, our-flat, TPM2, multi-language) |
| `docs/architecture/overview.md` | System architecture, layer diagram, component table |
| `docs/architecture/immutability-strategy.md` | Btrfs layout, fstab, snapshot flow |
| `docs/architecture/installer-phases.md` | All installer states, actions, rollback |
| `docs/installer/state-machine.md` | FSM spec and Python skeleton |
| `docs/installer/configuration-format.md` | YAML schema for unattended install |
| `docs/user-guide.md` | End-user installation and usage guide |
| `docs/developer-guide.md` | Build, test, contribute |
| `src/scripts/build-iso.sh` | ISO build script (mkarchiso wrapper) |
| `src/scripts/flash-usb.sh` | Safe dd wrapper for USB flashing |
| `src/installer/state_machine.py` | FSM implementation with checkpoints |
| `src/installer/config.py` | InstallerConfig + DesktopConfig dataclasses + YAML validation |
| `src/installer/desktop_profiles.py` | Desktop profile package sets (5 profiles) |
| `templates/install-config.yaml` | Default unattended install config template |
| `docs/architecture/systemd-integration.md` | systemd integration design |
| `src/ouroborOS-profile/profiledef.sh` | archiso profile definition |
| `IMPLEMENTATION_PLAN.md` | Phased roadmap with milestones |
| `.github/workflows/build.yml` | ISO build + release pipeline (dual-repo) |

---

## What NOT to Do

- Do not install or configure GRUB under any circumstances
- Do not add NetworkManager to any package list
- Do not use `/dev/sdX` paths in any configuration (always UUID)
- Do not mount root read-write in production (only during updates, via `our-pac`)
- Do not commit or push directly to `main` — always work on `dev`
- Do not add packages to the ISO without justification (bloat)
- Do not use PreTransaction pacman hooks for remounting (pacman checks writability before hooks)
- Do not write files only to `@etc` if systemd needs them at early boot (mirror to `@` too)
- Do not hardcode mirror URLs in pacman.conf — parametrize or use reflector
- Do not use `--fastest` with reflector — use `--sort score` (server-side, avoids long local benchmarks)
- Do not leave plaintext passwords on disk after use — always clean up immediately

## E2E Testing

Full lifecycle test: build ISO → unattended install in QEMU → verify installed system.

### Key Constraints
- Always use `setsid` to launch QEMU (survives tool timeouts)
- Always `fuser -k 2222/tcp` before launching (kill zombie QEMU)
- Always use `-device e1000` (virtio-net hangs under sustained pacstrap load)
- Always use `-display none -vga virtio` (never `-nographic`, disables VGA for VNC)
- Build workdir and QEMU disk on `/home/` — `/tmp/` is tmpfs (~4 GB), build needs 6-8 GB
- Use `ps aux | grep qemu` to find real PID (`$!` is wrong with setsid)
- Serial log at `/tmp/ouroboros-serial-install.log`

### Known Issues
- `homectl create --identity=JSON` fails in QEMU with generic error (under investigation)
- SSH on installed system only listens on AF_UNIX socket by default (networkd DHCP in SLIRP needs investigation)
- homed-migration rollback works correctly when create fails — user stays as classic `/etc/passwd` user

### Installer States (12 total)
```
INIT → PREFLIGHT → LOCALE → USER → DESKTOP → SECURE_BOOT → PARTITION → FORMAT → INSTALL → CONFIGURE → SNAPSHOT → FINISH
```

### Password Plaintext Lifecycle
- `UserConfig.password_plaintext` is transient — filled during `load_config` or TUI
- Passed to `configure.sh` as `USER_PASSWORD` env var
- Written to `/etc/ouroboros/homed-migration.conf` (chmod 600) for first-boot homed migration
- Cleared in `state_machine.py` immediately after `configure.sh` finishes
- homed-migrate.sh removes `HOMED_PASSWORD` from conf file after successful migration
- Never persisted in checkpoints
