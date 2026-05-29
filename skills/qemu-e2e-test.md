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
sudo bash src/scripts/build-iso.sh --clean \
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
# Kill any zombie QEMU holding port 2223
fuser -k 2223/tcp 2>/dev/null || true

# Clean previous test artifacts
rm -f /home/ouroboros-test.qcow2 /tmp/ouroboros-serial-install.log

# Create virtual disk on /home (NOT /tmp — tmpfs ~4 GB fills during pacstrap)
# Use 40G for Hyprland/GNOME/KDE profiles; 20G is enough for minimal
qemu-img create -f qcow2 /home/ouroboros-test.qcow2 40G

# Launch QEMU — headless, VNC on :1 (localhost:5901), SSH forwarded to 2223
# Use setsid so QEMU survives tool/shell timeouts
setsid qemu-system-x86_64 \
  -enable-kvm \
  -cpu host \
  -smp 2 \
  -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive file=/home/ouroboros-test.qcow2,format=qcow2,if=virtio,cache=writeback \
  -cdrom out/ouroborOS-*.iso \
  -boot d \
  -netdev user,id=net0,hostfwd=tcp::2223-:22 \
  -device e1000,netdev=net0 \
  -rtc base=utc,clock=host \
  -serial file:/tmp/ouroboros-serial-install.log \
  -vga std \
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
> **IMPORTANT**: Use `-vga std -display none` — never `-nographic` (disables VGA for VNC). Do NOT use `-vga virtio` (not supported in headless mode).
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
# All 13 states must appear as completed
for state in INIT NETWORK_SETUP PREFLIGHT LOCALE USER DESKTOP SECURE_BOOT PARTITION FORMAT INSTALL CONFIGURE SNAPSHOT FINISH; do
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

**Pass criteria:** All 13 states ✓, no FAILED/ERROR from installer, snapshot ✓, boot entry ✓, /etc seed ✓.

---

## Phase 3 — Verify Installed System

### 3.1 Boot installed system (no ISO)

```bash
# Kill any leftover QEMU — must kill process, not just close terminal
# WARNING: `systemctl reboot` inside QEMU does NOT guarantee a full UEFI cold boot.
# For our-rollback promote to take effect (new @ subvolume), kill the QEMU process
# entirely and restart it fresh — that is the only reliable "cold reboot" in QEMU.
pkill -f "qemu.*ouroboros-test" 2>/dev/null || true
sleep 3

rm -f /tmp/ouroboros-serial-boot.log

setsid qemu-system-x86_64 \
  -enable-kvm \
  -cpu host \
  -smp 2 \
  -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
  -drive file=/home/ouroboros-test.qcow2,format=qcow2,if=virtio,cache=writeback \
  -netdev user,id=net0,hostfwd=tcp::2223-:22 \
  -device e1000,netdev=net0 \
  -rtc base=utc,clock=host \
  -serial file:/tmp/ouroboros-serial-boot.log \
  -vga std \
  -display none \
  -vnc :1 \
  >/dev/null 2>&1 &

sleep 4
QEMU_PID=$(pgrep -f "qemu.*ouroboros-test" | head -1)
echo "QEMU PID: $QEMU_PID"

# Verify QEMU bound port 2223 (hostfwd active)
ss -tln | grep -q 2223 && echo "✓ port 2223 bound" || echo "✗ QEMU failed — check serial log"

# Wait for login prompt (up to 90s)
timeout 90 bash -c 'until grep -q "login:" /tmp/ouroboros-serial-boot.log 2>/dev/null; do sleep 2; done'
echo "System booted"
```

> **virgl prerequisite:** `pacman -S virglrenderer` on host. If port 2222 doesn't bind,
> check `/tmp/qemu-boot-err.log`. Fallback (no GPU acceleration): replace
> `-device virtio-vga-gl -display egl-headless,gl=on` with `-vga virtio -display none`.

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
# User from tests/qemu/minimal-e2e.yaml: testuser / testpass123
# SSH forwarded to localhost:2222

# Clear stale host key from previous runs
ssh-keygen -R "[localhost]:2223" 2>/dev/null || true

# Wait for SSH to be available (up to 90s)
timeout 90 bash -c 'until sshpass -p "testpass123" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=3 -p 2223 testuser@localhost true 2>/dev/null; do sleep 3; done'
echo "SSH ready"

# Helper alias
SSH="sshpass -p testpass123 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2223 testuser@localhost"
```

### 3.4 System verification commands

```bash
# --- Root filesystem is read-only (Btrfs property — mount option alone is unreliable on Btrfs) ---
$SSH "echo testpass123 | sudo -S btrfs property get / ro 2>/dev/null | grep -q 'ro=true'" && echo "✓ Root is RO (Btrfs property)" || echo "✗ Root is NOT read-only"

# --- No failed systemd units ---
FAILED=$($SSH 'systemctl --failed --no-legend | wc -l')
[[ "$FAILED" -eq 0 ]] && echo "✓ No failed units" || echo "✗ ${FAILED} failed unit(s): $($SSH 'systemctl --failed --no-legend')"

# --- Btrfs subvolumes present ---
for sv in @ @var @etc @home @snapshots; do
  $SSH "echo testpass123 | sudo -S btrfs subvolume list / 2>/dev/null | grep -q '${sv}$'" && echo "✓ Subvolume ${sv}" || echo "✗ Subvolume ${sv} missing"
done

# --- Install snapshot exists ---
$SSH "echo testpass123 | sudo -S btrfs subvolume list / 2>/dev/null | grep -q '@snapshots/install'" && echo "✓ Snapshot install" || echo "✗ Snapshot install missing"

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

# --- our-pac and our-container binaries ---
$SSH 'test -x /usr/local/bin/our-pac' && echo "✓ our-pac installed" || echo "✗ our-pac missing"
$SSH 'test -x /usr/local/bin/our-container' && echo "✓ our-container installed" || echo "✗ our-container missing"
$SSH 'test -L /usr/local/bin/ouroboros-upgrade' && echo "✗ ouroboros-upgrade symlink still present (should be gone)" || echo "✓ ouroboros-upgrade symlink removed"

# --- user created correctly ---
$SSH 'id testuser' | grep -q "wheel" && echo "✓ User testuser in wheel" || echo "✗ User not in wheel"

# --- bootctl EFI binary present ---
$SSH 'test -f /boot/EFI/systemd/systemd-bootx64.efi' && echo "✓ EFI binary present" || echo "✗ EFI binary missing"

# --- resolved.conf on @etc ---
$SSH 'cat /etc/systemd/resolved.conf' | grep "DNSOverTLS" && echo "✓ resolved.conf OK" || echo "✗ resolved.conf missing"
```

### 3.5 our-pac / our-aur over SSH — use nohup (SSH drops during mkinitcpio)

`our-pac -S <pkg>` runs `mkinitcpio` as a pacman hook. This hook can interrupt the SSH connection mid-command, leaving the operation hanging. Always use `nohup` and poll the log:

```bash
# Install a package via our-pac without risking SSH drop
$SSH 'nohup bash -c "echo ouroboros | sudo -S our-pac -S <pkg> --noconfirm" > /tmp/our-pac.log 2>&1 &'

# Poll until done
until $SSH 'grep -qE "boot entries|ERROR|exit" /tmp/our-pac.log 2>/dev/null'; do sleep 5; done
$SSH 'cat /tmp/our-pac.log'
```

Same pattern for `our-aur -S <pkg>` (nspawn container build can also drop SSH).

### 3.6 our-rollback promote — use --force for non-interactive use

`our-rollback promote` requires typing `yes` interactively. In automated E2E use `--force` / `-y`:

```bash
$SSH 'echo ouroboros | sudo -S our-rollback promote <snapshot-name> --force'

# After promote, a FULL cold reboot is required for the new @ to take effect.
# systemctl reboot alone is not sufficient in QEMU (doesn't always cycle UEFI).
# Kill the QEMU process and restart it (see Phase 3.1 boot command above).
pkill -f "qemu.*ouroboros-test"
# → restart QEMU process fresh
```

### 3.7 Launch Hyprland (optional)

```bash
# Launch Hyprland via SSH — compositor runs in guest, visible on VNC :1 (localhost:5901)
$SSH 'WLR_RENDERER=gles2 Hyprland > /tmp/hyprland.log 2>&1 &'
sleep 3
$SSH 'cat /tmp/hyprland.log | head -20'

```

### 3.8 Teardown

```bash
pkill qemu 2>/dev/null || true
echo "Teardown complete"
```

---

## Pass/Fail Summary

| Phase | Check | Expected |
|-------|-------|----------|
| Build | ISO exists, size 800M–2G | ✓ |
| Install | All 13 states completed | ✓ |
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
| Verify | our-pac + our-container present, ouroboros-upgrade symlink absent | ✓ |
| Verify | User testuser in wheel group | ✓ |
| Verify | EFI binary at /boot/EFI/systemd/ | ✓ |

**Overall PASS**: All rows ✓ with zero exceptions.

---

## Known Constraints

| Constraint | Reason |
|-----------|--------|
| Host must have KVM (`/dev/kvm`) | `-enable-kvm` is required for acceptable performance |
| Host RAM ≥ 8 GB for `-m 4096` | 4096 MB allocated to VM; Hyprland profile needs ≥ 4 GB inside guest |
| Disk image: 40G on `/home` | `/tmp` is tmpfs (~4 GB); Hyprland profile + build artifacts need 6-8 GB; 20G too small |
| Use `-device e1000` | virtio-net hangs under sustained download load in QEMU userspace |
| Use `-vga std -display none` | `-vga virtio` is NOT supported in headless mode (exits with error). `-nographic` disables VGA entirely. `-vga std` is the correct headless choice. |
| Use `setsid` to launch QEMU | bash tool kills child processes on timeout; setsid detaches QEMU |
| Use `fuser -k 2223/tcp` before launch | Zombie QEMU from prior run blocks port 2223 |
| Build workdir on `/home` | `/tmp` is tmpfs (~4 GB), ISO build + qcow2 need 6-8 GB |
| `sshpass` required | Automated SSH with password; install via `pacman -S sshpass` |
| `ssh-keygen -R "[localhost]:2223"` before SSH | known_hosts persists between runs, breaking auth |
| Use `echo testpass123 \| sudo -S <cmd>` for privileged cmds | `sudo` in installed system is non-interactive over SSH |
| Use `nohup` for `our-pac`/`our-aur` over SSH | mkinitcpio hook can drop the SSH connection; use nohup + poll log |
| Kill+restart QEMU for cold reboot after promote | `systemctl reboot` in QEMU doesn't guarantee full UEFI cycle; kill the process and relaunch |
| Use `our-rollback promote --force` | Without `--force`, promote waits for interactive `yes` input — hangs over SSH |

## Known Issues

| Issue | Status |
|-------|--------|
| `homectl create --identity=JSON` fails in QEMU | Under investigation — use `homed_storage: classic` in E2E config |
| homed-migrate.sh rollback leaves user as classic | Expected — system functional, home encryption disabled |
| mkarchiso patch must be applied locally before build | `sudo sed -i '537s/^    )"$/    )" \|\| true/' /usr/bin/mkarchiso` — CI applies it automatically but local builds don't |

---

## Phase 5 — Additional Verifications

Run these after the standard Phase 3 verifications for Phase 5 milestones.

### v0.5.0 — system.yaml

```bash
# system.yaml exists and is valid YAML
$SSH 'test -f /etc/ouroboros/system.yaml' && echo "✓ system.yaml" || echo "✗ system.yaml MISSING"
$SSH 'python3 -c "import yaml; yaml.safe_load(open(\"/etc/ouroboros/system.yaml\"))" 2>/dev/null' \
    && echo "✓ YAML válido" || echo "✗ YAML inválido"
$SSH 'grep -q "channel:" /etc/ouroboros/system.yaml' && echo "✓ channel field" || echo "✗"
$SSH 'grep -q "base_packages:" /etc/ouroboros/system.yaml' && echo "✓ base_packages" || echo "✗"
$SSH 'grep -q "users:" /etc/ouroboros/system.yaml' && echo "✓ users" || echo "✗"
```

### v0.5.1 — .snapshot.yaml

```bash
# install snapshot has .snapshot.yaml
$SSH 'echo testpass123 | sudo -S test -f /.snapshots/install/.snapshot.yaml' \
    && echo "✓ install .snapshot.yaml" || echo "✗"
$SSH 'echo testpass123 | sudo -S grep -q "type: install" /.snapshots/install/.snapshot.yaml' \
    && echo "✓ type: install" || echo "✗"

# Create snapshot and verify .snapshot.yaml generated
$SSH 'echo testpass123 | sudo -S our-snapshot create --name phase5-test'
$SSH 'echo testpass123 | sudo -S test -f /.snapshots/phase5-test/.snapshot.yaml' \
    && echo "✓ .snapshot.yaml creado" || echo "✗"

# ouroboros-rebase --dry-run
$SSH 'echo testpass123 | sudo -S ouroboros-rebase --dry-run 2>&1' | grep -qiE "nothing|up.to.date|dry" \
    && echo "✓ rebase dry-run OK" || echo "✗"
```

### v0.5.3 — ouroboros-health

```bash
# Health reports clean system
HEALTH=$($SSH 'echo testpass123 | sudo -S ouroboros-health 2>&1')
echo "$HEALTH" | grep -q "0 failed" && echo "✓ 0 failed units" || echo "✗"
echo "$HEALTH" | grep -q "read-only\|ro=true" && echo "✓ root RO" || echo "✗"
echo "$HEALTH" | grep -q "system.yaml" && echo "✓ system.yaml check" || echo "✗"

# Doctor finds nothing to fix on clean install
$SSH 'echo testpass123 | sudo -S ouroboros-health --doctor 2>&1' \
    | grep -qi "all.*ok\|nothing\|clean" && echo "✓ doctor clean" || echo "✗"
```

### v0.5.4 — Multi-usuario (E2E YAML: phase5-e2e.yaml con 2 usuarios)

```bash
# Both users exist
for user in admin testuser; do
    $SSH "id $user 2>/dev/null" | grep -q "uid=" \
        && echo "✓ user $user exists" || echo "✗ user $user MISSING"
done

# admin in wheel, testuser not
$SSH 'id admin' | grep -q "wheel" && echo "✓ admin in wheel" || echo "✗"
$SSH 'id testuser' | grep -v "wheel" > /dev/null && echo "✓ testuser not in wheel" || echo "✗"

# Homes exist
for user in admin testuser; do
    $SSH "test -d /home/$user" && echo "✓ /home/$user" || echo "✗ /home/$user MISSING"
done

# system.yaml lists both users
$SSH 'grep -c "username:" /etc/ouroboros/system.yaml' | grep -q "2" \
    && echo "✓ 2 users in system.yaml" || echo "✗"
```

### v0.5.5 — homed luks + TPM2/FIDO2

> **QEMU constraint**: `homed_storage: luks` requires a real LUKS-capable kernel path that fails in QEMU userspace. E2E config always uses `classic`. These checks verify the binaries and services are present; full luks/TPM2/FIDO2 flow requires real hardware.

```bash
# systemd-homed service is active
$SSH 'systemctl is-active systemd-homed' | grep -q "active" && echo "✓ systemd-homed active" || echo "✗"

# homectl binary available
$SSH 'test -x /usr/bin/homectl' && echo "✓ homectl present" || echo "✗"

# home directory storage is classic (QEMU constraint acknowledged)
$SSH 'echo testpass123 | sudo -S homectl inspect testuser 2>/dev/null | grep -i storage' \
    | grep -qi "classic\|directory" && echo "✓ storage: classic (QEMU expected)" || echo "⚠ check storage type"

# luks path available in kernel (module loaded, not necessarily used)
$SSH 'echo testpass123 | sudo -S modprobe dm-crypt 2>/dev/null && echo "✓ dm-crypt available" || echo "⚠ dm-crypt not loaded (expected on minimal)"'
```

### v0.5.6 — ouroboros-rebase + our-snapshot diff

```bash
# our-snapshot diff (requires 2+ snapshots)
$SSH 'echo testpass123 | sudo -S our-snapshot diff install phase5-test 2>&1' \
    | grep -qiE "added|modified|deleted|no.diff|identical" && echo "✓ diff OK" || echo "✗"

# pending-verification created by our-pac (mock test)
$SSH 'echo testpass123 | sudo -S our-pac --dry-run -Syu 2>/dev/null || true'
```

### v0.5.7 — GPG signing + bluetooth hook

> **GPG**: signing happens in CI only (requires secrets). QEMU verifies the installed system has the tooling and that the bluetooth hook fires correctly.

```bash
# gpg available in installed system (for manual verification)
$SSH 'test -x /usr/bin/gpg' && echo "✓ gpg present" || echo "✗ gpg missing"

# bluetooth.service disabled when not configured (minimal-e2e.yaml has no bluetooth)
$SSH 'systemctl is-enabled bluetooth 2>/dev/null' \
    | grep -qE "disabled|masked|not-found" && echo "✓ bluetooth disabled (not configured)" || echo "✗ bluetooth unexpectedly enabled"

# For bluetooth E2E: rebuild with a config that sets network.bluetooth.enable: true
# then verify:
#   $SSH 'systemctl is-enabled bluetooth' | grep -q "enabled" && echo "✓ bluetooth enabled" || echo "✗"
#   $SSH 'systemctl is-active bluetooth' | grep -q "active" && echo "✓ bluetooth active" || echo "✗"

# ouroboros-update binary and timer present (v0.5.2, validated alongside v0.5.7)
$SSH 'test -x /usr/local/bin/ouroboros-update' && echo "✓ ouroboros-update present" || echo "✗"
$SSH 'systemctl is-enabled ouroboros-update.timer 2>/dev/null' \
    | grep -q "enabled" && echo "✓ ouroboros-update.timer enabled" || echo "✗"
```

### v0.5.8 — Documentation

> v0.5.8 is documentation-only — no new binaries or services. All checks run on the **host** (repo working tree), not inside the QEMU guest. Run these before cutting the tag.

```bash
REPO=$(git -C . rev-parse --show-toplevel)

# Required files exist
for doc in \
    docs/user-guide.md \
    docs/architecture/our-aur.md \
    docs/architecture/our-flat.md \
    docs/architecture/snapshot-system.md \
    docs/architecture/declarative-system.md \
    docs/architecture/multi-user.md \
    docs/architecture/systemd-integration.md; do
    test -f "$REPO/$doc" \
        && echo "✓ $doc" \
        || echo "✗ $doc MISSING"
done

# user-guide.md covers Phase 5 features
for term in homed "multi-user\|multi user\|usuarios" our-aur our-flat \
            ouroboros-rebase ouroboros-health bluetooth GPG signing; do
    grep -qiE "$term" "$REPO/docs/user-guide.md" \
        && echo "✓ user-guide covers: $term" \
        || echo "✗ user-guide missing: $term"
done

# Architecture docs are not empty stubs (≥ 30 lines each)
for doc in our-aur our-flat snapshot-system declarative-system multi-user; do
    LINES=$(wc -l < "$REPO/docs/architecture/$doc.md" 2>/dev/null || echo 0)
    [[ "$LINES" -ge 30 ]] \
        && echo "✓ docs/architecture/$doc.md ($LINES lines)" \
        || echo "✗ docs/architecture/$doc.md too short or missing ($LINES lines)"
done

# PHASE_5_PLAN.md milestone table has no pending ❌ items (only Phase 6+ deferrals)
PENDING=$(grep -c "| ❌ " "$REPO/docs/PHASE_5_PLAN.md" 2>/dev/null || echo 0)
# ❌ entries for Phase 6+ are expected (5.17-5.20); anything else is a gap
[[ "$PENDING" -le 4 ]] \
    && echo "✓ PHASE_5_PLAN.md: no unexpected pending milestones ($PENDING ❌ = Phase 6+ deferrals)" \
    || echo "✗ PHASE_5_PLAN.md has $PENDING ❌ entries — check for incomplete milestones"
```

## Pass/Fail Summary — Phase 5

| Tag | Check | Expected |
|-----|-------|----------|
| v0.5.0 | system.yaml exists and valid | ✓ |
| v0.5.0 | base_packages + users in system.yaml | ✓ |
| v0.5.1 | .snapshot.yaml in install snapshot | ✓ |
| v0.5.1 | our-snapshot create generates .snapshot.yaml | ✓ |
| v0.5.1 | ouroboros-rebase --dry-run runs without error | ✓ |
| v0.5.3 | ouroboros-health reports 0 failed units | ✓ |
| v0.5.3 | ouroboros-health --doctor reports clean | ✓ |
| v0.5.4 | 2+ users created and functional | ✓ |
| v0.5.4 | Correct wheel membership per user | ✓ |
| v0.5.4 | system.yaml lists all users | ✓ |
| v0.5.5 | systemd-homed active + homectl present | ✓ |
| v0.5.5 | homed_storage: classic in QEMU (luks: real hardware only) | ✓ |
| v0.5.6 | our-snapshot diff runs without error | ✓ |
| v0.5.7 | bluetooth disabled when not configured | ✓ |
| v0.5.7 | ouroboros-update binary + timer enabled | ✓ |
| v0.5.8 | All 7 doc files exist (host check) | ✓ |
| v0.5.8 | user-guide.md covers Phase 5 features (host check) | ✓ |
| v0.5.8 | Architecture docs ≥ 30 lines each (host check) | ✓ |
| v0.5.8 | PHASE_5_PLAN.md has no unexpected pending milestones | ✓ |
