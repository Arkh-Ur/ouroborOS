#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail
# =============================================================================
# e2e-phase6.sh — E2E tests for ouroborOS v0.6.0
# =============================================================================
# Tests:
#   Phase 0  — Prerequisites
#   Phase 1  — ISO build (or re-use existing)
#   Phase 2  — Unattended install in QEMU
#   Phase 3  — Boot installed system + SSH ready
#   Phase 4  — Core system health (baseline)
#   Phase 5  — our-wall: binary presence, permissions, firewalld state
#   Phase 6  — our-wall: allow/deny/list/preset (firewall rule operations)
#   Phase 7  — ouroboros-install launcher: binary presence + permissions
#   Phase 8  — Textual TUI files present on installed system
#   Phase 9  — Thunderbolt: NOT detected in QEMU, bolt NOT installed
#   Phase 10 — Report
#
# Variables (all have defaults):
#   P6_TEST_USER       — SSH username (default: admin)
#   P6_TEST_PASSWORD   — SSH password (default: changeme)
#   P6_TEST_SSH_PORT   — SSH port (default: 2224)
#   P6_VNC_DISPLAY     — VNC display number (default: 3, → port 5903)
#   P6_DISK_SIZE       — QEMU disk size (default: 15G)
#   P6_QEMU_MEMORY     — RAM in MB (default: 2048)
#   P6_BUILD_WORKDIR   — ISO build workdir (default: /home/p6-build)
#   P6_SERIAL_DIR      — directory for serial logs (default: /tmp/p6-serial)
#   P6_KEEP_ARTIFACTS  — set to 1 to keep disk + logs after run (default: 0)
#   P6_ISO_PATH        — path to pre-built ISO; skips build step if set
#   P6_INSTALL_TIMEOUT — seconds to wait for install (default: 600)
#   P6_BOOT_TIMEOUT    — seconds to wait for boot SSH (default: 120)

# ── Source shared E2E infrastructure ──────────────────────────────────────────
# shellcheck disable=SC2034
E2E_PREFIX="P6"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/e2e-common.sh"

# ── Configuration ─────────────────────────────────────────────────────────────
P6_TEST_USER="${P6_TEST_USER:-admin}"
P6_TEST_PASSWORD="${P6_TEST_PASSWORD:-changeme}"
P6_TEST_SSH_PORT="${P6_TEST_SSH_PORT:-2224}"
P6_VNC_DISPLAY="${P6_VNC_DISPLAY:-3}"
P6_DISK_SIZE="${P6_DISK_SIZE:-15G}"
P6_QEMU_MEMORY="${P6_QEMU_MEMORY:-2048}"
P6_BUILD_WORKDIR="${P6_BUILD_WORKDIR:-/home/p6-build}"
P6_SERIAL_DIR="${P6_SERIAL_DIR:-/tmp/p6-serial}"
P6_KEEP_ARTIFACTS="${P6_KEEP_ARTIFACTS:-0}"
P6_INSTALL_TIMEOUT="${P6_INSTALL_TIMEOUT:-600}"
P6_BOOT_TIMEOUT="${P6_BOOT_TIMEOUT:-120}"
P6_ISO_PATH="${P6_ISO_PATH:-}"

readonly OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
readonly OVMF_CODE_ALT="/usr/share/edk2-ovmf/x64/OVMF_CODE.4m.fd"
readonly E2E_CONFIG="tests/qemu/phase6-e2e.yaml"

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
FAILURES=0
SKIPPED=0
TESTS_RUN=0
# shellcheck disable=SC2034
QEMU_PID=""
OVMF_PATH=""
DISK_PATH=""
SERIAL_INSTALL=""
SERIAL_BOOT=""

# ── Cleanup on exit ────────────────────────────────────────────────────────────
# shellcheck disable=SC2329
cleanup() {
    kill_qemu
    if [[ "$P6_KEEP_ARTIFACTS" != "1" ]]; then
        [[ -n "$DISK_PATH"       ]] && rm -f "$DISK_PATH"
        [[ -n "$SERIAL_INSTALL"  ]] && rm -f "$SERIAL_INSTALL"
        [[ -n "$SERIAL_BOOT"     ]] && rm -f "$SERIAL_BOOT"
        [[ -n "${local_config_iso:-}" ]] && rm -f "$local_config_iso"
    else
        log_info "Artifacts kept (P6_KEEP_ARTIFACTS=1):"
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

if [[ -f "$OVMF_CODE" ]]; then
    OVMF_PATH="$OVMF_CODE"
elif [[ -f "$OVMF_CODE_ALT" ]]; then
    OVMF_PATH="$OVMF_CODE_ALT"
else
    log_die "OVMF firmware not found. Install: sudo pacman -S edk2-ovmf"
fi
log_ok "OVMF firmware: ${OVMF_PATH}"

[[ -c /dev/kvm ]] || log_die "/dev/kvm not available. Enable KVM in BIOS or use a KVM-capable host."
log_ok "KVM available"

for tool in qemu-system-x86_64 sshpass genisoimage qemu-img; do
    command -v "$tool" &>/dev/null || log_die "Required tool not found: ${tool}"
    log_ok "Tool: ${tool}"
done

fuser -k "${P6_TEST_SSH_PORT}/tcp" &>/dev/null || true
log_ok "Port ${P6_TEST_SSH_PORT} available"

mkdir -p "$P6_SERIAL_DIR"

[[ -f "$E2E_CONFIG" ]] || log_die "Phase 6 E2E config not found: ${E2E_CONFIG}"
log_ok "E2E config: ${E2E_CONFIG}"

# =============================================================================
# Phase 1 — ISO
# =============================================================================
log_section "Phase 1: ISO"

if [[ -n "$P6_ISO_PATH" ]]; then
    [[ -f "$P6_ISO_PATH" ]] || log_die "ISO not found at P6_ISO_PATH=${P6_ISO_PATH}"
    log_ok "Using existing ISO: ${P6_ISO_PATH}"
else
    log_info "Building ISO with Phase 6 config..."
    mkdir -p "$P6_BUILD_WORKDIR" "${P6_BUILD_WORKDIR}/out"
    if ! sudo bash src/scripts/build-iso.sh \
            --clean \
            --workdir "$P6_BUILD_WORKDIR" \
            --output "${P6_BUILD_WORKDIR}/out" \
            --e2e-config="$E2E_CONFIG" 2>&1 | tail -5; then
        log_die "ISO build failed"
    fi
    P6_ISO_PATH="$(find "${P6_BUILD_WORKDIR}/out" -name 'ouroborOS-*.iso' -maxdepth 1 -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
    [[ -f "$P6_ISO_PATH" ]] || log_die "ISO build completed but ISO not found in ${P6_BUILD_WORKDIR}/out/"
    log_ok "ISO built: ${P6_ISO_PATH}"
fi

# =============================================================================
# Phase 2 — Unattended install
# =============================================================================
log_section "Phase 2: Unattended Install"

DISK_PATH="${P6_SERIAL_DIR}/phase6-test.qcow2"
SERIAL_INSTALL="${P6_SERIAL_DIR}/install.log"

rm -f "$DISK_PATH" "$SERIAL_INSTALL"
qemu-img create -f qcow2 "$DISK_PATH" "$P6_DISK_SIZE" -q
log_ok "Disk created: ${DISK_PATH} (${P6_DISK_SIZE})"

local_config_iso="${P6_SERIAL_DIR}/phase6-config.iso"
genisoimage -quiet -V OUROBOROS-CONFIG -r -J -o "$local_config_iso" "$E2E_CONFIG" 2>/dev/null \
    || log_die "Failed to create config ISO"
log_ok "Config ISO created for CD-ROM injection"

launch_qemu "$DISK_PATH" "$P6_ISO_PATH" "$SERIAL_INSTALL" "$local_config_iso"
log_info "Install started — monitor at: vncviewer localhost:590${P6_VNC_DISPLAY}"
log_info "Serial log: ${SERIAL_INSTALL}"

wait_qemu_exit "$P6_INSTALL_TIMEOUT"

log_info "Checking install serial log..."
for state in INIT NETWORK_SETUP PREFLIGHT LOCALE USER DESKTOP SECURE_BOOT PARTITION FORMAT INSTALL CONFIGURE SNAPSHOT FINISH; do
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

# Thunderbolt in serial log: must NOT appear as detected (no Thunderbolt HW in QEMU)
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "Thunderbolt: boltd enabled" "$SERIAL_INSTALL" 2>/dev/null; then
    log_fail "Install log: boltd was enabled — unexpected for QEMU (no Thunderbolt HW)"
else
    log_ok "Install log: Thunderbolt not detected (correct — QEMU has no TB hardware)"
fi

# =============================================================================
# Phase 3 — Boot installed system
# =============================================================================
log_section "Phase 3: Boot Installed System"

SERIAL_BOOT="${P6_SERIAL_DIR}/boot.log"
rm -f "$SERIAL_BOOT"

launch_qemu "$DISK_PATH" "" "$SERIAL_BOOT"
log_info "Boot started — monitor at: vncviewer localhost:590${P6_VNC_DISPLAY}"
log_info "Serial log: ${SERIAL_BOOT}"

wait_ssh 40
log_ok "SSH ready — installed system is up"

# =============================================================================
# Phase 4 — Core system health (baseline)
# =============================================================================
log_section "Phase 4: Core System Health"

mnt_opts=$(ssh_root_out "cat /proc/mounts 2>/dev/null | grep ' / '" || true)
assert_contains "Root filesystem is read-only" "$mnt_opts" "ro"
assert_contains "Root filesystem uses Btrfs" "$mnt_opts" "compress=zstd|btrfs"

failed_units=$(ssh_root_out "systemctl --failed --no-legend --no-pager 2>/dev/null | wc -l | tr -d ' '" || echo "99")
assert_zero "No failed systemd units" "$failed_units"

assert_unit_active "systemd-networkd active" "systemd-networkd"
assert_unit_active "sshd active" "sshd"

# =============================================================================
# Phase 5 — our-wall: presence and firewalld state
# =============================================================================
log_section "Phase 5: our-wall — Binary and Service"

# Binary presence and permissions
assert_cmd_exists "our-wall exists"       "/usr/local/bin/our-wall"
assert_file_executable "our-wall is executable" "/usr/local/bin/our-wall"

wall_perms=$(ssh_root_out "stat -c '%a' /usr/local/bin/our-wall 2>/dev/null" || true)
assert_equals "our-wall permissions: 755" "$wall_perms" "755"

# firewalld enabled and active
assert_unit_enabled "firewalld.service enabled" "firewalld"
assert_unit_active  "firewalld.service active"  "firewalld"

# our-wall status output
log_info "our-wall status..."
wall_status=$(ssh_root_out "our-wall status 2>&1" || true)
assert_contains "our-wall status: shows active" "$wall_status" "active"
assert_contains "our-wall status: shows zone"   "$wall_status" "zone"

# our-wall help
log_info "our-wall --help..."
wall_help=$(ssh_root_out "our-wall --help 2>&1" || true)
assert_contains "our-wall help: allow documented"  "$wall_help" "allow"
assert_contains "our-wall help: deny documented"   "$wall_help" "deny"
assert_contains "our-wall help: preset documented" "$wall_help" "preset"
assert_contains "our-wall help: zone documented"   "$wall_help" "zone"

# Default zone is public (ouroborOS default)
log_info "our-wall zone show (default: public)..."
wall_zone=$(ssh_root_out "our-wall zone show 2>&1" || true)
assert_contains "our-wall zone: public is active zone" "$wall_zone" "public"

# =============================================================================
# Phase 6 — our-wall: rule operations
# =============================================================================
log_section "Phase 6: our-wall — Rule Operations"

# allow a test port, verify it appears in list, then deny it
log_info "our-wall allow 19876/tcp..."
allow_out=$(ssh_root_out "our-wall allow 19876/tcp 2>&1" || true)
assert_contains "our-wall allow 19876/tcp: success message" "$allow_out" "Allowed|allowed|19876"

log_info "our-wall list (port 19876/tcp should appear)..."
list_after_allow=$(ssh_root_out "our-wall list 2>&1" || true)
assert_contains "our-wall list: 19876/tcp present after allow" "$list_after_allow" "19876"

log_info "our-wall deny 19876/tcp..."
deny_out=$(ssh_root_out "our-wall deny 19876/tcp 2>&1" || true)
assert_contains "our-wall deny 19876/tcp: success message" "$deny_out" "Removed|removed|19876"

log_info "our-wall list (port 19876/tcp should be gone)..."
list_after_deny=$(ssh_root_out "our-wall list 2>&1" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$list_after_deny" | grep -q "19876"; then
    log_fail "our-wall deny 19876/tcp: port still listed after deny"
else
    log_ok "our-wall deny 19876/tcp: port absent after deny"
fi

# allow + deny a service
log_info "our-wall allow http..."
allow_svc=$(ssh_root_out "our-wall allow http 2>&1" || true)
assert_contains "our-wall allow http: success message" "$allow_svc" "Allowed|allowed|http"

log_info "our-wall deny http..."
deny_svc=$(ssh_root_out "our-wall deny http 2>&1" || true)
assert_contains "our-wall deny http: success message" "$deny_svc" "Removed|removed|http"

# preset reset — baseline restore
log_info "our-wall preset reset (restore public + ssh only)..."
preset_reset=$(ssh_root_out "our-wall preset reset 2>&1" || true)
assert_contains "our-wall preset reset: success message" "$preset_reset" "Reset|reset|public|ssh"

log_info "our-wall status after reset (firewalld still active)..."
wall_status_post=$(ssh_root_out "our-wall status 2>&1" || true)
assert_contains "our-wall status after reset: still active" "$wall_status_post" "active"

# reload does not drop the service
log_info "our-wall reload..."
reload_out=$(ssh_root_out "our-wall reload 2>&1" || true)
assert_contains "our-wall reload: success" "$reload_out" "reload"
assert_unit_active "firewalld still active after reload" "firewalld"

# unknown command exits non-zero
log_info "our-wall unknown-cmd: exit non-zero..."
unknown_exit=$(ssh_root_out "our-wall unknown-cmd; echo exit_code=\$?" 2>/dev/null || echo "exit_code=1")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$unknown_exit" | grep -qE "exit_code=0"; then
    log_fail "our-wall unknown-cmd: exited 0 (should exit non-zero)"
else
    log_ok "our-wall unknown-cmd: exits non-zero"
fi

# =============================================================================
# Phase 7 — ouroboros-install launcher
# =============================================================================
log_section "Phase 7: ouroboros-install Launcher"

assert_cmd_exists "ouroboros-install exists" "/usr/local/bin/ouroboros-install"
assert_file_executable "ouroboros-install is executable" "/usr/local/bin/ouroboros-install"

inst_perms=$(ssh_root_out "stat -c '%a' /usr/local/bin/ouroboros-install 2>/dev/null" || true)
assert_equals "ouroboros-install permissions: 755" "$inst_perms" "755"

# Confirm it is a bash script (not a Python file)
log_info "ouroboros-install: confirm bash shebang..."
inst_shebang=$(ssh_root_out "head -1 /usr/local/bin/ouroboros-install 2>/dev/null" || true)
assert_contains "ouroboros-install: bash shebang" "$inst_shebang" "bash"

# OUROBOROS_AUTOSTART snippet is present
assert_file_exists "ouroboros-autostart.sh exists" \
    "/etc/profile.d/ouroboros-autostart.sh"

# =============================================================================
# Phase 8 — v0.6.0 install log markers
# =============================================================================
# Note: tui_textual.py and installer.tcss live on the live ISO only (not on
# the installed system). We verify v0.6.0 features by checking configure.sh
# output in the install serial log.
log_section "Phase 8: v0.6.0 Install Log Markers"

# firewalld was enabled during CONFIGURE
log_info "firewalld enabled in configure.sh..."
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "firewalld enabled" "$SERIAL_INSTALL" 2>/dev/null; then
    log_ok "Install log: firewalld.service enabled during CONFIGURE"
else
    log_fail "Install log: 'firewalld enabled' not found — configure.sh may not have run"
fi

# ouroboros-autostart.sh was installed on target
log_info "ouroboros-autostart.sh installed in configure.sh..."
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "ouroboros-autostart.sh" "$SERIAL_INSTALL" 2>/dev/null; then
    log_ok "Install log: ouroboros-autostart.sh installed"
else
    log_fail "Install log: ouroboros-autostart.sh not mentioned — check configure.sh PHASE 3"
fi

# our-wall was copied to installed system
log_info "our-wall copied to installed system..."
TESTS_RUN=$((TESTS_RUN + 1))
if grep -qi "our-wall" "$SERIAL_INSTALL" 2>/dev/null; then
    log_ok "Install log: our-wall referenced during CONFIGURE"
else
    log_fail "Install log: our-wall not referenced — check _p3_tools in configure.sh"
fi

# =============================================================================
# Phase 9 — Thunderbolt: not detected in QEMU
# =============================================================================
log_section "Phase 9: Thunderbolt — Not Detected in QEMU"

# bolt must NOT be installed (no Thunderbolt hardware in QEMU)
log_info "bolt: must NOT be installed..."
bolt_pkg=$(ssh_root_out "pacman -Q bolt 2>/dev/null || echo absent" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$bolt_pkg" | grep -q "absent"; then
    log_ok "bolt: not installed (correct — QEMU has no Thunderbolt hardware)"
else
    log_fail "bolt: installed in QEMU — Thunderbolt detection false-positive"
fi

# boltd must NOT be enabled
log_info "boltd.service: must NOT be enabled..."
boltd_enabled=$(ssh_root_out "systemctl is-enabled boltd.service 2>/dev/null || echo disabled" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$boltd_enabled" | grep -qE "^enabled$"; then
    log_fail "boltd.service: enabled in QEMU — unexpected (no Thunderbolt hardware)"
else
    log_ok "boltd.service: not enabled (correct)"
fi

# lspci itself must work (it is used during PREFLIGHT)
log_info "lspci available and runs without error..."
lspci_out=$(ssh_root_out "lspci -nn 2>&1 | head -3" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$lspci_out" | grep -qiE "error|command not found"; then
    log_fail "lspci: error on installed system"
else
    log_ok "lspci: runs without error"
fi

# =============================================================================
# Phase 10 — Teardown and Report
# =============================================================================
log_section "Phase 10: Report"

log_info "Shutting down VM..."
ssh_root "systemctl poweroff" 2>/dev/null || true
sleep 5
kill_qemu

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Phase 6 E2E — Test Results${RESET}"
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
    if [[ "$P6_KEEP_ARTIFACTS" != "1" ]]; then
        log_info "Re-run with P6_KEEP_ARTIFACTS=1 to keep disk and logs"
        log_info "Connect to VM during run: vncviewer localhost:590${P6_VNC_DISPLAY}"
    fi
    exit 1
fi
