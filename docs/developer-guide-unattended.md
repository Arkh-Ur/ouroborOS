# Unattended Install Testing — Developer Guide

This guide explains how to run unattended ouroborOS installs in QEMU using the
config ISO mechanism, and documents the Claude Code skills available in this project
for AI agents picking up this work.

---

## How config media detection works

The ouroborOS installer auto-detects its run mode at boot:

| Scenario | Behavior |
|----------|----------|
| ISO alone | Attended — TUI launches normally |
| ISO + config media (LABEL=OUROBOROS_CFG) | Unattended — silent install, no prompt |

The detection order in `find_unattended_config()` (`src/installer/config.py`):

1. Kernel cmdline `ouroborOS.config=/path` — highest priority
2. Block device with `LABEL=OUROBOROS_CFG` containing `unattended.yaml` ← config ISO
3. `/tmp/ouroborOS-config.yaml`, `/run/ouroborOS-config.yaml` — legacy paths
4. YAML files under `/run/media/` — udisks auto-mounts

The config media is mounted read-only at `/run/ouroboros-config/`. The config file
must be named `unattended.yaml` at the root of the media.

---

## Quick start — unattended install in QEMU

### Prerequisites

```bash
# Host packages required:
sudo pacman -S qemu-system-x86 edk2-ovmf sshpass xorriso

# ouroborOS ISO already built:
ls out/ouroborOS-*.iso
```

### Step 1 — Build the config ISO

```bash
bash src/scripts/build-config-iso.sh \
  --config tests/e2e/e2e-unattended.yaml \
  --output /tmp/unattended.iso

# Verify label:
blkid /tmp/unattended.iso
# → /tmp/unattended.iso: ... LABEL="OUROBOROS_CFG" ...
```

### Step 2 — Create disk and launch QEMU (unattended)

```bash
qemu-img create -f qcow2 /home/$USER/e2e/disk.qcow2 25G

setsid qemu-system-x86_64 \
  -enable-kvm -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso \
  -drive file=/tmp/unattended.iso,if=ide,media=cdrom,index=1 \
  -drive file=/home/$USER/e2e/disk.qcow2,if=virtio \
  -device e1000,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2225-:22 \
  -display none -vga virtio \
  -serial file:/tmp/ouroboros-serial.log &

# Follow progress:
tail -f /tmp/ouroboros-serial.log | grep -E "STATE|ERROR|shutdown"
```

The installer reads `unattended.yaml` from the config ISO and installs silently.
With `post_install_action: shutdown` in the YAML, it shuts down when done.

### Step 3 — Boot the installed system

```bash
setsid qemu-system-x86_64 \
  -enable-kvm -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -drive file=/home/$USER/e2e/disk.qcow2,if=virtio \
  -device e1000,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2225-:22 \
  -display none -vga virtio &

# Wait ~30s for boot, then SSH:
sshpass -p toor ssh -p 2225 \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@localhost "systemctl is-system-running"
```

### Step 4 — Run E2E tests

```bash
# Full our-tools E2E (80 tests):
E2E_ROOT_PASS=toor E2E_SSH_PORT=2225 bash tests/scripts/e2e-our-tools.sh

# Phase 6 tests:
E2E_ROOT_PASS=toor E2E_SSH_PORT=2225 bash tests/scripts/e2e-phase6.sh

# Dotfiles packs (all 7):
E2E_ROOT_PASS=toor E2E_SSH_PORT=2225 bash tests/e2e/test_dots_e2e.sh --all
```

---

## E2E environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_ROOT_PASS` | `toor` | root password on installed system |
| `E2E_USER_PASS` | `e2etest` | regular user password |
| `E2E_USER` | `e2e` | regular username |
| `E2E_SSH_PORT` | `2225` | SSH port forwarded from QEMU |

---

## Creating a custom config ISO

To test a specific installation scenario, copy and edit `tests/e2e/e2e-unattended.yaml`:

```bash
cp tests/e2e/e2e-unattended.yaml /tmp/my-config.yaml
# Edit /tmp/my-config.yaml as needed

bash src/scripts/build-config-iso.sh \
  --config /tmp/my-config.yaml \
  --output /tmp/my-unattended.iso
```

For USB-based unattended installs on real hardware:
```bash
# Write config to USB (replace /dev/sdX):
sudo mkfs.vfat -n OUROBOROS_CFG /dev/sdX
sudo mount /dev/sdX /mnt
sudo cp /tmp/my-config.yaml /mnt/unattended.yaml
sudo umount /mnt
```

---

## Claude Code Skills available in this project

Skills are invoked with `/skill-name` in Claude Code. The full registry is at `.atl/skill-registry.md`.

| Skill | When to use | Invoke |
|-------|-------------|--------|
| `installer-developer` | Changes to `state_machine.py`, `config.py`, `tui.py` | `/installer-developer` |
| `systemd-expert` | systemd units, networkd, homed, repart, boot | `/systemd-expert` |
| `immutable-systems-expert` | Btrfs snapshots, read-only root, atomic updates | `/immutable-systems-expert` |
| `archiso-builder` | ISO profile, packages, airootfs, build process | `/archiso-builder` |
| `filesystem-storage-expert` | Partitioning, fstab, LUKS, Btrfs | `/filesystem-storage-expert` |
| `judgment-day` | Dual adversarial review of code or architecture | `/judgementday` |

### Judgment Day workflow

1. Claude reads `.atl/skill-registry.md` to resolve skill paths
2. Launches Judge A and Judge B in parallel (Opus model, adversarial, no shared context)
3. Synthesizes: **Confirmed** (both agree) / **Suspect** (one judge) / **INFO** (theoretical)
4. Asks before fixing — never auto-applies
5. Fix agent applies only confirmed issues
6. Re-judges with two fresh judges
7. Terminal verdict: `JUDGMENT: APPROVED` or `JUDGMENT: ESCALATED`

### Standard E2E workflow for this project

```
1. Build ISO: sudo bash src/scripts/build-iso.sh --clean
2. Build config ISO: bash src/scripts/build-config-iso.sh --config tests/e2e/e2e-unattended.yaml
3. Install in QEMU (unattended, see above)
4. Boot installed system (see above)
5. Run E2E: E2E_ROOT_PASS=toor bash tests/scripts/e2e-our-tools.sh
6. Commit fixes on branch dev (never main directly)
```

---

## Key implementation files

| File | What it does |
|------|--------------|
| `src/installer/config.py` | `_config_from_labeled_media()` — detects OUROBOROS_CFG device |
| `src/installer/state_machine.py` | `_handle_init()` — uses labeled media as automated signal |
| `src/scripts/build-config-iso.sh` | Creates `unattended.iso` from a YAML config |
| `tests/e2e/e2e-unattended.yaml` | Reference config for unattended E2E testing |
| `src/installer/tests/test_config.py` | Unit tests for config detection including labeled media |
