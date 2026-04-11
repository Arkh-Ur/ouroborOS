# ouroborOS — Developer Guide

This guide covers everything you need to build, test, and contribute to ouroborOS.

---

## Requirements

### Host system

An **Arch Linux** host is required for building the ISO. The build uses `mkarchiso`, which is only available on Arch.

> Running inside a Docker container with `archlinux:latest` and `--privileged` also works — this is what CI uses.

### Required packages

```bash
# Install all build and development tools
bash src/scripts/setup-dev-env.sh
```

The script installs:

| Tool | Purpose |
|------|---------|
| `archiso` | ISO build system |
| `shellcheck` | Shell script linter |
| `python` + `python-yaml` | Installer runtime |
| `python-pytest` | Unit test runner |
| `qemu` + `edk2-ovmf` | E2E testing in QEMU |
| `sshpass` | SSH automation in E2E tests |

---

## Repository layout

```
ouroborOS/
├── src/
│   ├── installer/           # Python installer
│   │   ├── state_machine.py # FSM core — all install states
│   │   ├── tui.py           # Rich TUI + whiptail fallback
│   │   ├── config.py        # YAML config loading + validation
│   │   ├── main.py          # CLI entry point
│   │   ├── ops/
│   │   │   ├── disk.sh      # Partitioning, Btrfs, fstab
│   │   │   ├── configure.sh # Chroot post-install config
│   │   │   └── snapshot.sh  # Btrfs snapshot management
│   │   └── tests/           # pytest unit tests
│   ├── scripts/
│   │   ├── build-iso.sh     # mkarchiso wrapper
│   │   ├── flash-usb.sh     # Safe dd wrapper for USB
│   │   └── setup-dev-env.sh # Host dev environment setup
│   └── ouroborOS-profile/   # archiso profile
│       ├── profiledef.sh
│       ├── packages.x86_64
│       ├── airootfs/        # Files injected into the live ISO
│       └── efiboot/         # systemd-boot entries for live ISO
├── templates/
│   └── install-config.yaml  # Unattended install config template
├── docs/                    # All documentation
├── tests/                   # CI test scripts + Docker test image
│   ├── Dockerfile
│   └── scripts/
│       ├── test-shellcheck.sh
│       ├── lint-python.sh
│       ├── run-pytest.sh
│       └── smoke-test.sh
└── .github/workflows/
    ├── build.yml            # ISO build on push to dev
    ├── test.yml             # Unit + smoke tests
    └── lint.yml             # shellcheck + ruff
```

---

## Building the ISO

```bash
# Full clean build (recommended)
sudo bash src/scripts/build-iso.sh --clean

# With custom output and workdir (useful for repeated builds)
sudo bash src/scripts/build-iso.sh --clean \
  --output /tmp/out \
  --workdir /home/ouroborOS-build   # avoids /tmp tmpfs size limit

# GPG-sign the ISO
sudo bash src/scripts/build-iso.sh --clean --sign
```

> **Workdir location matters:** `mkarchiso` writes 4–8 GB to the workdir.
> `/tmp` is tmpfs and may not have enough space. Use `/home` or another disk-backed path.

Build output:

```
out/
├── ouroborOS-0.1.0-x86_64.iso
└── ouroborOS-0.1.0-x86_64.iso.sha256
```

---

## Running the test suite

### Unit tests (Python)

```bash
# Run all unit tests
pytest src/installer/tests/ -v

# With coverage report
pytest src/installer/tests/ --cov=src/installer --cov-report=term-missing
```

### Lint

```bash
# Shell scripts
shellcheck src/installer/ops/*.sh src/scripts/*.sh

# Python
ruff check \
  --select "E,W,F,I,UP,ANN001,ANN201,E722" \
  --line-length 120 \
  src/installer/
```

### Full CI suite (Docker)

```bash
# Build the test image
docker build -t ouroboros-test:ci tests/

# Shell validation
docker run --rm -v "$PWD:/workspace:ro" -e WORKSPACE=/workspace \
  ouroboros-test:ci bash /workspace/tests/scripts/test-shellcheck.sh

# Python tests
docker run --rm -v "$PWD:/workspace" -e WORKSPACE=/workspace \
  ouroboros-test:ci bash /workspace/tests/scripts/run-pytest.sh

# Profile smoke test
docker run --rm -v "$PWD:/workspace:ro" -e WORKSPACE=/workspace \
  ouroboros-test:ci bash /workspace/tests/scripts/smoke-test.sh
```

### E2E test (QEMU)

The E2E test builds the ISO, installs it in QEMU via unattended config, boots the installed system, and verifies 15 checks via SSH. See the [qemu-e2e-test skill](../skills/qemu-e2e-test/SKILL.md) for the full procedure.

Quick reference:

```bash
# Config used by the E2E test
cat templates/install-config.yaml

# Serial log during install
tail -f /tmp/ouroboros-serial-install.log

# Serial log during boot
tail -f /tmp/ouroboros-serial-boot.log

# SSH into the running VM (password: from install-config.yaml)
sshpass -p <password> ssh -o StrictHostKeyChecking=no -p 2222 <user>@localhost
```

---

## Branch strategy

| Branch | Purpose | Rules |
|--------|---------|-------|
| `master` | Stable releases | Merge from `dev` via PR only |
| `dev` | Active development | Main working branch |
| `feature/NAME` | New features | Branch from `dev`, PR back to `dev` |
| `fix/NAME` | Bug fixes | Branch from `dev` (or `master` for hotfixes) |

**Never commit directly to `master`.**

---

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <short description>
```

Types: `feat` · `fix` · `docs` · `build` · `installer` · `test` · `chore` · `refactor` · `ci`

Examples:

```
feat(installer): add disk encryption (LUKS2) support
fix(snapshot): correct timestamp parsing in prune_snapshots
ci(build): add ISO build workflow on push to dev
docs(user-guide): document our-pacman workflow
```

---

## Code conventions

### Bash

- All scripts start with `set -euo pipefail`
- All scripts pass `shellcheck -S style`
- No hardcoded device paths (`/dev/sdX`) — always use variables or UUIDs
- Functions follow `snake_case` naming
- Log via `log_ok`, `log_info`, `log_warn`, `log_error` helpers (see `configure.sh`)

### Python

- Line length: 120 characters (project standard)
- Linter: `ruff` with rules `E,W,F,I,UP,ANN001,ANN201,E722`
- Type annotations required on public function signatures
- No `subprocess.shell=True` — always use list form
- Tests: `pytest`, no `unittest.TestCase` — use plain functions or classes

### archiso profile

- Adding a package to `packages.x86_64` requires justification in the commit message
- Files in `airootfs/` are copied verbatim into the live ISO root
- `profiledef.sh` controls ISO metadata — do not change `iso_name` without updating `build-iso.sh`

---

## Key design constraints

1. **Root is read-only.** Any operation that writes to `/` in the installed system must use `our-pacman`.
2. **UEFI only.** Do not add GRUB or BIOS boot support.
3. **No NetworkManager.** Use `systemd-networkd` + `iwd`.
4. **Python for logic, Bash for system ops.** The installer FSM is Python; disk/snapshot/configure operations are Bash.
5. **UUID in fstab.** Never use `/dev/sdX` in generated fstab entries.
6. **Microcode auto-detected.** `state_machine.py` reads `/proc/cpuinfo` to select `intel-ucode` or `amd-ucode`.

---

## Architecture references

- [Architecture Overview](architecture/overview.md) — system layers and component diagram
- [Immutability Strategy](architecture/immutability-strategy.md) — Btrfs layout, fstab, snapshot flow
- [Installer Phases](architecture/installer-phases.md) — all FSM states, actions, rollback
- [systemd Integration](architecture/systemd-integration.md) — networkd, resolved, zram, homed
- [Configuration Format](installer/configuration-format.md) — YAML schema for unattended install
