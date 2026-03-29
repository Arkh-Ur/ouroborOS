# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-28
**Commit:** 6650663
**Branch:** dev

## OVERVIEW

ouroborOS is an ArchLinux-based immutable Linux distribution using systemd-boot, Btrfs snapshots, and a Python FSM installer with Bash ops. Rolling release, minimal bloat, UEFI-only.

## STRUCTURE

```
ouroborOS/
├── src/
│   ├── installer/         # Python FSM installer + Bash ops (core app)
│   ├── scripts/           # Build, flash, dev-env shell scripts
│   └── ouroborOS-profile/ # archiso profile (airootfs, efiboot, packages)
├── docs/                  # Architecture, build, installer, messages
├── tests/                 # Docker-based test infra + shell scripts
├── agents/                # Agent role definitions (qa-tester, developer, etc.)
├── skills/                # Domain skill docs (systemd, archiso, filesystem, etc.)
├── CLAUDE.md              # Canonical project constraints
├── IMPLEMENTATION_PLAN.md # Phased roadmap
└── README.md
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add installer state/phase | `src/installer/state_machine.py` | FSM with checkpoints, see installer/AGENTS.md |
| Add TUI screen | `src/installer/tui.py` | whiptail wrapper, returns dicts |
| Change config schema | `src/installer/config.py` | Dataclasses + YAML validation |
| Add disk/snapshot/config op | `src/installer/ops/*.sh` | Bash libs called via `_run_op()` |
| Add ISO package | `src/ouroborOS-profile/packages.x86_64` | Must justify (bloat concern) |
| Change boot entries | `src/ouroborOS-profile/efiboot/` | systemd-boot .conf files |
| Change live ISO filesystem | `src/ouroborOS-profile/airootfs/` | Copied into ISO at build |
| Build ISO | `src/scripts/build-iso.sh` | mkarchiso wrapper |
| Flash USB | `src/scripts/flash-usb.sh` | Safe dd wrapper |
| Dev environment | `src/scripts/setup-dev-env.sh` | Installs build deps on Arch host |
| Add CI check | `.github/workflows/` | lint.yml, test.yml, code-review.yml |
| Add test | `src/installer/tests/` or `tests/scripts/` | pytest or shell scripts |
| Architecture decisions | `docs/architecture/` | overview, immutability, systemd, installer-phases |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `Installer` | class | `src/installer/state_machine.py` | Core FSM orchestrator |
| `State` | enum | `src/installer/state_machine.py` | INIT→PREFLIGHT→LOCALE→PARTITION→FORMAT→INSTALL→CONFIGURE→SNAPSHOT→FINISH |
| `TUI` | class | `src/installer/tui.py` | whiptail UI wrapper |
| `InstallerConfig` | dataclass | `src/installer/config.py` | Single config model (disk, locale, network, user) |
| `load_config` | func | `src/installer/config.py` | YAML→InstallerConfig loader |
| `validate_config` | func | `src/installer/config.py` | Schema validation (disk path, timezone, hostname, username) |
| `find_unattended_config` | func | `src/installer/config.py` | Discovers YAML on cmdline/USB/tmp |
| `main` | func | `src/installer/main.py` | CLI entry (--resume, --config, --validate-config) |
| `prepare_disk` | func | `src/installer/ops/disk.sh` | End-to-end partition→format→subvol→mount→fstab |
| `create_install_snapshot` | func | `src/installer/ops/snapshot.sh` | Baseline Btrfs snapshot |
| configure steps | funcs | `src/installer/ops/configure.sh` | Chroot: locale, timezone, hostname, bootloader, network, users, immutable root |

## CONVENTIONS

- **Python for logic, Bash for ops.** No mixing. `state_machine.py` orchestrates; `ops/*.sh` executes.
- **Conventional Commits:** `feat|fix|docs|build|installer|test|chore|refactor)(scope): description`
- **Branch strategy:** `dev` or `feature/*` only. PR to merge. Never push to `master`.
- **All shell scripts:** `set -euo pipefail` + pass `shellcheck -S style` (zero warnings).
- **Python lint:** Ruff with E,W,F,I,UP,ANN001,ANN201,E722.
- **Test coverage gate:** 70% minimum (enforced by `tests/scripts/run-pytest.sh`).
- **No GRUB, no NetworkManager, no /dev/sdX, no root rw in production.** See ANTI-PATTERNS.

## ANTI-PATTERNS

| Forbidden | Why |
|-----------|-----|
| GRUB in code/configs | systemd-boot only; UEFI-only |
| NetworkManager | systemd-networkd + iwd |
| `/dev/sdX` in runtime code | Use UUID everywhere |
| Root mounted read-write in production | Immutable design; writes to /var, /etc, /tmp, /home |
| Direct commits to master | Branch strategy: dev→PR→master |
| Unjustified packages in ISO | Keep ISO lean |
| `shellcheck` failures | All scripts must pass with zero warnings |
| TODO in submitted code | Track properly or implement |
| PARTUUID in fstab for root | Use UUID= for root subvolume |
| Hardcoded archisolabel in boot entries | Use `%ARCHISO_UUID%` template + `archisosearchuuid=` (archiso v87+) |
| Plaintext passwords in scripts/config | Hash via SHA-512 crypt; LUKS passphrase via stdin |
| Python logic in Bash ops or vice versa | Strict separation of concerns |
| Hardcoded mirror URLs in pacman.conf | Parameterize or configure |

## UNIQUE STYLES

- **FSM with checkpoints:** Installer state persisted per-phase in `/tmp/ouroborOS-checkpoints/`; supports resume after interruption.
- **Python↔Bash boundary:** `state_machine._run_op()` invokes `ops/*.sh` with `--action` and `--target` flags; `configure.sh` driven by environment variables.
- **archiso profile layout:** `airootfs/` mirrors live ISO filesystem; `efiboot/` contains systemd-boot entries; `profiledef.sh` defines build metadata.
- **Docker-based test infra:** All CI tests run in an Arch Linux container built from `tests/Dockerfile`.

## COMMANDS

```bash
# Setup (Arch host)
bash src/scripts/setup-dev-env.sh

# Build ISO
sudo bash src/scripts/build-iso.sh --clean

# Flash USB
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso

# Test in QEMU
qemu-system-x86_64 -enable-kvm -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso -boot d

# Unit tests
pytest src/installer/tests/ -v

# Full CI suite (Docker)
docker-compose -f tests/docker-compose.yml run --rm full-suite

# Individual test suites
docker-compose -f tests/docker-compose.yml run --rm shellcheck-suite
docker-compose -f tests/docker-compose.yml run --rm pytest-suite
docker-compose -f tests/docker-compose.yml run --rm smoke-test

# Lint
tests/scripts/lint-python.sh
tests/scripts/test-shellcheck.sh
```

## NOTES

- No `pyproject.toml`, `pytest.ini`, `conftest.py`, or `Makefile` — test config is in `tests/scripts/`.
- `out/` contains build artifacts (ISO), gitignored.
- `IMPLEMENTATION_PLAN.md` tracks phase progress; currently at Phase 3 complete.
- `skills/` and `agents/` are non-code knowledge bases for Claude Code; not executed.
