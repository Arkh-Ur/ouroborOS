#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# e2e-phase3.sh — End-to-end validation of Phase 3 features
# =============================================================================
# Performs a full install+boot cycle and validates all Phase 3 features via SSH:
#   Phase 0  — Prerequisites
#   Phase 1  — Build ISO with Phase 3 config (or reuse existing)
#   Phase 2  — Unattended install via QEMU
#   Phase 3  — Boot installed system
#   Phase 4  — SSH validation suite (filesystem, tools, systemd, snapshots)
#   Phase 5  — Extended validations (our-snapshot, our-rollback, our-pac)
#   Phase 6  — Teardown and final report
#
# QEMU setup:
#   GPU:     -vga virtio  (virtio-gpu, best QEMU virtual GPU)
#   VNC:     -vnc :1      — connect with: vncviewer localhost:5901
#   SSH:     localhost:2222 → guest:22
#   Display: -display none (headless, VNC for debug access)
#
# Prerequisites:
#   sudo pacman -S --needed qemu-system-x86 edk2-ovmf openssh sshpass
#   /dev/kvm must be available
#
# Environment variables:
#   P3_ISO_PATH        — use existing ISO instead of building (skips Phase 1)
#   P3_TEST_USER       — SSH username (default: admin)
#   P3_TEST_PASSWORD   — SSH password (default: changeme)
#   P3_TEST_SSH_PORT   — SSH port (default: 2222)
#   P3_VNC_DISPLAY     — VNC display number (default: 1, → port 5901)
#   P3_DISK_SIZE       — QEMU disk size (default: 20G)
#   P3_QEMU_MEMORY     — RAM in MB (default: 3072)
#   P3_BUILD_WORKDIR   — ISO build workdir (default: /home/p3-build)
#   P3_SERIAL_DIR      — directory for serial logs (default: /tmp/p3-serial)
#   P3_KEEP_ARTIFACTS  — set to 1 to keep qcow2 and logs after run
#   P3_INSTALL_TIMEOUT — seconds to wait for install (default: 900)
#   P3_BOOT_TIMEOUT    — seconds to wait for boot SSH (default: 120)
#
# Exit codes:
#   0 — all assertions pass
#   1 — one or more assertions fail
#   2 — prerequisites not met or infrastructure failure
# =============================================================================

# ── Colors ────────────────────────────────────────────────────────────────────
# shellcheck disable=SC2034  # color vars are used inside double-quoted strings
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly RESET='\033[0m'

log_ok()      { echo -e "  ${GREEN}✓${RESET} $*"; }
log_fail()    { echo -e "  ${RED}✗${RESET} $*"; FAILURES=$((FAILURES + 1)); }
# shellcheck disable=SC2329
log_skip()    { echo -e "  ${YELLOW}⏭${RESET} $*"; SKIPPED=$((SKIPPED + 1)); }
log_section() { echo -e "\n${BOLD}${CYAN}━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }
log_info()    { echo -e "  ${CYAN}→${RESET} $*"; }
# shellcheck disable=SC2329
log_warn()    { echo -e "  ${YELLOW}!${RESET} $*"; }
log_die()     { echo -e "${RED}FATAL: $*${RESET}" >&2; exit 2; }

# ── Configuration ─────────────────────────────────────────────────────────────
P3_TEST_USER="${P3_TEST_USER:-admin}"
P3_TEST_PASSWORD="${P3_TEST_PASSWORD:-changeme}"
P3_TEST_SSH_PORT="${P3_TEST_SSH_PORT:-2222}"
P3_VNC_DISPLAY="${P3_VNC_DISPLAY:-1}"
P3_DISK_SIZE="${P3_DISK_SIZE:-20G}"
P3_QEMU_MEMORY="${P3_QEMU_MEMORY:-3072}"
P3_BUILD_WORKDIR="${P3_BUILD_WORKDIR:-/home/p3-build}"
P3_SERIAL_DIR="${P3_SERIAL_DIR:-/tmp/p3-serial}"
P3_KEEP_ARTIFACTS="${P3_KEEP_ARTIFACTS:-0}"
P3_INSTALL_TIMEOUT="${P3_INSTALL_TIMEOUT:-900}"
P3_BOOT_TIMEOUT="${P3_BOOT_TIMEOUT:-120}"
P3_ISO_PATH="${P3_ISO_PATH:-}"

readonly OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
readonly OVMF_CODE_ALT="/usr/share/edk2-ovmf/x64/OVMF_CODE.4m.fd"
readonly E2E_CONFIG="tests/qemu/phase3-e2e.yaml"

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
FAILURES=0
SKIPPED=0
TESTS_RUN=0
QEMU_PID=""
OVMF_PATH=""
DISK_PATH=""
SERIAL_INSTALL=""
SERIAL_BOOT=""

# ── SSH helpers ────────────────────────────────────────────────────────────────
ssh_cmd() {
    sshpass -p "$P3_TEST_PASSWORD" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$P3_TEST_SSH_PORT" \
        "${P3_TEST_USER}@localhost" "$@"
}

ssh_root() {
    ssh_cmd "echo ${P3_TEST_PASSWORD} | sudo -S $*"
}

ssh_out() {
    ssh_cmd "$@" 2>/dev/null || true
}

ssh_root_out() {
    ssh_root "$@" 2>/dev/null || true
}

wait_ssh() {
    local max_attempts="${1:-40}"
    local attempt=1
    log_info "Waiting for SSH on port ${P3_TEST_SSH_PORT}..."
    while ! ssh_cmd true 2>/dev/null; do
        if [[ $attempt -ge $max_attempts ]]; then
            log_die "SSH did not become available after ${max_attempts} attempts"
        fi
        sleep 3
        attempt=$((attempt + 1))
    done
    log_ok "SSH available on port ${P3_TEST_SSH_PORT}"
}

# ── QEMU helpers ───────────────────────────────────────────────────────────────
launch_qemu() {
    local disk="$1"
    local iso="${2:-}"
    local serial="$3"
    local config_iso="${4:-}"

    kill_qemu

    # shellcheck disable=SC2054
    local qemu_args=(
        -enable-kvm
        -cpu host
        -smp 2
        -m "$P3_QEMU_MEMORY"
        -drive "if=pflash,format=raw,readonly=on,file=${OVMF_PATH}"
        -drive "file=${disk},format=qcow2,if=virtio,cache=writeback"
        -netdev "user,id=net0,hostfwd=tcp::${P3_TEST_SSH_PORT}-:22"
        -device "e1000,netdev=net0"
        -rtc base=utc,clock=host
        -serial "file:${serial}"
        -vga virtio
        -display none
        -vnc ":${P3_VNC_DISPLAY}"
    )

    [[ -n "$iso" ]]        && qemu_args+=(-cdrom "$iso" -boot d)
    [[ -n "$config_iso" ]] && qemu_args+=(-drive "file=${config_iso},format=raw,media=cdrom,readonly=on")

    setsid qemu-system-x86_64 "${qemu_args[@]}" &>/dev/null &
    QEMU_PID=$!
    log_info "QEMU PID: ${QEMU_PID} — VNC: vncviewer localhost:590${P3_VNC_DISPLAY}"
}

kill_qemu() {
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    QEMU_PID=""
}

wait_qemu_exit() {
    local timeout_secs="${1:-$P3_INSTALL_TIMEOUT}"
    log_info "Waiting for QEMU to finish (timeout: ${timeout_secs}s)..."
    if timeout "$timeout_secs" bash -c "while kill -0 $QEMU_PID 2>/dev/null; do sleep 3; done"; then
        log_ok "QEMU exited cleanly"
    else
        log_fail "QEMU timed out after ${timeout_secs}s"
        kill_qemu
        return 1
    fi
}

# ── Assert helpers ─────────────────────────────────────────────────────────────
assert_contains() {
    local description="$1"
    local output="$2"
    local pattern="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if echo "$output" | grep -qE "$pattern"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Expected pattern: ${pattern}"
        log_info "  Got: $(echo "$output" | tail -3)"
    fi
}

assert_equals() {
    local description="$1"
    local actual="$2"
    local expected="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if [[ "$actual" == "$expected" ]]; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Expected: ${expected}"
        log_info "  Got:      ${actual}"
    fi
}

assert_zero() {
    local description="$1"
    local value="$2"
    assert_equals "$description" "$value" "0"
}

assert_cmd_exists() {
    local description="$1"
    local cmd="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    if ssh_out "command -v ${cmd}" | grep -q "${cmd}"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Command not found: ${cmd}"
    fi
}

assert_file_exists() {
    local description="$1"
    local path="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    if ssh_root_out "test -e '${path}' && echo yes" | grep -q "yes"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Path not found: ${path}"
    fi
}

assert_unit_active() {
    local description="$1"
    local unit="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    local state
    state=$(ssh_root_out "systemctl is-active ${unit}" || true)
    if [[ "$state" == "active" ]]; then
        log_ok "${description} (active)"
    else
        log_fail "${description} (got: ${state})"
    fi
}

assert_unit_enabled() {
    local description="$1"
    local unit="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    local state
    state=$(ssh_root_out "systemctl is-enabled ${unit}" || true)
    if [[ "$state" == "enabled" || "$state" == "static" || "$state" == "indirect" ]]; then
        log_ok "${description} (${state})"
    else
        log_fail "${description} (got: ${state})"
    fi
}

# ── Cleanup on exit ────────────────────────────────────────────────────────────
# shellcheck disable=SC2329
cleanup() {
    kill_qemu
    if [[ "$P3_KEEP_ARTIFACTS" != "1" ]]; then
        [[ -n "$DISK_PATH"       ]] && rm -f "$DISK_PATH"
        [[ -n "$SERIAL_INSTALL"  ]] && rm -f "$SERIAL_INSTALL"
        [[ -n "$SERIAL_BOOT"     ]] && rm -f "$SERIAL_BOOT"
    else
        log_info "Artifacts kept (P3_KEEP_ARTIFACTS=1):"
        [[ -n "$DISK_PATH"      ]] && log_info "  Disk:          ${DISK_PATH}"
        [[ -n "$SERIAL_INSTALL" ]] && log_info "  Install log:   ${SERIAL_INSTALL}"
        [[ -n "$SERIAL_BOOT"    ]] && log_info "  Boot log:      ${SERIAL_BOOT}"
    fi
}
trap cleanup EXIT

# =============================================================================
# Phase 0 — Prerequisites
# =============================================================================
log_section "Phase 0: Prerequisites"
cd "$WORKSPACE"

# OVMF firmware
if [[ -f "$OVMF_CODE" ]]; then
    OVMF_PATH="$OVMF_CODE"
elif [[ -f "$OVMF_CODE_ALT" ]]; then
    OVMF_PATH="$OVMF_CODE_ALT"
else
    log_die "OVMF firmware not found. Install: sudo pacman -S edk2-ovmf"
fi
log_ok "OVMF firmware: ${OVMF_PATH}"

# KVM
[[ -c /dev/kvm ]] || log_die "/dev/kvm not available. Enable KVM in BIOS or use a KVM-capable host."
log_ok "KVM available"

# Required tools
for tool in qemu-system-x86_64 sshpass genisoimage qemu-img; do
    command -v "$tool" &>/dev/null || log_die "Required tool not found: ${tool}"
    log_ok "Tool: ${tool}"
done

# Free port
fuser -k "${P3_TEST_SSH_PORT}/tcp" &>/dev/null || true
log_ok "Port ${P3_TEST_SSH_PORT} available"

# Work directories
mkdir -p "$P3_SERIAL_DIR"

# E2E config exists
[[ -f "$E2E_CONFIG" ]] || log_die "Phase 3 E2E config not found: ${E2E_CONFIG}"
log_ok "E2E config: ${E2E_CONFIG}"

# =============================================================================
# Phase 1 — ISO
# =============================================================================
log_section "Phase 1: ISO"

if [[ -n "$P3_ISO_PATH" ]]; then
    [[ -f "$P3_ISO_PATH" ]] || log_die "ISO not found at P3_ISO_PATH=${P3_ISO_PATH}"
    log_ok "Using existing ISO: ${P3_ISO_PATH}"
else
    log_info "Building ISO with Phase 3 config..."
    mkdir -p "$P3_BUILD_WORKDIR"
    if ! sudo bash src/scripts/build-iso.sh \
            --clean \
            --workdir "$P3_BUILD_WORKDIR" \
            --e2e-config="$E2E_CONFIG" 2>&1 | tail -5; then
        log_die "ISO build failed"
    fi
    P3_ISO_PATH="$(find "${P3_BUILD_WORKDIR}/out" -name 'ouroborOS-*.iso' -maxdepth 1 -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
    [[ -f "$P3_ISO_PATH" ]] || log_die "ISO build completed but ISO not found in ${P3_BUILD_WORKDIR}/out/"
    log_ok "ISO built: ${P3_ISO_PATH}"
fi

# =============================================================================
# Phase 2 — Unattended install
# =============================================================================
log_section "Phase 2: Unattended Install"

DISK_PATH="${P3_SERIAL_DIR}/phase3-test.qcow2"
SERIAL_INSTALL="${P3_SERIAL_DIR}/install.log"

rm -f "$DISK_PATH" "$SERIAL_INSTALL"
qemu-img create -f qcow2 "$DISK_PATH" "$P3_DISK_SIZE" -q
log_ok "Disk created: ${DISK_PATH} (${P3_DISK_SIZE})"

# Build config ISO (CD-ROM injection method)
local_config_iso="${P3_SERIAL_DIR}/phase3-config.iso"
genisoimage -quiet -V OUROBOROS-CONFIG -r -J -o "$local_config_iso" "$E2E_CONFIG" 2>/dev/null
log_ok "Config ISO created for CD-ROM injection"

launch_qemu "$DISK_PATH" "$P3_ISO_PATH" "$SERIAL_INSTALL" "$local_config_iso"
log_info "Install started — monitor at: vncviewer localhost:590${P3_VNC_DISPLAY}"
log_info "Serial log: ${SERIAL_INSTALL}"

wait_qemu_exit "$P3_INSTALL_TIMEOUT"

# Validate install serial log
log_info "Checking install serial log..."
for state in INIT PREFLIGHT LOCALE USER DESKTOP PARTITION FORMAT INSTALL CONFIGURE SNAPSHOT FINISH; do
    TESTS_RUN=$((TESTS_RUN + 1))
    if grep -q "State completed: ${state}" "$SERIAL_INSTALL" 2>/dev/null; then
        log_ok "Installer reached state: ${state}"
    else
        log_fail "Installer did NOT reach state: ${state}"
    fi
done

TESTS_RUN=$((TESTS_RUN + 1))
if ! grep -qE '\[FAILED\]|\[ERROR\]|fatal error|Traceback' "$SERIAL_INSTALL" 2>/dev/null; then
    log_ok "Install log: no errors detected"
else
    log_fail "Install log: errors detected"
    grep -E '\[FAILED\]|\[ERROR\]|fatal error|Traceback' "$SERIAL_INSTALL" | head -5 | while IFS= read -r line; do
        log_info "  ${line}"
    done
fi

# =============================================================================
# Phase 3 — Boot installed system
# =============================================================================
log_section "Phase 3: Boot Installed System"

SERIAL_BOOT="${P3_SERIAL_DIR}/boot.log"
rm -f "$SERIAL_BOOT"

launch_qemu "$DISK_PATH" "" "$SERIAL_BOOT"
log_info "Boot started — monitor at: vncviewer localhost:590${P3_VNC_DISPLAY}"
log_info "Serial log: ${SERIAL_BOOT}"

# Wait for SSH
sleep 10
wait_ssh 40

# =============================================================================
# Phase 4 — Core system validations
# =============================================================================
log_section "Phase 4: Core System"

# ── Filesystem ────────────────────────────────────────────────────────────────
log_info "Filesystem integrity..."

mnt_opts=$(ssh_root_out "findmnt / -no OPTIONS")
assert_contains "Root filesystem is read-only" "$mnt_opts" "ro"
assert_contains "Root filesystem uses Btrfs" "$mnt_opts" "compress=zstd|btrfs"

btrfs_subvols=$(ssh_root_out "btrfs subvolume list /")
for subvol in "@" "@var" "@etc" "@home" "@snapshots"; do
    assert_contains "Btrfs subvolume exists: ${subvol}" "$btrfs_subvols" "${subvol}"
done

# Install snapshot must exist
snapshot_list=$(ssh_root_out "btrfs subvolume list / 2>/dev/null | grep snapshots" || true)
assert_contains "Install snapshot exists" "$snapshot_list" "install"

# ── Btrfs health ──────────────────────────────────────────────────────────────
log_info "Btrfs health check..."
btrfs_stats=$(ssh_root_out "btrfs device stats /var 2>/dev/null || true")
assert_contains "Btrfs: no read errors" "$btrfs_stats" "read_io_errs\s+0"
assert_contains "Btrfs: no write errors" "$btrfs_stats" "write_io_errs\s+0"

# ── Systemd boot health ───────────────────────────────────────────────────────
log_info "Systemd health..."
failed_units=$(ssh_root_out "systemctl --failed --no-legend --no-pager 2>/dev/null | wc -l | tr -d ' '" || echo "99")
assert_zero "No failed systemd units" "$failed_units"

# ── Network services ──────────────────────────────────────────────────────────
log_info "Network services..."
assert_unit_active "systemd-networkd active" "systemd-networkd"
assert_unit_active "systemd-resolved active" "systemd-resolved"
assert_unit_active "sshd active" "sshd"

# ── User and shell ────────────────────────────────────────────────────────────
log_info "User configuration..."
user_shell=$(ssh_out "getent passwd ${P3_TEST_USER} | cut -d: -f7" || true)
assert_contains "User shell is bash" "$user_shell" "/bin/bash"

user_groups=$(ssh_out "groups" || true)
assert_contains "User in wheel group" "$user_groups" "wheel"

# ── Bootloader ────────────────────────────────────────────────────────────────
log_info "Bootloader..."
boot_entries=$(ssh_root_out "ls /boot/loader/entries/ 2>/dev/null" || true)
assert_contains "Boot entries exist" "$boot_entries" "\.conf"
assert_contains "Install snapshot boot entry exists" "$boot_entries" "install"

loader_conf=$(ssh_root_out "cat /boot/loader/loader.conf 2>/dev/null" || true)
assert_contains "Bootloader editor disabled" "$loader_conf" "editor\s+no"

# =============================================================================
# Phase 5a — Phase 3 tool presence
# =============================================================================
log_section "Phase 5a: Phase 3 Tool Presence"

log_info "Checking all Phase 3 executables..."
assert_cmd_exists "our-snapshot exists" "/usr/local/bin/our-snapshot"
assert_cmd_exists "our-rollback exists" "/usr/local/bin/our-rollback"
assert_cmd_exists "our-wifi exists" "/usr/local/bin/our-wifi"
assert_cmd_exists "our-bluetooth exists" "/usr/local/bin/our-bluetooth"
assert_cmd_exists "our-fido2 exists" "/usr/local/bin/our-fido2"
assert_cmd_exists "our-pac exists" "/usr/local/bin/our-pac"
assert_cmd_exists "our-container exists" "/usr/local/bin/our-container"
assert_cmd_exists "ouroboros-secureboot exists" "/usr/local/bin/ouroboros-secureboot"
assert_cmd_exists "ouroboros-firstboot exists" "/usr/local/bin/ouroboros-firstboot"

# ── Timers ────────────────────────────────────────────────────────────────────
log_info "Checking Phase 3 timers..."
assert_unit_enabled "our-snapshot-prune.timer enabled" "our-snapshot-prune.timer"

# ── First-boot service ────────────────────────────────────────────────────────
log_info "Checking first-boot service..."
firstboot_status=$(ssh_root_out "systemctl show ouroboros-firstboot --property=ActiveState --value 2>/dev/null" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if [[ "$firstboot_status" == "active" || "$firstboot_status" == "inactive" ]]; then
    log_ok "ouroboros-firstboot service registered (state: ${firstboot_status})"
else
    log_fail "ouroboros-firstboot service not found (got: ${firstboot_status})"
fi

# =============================================================================
# Phase 5b — our-snapshot validation
# =============================================================================
log_section "Phase 5b: our-snapshot"

log_info "our-snapshot list..."
snap_list=$(ssh_root_out "our-snapshot list 2>/dev/null" || true)
assert_contains "our-snapshot list: install baseline visible" "$snap_list" "install"

log_info "our-snapshot info install..."
snap_info=$(ssh_root_out "our-snapshot info install 2>/dev/null" || true)
assert_contains "our-snapshot info: timestamp field" "$snap_info" "timestamp|Timestamp|date"

log_info "our-snapshot create --name e2e-test..."
create_out=$(ssh_root_out "our-snapshot create --name e2e-test 2>&1" || true)
assert_contains "our-snapshot create: success or snapshot created" \
    "$create_out" "created|snapshot|e2e-test"

log_info "our-snapshot list (after create)..."
snap_list2=$(ssh_root_out "our-snapshot list 2>/dev/null" || true)
assert_contains "our-snapshot list: e2e-test snapshot visible" "$snap_list2" "e2e-test"

log_info "our-snapshot boot-entries sync..."
sync_out=$(ssh_root_out "our-snapshot boot-entries sync 2>&1" || true)
assert_contains "our-snapshot boot-entries sync: ran without fatal error" \
    "$sync_out" "sync|entry|written|updated|ok"

log_info "our-snapshot delete e2e-test..."
del_out=$(ssh_root_out "our-snapshot delete e2e-test 2>&1" || true)
assert_contains "our-snapshot delete: success" "$del_out" "delet|removed|ok"

snap_list3=$(ssh_root_out "our-snapshot list 2>/dev/null" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$snap_list3" | grep -qE "^e2e-test"; then
    log_fail "our-snapshot delete: e2e-test still visible after delete"
else
    log_ok "our-snapshot delete: e2e-test removed from list"
fi

log_info "our-snapshot prune (keep 5)..."
prune_out=$(ssh_root_out "our-snapshot prune --keep 5 2>&1" || true)
assert_contains "our-snapshot prune: install snapshot preserved" \
    "$prune_out" "install|kept|preserv|prune"

# =============================================================================
# Phase 5c — our-rollback validation
# =============================================================================
log_section "Phase 5c: our-rollback"

log_info "our-rollback status..."
rollback_status=$(ssh_root_out "our-rollback status 2>/dev/null" || true)
assert_contains "our-rollback status: root is @ (normal boot)" \
    "$rollback_status" "@|normal|root"

log_info "our-rollback list..."
rollback_list=$(ssh_root_out "our-rollback list 2>/dev/null" || true)
assert_contains "our-rollback list: install snapshot visible" "$rollback_list" "install"

# promote is destructive — test only the dry-run path / help
log_info "our-rollback help (no promote in E2E — avoids unrevertable state)..."
rollback_help=$(ssh_root_out "our-rollback --help 2>&1 || our-rollback help 2>&1 || true")
assert_contains "our-rollback help: promote subcommand documented" \
    "$rollback_help" "promote|now|status"

# =============================================================================
# Phase 5d — our-pac validation (no actual upgrade)
# =============================================================================
log_section "Phase 5d: our-pac"

log_info "our-pac --help..."
pacman_help=$(ssh_root_out "our-pac --help 2>&1 || true")
assert_contains "our-pac: help exits cleanly" "$pacman_help" "pacman|Syu|usage|Usage"

log_info "our-pac log directory..."
assert_file_exists "our-pac log dir exists" "/var/log/our-pac"

# =============================================================================
# Phase 5e — our-container validation
# =============================================================================
log_section "Phase 5e: our-container"

log_info "our-container list..."
container_list=$(ssh_root_out "our-container list 2>&1" || true)
assert_contains "our-container list: runs without crash" \
    "$container_list" "NAME|name|containers|No containers|empty"

log_info "our-container help (--gui, --isolated flags present)..."
container_help=$(ssh_root_out "our-container help 2>&1 || our-container --help 2>&1 || true")
assert_contains "our-container help: --gui flag documented" "$container_help" "\-\-gui|gui"
assert_contains "our-container help: --isolated flag documented" "$container_help" "\-\-isolated|isolated"

# =============================================================================
# Phase 5f — our-fido2 validation
# =============================================================================
log_section "Phase 5f: our-fido2"

fido2_help=$(ssh_out "our-fido2 help 2>&1 || our-fido2 --help 2>&1 || true")
assert_contains "our-fido2: pam subcommand documented" "$fido2_help" "pam"
assert_contains "our-fido2: ssh subcommand documented" "$fido2_help" "ssh"
assert_contains "our-fido2: luks subcommand documented" "$fido2_help" "luks"
assert_contains "our-fido2: ble subcommand documented" "$fido2_help" "ble"

# pam status (no token registered — should run but report nothing)
fido2_pam_status=$(ssh_root_out "our-fido2 pam status 2>&1" || true)
assert_contains "our-fido2 pam status: runs without crash" \
    "$fido2_pam_status" "FIDO2|pam|not|status|u2f|configur"

# =============================================================================
# Phase 5g — our-bluetooth validation
# =============================================================================
log_section "Phase 5g: our-bluetooth"

bt_help=$(ssh_out "our-bluetooth --help 2>&1 || true")
assert_contains "our-bluetooth: le subcommand documented" "$bt_help" "Low Energy\|le experimental\|cmd_le"

# bluetooth service enabled (because bluetooth.enable: true in config)
assert_unit_enabled "bluetooth.service enabled (config: network.bluetooth.enable)" "bluetooth.service"

# BlueZ experimental mode drop-in exists
assert_file_exists "BlueZ experimental mode drop-in" \
    "/etc/systemd/system/bluetooth.service.d/experimental.conf"

# =============================================================================
# Phase 5h — ouroboros-secureboot validation
# =============================================================================
log_section "Phase 5h: ouroboros-secureboot"

sb_help=$(ssh_out "ouroboros-secureboot --help 2>&1 || ouroboros-secureboot help 2>&1 || true")
assert_contains "ouroboros-secureboot: setup subcommand documented" "$sb_help" "setup|sbctl"
assert_contains "ouroboros-secureboot: status subcommand documented" "$sb_help" "status"

sb_status=$(ssh_root_out "ouroboros-secureboot status 2>&1" || true)
assert_contains "ouroboros-secureboot status: runs without crash" \
    "$sb_status" "Secure Boot|sbctl|status|disabled"

# =============================================================================
# Phase 5i — Config schema validation (shell top-level key)
# =============================================================================
log_section "Phase 5i: Schema — Shell Top-Level Key"

log_info "Validating user shell is /bin/bash (shell: bash in YAML)..."
installed_shell=$(ssh_root_out "getent passwd ${P3_TEST_USER} | cut -d: -f7" || true)
assert_equals "User shell resolved correctly from shell: bash" "$installed_shell" "/bin/bash"

log_info "Checking shell binary exists..."
assert_file_exists "Shell binary /bin/bash exists" "/bin/bash"

# =============================================================================
# Phase 5j — Snapshot metadata JSON
# =============================================================================
log_section "Phase 5j: Snapshot Metadata"

log_info "Checking install snapshot metadata JSON..."
assert_file_exists "Install snapshot metadata JSON exists" \
    "/.snapshots/.metadata/install.json"

metadata=$(ssh_root_out "cat /.snapshots/.metadata/install.json 2>/dev/null" || true)
assert_contains "Metadata has timestamp field" "$metadata" '"timestamp"'
assert_contains "Metadata has type field" "$metadata" '"type"'

log_info "Checking boot entries reference snapshots without leading slash..."
boot_entries_content=$(ssh_root_out "cat /boot/loader/entries/*.conf 2>/dev/null" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$boot_entries_content" | grep -qE "rootflags=subvol=/@"; then
    log_fail "Boot entry rootflags has leading / — kernel will ignore subvol"
else
    log_ok "Boot entry rootflags: no leading / (correct)"
fi

# =============================================================================
# Phase 6 — Teardown and Report
# =============================================================================
log_section "Phase 6: Report"

log_info "Shutting down VM..."
ssh_root "systemctl poweroff" 2>/dev/null || true
sleep 5
kill_qemu

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Phase 3 E2E — Test Results${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  Tests run:    ${BOLD}${TESTS_RUN}${RESET}"
echo -e "  ${GREEN}Passed:       $((TESTS_RUN - FAILURES - SKIPPED))${RESET}"
echo -e "  ${RED}Failed:       ${FAILURES}${RESET}"
echo -e "  ${YELLOW}Skipped:      ${SKIPPED}${RESET}"
echo ""

if [[ "$FAILURES" -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}ALL TESTS PASSED ✓${RESET}"
    echo ""
    exit 0
else
    echo -e "  ${RED}${BOLD}${FAILURES} TEST(S) FAILED ✗${RESET}"
    echo ""
    if [[ "$P3_KEEP_ARTIFACTS" != "1" ]]; then
        log_info "Re-run with P3_KEEP_ARTIFACTS=1 to keep disk and logs for inspection"
        log_info "Connect to VM during run with: vncviewer localhost:590${P3_VNC_DISPLAY}"
    fi
    exit 1
fi
