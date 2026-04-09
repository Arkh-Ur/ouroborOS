---
name: qemu-e2e-test
description: >
  E2E test plan for ouroborOS: build ISO with --e2e-config, unattended install in QEMU,
  and verify the installed system via SSH and serial log. Covers the full lifecycle from source
  to running system. Invoked with /qemu-e2e-test or whenever a full integration test
  is needed after changes to the installer, configure.sh, snapshot.sh, or ISO profile.
---

You are executing the **ouroborOS E2E Test Suite** — full lifecycle from build to running system.

---

## Prerequisites

```bash
# Required packages on host
sudo pacman -S --needed qemu-system-x86 edk2-ovmf openssh sshpass psmisc

# OVMF firmware path (ArchLinux)
/usr/share/edk2/x64/OVMF_CODE.4m.fd

# Repo root must have a fresh checkout on dev
git status  # must be clean
```

---

## Phase 1 — Build ISO

```bash
# Build with E2E config injected — workdir on /home (needs ~6-8 GB, /tmp too small)
echo "7907" | sudo -S bash src/scripts/build-iso.sh --clean \
  --e2e-config=tests/qemu/minimal-e2e.yaml \
  --workdir /home/ouroborOS-build

# Expected last lines:
# [OK]  ouroborOS ISO ready.
# [WARN] This ISO is for testing only — NOT for production use.

# Verify ISO exists and is ≥ 800 MB
ls -lh out/ouroborOS-*.iso
```

**Pass criteria:**
- Exit code 0
- ISO file exists in `out/`
- Size between 800 MB and 2 GB

---

## Phase 2 — Unattended Install

### 2.1 Prepare disk and launch QEMU

```bash
# Kill any zombie QEMU holding port 2222
fuser -k 2222/tcp 2>/dev/null || true

# Clean previous test artifacts
rm -f /home/ouroboros-test.qcow2 /tmp/ouroboros-serial-install.log

# Create virtual disk on /home (NOT /tmp — tmpfs ~4 GB fills during pacstrap)
qemu-img create -f qcow2 /home/ouroboros-test.qcow2 20G

# Launch QEMU — headless, VNC on :1 (localhost:5901), SSH forwarded to 2222
# Use setsid so QEMU survives tool/shell timeouts
setsid qemu-system-x86_64 \
  -enable-kvm \
  -cpu host \
  -smp 2 \
  -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive file=/home/ouroboros-test.qcow2,format=qcow2,if=virtio,cache=writeback \
  -cdrom out/ouroborOS-*.iso \
  -boot d \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -device e1000,netdev=net0 \
  -rtc base=utc,clock=host \
  -serial file:/tmp/ouroboros-serial-install.log \
  -vga virtio \
  -display none \
  -vnc :1 \
  >/dev/null 2>&1 &

# Get real QEMU PID ($! is setsid wrapper, not qemu)
sleep 2
QEMU_PID=$(pgrep -f "qemu.*ouroboros-test" | head -1)
echo "QEMU PID: $QEMU_PID"
```

> **VNC**: Connect to `localhost:5901` with any VNC client to watch visually.
> **IMPORTANT**: Use `-device e1000` — virtio-net hangs under sustained pacstrap load.
> **IMPORTANT**: Use `-display none -vga virtio` — never `-nographic` (disables VGA for VNC).
> **IMPORTANT**: Use `setsid` — bash tool kills child processes on timeout.

### 2.2 Monitor install via serial log

```bash
# Follow the install log — installer auto-detects ouroborOS-config.yaml
tail -f /tmp/ouroboros-serial-install.log
```

### 2.3 Wait for completion

The installer shuts down the VM automatically (`post_install_action: shutdown`).

```bash
# Poll until QEMU exits (timeout: 20 minutes)
timeout 1200 bash -c "while kill -0 $QEMU_PID 2>/dev/null; do sleep 5; done"
echo "Install complete"
```

### 2.4 Verify install serial log

```bash
# All 11 states must appear as completed
for state in INIT PREFLIGHT LOCALE USER DESKTOP PARTITION FORMAT INSTALL CONFIGURE SNAPSHOT FINISH; do
  if grep -q "State completed: ${state}" /tmp/ouroboros-serial-install.log; then
    echo "✓ ${state}"
  else
    echo "✗ ${state} — MISSING"
  fi
done

# No FAILED or ERROR lines from installer
grep -E "^\[.*FAILED\]|\[ERROR\]" /tmp/ouroboros-serial-install.log && echo "ERRORS FOUND" || echo "✓ No errors"

# Snapshot must be created
grep "Snapshot created" /tmp/ouroboros-serial-install.log && echo "✓ Snapshot OK" || echo "✗ Snapshot missing"

# Boot entry must be written
grep "Boot entry written" /tmp/ouroboros-serial-install.log && echo "✓ Boot entry OK" || echo "✗ Boot entry missing"

# machine-id + group files written to @
grep "Critical /etc files written" /tmp/ouroboros-serial-install.log && echo "✓ /etc seed OK" || echo "✗ /etc seed missing"
```

**Pass criteria:** All 11 states ✓, no FAILED/ERROR from installer, snapshot ✓, boot entry ✓, /etc seed ✓.

---

## Phase 3 — Verify Installed System

### 3.1 Boot installed system (no ISO)

```bash
# Kill any leftover QEMU on port 2222
fuser -k 2222/tcp 2>/dev/null || true
sleep 1

rm -f /tmp/ouroboros-serial-boot.log

setsid qemu-system-x86_64 \
  -enable-kvm \
  -cpu host \
  -smp 2 \
  -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive file=/home/ouroboros-test.qcow2,format=qcow2,if=virtio,cache=writeback \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -device e1000,netdev=net0 \
  -rtc base=utc,clock=host \
  -serial file:/tmp/ouroboros-serial-boot.log \
  -vga virtio \
  -display none \
  -vnc :1 \
  >/dev/null 2>&1 &

sleep 2
QEMU_PID=$(pgrep -f "qemu.*ouroboros-test" | head -1)

# Wait for login prompt (up to 90s)
timeout 90 bash -c 'until grep -q "ouroboros login:" /tmp/ouroboros-serial-boot.log 2>/dev/null; do sleep 2; done'
echo "System booted"
```

### 3.2 Verify boot is clean

```bash
# No FAILED units on boot
grep "FAILED" /tmp/ouroboros-serial-boot.log && echo "✗ Boot has FAILED units" || echo "✓ Clean boot"

# Login prompt reached
grep -q "ouroboros login:" /tmp/ouroboros-serial-boot.log && echo "✓ Login prompt OK" || echo "✗ Login prompt missing"

# systemd-boot menu showed correct entries
grep -q "ouroborOS" /tmp/ouroboros-serial-boot.log && echo "✓ Boot menu OK" || echo "✗ Boot menu missing"
grep -q "snapshot (install)" /tmp/ouroboros-serial-boot.log && echo "✓ Snapshot entry OK" || echo "✗ Snapshot entry missing"
```

### 3.3 SSH into installed system

```bash
# User from tests/qemu/minimal-e2e.yaml: hbuddenberg / 7907
# SSH forwarded to localhost:2222

# Clear stale host key from previous runs
ssh-keygen -R "[localhost]:2222" 2>/dev/null || true

# Wait for SSH to be available (up to 90s)
timeout 90 bash -c 'until sshpass -p "7907" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=3 -p 2222 hbuddenberg@localhost true 2>/dev/null; do sleep 3; done'
echo "SSH ready"

# Helper alias
SSH="sshpass -p 7907 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 hbuddenberg@localhost"
```

### 3.4 System verification commands

```bash
# --- Root filesystem is read-only (Btrfs property — mount option alone is unreliable on Btrfs) ---
$SSH "echo 7907 | sudo -S btrfs property get / ro 2>/dev/null | grep -q 'ro=true'" && echo "✓ Root is RO (Btrfs property)" || echo "✗ Root is NOT read-only"

# --- No failed systemd units ---
FAILED=$($SSH 'systemctl --failed --no-legend | wc -l')
[[ "$FAILED" -eq 0 ]] && echo "✓ No failed units" || echo "✗ ${FAILED} failed unit(s): $($SSH 'systemctl --failed --no-legend')"

# --- Btrfs subvolumes present ---
for sv in @ @var @etc @home @snapshots; do
  $SSH "echo 7907 | sudo -S btrfs subvolume list / 2>/dev/null | grep -q '${sv}$'" && echo "✓ Subvolume ${sv}" || echo "✗ Subvolume ${sv} missing"
done

# --- Install snapshot exists ---
$SSH "echo 7907 | sudo -S btrfs subvolume list / 2>/dev/null | grep -q '@snapshots/install'" && echo "✓ Snapshot install" || echo "✗ Snapshot install missing"

# --- systemd-boot entries ---
$SSH "ls /boot/loader/entries/" | grep -q "ouroborOS.conf" && echo "✓ Main boot entry" || echo "✗ Main boot entry missing"
$SSH "ls /boot/loader/entries/" | grep -q "snapshot-install" && echo "✓ Snapshot boot entry" || echo "✗ Snapshot boot entry missing"

# --- machine-id is set ---
MACHINEID=$($SSH 'cat /etc/machine-id')
[[ ${#MACHINEID} -eq 32 ]] && echo "✓ machine-id set (${MACHINEID})" || echo "✗ machine-id invalid"

# --- DNS over TLS configured ---
$SSH 'grep -q "DNSOverTLS=opportunistic" /etc/systemd/resolved.conf' && echo "✓ DoT configured" || echo "✗ DoT not configured"

# --- zram swap active ---
$SSH 'swapon --show | grep -q zram' && echo "✓ zram active" || echo "✗ zram not active"

# --- Network services active ---
for svc in systemd-networkd systemd-resolved systemd-timesyncd; do
  $SSH "systemctl is-active ${svc}" | grep -q "active" && echo "✓ ${svc}" || echo "✗ ${svc} not active"
done

# --- our-pac and our-box binaries ---
$SSH 'test -x /usr/local/bin/our-pac' && echo "✓ our-pac installed" || echo "✗ our-pac missing"
$SSH 'test -x /usr/local/bin/our-box' && echo "✓ our-box installed" || echo "✗ our-box missing"
$SSH 'test -L /usr/local/bin/ouroboros-upgrade' && echo "✗ ouroboros-upgrade symlink still present (should be gone)" || echo "✓ ouroboros-upgrade symlink removed"

# --- user created correctly ---
$SSH 'id hbuddenberg' | grep -q "wheel" && echo "✓ User hbuddenberg in wheel" || echo "✗ User not in wheel"

# --- bootctl EFI binary present ---
$SSH 'test -f /boot/EFI/systemd/systemd-bootx64.efi' && echo "✓ EFI binary present" || echo "✗ EFI binary missing"

# --- resolved.conf on @etc ---
$SSH 'cat /etc/systemd/resolved.conf' | grep "DNSOverTLS" && echo "✓ resolved.conf OK" || echo "✗ resolved.conf missing"
```

### 3.5 Teardown

```bash
kill $QEMU_PID 2>/dev/null || pkill -f "qemu.*ouroboros-test" || true
rm -f /home/ouroboros-test.qcow2 /tmp/ouroboros-serial-*.log
echo "Teardown complete"
```

---

## Pass/Fail Summary

| Phase | Check | Expected |
|-------|-------|----------|
| Build | ISO exists, size 800M–2G | ✓ |
| Install | All 11 states completed | ✓ |
| Install | No FAILED/ERROR from installer | ✓ |
| Install | Snapshot + boot entry written | ✓ |
| Install | /etc seed (machine-id, group) written | ✓ |
| Boot | No FAILED units | ✓ |
| Boot | Login prompt reached | ✓ |
| Boot | systemd-boot snapshot entry visible | ✓ |
| Verify | Root filesystem is RO (btrfs property ro=true) | ✓ |
| Verify | 0 failed systemd units | ✓ |
| Verify | All 5 Btrfs subvolumes + install snapshot | ✓ |
| Verify | machine-id is 32-char hex | ✓ |
| Verify | DNSOverTLS=opportunistic in resolved.conf | ✓ |
| Verify | zram swap active | ✓ |
| Verify | our-pac + our-box present, ouroboros-upgrade symlink absent | ✓ |
| Verify | User hbuddenberg in wheel group | ✓ |
| Verify | EFI binary at /boot/EFI/systemd/ | ✓ |

**Overall PASS**: All rows ✓ with zero exceptions.

---

## Known Constraints

| Constraint | Reason |
|-----------|--------|
| Host must have KVM (`/dev/kvm`) | `-enable-kvm` is required for acceptable performance |
| Host RAM ≥ 8 GB for `-m 2048` | Smaller allocation triggers OOM during pacstrap |
| Use `-device e1000` | virtio-net hangs under sustained download load in QEMU userspace |
| Use `-display none -vga virtio` | `-nographic` disables VGA device — VNC shows blank screen |
| Use `setsid` to launch QEMU | bash tool kills child processes on timeout; setsid detaches QEMU |
| Use `fuser -k 2222/tcp` before launch | Zombie QEMU from prior run blocks port 2222 |
| Build workdir + disk image on `/home` | `/tmp` is tmpfs (~4 GB), ISO build + qcow2 need 6-8 GB |
| `sshpass` required | Automated SSH with password; install via `pacman -S sshpass` |
| `ssh-keygen -R "[localhost]:2222"` before SSH | known_hosts persists between runs, breaking auth |
| Use `echo 7907 \| sudo -S <cmd>` for privileged cmds | `sudo` in installed system is non-interactive over SSH |

## Known Issues

| Issue | Status |
|-------|--------|
| `homectl create --identity=JSON` fails in QEMU | Under investigation — use `homed_storage: classic` in E2E config |
| homed-migrate.sh rollback leaves user as classic | Expected — system functional, home encryption disabled |
