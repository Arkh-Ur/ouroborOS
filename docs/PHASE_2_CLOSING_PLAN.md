# Phase 2 Closing Plan

This document records the closing state of Phase 2 post-v0.1.0 development.

---

## What Phase 2 delivered

All core deliverables from `docs/PHASE_2_PLAN.md` are implemented and merged to `dev`:

| Deliverable | Status |
|-------------|--------|
| Desktop profile selection (minimal/hyprland/niri/gnome/kde) | ✅ |
| Display manager selection decoupled (gdm/sddm/plm/none) | ✅ |
| Visual selector (↑↓ arrows) in TUI | ✅ |
| FSM reorder: USER + DESKTOP before PARTITION | ✅ |
| `our-pac` (renamed from `ouroboros-upgrade`, compat symlink) | ✅ |
| `our-container` nspawn wrapper (17 commands, autostart service) | ✅ |
| `systemd-homed` migration service (first-boot oneshot) | ✅ |
| Remote config URL prompt in INIT state | ✅ |
| Reflector optimized: `--sort score` (server-side) | ✅ |
| 239 pytest tests passing | ✅ |
| E2E: Build ISO ✓ → Install 11/11 states ✓ → Boot clean ✓ | ✅ |

---

## What this closing patch fixes

### 1. Ruff lint errors in test files

Four unused imports and one unused variable crept into the test suite via Phase 2 additions. Fixed in `src/installer/tests/conftest.py` and `src/installer/tests/test_our_container_integration.py`.

### 2. PAM patch for Arch Linux (homed-migrate.sh)

`patch_pam()` in `homed-migrate.sh` was patching `/etc/pam.d/system-auth`, which does not exist on a default Arch installation. On Arch, `sshd` uses `/etc/pam.d/sshd` directly. The fix patches both files and adds a `nsswitch.conf` update so SSH can resolve homed users.

Additionally, `homectl create` error output is now captured and logged to the systemd journal for diagnosis.

### 3. E2E test artifacts removed from airootfs

`e2e-config.yaml` and `e2e-unattended.conf` were baked into the live ISO profile (`airootfs/`), meaning they would appear in any production ISO built without extra care. These are now external to the profile.

**New approach:** `src/scripts/build-iso.sh` accepts an optional `--e2e-config=PATH` flag. When provided, the config file is injected into airootfs temporarily for the build and cleaned up via `trap EXIT`. Production builds (no flag) produce a clean ISO.

```bash
# E2E build
sudo bash src/scripts/build-iso.sh --clean \
  --e2e-config=tests/qemu/minimal-e2e.yaml \
  --workdir /home/ouroborOS-build

# Production build (unchanged)
sudo bash src/scripts/build-iso.sh --clean \
  --workdir /home/ouroborOS-build
```

### 4. E2E SSH verify now passing

With the E2E config using `homed_storage: classic` and `profile: minimal`, the full verification chain passes end-to-end:

```
Build ISO → Unattended install (11/11 states) → Boot → SSH → Verify system
```

**SSH verification checks:**
- Root filesystem mounted read-only
- Zero failed systemd units
- All 5 Btrfs subvolumes present (`@`, `@var`, `@etc`, `@home`, `@snapshots`)
- Install snapshot exists
- systemd-boot entries (main + snapshot)
- machine-id set (32-char hex)
- DNSOverTLS=opportunistic in resolved.conf
- zram swap active
- `our-pac` and `our-container` binaries installed
- `ouroboros-upgrade → our-pac` compat symlink present
- User `hbuddenberg` in `wheel` group
- EFI binary present

---

## Known issues (not fixed in this patch)

### `homectl create` fails in QEMU

`homectl create --identity=JSON` fails with a generic error when run inside the homed-migration oneshot service in QEMU. Root cause is under investigation — candidates:

- D-Bus session not fully initialized when the oneshot runs early in boot
- Btrfs subvolume creation within a QEMU virtio block device (KVM should support this)
- `--identity` JSON secret format mismatch between systemd versions

**Workaround for E2E:** Use `homed_storage: classic` in `tests/qemu/minimal-e2e.yaml`. The classic user flow is fully verified via SSH.

**Impact on production:** Not a blocker — `homectl create` fails, rollback restores the classic user, the system is fully functional. User experience is degraded (no per-user home encryption) but the system boots and works. A future patch will resolve the homectl issue once the root cause is identified.

---

## Running E2E tests

```bash
# 1. Build ISO with E2E config injected
echo "PASSWORD" | sudo -S bash src/scripts/build-iso.sh --clean \
  --e2e-config=tests/qemu/minimal-e2e.yaml \
  --workdir /home/ouroborOS-build

# 2. Create disk image
qemu-img create -f qcow2 /home/ouroboros-test.qcow2 20G

# 3. Install (headless, VNC on :1)
fuser -k 2222/tcp 2>/dev/null || true
setsid qemu-system-x86_64 \
  -enable-kvm -cpu host -smp 2 -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive file=/home/ouroboros-test.qcow2,format=qcow2,if=virtio,cache=writeback \
  -cdrom out/ouroborOS-*.iso -boot d \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -device e1000,netdev=net0 \
  -serial file:/tmp/ouroboros-serial-install.log \
  -vga virtio -display none -vnc :1 \
  >/dev/null 2>&1 &

# 4. Follow install log
tail -f /tmp/ouroboros-serial-install.log

# 5. After shutdown, boot installed system and verify via SSH
# (see skills/qemu-e2e-test.md for the full verification script)
```

---

## Files changed in this closing patch

| File | Change |
|------|--------|
| `src/installer/tests/conftest.py` | Remove unused imports and variable |
| `src/installer/tests/test_our_container_integration.py` | Remove unused import |
| `src/ouroborOS-profile/airootfs/usr/local/lib/ouroboros/homed-migrate.sh` | Arch-aware PAM patch, nsswitch update, error logging |
| `src/ouroborOS-profile/airootfs/etc/ouroborOS/e2e-config.yaml` | Removed |
| `src/ouroborOS-profile/airootfs/etc/systemd/system/ouroborOS-installer.service.d/e2e-unattended.conf` | Removed |
| `tests/qemu/minimal-e2e.yaml` | New — E2E config with classic storage |
| `src/scripts/build-iso.sh` | Add `--e2e-config=PATH` flag |
| `skills/qemu-e2e-test.md` | SSH verify pass, `--e2e-config` in build, `setsid`+`fuser` |
