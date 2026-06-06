---
name: qemu-e2e-test
description: >
  Full E2E test workflow for ouroborOS: build ISO with --e2e-config, unattended QEMU install,
  verify installed system via SSH, and run the automated tool suite (tests/scripts/e2e-our-tools.sh).
  Covers the full lifecycle from source to running system. Invoke with /qemu-e2e-test or whenever
  changes land in the installer, configure.sh, snapshot.sh, our_* tools, or the ISO profile.
  Includes Extension Protocol — how to grow this skill as new phases/tools ship.
---

You are executing the **ouroborOS E2E Test Suite** — full lifecycle from source to running system.

---

## Quick Reference — Ports and Credentials

| Config file | SSH port | root password | user |
|---|---|---|---|
| `tests/qemu/phase6-e2e.yaml` | 2225 | `7907` | `hbuddenberg` |
| `tests/qemu/hyprland-e2e.yaml` | 2225 | `toor` | `admin` / `admin` |
| `tests/qemu/minimal-e2e.yaml` | 2225 | set in yaml | set in yaml |

---

## Prerequisites

```bash
# Required packages on host
sudo pacman -S --needed qemu-system-x86 edk2-ovmf openssh sshpass

# OVMF firmware paths (ArchLinux)
OVMF_CODE=/usr/share/edk2/x64/OVMF_CODE.4m.fd    # read-only, shared
OVMF_VARS=/usr/share/edk2/x64/OVMF_VARS.4m.fd    # copy this per VM — DO NOT share

# Repo root must be on dev and clean
git status
```

---

## Phase 1 — Build E2E ISO

```bash
# Always build on a clean tree — --e2e-config injects the YAML into the live ISO
echo "7907" | sudo -S bash src/scripts/build-iso.sh --clean \
  --e2e-config=tests/qemu/<profile>-e2e.yaml

# Expected last lines:
# [OK]  ouroborOS ISO ready.
# [WARN] This ISO is for testing only — NOT for production use.

ls -lh out/ouroborOS-*.iso   # must be between 800 MB and 3 GB
```

**Pass criteria:** exit 0, ISO in `out/`, size 800 MB–3 GB.

---

## Phase 2 — Unattended Install in QEMU

### 2.1 Prepare disk and OVMF VARS

```bash
DISK=/home/hbuddenberg/developments/ouroborOS/out/test-<profile>.qcow2
VARS_COPY=/home/hbuddenberg/developments/ouroborOS/out/test-<profile>-vars.fd

# Always start from fresh disk and fresh VARS
# VARS accumulates boot entries across runs — stale entries cause unexpected boots
rm -f "$DISK" "$VARS_COPY"
qemu-img create -f qcow2 "$DISK" 25G
cp /usr/share/edk2/x64/OVMF_VARS.4m.fd "$VARS_COPY"
```

> **Why copy VARS?** The OVMF VARS file stores UEFI NVRAM (boot entries, SecureBoot keys).
> After install, systemd-boot writes a boot entry there. On subsequent boots UEFI picks it up
> automatically. If you reuse a VARS from a previous install, UEFI may try to boot a ghost entry.

### 2.2 Launch QEMU for install

```bash
ISO=/home/hbuddenberg/developments/ouroborOS/out/ouroborOS-0.6.0-x86_64.iso
OVMF=/usr/share/edk2/x64/OVMF_CODE.4m.fd

# Kill any zombie QEMU on the port first
fuser -k 2225/tcp 2>/dev/null || true

# Use setsid — bash tool kills child processes on timeout
setsid qemu-system-x86_64 \
  -enable-kvm \
  -m 4096 \
  -smp 4 \
  -cpu host \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF" \
  -drive if=pflash,format=raw,file="$VARS_COPY" \
  -drive file="$DISK",format=qcow2,if=virtio \
  -cdrom "$ISO" \
  -boot order=d \
  -device e1000,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2225-:22 \
  -display none \
  -vga std \
  -vnc :3 \
  -serial file:/tmp/ouroboros-install.log \
  -no-reboot \
  > /tmp/qemu-install.log 2>&1 &

sleep 3
QEMU_PID=$(ps aux | grep 'qemu-system-x86_64' | grep "test-<profile>" | grep -v grep | awk '{print $2}')
echo "QEMU PID: $QEMU_PID"
```

> **VNC**: connect to `192.168.1.X:5903` (`:3` offset = port 5903) to watch visually.

### 2.3 Wait for install to complete

```bash
# post_install_action: shutdown causes QEMU to exit (with -no-reboot)
# hyprland profile: ~8 min; minimal profile: ~3 min; gnome/kde: ~15-20 min
DEADLINE=$((SECONDS + 2400))
while kill -0 $QEMU_PID 2>/dev/null; do
  [[ $SECONDS -gt $DEADLINE ]] && echo "TIMEOUT" && break
  echo "$(date '+%H:%M:%S') | $(tail -1 /tmp/ouroboros-install.log 2>/dev/null | tr -d '\r' | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')"
  sleep 15
done
echo "QEMU exited at $(date '+%H:%M:%S')"
```

**Pass criteria:** QEMU exits via `reboot: Power down` in the serial log.

---

## Phase 3 — Boot Installed System

### 3.1 Launch QEMU from disk (no ISO)

```bash
setsid qemu-system-x86_64 \
  -enable-kvm \
  -m 4096 \
  -smp 4 \
  -cpu host \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF" \
  -drive if=pflash,format=raw,file="$VARS_COPY" \
  -drive file="$DISK",format=qcow2,if=virtio \
  -device e1000,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2225-:22 \
  -display none \
  -vga std \
  -vnc :3 \
  -serial file:/tmp/ouroboros-boot.log \
  -no-reboot \
  > /tmp/qemu-boot.log 2>&1 &

sleep 3
QEMU_PID=$(ps aux | grep 'qemu-system-x86_64' | grep "test-<profile>" | grep -v grep | awk '{print $2}')
echo "QEMU PID: $QEMU_PID"
```

### 3.2 Wait for SSH

```bash
# CRITICAL: use sshpass for the wait loop — BatchMode=yes silently fails with password auth
ROOT_PASS=toor   # or 7907 for phase6-e2e

DEADLINE=$((SECONDS + 120))
until sshpass -p "$ROOT_PASS" ssh -p 2225 \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o PasswordAuthentication=yes \
    -o ConnectTimeout=5 \
    root@localhost echo "SSH up" 2>/dev/null; do
  [[ $SECONDS -gt $DEADLINE ]] && echo "TIMEOUT" && break
  echo "$(date '+%H:%M:%S') waiting..."
  sleep 5
done
```

---

## Phase 4 — Run Automated Tool Suite

```bash
E2E_ROOT_PASS=toor E2E_SSH_PORT=2225 bash tests/scripts/e2e-our-tools.sh
```

**Pass criteria: 72/72 PASS** (as of v0.6.0 — number grows with each new phase).

---

## Known Constraints

| Constraint | Reason |
|---|---|
| `-vga std` (not `-vga virtio`, not `-nographic`) | `virtio` VGA fails in headless QEMU builds; `-nographic` disables the VGA needed for VNC. `std` is the reliable headless choice. |
| `-device e1000` (not `virtio-net`) | `virtio-net` hangs under sustained pacstrap download load. |
| `setsid` before QEMU | bash tool kills child processes on timeout; setsid detaches QEMU. |
| `fuser -k 2225/tcp` before launch | A zombie QEMU from a prior run holds the port. |
| Fresh `VARS_COPY` per install | OVMF VARS accumulates boot entries; stale entries cause ghost boot attempts. |
| `sshpass` in wait loop | `-o BatchMode=yes` silently rejects password auth — loop never exits. |
| `build on /home`, not `/tmp` | `/tmp` is tmpfs (~4 GB); ISO build + qcow2 + pacstrap artifacts need 6–8 GB. |
| `homed_storage: classic` in E2E configs | `homectl create` with `subvolume` fails in QEMU (Btrfs subvolume conflict in userspace). |
| `secure_boot: false` in E2E configs | `sbctl` requires real UEFI Setup Mode; OVMF doesn't expose it. |
| `PermitRootLogin yes` (configure.sh) | OpenSSH default is `prohibit-password`; password-based root login is needed for E2E. Already added to configure.sh when `ENABLE_SSH=1`. |
| `PerSourcePenalties no` (configure.sh) | OpenSSH 10.3+ bans IPs after repeated failures; in SLIRP all SSH clients appear as `10.0.2.2`. |
| `nohup` for `our-pac`/`our-aur` | `mkinitcpio` hook can drop the SSH connection mid-command. Use nohup + poll log. |
| Kill+restart QEMU for cold reboot | After `our-rollback promote`, the new `@` only takes effect on a full UEFI cycle. `systemctl reboot` alone is unreliable in QEMU — kill the process and relaunch. |

## Known Issues

| Issue | Status |
|---|---|
| `homectl create --identity=JSON` fails in QEMU | Under investigation — E2E always uses `classic` |
| homed-migrate.sh rollback leaves user as classic | Expected — home unencrypted, system functional |

---

## Phase 5 Verifications (v0.5.x)

Run after Phase 4 on a booted system.

### v0.5.0 — system.yaml

```bash
SSH="sshpass -p $ROOT_PASS ssh -p 2225 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@localhost"

$SSH 'test -f /etc/ouroboros/system.yaml' && echo "✓ system.yaml" || echo "✗"
$SSH 'python3 -c "import yaml; yaml.safe_load(open(\"/etc/ouroboros/system.yaml\"))"' \
    && echo "✓ valid YAML" || echo "✗ invalid"
for field in channel base_packages users; do
  $SSH "grep -q '${field}:' /etc/ouroboros/system.yaml" && echo "✓ $field" || echo "✗ $field"
done
```

### v0.5.1 — .snapshot.yaml

```bash
$SSH 'test -f /.snapshots/install/.snapshot.yaml' && echo "✓" || echo "✗"
$SSH 'grep -q "type: install" /.snapshots/install/.snapshot.yaml' && echo "✓" || echo "✗"
```

### v0.5.3 — ouroboros-health

```bash
$SSH 'ouroboros-health' && echo "✓ exits 0" || echo "✗"
$SSH 'ouroboros-health --json' | python3 -c "import sys,json; d=json.load(sys.stdin); print('✓ JSON valid')" 2>/dev/null || echo "✗ invalid JSON"
$SSH 'ouroboros-health --yaml' | python3 -c "import sys,yaml; yaml.safe_load(sys.stdin); print('✓ YAML valid')" 2>/dev/null || echo "✗ invalid YAML"
```

### v0.5.5 — systemd-homed

```bash
$SSH 'systemctl is-active systemd-homed' | grep -q "active" && echo "✓ homed active" || echo "✗"
$SSH 'test -x /usr/bin/homectl' && echo "✓ homectl" || echo "✗"
```

### v0.5.7 — GPG + bluetooth

```bash
$SSH 'test -x /usr/bin/gpg' && echo "✓ gpg" || echo "✗"
# bluetooth disabled when not configured (no bluetooth.enable: true in E2E config)
$SSH 'systemctl is-enabled bluetooth 2>/dev/null' \
    | grep -qE "disabled|masked|not-found" && echo "✓ bluetooth disabled" || echo "✗"
```

---

## Phase 6 Verifications (v0.6.x)

### v0.6.0 — our-wall (firewalld)

```bash
# firewalld + Python bindings must be installed (auto-installed by e2e-our-tools.sh)
$SSH 'systemctl is-active firewalld' | grep -q active && echo "✓ firewalld active" || echo "✗"
$SSH 'our-wall status' | grep -qi "running\|active" && echo "✓ our-wall status" || echo "✗"
$SSH 'our-wall allow ssh' && echo "✓ allow ssh" || echo "✗"
$SSH 'our-wall deny ssh' && echo "✓ deny ssh" || echo "✗"
$SSH 'our-wall reload' && echo "✓ reload" || echo "✗"
```

### v0.6.0 — SSH opt-in (enable_ssh flag)

```bash
# When enable_ssh: false (default), openssh must NOT be installed
# Check on a system installed without enable_ssh
$SSH 'test -x /usr/bin/sshd' && echo "✗ sshd installed (should NOT be)" || echo "✓ sshd absent"

# When enable_ssh: true, sshd must be active AND accept root password login
$SSH 'systemctl is-active sshd' | grep -q active && echo "✓ sshd active" || echo "✗"
$SSH 'grep -q "PermitRootLogin yes" /etc/ssh/sshd_config' && echo "✓ PermitRootLogin yes" || echo "✗"
$SSH 'grep -q "PerSourcePenalties no" /etc/ssh/sshd_config' && echo "✓ PerSourcePenalties no" || echo "✗"
```

### v0.6.0 — Thunderbolt (bolt)

```bash
# In QEMU there is no Thunderbolt hardware — bolt must NOT be installed
$SSH 'test -x /usr/bin/boltctl' && echo "✗ bolt installed (no Thunderbolt in QEMU)" || echo "✓ bolt absent"
```

### v0.6.0 — Textual TUI files present

```bash
$SSH 'test -f /usr/lib/ouroborOS/installer/tui.py' && echo "✓ tui.py" || echo "✗"
$SSH 'python3 -c "from textual.app import App; print(\"✓ textual importable\")" 2>/dev/null' || echo "✗ textual missing"
```

---

## Pass/Fail Summary — v0.6.0

| Check | Expected |
|---|---|
| ISO builds without error | ✓ |
| QEMU install exits via Power Down | ✓ |
| `ouroborOS 0.6.0` in serial boot log | ✓ |
| correct hostname (from E2E config) in serial log | ✓ |
| sshd starts on installed system | ✓ |
| SSH root login via password works | ✓ |
| root fs is Btrfs ro=true | ✓ |
| `e2e-our-tools.sh`: 72/72 PASS | ✓ |

---

## Extension Protocol — Growing This Skill

When a new phase ships (e.g. v0.7.0, v0.8.0) or a new `our-*` tool lands, follow this protocol:

### Step 1 — Add a new E2E config if the profile is new

```bash
# Copy the closest existing config
cp tests/qemu/phase6-e2e.yaml tests/qemu/<phase>-e2e.yaml

# Adjust:
#   - extra_packages: add anything the new feature needs at install time
#   - desktop.profile: change if testing a GUI profile
#   - post_install_action: shutdown  ← always keep this
#   - network.enable_ssh: true       ← always keep this
#   - homed_storage: classic         ← always keep this (QEMU constraint)
```

### Step 2 — Add a new section to `tests/scripts/e2e-our-tools.sh`

The test script follows this pattern — add a new `section` block at the end, before `RESULTS`:

```bash
# ─────────────────────────────────────────────────────────────
section "N. our-<toolname> — <short description>"
# Auto-install any dependency not in the base profile:
$SSH "command -v <dep> &>/dev/null || our-pac -S <dep> --noconfirm" 2>/dev/null && true
# Happy path
check      "tool exists"               "test -x /usr/local/bin/our-<toolname>"
check      "basic operation"           "our-<toolname> <subcommand>"
check_contains "output contains key"  "expected string"  "our-<toolname> <subcommand> 2>&1"
# Error path (expected failures are documented)
check_fail "invalid subcommand exits 1" "our-<toolname> notacommand"
```

**Helper functions available in the script:**

| Function | Use |
|---|---|
| `check "name" "cmd"` | Pass if exit 0 |
| `check_fail "name" "cmd"` | Pass if exit non-0 |
| `check_contains "name" "pattern" "cmd"` | Pass if stdout contains pattern |
| `section "N. title"` | Print bold section header |

### Step 3 — Add Phase N verifications to this skill

Under a new `## Phase N Verifications (v0.N.x)` heading, document:
1. The new binaries/services that must be present
2. The happy-path functional checks (can be shell snippets)
3. QEMU constraints that apply to this feature (if any)
4. A row in the Pass/Fail Summary table

### Step 4 — Update the Pass/Fail Summary count

When the test count changes, update the **Pass criteria** line in Phase 4:

```
**Pass criteria: NN/NN PASS** (as of v0.N.0 — number grows with each new phase).
```

### Checklist for adding a new `our-*` tool

- [ ] Binary installed at `/usr/local/bin/our-<toolname>` (executable)
- [ ] Tool appears in section 0 SETUP check in `e2e-our-tools.sh`
- [ ] Has its own test section in `e2e-our-tools.sh` covering: exists, basic op, error path
- [ ] If it needs dependencies not in the ISO: auto-install guard at top of the section
- [ ] If it depends on hardware absent from QEMU: skip guard with `SKIP` counter
- [ ] Pass/Fail Summary updated in this skill file
- [ ] E2E YAML config includes any required `extra_packages`

### Checklist for a new feature in an existing tool

- [ ] Add checks to the existing section in `e2e-our-tools.sh`
- [ ] If the feature has QEMU constraints, note them in **Known Constraints**
- [ ] Run the full suite and confirm total count increases by the number of new checks

### When a feature needs real hardware (TPM2, FIDO2, GPU, Thunderbolt)

- Add a skip guard: `$SSH "test -e /sys/bus/thunderbolt || { echo SKIP; exit 0; }"`
- Document it in **Known Constraints** and **Known Issues**
- Write a stub check that verifies the binary/service is present even if the feature can't run:
  ```bash
  check "boltctl binary present (HW test needs real Thunderbolt)" "test -x /usr/bin/boltctl"
  ```
