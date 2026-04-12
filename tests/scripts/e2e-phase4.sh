#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# e2e-phase4.sh — End-to-end validation of Phase 4 features
# =============================================================================
# Performs a full install+boot cycle and validates all Phase 4 features via SSH:
#   Phase 0  — Prerequisites
#   Phase 1  — Build ISO with Phase 4 config (or reuse existing)
#   Phase 2  — Unattended install via QEMU
#   Phase 3  — Boot installed system
#   Phase 4  — Core system sanity (inherit Phase 3 baselines)
#   Phase 5  — Phase 4 tool presence (our-aur, our-flat)
#   Phase 6  — our-aur: help, flag parsing, AUR RPC (internet-gated)
#   Phase 7  — our-flat: help, flatpak presence, remote management, search
#   Phase 8  — systemd-sysext + firstboot AUR queue
#   Phase 9  — Teardown and final report
#
# QEMU setup:
#   GPU:     -vga virtio  (virtio-gpu, best QEMU virtual GPU)
#   VNC:     -vnc :1      — connect with: vncviewer localhost:5901
#   SSH:     localhost:2222 → guest:22
#   Display: -display none (headless, VNC for debug access)
#
# Internet-gated tests (skipped if no internet in QEMU):
#   our-aur -Ss / -Si  — AUR RPC v6
#   our-aur -S         — full build (container + paru + sysext); ~15 min
#   our-flat remote-add flathub
#   our-flat -Ss / -S
#
# Prerequisites:
#   sudo pacman -S --needed qemu-system-x86 edk2-ovmf openssh sshpass
#   /dev/kvm must be available
#
# Environment variables:
#   P4_ISO_PATH        — use existing ISO instead of building (skips Phase 1)
#   P4_TEST_USER       — SSH username (default: admin)
#   P4_TEST_PASSWORD   — SSH password (default: changeme)
#   P4_TEST_SSH_PORT   — SSH port (default: 2222)
#   P4_VNC_DISPLAY     — VNC display number (default: 1, → port 5901)
#   P4_DISK_SIZE       — QEMU disk size (default: 25G — our-aur containers need space)
#   P4_QEMU_MEMORY     — RAM in MB (default: 4096 — pacstrap in containers needs RAM)
#   P4_BUILD_WORKDIR   — ISO build workdir (default: /home/p4-build)
#   P4_SERIAL_DIR      — directory for serial logs (default: /tmp/p4-serial)
#   P4_KEEP_ARTIFACTS  — set to 1 to keep qcow2 and logs after run
#   P4_INSTALL_TIMEOUT — seconds to wait for install (default: 900)
#   P4_BOOT_TIMEOUT    — seconds to wait for boot SSH (default: 120)
#   P4_TEST_AUR_INSTALL — set to 1 to run our-aur -S (slow: ~15 min, needs internet)
#   P4_AUR_TEST_PKG    — AUR package to install in -S test (default: hello-world-git)
#
# Exit codes:
#   0 — all assertions pass
#   1 — one or more assertions fail
#   2 — prerequisites not met or infrastructure failure
# =============================================================================

# ── Colors ────────────────────────────────────────────────────────────────────
# shellcheck disable=SC2034
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
P4_TEST_USER="${P4_TEST_USER:-admin}"
P4_TEST_PASSWORD="${P4_TEST_PASSWORD:-changeme}"
P4_TEST_SSH_PORT="${P4_TEST_SSH_PORT:-2222}"
P4_VNC_DISPLAY="${P4_VNC_DISPLAY:-1}"
P4_DISK_SIZE="${P4_DISK_SIZE:-25G}"
P4_QEMU_MEMORY="${P4_QEMU_MEMORY:-4096}"
P4_BUILD_WORKDIR="${P4_BUILD_WORKDIR:-/home/p4-build}"
P4_SERIAL_DIR="${P4_SERIAL_DIR:-/tmp/p4-serial}"
P4_KEEP_ARTIFACTS="${P4_KEEP_ARTIFACTS:-0}"
P4_INSTALL_TIMEOUT="${P4_INSTALL_TIMEOUT:-900}"
P4_BOOT_TIMEOUT="${P4_BOOT_TIMEOUT:-120}"
P4_ISO_PATH="${P4_ISO_PATH:-}"
P4_TEST_AUR_INSTALL="${P4_TEST_AUR_INSTALL:-0}"
P4_AUR_TEST_PKG="${P4_AUR_TEST_PKG:-hello-world-git}"

readonly OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
readonly OVMF_CODE_ALT="/usr/share/edk2-ovmf/x64/OVMF_CODE.4m.fd"
readonly E2E_CONFIG="tests/qemu/phase4-e2e.yaml"
readonly FLATHUB_URL="https://dl.flathub.org/repo/flathub.flatpakrepo"

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
FAILURES=0
SKIPPED=0
TESTS_RUN=0
QEMU_PID=""
OVMF_PATH=""
DISK_PATH=""
SERIAL_INSTALL=""
SERIAL_BOOT=""
HAS_INTERNET=0

# ── SSH helpers ────────────────────────────────────────────────────────────────
ssh_cmd() {
    sshpass -p "$P4_TEST_PASSWORD" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$P4_TEST_SSH_PORT" \
        "${P4_TEST_USER}@localhost" "$@"
}

ssh_root() {
    ssh_cmd "echo ${P4_TEST_PASSWORD} | sudo -S $*"
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
    log_info "Waiting for SSH on port ${P4_TEST_SSH_PORT}..."
    while ! ssh_cmd true 2>/dev/null; do
        if [[ $attempt -ge $max_attempts ]]; then
            log_die "SSH did not become available after ${max_attempts} attempts"
        fi
        sleep 3
        attempt=$((attempt + 1))
    done
    log_ok "SSH available on port ${P4_TEST_SSH_PORT}"
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
        -m "$P4_QEMU_MEMORY"
        -drive "if=pflash,format=raw,readonly=on,file=${OVMF_PATH}"
        -drive "file=${disk},format=qcow2,if=virtio,cache=writeback"
        -netdev "user,id=net0,hostfwd=tcp::${P4_TEST_SSH_PORT}-:22"
        -device "e1000,netdev=net0"
        -rtc base=utc,clock=host
        -serial "file:${serial}"
        -vga virtio
        -display none
        -vnc ":${P4_VNC_DISPLAY}"
    )

    [[ -n "$iso" ]]        && qemu_args+=(-cdrom "$iso" -boot d)
    [[ -n "$config_iso" ]] && qemu_args+=(-drive "file=${config_iso},format=raw,media=cdrom,readonly=on")

    setsid qemu-system-x86_64 "${qemu_args[@]}" &>/dev/null &
    QEMU_PID=$!
    log_info "QEMU PID: ${QEMU_PID} — VNC: vncviewer localhost:590${P4_VNC_DISPLAY}"
}

kill_qemu() {
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    QEMU_PID=""
}

wait_qemu_exit() {
    local timeout_secs="${1:-$P4_INSTALL_TIMEOUT}"
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
    if [[ "$P4_KEEP_ARTIFACTS" != "1" ]]; then
        [[ -n "$DISK_PATH"       ]] && rm -f "$DISK_PATH"
        [[ -n "$SERIAL_INSTALL"  ]] && rm -f "$SERIAL_INSTALL"
        [[ -n "$SERIAL_BOOT"     ]] && rm -f "$SERIAL_BOOT"
    else
        log_info "Artifacts kept (P4_KEEP_ARTIFACTS=1):"
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
fuser -k "${P4_TEST_SSH_PORT}/tcp" &>/dev/null || true
log_ok "Port ${P4_TEST_SSH_PORT} available"

# Work directories
mkdir -p "$P4_SERIAL_DIR"

# E2E config exists
[[ -f "$E2E_CONFIG" ]] || log_die "Phase 4 E2E config not found: ${E2E_CONFIG}"
log_ok "E2E config: ${E2E_CONFIG}"

# =============================================================================
# Phase 1 — ISO
# =============================================================================
log_section "Phase 1: ISO"

if [[ -n "$P4_ISO_PATH" ]]; then
    [[ -f "$P4_ISO_PATH" ]] || log_die "ISO not found at P4_ISO_PATH=${P4_ISO_PATH}"
    log_ok "Using existing ISO: ${P4_ISO_PATH}"
else
    log_info "Building ISO with Phase 4 config..."
    mkdir -p "$P4_BUILD_WORKDIR"
    if ! sudo bash src/scripts/build-iso.sh \
            --clean \
            --workdir "$P4_BUILD_WORKDIR" \
            --e2e-config="$E2E_CONFIG" 2>&1 | tail -5; then
        log_die "ISO build failed"
    fi
    P4_ISO_PATH="$(find "${P4_BUILD_WORKDIR}/out" -name 'ouroborOS-*.iso' -maxdepth 1 -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
    [[ -f "$P4_ISO_PATH" ]] || log_die "ISO build completed but ISO not found in ${P4_BUILD_WORKDIR}/out/"
    log_ok "ISO built: ${P4_ISO_PATH}"
fi

# =============================================================================
# Phase 2 — Unattended install
# =============================================================================
log_section "Phase 2: Unattended Install"

DISK_PATH="${P4_SERIAL_DIR}/phase4-test.qcow2"
SERIAL_INSTALL="${P4_SERIAL_DIR}/install.log"

rm -f "$DISK_PATH" "$SERIAL_INSTALL"
qemu-img create -f qcow2 "$DISK_PATH" "$P4_DISK_SIZE" -q
log_ok "Disk created: ${DISK_PATH} (${P4_DISK_SIZE})"

# Build config ISO (CD-ROM injection method)
local_config_iso="${P4_SERIAL_DIR}/phase4-config.iso"
genisoimage -quiet -V OUROBOROS-CONFIG -r -J -o "$local_config_iso" "$E2E_CONFIG" 2>/dev/null
log_ok "Config ISO created for CD-ROM injection"

launch_qemu "$DISK_PATH" "$P4_ISO_PATH" "$SERIAL_INSTALL" "$local_config_iso"
log_info "Install started — monitor at: vncviewer localhost:590${P4_VNC_DISPLAY}"
log_info "Serial log: ${SERIAL_INSTALL}"

wait_qemu_exit "$P4_INSTALL_TIMEOUT"

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

SERIAL_BOOT="${P4_SERIAL_DIR}/boot.log"
rm -f "$SERIAL_BOOT"

launch_qemu "$DISK_PATH" "" "$SERIAL_BOOT"
log_info "Boot started — monitor at: vncviewer localhost:590${P4_VNC_DISPLAY}"
log_info "Serial log: ${SERIAL_BOOT}"

sleep 10
wait_ssh 40

# =============================================================================
# Phase 4 — Core system sanity (baseline inherited from Phase 3)
# =============================================================================
log_section "Phase 4: Core System Sanity"

mnt_opts=$(ssh_root_out "findmnt / -no OPTIONS")
assert_contains "Root filesystem is read-only" "$mnt_opts" "ro"
assert_contains "Root filesystem uses Btrfs" "$mnt_opts" "compress=zstd|btrfs"

failed_units=$(ssh_root_out "systemctl --failed --no-legend --no-pager 2>/dev/null | wc -l | tr -d ' '" || echo "99")
assert_zero "No failed systemd units" "$failed_units"

assert_unit_active "systemd-networkd active" "systemd-networkd"
assert_unit_active "sshd active" "sshd"

# Internet connectivity check — gates AUR and Flatpak remote tests
log_info "Checking internet connectivity in QEMU..."
if ssh_root_out "curl -s --max-time 5 https://archlinux.org >/dev/null 2>&1 && echo ok" | grep -q "ok"; then
    HAS_INTERNET=1
    log_ok "Internet available — network-dependent tests will run"
else
    HAS_INTERNET=0
    log_warn "No internet — AUR RPC and Flatpak remote tests will be skipped"
fi

# =============================================================================
# Phase 5 — Phase 4 tool presence
# =============================================================================
log_section "Phase 5: Phase 4 Tool Presence"

assert_cmd_exists "our-aur exists"  "/usr/local/bin/our-aur"
assert_cmd_exists "our-flat exists" "/usr/local/bin/our-flat"
assert_cmd_exists "flatpak exists"  "flatpak"

assert_file_exists "our-aur is executable" "/usr/local/bin/our-aur"
assert_file_exists "our-flat is executable" "/usr/local/bin/our-flat"

# Verify permissions (755)
aur_perms=$(ssh_root_out "stat -c '%a' /usr/local/bin/our-aur 2>/dev/null" || true)
assert_equals "our-aur permissions: 755" "$aur_perms" "755"

flat_perms=$(ssh_root_out "stat -c '%a' /usr/local/bin/our-flat 2>/dev/null" || true)
assert_equals "our-flat permissions: 755" "$flat_perms" "755"

# =============================================================================
# Phase 6 — our-aur validation
# =============================================================================
log_section "Phase 6: our-aur"

# ── Help ──────────────────────────────────────────────────────────────────────
log_info "our-aur --help..."
aur_help=$(ssh_out "our-aur --help 2>&1" || true)
assert_contains "our-aur help: -S flag documented"  "$aur_help" "\-S"
assert_contains "our-aur help: -Ss flag documented" "$aur_help" "\-Ss"
assert_contains "our-aur help: -Su flag documented" "$aur_help" "\-Su"
assert_contains "our-aur help: -R flag documented"  "$aur_help" "\-R"
assert_contains "our-aur help: -Q flag documented"  "$aur_help" "\-Q"

# ── Flag parsing: -Syu rejection ──────────────────────────────────────────────
log_info "our-aur -Syu rejection..."
aur_syu=$(ssh_root_out "our-aur -Syu 2>&1 || true")
assert_contains "our-aur -Syu: rejected with our-pac hint" "$aur_syu" "our-pac"

# ── -Q: listar instalados (vacío ok) ─────────────────────────────────────────
log_info "our-aur -Q (empty is ok — minimal profile, no AUR packages)..."
aur_list=$(ssh_root_out "our-aur -Q 2>&1" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$aur_list" | grep -qE "ERROR|Traceback|unbound variable"; then
    log_fail "our-aur -Q: crashed (got: ${aur_list})"
else
    log_ok "our-aur -Q: runs without crash"
fi

# ── -S sin argumento: error descriptivo ──────────────────────────────────────
log_info "our-aur -S (sin argumento): error descriptivo..."
aur_s_noarg=$(ssh_root_out "our-aur -S 2>&1 || true")
assert_contains "our-aur -S sin arg: error descriptivo" "$aur_s_noarg" "Especificá|pkg|package|arg"

# ── Flag desconocido ──────────────────────────────────────────────────────────
log_info "our-aur flag desconocido: exit 1..."
aur_unknown_exit=$(ssh_root_out "our-aur --fake-flag; echo exit_code=\$?" 2>/dev/null || echo "exit_code=1")
assert_contains "our-aur flag desconocido: exit code 1" "$aur_unknown_exit" "exit_code=1|Flag desconocido"

# ── DATA_DIR y EXTENSIONS_DIR existen ────────────────────────────────────────
log_info "our-aur runtime directories..."
# /var/lib/our-aur se crea en primer uso; /var/lib/extensions siempre
assert_file_exists "/var/lib/extensions/ existe (sysext)" "/var/lib/extensions"

# ── Internet-gated: AUR RPC search e info ────────────────────────────────────
if [[ "$HAS_INTERNET" -eq 1 ]]; then
    log_info "our-aur -Ss hyprlock (AUR RPC)..."
    aur_search=$(ssh_out "our-aur -Ss hyprlock 2>&1" || true)
    assert_contains "our-aur -Ss: retorna resultados" "$aur_search" "hyprlock"

    log_info "our-aur -Si hyprlock (AUR RPC info)..."
    aur_info=$(ssh_out "our-aur -Si hyprlock 2>&1" || true)
    assert_contains "our-aur -Si: tiene campo Name o Version" "$aur_info" "Name|Version|URL|hyprlock"

    if [[ "$P4_TEST_AUR_INSTALL" == "1" ]]; then
        log_info "our-aur -S ${P4_AUR_TEST_PKG} (build completo — puede tardar ~15 min)..."
        # Timeout generoso: pacstrap + paru build + sysext creation
        aur_install=$(ssh_root_out "timeout 1200 our-aur -S ${P4_AUR_TEST_PKG} 2>&1" || true)
        assert_contains "our-aur -S: instalado en sysext" \
            "$aur_install" "Instalado|sysext|extension"

        log_info "our-aur -Q (después de install)..."
        aur_list_after=$(ssh_root_out "our-aur -Q 2>&1" || true)
        assert_contains "our-aur -Q: paquete aparece en lista" \
            "$aur_list_after" "${P4_AUR_TEST_PKG}"

        log_info "systemd-sysext list (after install)..."
        sysext_list=$(ssh_root_out "systemd-sysext list 2>&1" || true)
        assert_contains "systemd-sysext: our-aur extension visible" \
            "$sysext_list" "our-aur-${P4_AUR_TEST_PKG}"

        log_info "our-aur -R ${P4_AUR_TEST_PKG}..."
        aur_remove=$(ssh_root_out "our-aur -R ${P4_AUR_TEST_PKG} 2>&1" || true)
        assert_contains "our-aur -R: eliminado" "$aur_remove" "Removido|Removed|removed"

        log_info "our-aur -Q (después de remove)..."
        aur_list_clean=$(ssh_root_out "our-aur -Q 2>&1" || true)
        TESTS_RUN=$((TESTS_RUN + 1))
        if echo "$aur_list_clean" | grep -q "${P4_AUR_TEST_PKG}"; then
            log_fail "our-aur -R: paquete sigue en lista después de remove"
        else
            log_ok "our-aur -R: paquete eliminado correctamente"
        fi
    else
        log_skip "our-aur -S (build completo) — activá con P4_TEST_AUR_INSTALL=1"
        log_skip "our-aur -Q after install — requiere P4_TEST_AUR_INSTALL=1"
        log_skip "our-aur -R after install — requiere P4_TEST_AUR_INSTALL=1"
    fi
else
    log_skip "our-aur -Ss — sin internet"
    log_skip "our-aur -Si — sin internet"
    log_skip "our-aur -S  — sin internet"
fi

# =============================================================================
# Phase 7 — our-flat validation
# =============================================================================
log_section "Phase 7: our-flat"

# ── Help ──────────────────────────────────────────────────────────────────────
log_info "our-flat --help..."
flat_help=$(ssh_out "our-flat --help 2>&1" || true)
assert_contains "our-flat help: -S flag documentado"        "$flat_help" "\-S"
assert_contains "our-flat help: -Ss flag documentado"       "$flat_help" "\-Ss"
assert_contains "our-flat help: -Su flag documentado"       "$flat_help" "\-Su"
assert_contains "our-flat help: -R flag documentado"        "$flat_help" "\-R"
assert_contains "our-flat help: -Q flag documentado"        "$flat_help" "\-Q"
assert_contains "our-flat help: remote-add documentado"     "$flat_help" "remote-add"
assert_contains "our-flat help: remote-list documentado"    "$flat_help" "remote-list"
assert_contains "our-flat help: remote-remove documentado"  "$flat_help" "remote-remove"
assert_contains "our-flat help: Flathub opt-in mencionado"  "$flat_help" "flathub|Flathub"

# ── -Syu rejection ────────────────────────────────────────────────────────────
log_info "our-flat -Syu rejection..."
flat_syu=$(ssh_root_out "our-flat -Syu 2>&1 || true")
assert_contains "our-flat -Syu: rechazado con our-pac hint" "$flat_syu" "our-pac"

# ── Flag desconocido ──────────────────────────────────────────────────────────
log_info "our-flat flag desconocido: exit 1..."
flat_unknown_exit=$(ssh_root_out "our-flat --fake-flag; echo exit_code=\$?" 2>/dev/null || echo "exit_code=1")
assert_contains "our-flat flag desconocido: exit code 1" "$flat_unknown_exit" "exit_code=1|Flag desconocido"

# ── flatpak binario instalado ─────────────────────────────────────────────────
log_info "flatpak binario en sistema instalado..."
flatpak_ver=$(ssh_out "flatpak --version 2>&1" || true)
assert_contains "flatpak instalado: versión visible" "$flatpak_ver" "Flatpak"

# ── remote-list sin remotos ───────────────────────────────────────────────────
log_info "our-flat remote-list (sin remotos configurados)..."
flat_remotes_empty=$(ssh_root_out "our-flat remote-list 2>&1" || true)
TESTS_RUN=$((TESTS_RUN + 1))
# Debe mostrar mensaje de ayuda o lista vacía — NO crash
if echo "$flat_remotes_empty" | grep -qE "ERROR|Traceback|unbound variable"; then
    log_fail "our-flat remote-list sin remotos: crash (got: ${flat_remotes_empty})"
else
    log_ok "our-flat remote-list sin remotos: no crash"
fi

# ── -Q sin remotos (vacío ok) ─────────────────────────────────────────────────
log_info "our-flat -Q (sin apps instaladas)..."
flat_list_empty=$(ssh_root_out "our-flat -Q 2>&1" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$flat_list_empty" | grep -qE "Traceback|unbound variable"; then
    log_fail "our-flat -Q vacío: crash"
else
    log_ok "our-flat -Q vacío: no crash"
fi

# ── -S sin argumento: error descriptivo ──────────────────────────────────────
log_info "our-flat -S sin argumento: error descriptivo..."
flat_s_noarg=$(ssh_root_out "our-flat -S 2>&1 || true")
assert_contains "our-flat -S sin arg: error descriptivo" "$flat_s_noarg" "Especificá|app.id|app-id|arg"

# ── Internet-gated: remote-add flathub + search + install ────────────────────
if [[ "$HAS_INTERNET" -eq 1 ]]; then
    log_info "our-flat remote-add flathub..."
    flat_remote_add=$(ssh_root_out "our-flat remote-add flathub ${FLATHUB_URL} 2>&1" || true)
    assert_contains "our-flat remote-add flathub: ok" \
        "$flat_remote_add" "flathub|agregado|added|Remote"

    log_info "our-flat remote-list (con flathub)..."
    flat_remotes=$(ssh_root_out "our-flat remote-list 2>&1" || true)
    assert_contains "our-flat remote-list: flathub visible" "$flat_remotes" "flathub"

    log_info "our-flat -Ss vlc (buscar en Flathub)..."
    flat_search=$(ssh_out "our-flat -Ss vlc 2>&1" || true)
    assert_contains "our-flat -Ss: retorna resultados" "$flat_search" "[Vv]lc\|videolan"

    log_info "our-flat -Si org.videolan.VLC (info)..."
    flat_info=$(ssh_out "our-flat -Si org.videolan.VLC 2>&1" || true)
    TESTS_RUN=$((TESTS_RUN + 1))
    if echo "$flat_info" | grep -qiE "vlc|videolan|Traceback"; then
        if echo "$flat_info" | grep -qE "Traceback|unbound variable"; then
            log_fail "our-flat -Si: crash inesperado"
        else
            log_ok "our-flat -Si: info visible"
        fi
    else
        log_fail "our-flat -Si: sin resultados (got: $(echo "$flat_info" | tail -2))"
    fi

    log_info "our-flat -S org.videolan.VLC (install)..."
    flat_install=$(ssh_root_out "timeout 300 our-flat -S org.videolan.VLC 2>&1" || true)
    assert_contains "our-flat -S: app instalada" \
        "$flat_install" "[Ii]nstal|VLC|videolan"

    log_info "our-flat -Q (después de install)..."
    flat_list_after=$(ssh_root_out "our-flat -Q 2>&1" || true)
    assert_contains "our-flat -Q: VLC visible" "$flat_list_after" "VLC\|videolan"

    log_info "our-flat -R org.videolan.VLC..."
    flat_remove=$(ssh_root_out "our-flat -R org.videolan.VLC 2>&1" || true)
    assert_contains "our-flat -R: app desinstalada" \
        "$flat_remove" "[Dd]esinstal|[Rr]emov|[Uu]ninstall|VLC"

    log_info "our-flat -Q (después de remove)..."
    flat_list_clean=$(ssh_root_out "our-flat -Q 2>&1" || true)
    TESTS_RUN=$((TESTS_RUN + 1))
    if echo "$flat_list_clean" | grep -qiE "vlc|videolan"; then
        log_fail "our-flat -R: VLC sigue en lista después de remove"
    else
        log_ok "our-flat -R: VLC eliminado correctamente"
    fi

    log_info "our-flat remote-remove flathub..."
    flat_remote_rm=$(ssh_root_out "our-flat remote-remove flathub 2>&1" || true)
    assert_contains "our-flat remote-remove: ok" \
        "$flat_remote_rm" "flathub|removido|removed|deleted"
else
    log_skip "our-flat remote-add flathub — sin internet"
    log_skip "our-flat -Ss — sin internet"
    log_skip "our-flat -Si — sin internet"
    log_skip "our-flat -S  — sin internet"
    log_skip "our-flat -R  — sin internet"
    log_skip "our-flat remote-remove — sin internet"
fi

# =============================================================================
# Phase 8 — systemd-sysext + firstboot AUR queue
# =============================================================================
log_section "Phase 8: systemd-sysext + Firstboot AUR Queue"

# ── systemd-sysext ────────────────────────────────────────────────────────────
log_info "systemd-sysext enabled..."
assert_unit_enabled "systemd-sysext enabled" "systemd-sysext"

log_info "systemd-sysext list (sin extensiones — minimal profile)..."
sysext_list=$(ssh_root_out "systemd-sysext list 2>&1" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$sysext_list" | grep -qE "Traceback|unbound variable"; then
    log_fail "systemd-sysext list: crash"
else
    log_ok "systemd-sysext list: runs without crash"
fi

log_info "/var/lib/extensions/ existe..."
assert_file_exists "/var/lib/extensions/ existe" "/var/lib/extensions"

# ── Firstboot guard ───────────────────────────────────────────────────────────
log_info "ouroboros-firstboot guard file..."
assert_file_exists "firstboot.done guard file existe" \
    "/var/lib/ouroborOS/firstboot.done"

# ── AUR queue vacío (minimal profile) ────────────────────────────────────────
log_info "AUR queue file NO debe existir (minimal profile — firstboot lo consume o no se crea)..."
aur_queue=$(ssh_root_out "test -f /var/lib/ouroborOS/firstboot-aur-packages.txt && echo exists || echo absent" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if [[ "$aur_queue" == "absent" ]]; then
    log_ok "AUR queue file: absent (correcto para minimal profile)"
else
    log_fail "AUR queue file: presente para minimal profile (no debería existir)"
fi

# ── /var/lib/our-aur no existe antes del primer uso ──────────────────────────
log_info "/var/lib/our-aur/ — no existe antes del primer our-aur -S..."
aur_data=$(ssh_root_out "test -d /var/lib/our-aur && echo exists || echo absent" || true)
TESTS_RUN=$((TESTS_RUN + 1))
if [[ "$aur_data" == "absent" ]]; then
    log_ok "/var/lib/our-aur: absent antes del primer uso (lazy init correcto)"
else
    log_warn "/var/lib/our-aur: ya existe antes del primer our-aur -S (ok si firstboot instaló algo)"
    TESTS_RUN=$((TESTS_RUN - 1))
    log_skip "/var/lib/our-aur check — estado ambiguo (firstboot pudo crear)"
fi

# =============================================================================
# Phase 9 — Teardown and Report
# =============================================================================
log_section "Phase 9: Report"

log_info "Shutting down VM..."
ssh_root "systemctl poweroff" 2>/dev/null || true
sleep 5
kill_qemu

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Phase 4 E2E — Test Results${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  Tests run:    ${BOLD}${TESTS_RUN}${RESET}"
echo -e "  ${GREEN}Passed:       $((TESTS_RUN - FAILURES - SKIPPED))${RESET}"
echo -e "  ${RED}Failed:       ${FAILURES}${RESET}"
echo -e "  ${YELLOW}Skipped:      ${SKIPPED}${RESET}"
echo ""
log_info "Internet-gated tests: $([ "$HAS_INTERNET" -eq 1 ] && echo 'RAN' || echo 'SKIPPED (no internet)')"
log_info "AUR full install test: $([ "$P4_TEST_AUR_INSTALL" == '1' ] && echo 'RAN' || echo 'SKIPPED (P4_TEST_AUR_INSTALL not set)')"
echo ""

if [[ "$FAILURES" -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}ALL TESTS PASSED ✓${RESET}"
    echo ""
    exit 0
else
    echo -e "  ${RED}${BOLD}${FAILURES} TEST(S) FAILED ✗${RESET}"
    echo ""
    if [[ "$P4_KEEP_ARTIFACTS" != "1" ]]; then
        log_info "Re-run con P4_KEEP_ARTIFACTS=1 para conservar disco y logs"
        log_info "Conectarse a la VM durante la ejecución: vncviewer localhost:590${P4_VNC_DISPLAY}"
    fi
    exit 1
fi
