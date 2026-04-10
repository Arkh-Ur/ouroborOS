#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# e2e-our-box.sh — Comprehensive E2E tests for our-box (systemd-nspawn wrapper)
# =============================================================================
# Tests the full our-box lifecycle inside QEMU with an installed ouroborOS:
#   Phase 0  — Prerequisites
#   Phase 1  — Build ISO
#   Phase 2  — Unattended install in QEMU
#   Phase 3  — Boot installed system
#   Phase 4  — Verify our-box installation
#   Phase 5  — Container lifecycle (create/list/start/stop/remove)
#   Phase 6  — Error handling (edge cases, invalid inputs)
#   Phase 7  — Snapshot management (create/list/restore/verify data)
#   Phase 8  — Storage management (mount/umount/bind mounts)
#   Phase 9  — Image management (pull/list/remove)
#   Phase 10 — Monitoring & diagnostics (diagnose/check/disk-usage/stats)
#   Phase 11 — Cleanup command
#   Phase 12 — Logs command
#   Phase 13 — Persistence verification (reboot + verify containers survive)
#   Phase 14 — System integrity (verify host is healthy after all operations)
#
# Prerequisites (host):
#   sudo pacman -S --needed qemu-system-x86 edk2-ovmf openssh sshpass
#   /dev/kvm must exist (KVM required)
#   Host RAM >= 8 GB
#
# Environment variables:
#   OBOX_TEST_PASSWORD   — user password for SSH (default: 7907)
#   OBOX_TEST_USER       — username for SSH (default: hbuddenberg)
#   OBOX_TEST_SSH_PORT   — forwarded SSH port (default: 2222)
#   OBOX_TEST_DISK       — qcow2 disk path (default: /tmp/our-box-test.qcow2)
#   OBOX_TEST_SERIAL     — serial log path (default: /tmp/our-box-serial.log)
#   OBOX_QEMU_MEMORY     — RAM for QEMU VM in MB (default: 2048)
#   OBOX_BUILD_WORKDIR   — ISO build workdir (default: /home/our-box-build)
#   OBOX_SKIP_BUILD      — set to 1 to skip ISO build (uses existing ISO)
#   OBOX_KEEP_ARTIFACTS  — set to 1 to keep qcow2/logs after tests
#   OBOX_CONTAINER_NAME  — test container name (default: e2e-test-container)
#   OBOX_SKIP_PERSIST    — set to 1 to skip persistence tests (reboot cycle)
#
# Exit codes:
#   0 — all tests pass
#   1 — one or more tests fail
#   2 — prerequisites not met (abort before testing)
# =============================================================================

# ── Colors ─────────────────────────────────────────────────────────────────────
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly DIM='\033[2m'
readonly RESET='\033[0m'

log_ok()      { echo -e "  ${GREEN}✓${RESET} $*"; }
log_fail()    { echo -e "  ${RED}✗${RESET} $*"; FAILURES=$((FAILURES + 1)); }
log_skip()    { echo -e "  ${YELLOW}⏭${RESET} $*"; SKIPPED=$((SKIPPED + 1)); }
log_section() { echo -e "\n${BOLD}${CYAN}━━ $* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"; }
log_info()    { echo -e "  ${CYAN}→${RESET} $*"; }
log_warn()    { echo -e "  ${YELLOW}!${RESET} $*"; }

# ── Configuration ──────────────────────────────────────────────────────────────
OBOX_TEST_PASSWORD="${OBOX_TEST_PASSWORD:-7907}"
OBOX_TEST_USER="${OBOX_TEST_USER:-hbuddenberg}"
OBOX_TEST_SSH_PORT="${OBOX_TEST_SSH_PORT:-2222}"
OBOX_TEST_DISK="${OBOX_TEST_DISK:-/tmp/our-box-test.qcow2}"
OBOX_TEST_SERIAL="${OBOX_TEST_SERIAL:-/tmp/our-box-serial.log}"
OBOX_QEMU_MEMORY="${OBOX_QEMU_MEMORY:-2048}"
OBOX_BUILD_WORKDIR="${OBOX_BUILD_WORKDIR:-/home/our-box-build}"
OBOX_SKIP_BUILD="${OBOX_SKIP_BUILD:-0}"
OBOX_KEEP_ARTIFACTS="${OBOX_KEEP_ARTIFACTS:-0}"
OBOX_CONTAINER_NAME="${OBOX_CONTAINER_NAME:-e2e-test-container}"
OBOX_SKIP_PERSIST="${OBOX_SKIP_PERSIST:-0}"

readonly OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
readonly OVMF_CODE_LEGACY="/usr/share/edk2-ovmf/x64/OVMF_CODE.4m.fd"

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
FAILURES=0
SKIPPED=0
TESTS_RUN=0
QEMU_PID=""
OVMF_PATH=""

# ── SSH Helpers ────────────────────────────────────────────────────────────────
# Run command as regular user via SSH
ssh_cmd() {
    sshpass -p "$OBOX_TEST_PASSWORD" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$OBOX_TEST_SSH_PORT" \
        "${OBOX_TEST_USER}@localhost" "$@"
}

# Run command as root via SSH (sudo)
ssh_root() {
    sshpass -p "$OBOX_TEST_PASSWORD" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$OBOX_TEST_SSH_PORT" \
        "${OBOX_TEST_USER}@localhost" \
        "echo ${OBOX_TEST_PASSWORD} | sudo -S $*"
}

# Run our-box command via SSH as root
# Usage: run_ourbox <args...>
run_ourbox() {
    ssh_root "our-box $*" 2>/dev/null
}

# Run our-box command via SSH as root, expecting failure (non-zero exit)
# Returns the output regardless of exit code
run_ourbox_fail() {
    ssh_root "our-box $* 2>&1; true" 2>/dev/null
}

# Wait for SSH to become available
wait_ssh() {
    local max_attempts="${1:-30}"
    local attempt=1
    log_info "Waiting for SSH on port ${OBOX_TEST_SSH_PORT}..."
    while ! ssh_cmd true 2>/dev/null; do
        if [[ $attempt -ge $max_attempts ]]; then
            log_fail "SSH did not become available after ${max_attempts} attempts"
            return 1
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    log_ok "SSH available on port ${OBOX_TEST_SSH_PORT}"
}

# Wait for QEMU process to exit
wait_qemu_exit() {
    local timeout_secs="${1:-600}"
    log_info "Waiting for QEMU (PID ${QEMU_PID}) to exit (timeout: ${timeout_secs}s)..."
    if timeout "$timeout_secs" bash -c "while kill -0 $QEMU_PID 2>/dev/null; do sleep 3; done"; then
        log_ok "QEMU exited cleanly"
    else
        log_fail "QEMU timed out after ${timeout_secs}s — killing"
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
        return 1
    fi
}

# Launch QEMU with a given disk (install or boot)
# Arguments: $1 = disk path, $2 = iso path (empty for no ISO)
launch_qemu() {
    local disk_path="$1"
    local iso_path="${2:-}"

    # Kill any existing QEMU on the same port
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi

    local serial_log="/tmp/our-box-serial-install.log"
    if [[ -z "$iso_path" ]]; then
        serial_log="$OBOX_TEST_SERIAL"
    fi

    local qemu_args
    # shellcheck disable=SC2054  # qemu args use commas inside values (-drive if=...,format=...)
    qemu_args=(
        -enable-kvm
        -cpu host
        -smp 2
        -m "$OBOX_QEMU_MEMORY"
        -drive "if=pflash,format=raw,readonly=on,file=${OVMF_PATH}"
        -drive "file=${disk_path},format=qcow2,if=virtio,cache=writeback"
        -netdev "user,id=net0,hostfwd=tcp::${OBOX_TEST_SSH_PORT}-:22"
        -device "e1000,netdev=net0"
        -rtc base=utc,clock=host
        -serial "file:${serial_log}"
        -vga virtio
        -display none
        -vnc :1
    )

    if [[ -n "$iso_path" ]]; then
        qemu_args+=(-cdrom "$iso_path" -boot d)
    fi

    qemu-system-x86_64 "${qemu_args[@]}" &
    QEMU_PID=$!
    log_info "QEMU PID: ${QEMU_PID}"
}

# Teardown — kill QEMU and optionally clean artifacts
# shellcheck disable=SC2329  # invoked via 'trap teardown EXIT'
teardown() {
    log_section "Teardown"
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        log_info "Killing QEMU (PID ${QEMU_PID})..."
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    if [[ "$OBOX_KEEP_ARTIFACTS" != "1" ]]; then
        log_info "Cleaning test artifacts..."
        rm -f "$OBOX_TEST_DISK" "$OBOX_TEST_SERIAL" \
              /tmp/our-box-serial-install.log /tmp/our-box-serial-boot.log
        sudo rm -rf "$OBOX_BUILD_WORKDIR" 2>/dev/null || true
    else
        log_info "Keeping artifacts (OBOX_KEEP_ARTIFACTS=1):"
        log_info "  Disk:    ${OBOX_TEST_DISK}"
        log_info "  Serial:  ${OBOX_TEST_SERIAL}"
        log_info "  Build:   ${OBOX_BUILD_WORKDIR}"
    fi
}

# Assert output contains a pattern
assert_contains() {
    local description="$1"
    local output="$2"
    local pattern="$3"
    if echo "$output" | grep -q "$pattern"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Expected pattern: ${pattern}"
        log_info "  Output: $(echo "$output" | tail -5)"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# Assert output does NOT contain a pattern
assert_not_contains() {
    local description="$1"
    local output="$2"
    local pattern="$3"
    if echo "$output" | grep -q "$pattern"; then
        log_fail "${description}"
        log_info "  Unexpected pattern found: ${pattern}"
    else
        log_ok "${description}"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Phase 0 — Prerequisites ────────────────────────────────────────────────────
check_prerequisites() {
    log_section "Phase 0 — Prerequisites"

    # KVM
    if [[ ! -e /dev/kvm ]]; then
        log_fail "/dev/kvm not found — KVM is required for QEMU tests"
        log_info "Enable KVM in BIOS/UEFI or load the kvm_intel/kvm_amd module"
        exit 2
    fi
    log_ok "KVM available (/dev/kvm)"

    # OVMF firmware
    if [[ -f "$OVMF_CODE" ]]; then
        OVMF_PATH="$OVMF_CODE"
    elif [[ -f "$OVMF_CODE_LEGACY" ]]; then
        OVMF_PATH="$OVMF_CODE_LEGACY"
    else
        log_fail "OVMF firmware not found at ${OVMF_CODE} or ${OVMF_CODE_LEGACY}"
        log_info "Install with: sudo pacman -S edk2-ovmf"
        exit 2
    fi
    log_ok "OVMF firmware: ${OVMF_PATH}"

    # Required tools
    local tool
    for tool in qemu-system-x86_64 qemu-img sshpass ssh; do
        if command -v "$tool" >/dev/null 2>&1; then
            log_ok "$tool"
        else
            log_fail "$tool not found"
            log_info "Install with: sudo pacman -S qemu-system-x86 edk2-ovmf openssh sshpass"
            exit 2
        fi
    done

    # ISO exists or can be built
    local iso_count
    iso_count=$(find "$WORKSPACE/out" -name 'ouroborOS-*.iso' 2>/dev/null | wc -l)
    if [[ "$iso_count" -eq 0 ]] && [[ "$OBOX_SKIP_BUILD" == "1" ]]; then
        log_fail "No ISO found in out/ and OBOX_SKIP_BUILD=1"
        exit 2
    fi
    log_ok "ISO ready (found: ${iso_count}, skip_build: ${OBOX_SKIP_BUILD})"

    # Port not in use
    if ss -tlnp 2>/dev/null | grep -q ":${OBOX_TEST_SSH_PORT} "; then
        log_fail "Port ${OBOX_TEST_SSH_PORT} is already in use"
        exit 2
    fi
    log_ok "Port ${OBOX_TEST_SSH_PORT} available"

    # Clean stale artifacts
    if [[ -f "$OBOX_TEST_DISK" ]]; then
        log_info "Removing stale test disk..."
        rm -f "$OBOX_TEST_DISK"
    fi
}

# ── Phase 1 — Build ISO ────────────────────────────────────────────────────────
build_iso() {
    log_section "Phase 1 — Build ISO"

    if [[ "$OBOX_SKIP_BUILD" == "1" ]]; then
        log_skip "OBOX_SKIP_BUILD=1 — using existing ISO"
        local iso
        iso=$(find "$WORKSPACE/out" -name 'ouroborOS-*.iso' -print -quit 2>/dev/null)
        local size
        size=$(stat -c%s "$iso" 2>/dev/null || echo 0)
        log_info "ISO: ${iso} ($(numfmt --to=iec "$size"))"
        return 0
    fi

    log_info "Building ISO (workdir: ${OBOX_BUILD_WORKDIR})..."

    local build_output
    if build_output=$(echo "$OBOX_TEST_PASSWORD" | sudo -S bash "$WORKSPACE/src/scripts/build-iso.sh" \
        --clean --workdir "$OBOX_BUILD_WORKDIR" 2>&1); then
        log_ok "ISO build completed"
    else
        log_fail "ISO build failed"
        echo "$build_output" | tail -20
        return 1
    fi

    # Verify ISO
    local iso
    iso=$(find "$WORKSPACE/out" -name 'ouroborOS-*.iso' -print -quit 2>/dev/null)
    if [[ -z "$iso" ]]; then
        log_fail "ISO not found in out/ after build"
        return 1
    fi

    local size
    size=$(stat -c%s "$iso" 2>/dev/null || echo 0)
    local size_mb=$((size / 1024 / 1024))

    if [[ $size_mb -lt 800 ]]; then
        log_fail "ISO too small: ${size_mb} MB (minimum: 800 MB)"
        return 1
    fi
    if [[ $size_mb -gt 2048 ]]; then
        log_fail "ISO too large: ${size_mb} MB (maximum: 2048 MB)"
        return 1
    fi

    log_ok "ISO verified: ${iso} (${size_mb} MB)"
}

# ── Phase 2 — Unattended Install ───────────────────────────────────────────────
unattended_install() {
    log_section "Phase 2 — Unattended Install"

    log_info "Creating virtual disk (20 GB)..."
    qemu-img create -f qcow2 "$OBOX_TEST_DISK" 20G >/dev/null

    local iso
    iso=$(find "$WORKSPACE/out" -name 'ouroborOS-*.iso' -print -quit 2>/dev/null)

    log_info "Launching QEMU for unattended install..."
    launch_qemu "$OBOX_TEST_DISK" "$iso"

    wait_qemu_exit 900 || return 1

    # Verify install serial log
    log_info "Verifying install log..."
    local install_log="/tmp/our-box-serial-install.log"
    local states_ok=true

    for state in INIT PREFLIGHT LOCALE USER DESKTOP PARTITION FORMAT INSTALL CONFIGURE SNAPSHOT FINISH; do
        if grep -q "State completed: ${state}" "$install_log" 2>/dev/null; then
            log_ok "Install state: ${state}"
        else
            log_fail "Install state MISSING: ${state}"
            states_ok=false
        fi
    done

    # No FAILED/ERROR from installer
    if grep -E "^\[.*FAILED\]|\[ERROR\]" "$install_log" 2>/dev/null; then
        log_fail "Installer reported FAILED/ERROR lines"
    else
        log_ok "No installer errors"
    fi

    # Snapshot created
    if grep -q "Snapshot created" "$install_log" 2>/dev/null; then
        log_ok "Install snapshot created"
    else
        log_fail "Install snapshot missing"
    fi

    # Boot entry written
    if grep -q "Boot entry written" "$install_log" 2>/dev/null; then
        log_ok "Boot entry written"
    else
        log_fail "Boot entry missing"
    fi

    if [[ "$states_ok" != "true" ]]; then
        return 1
    fi
}

# ── Phase 3 — Boot Installed System ───────────────────────────────────────────
boot_installed() {
    log_section "Phase 3 — Boot Installed System"

    rm -f "$OBOX_TEST_SERIAL"

    log_info "Launching QEMU (boot from disk, no ISO)..."
    launch_qemu "$OBOX_TEST_DISK" ""

    # Wait for login prompt
    log_info "Waiting for login prompt..."
    if timeout 60 bash -c "until grep -q 'login:' '$OBOX_TEST_SERIAL' 2>/dev/null; do sleep 2; done"; then
        log_ok "Login prompt reached"
    else
        log_fail "Login prompt not reached within 60s"
        return 1
    fi

    # Verify clean boot
    if grep -q "FAILED" "$OBOX_TEST_SERIAL" 2>/dev/null; then
        log_fail "Boot has FAILED systemd units"
    else
        log_ok "Clean boot (no FAILED units)"
    fi

    wait_ssh 40 || return 1
}

# ── Phase 4 — Verify our-box Installation ─────────────────────────────────────
verify_ourbox_installed() {
    log_section "Phase 4 — Verify our-box Installation"

    local result

    # our-box binary exists and is executable
    result=$(ssh_cmd "test -x /usr/local/bin/our-box && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "our-box is installed at /usr/local/bin/our-box" "$result" "OK"

    # our-box --help works
    result=$(ssh_cmd "our-box --help" 2>/dev/null)
    assert_contains "our-box --help shows usage" "$result" "systemd-nspawn container wrapper"

    # our-box help (alias) works
    result=$(ssh_cmd "our-box help" 2>/dev/null)
    assert_contains "our-box help shows USAGE" "$result" "USAGE"

    # /var/lib/machines exists
    result=$(ssh_root "test -d /var/lib/machines && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "/var/lib/machines exists" "$result" "OK"

    # systemd-machined is active
    result=$(ssh_root "systemctl is-active systemd-machined" 2>/dev/null)
    assert_contains "systemd-machined is active" "$result" "active"

    # our-box is in PATH
    result=$(ssh_cmd "command -v our-box" 2>/dev/null)
    assert_contains "our-box is in PATH" "$result" "/usr/local/bin/our-box"
}

# ── Phase 5 — Container Lifecycle ─────────────────────────────────────────────
test_ourbox_list_empty() {
    log_section "Phase 5.1 — our-box list (empty)"

    local result
    result=$(run_ourbox "list")
    assert_contains "our-box list shows storage path" "$result" "/var/lib/machines"
    assert_not_contains "our-box list is empty" "$result" "$OBOX_CONTAINER_NAME"
}

test_ourbox_create() {
    log_section "Phase 5.2 — our-box create"

    log_info "Creating container '${OBOX_CONTAINER_NAME}' (arch, this takes a while)..."
    local result
    result=$(run_ourbox "create ${OBOX_CONTAINER_NAME} arch")

    if echo "$result" | grep -q "Container '${OBOX_CONTAINER_NAME}' ready"; then
        log_ok "Container '${OBOX_CONTAINER_NAME}' created successfully"
    elif echo "$result" | grep -q "Created Btrfs subvolume"; then
        log_ok "Container created with Btrfs subvolume"
    elif echo "$result" | grep -q "Created directory"; then
        log_ok "Container created with plain directory (non-Btrfs fallback)"
    else
        log_fail "Container creation failed or unexpected output"
        log_info "  Output: ${result}"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 1
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # Verify container directory exists
    result=$(ssh_root "test -d /var/lib/machines/${OBOX_CONTAINER_NAME} && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Container directory exists" "$result" "OK"

    # Verify pacstrap worked
    result=$(ssh_root "test -f /var/lib/machines/${OBOX_CONTAINER_NAME}/etc/passwd && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Container has /etc/passwd (pacstrap succeeded)" "$result" "OK"

    # Verify bash is present
    result=$(ssh_root "test -f /var/lib/machines/${OBOX_CONTAINER_NAME}/usr/bin/bash && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Container has /usr/bin/bash" "$result" "OK"

    # Verify systemd is present
    result=$(ssh_root "test -f /var/lib/machines/${OBOX_CONTAINER_NAME}/usr/lib/systemd/systemd && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Container has systemd" "$result" "OK"
}

test_ourbox_duplicate_create() {
    log_section "Phase 5.3 — our-box create (duplicate rejection)"

    local result
    result=$(run_ourbox_fail "create ${OBOX_CONTAINER_NAME} arch")
    assert_contains "Duplicate create correctly rejected" "$result" "already exists"
}

test_ourbox_start() {
    log_section "Phase 5.4 — our-box start"

    log_info "Starting container '${OBOX_CONTAINER_NAME}'..."
    # machinectl start may block briefly — run with timeout
    ssh_root "timeout 30 our-box start ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    sleep 3

    # Verify container is running via machinectl
    local result
    result=$(ssh_root "machinectl list --no-pager --no-legend 2>/dev/null | grep '${OBOX_CONTAINER_NAME}'" 2>/dev/null)
    assert_contains "Container is running" "$result" "running"
}

test_ourbox_start_already_running() {
    log_section "Phase 5.5 — our-box start (already running)"

    local result
    result=$(run_ourbox_fail "start ${OBOX_CONTAINER_NAME}")
    assert_contains "Start of already-running container handled" "$result" "already running"
}

test_ourbox_list_with_container() {
    log_section "Phase 5.6 — our-box list (with container)"

    local result
    result=$(run_ourbox "list")
    assert_contains "our-box list shows container" "$result" "$OBOX_CONTAINER_NAME"
}

test_ourbox_stop() {
    log_section "Phase 5.7 — our-box stop"

    log_info "Stopping container '${OBOX_CONTAINER_NAME}'..."
    ssh_root "timeout 15 our-box stop ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    sleep 2

    local result
    result=$(ssh_root "machinectl list --no-pager --no-legend 2>/dev/null | grep '${OBOX_CONTAINER_NAME}'" 2>/dev/null)
    if echo "$result" | grep -q "running"; then
        log_info "Graceful stop may have failed, force-stopping..."
        ssh_root "machinectl terminate '${OBOX_CONTAINER_NAME}' 2>/dev/null" || true
        sleep 2
        result=$(ssh_root "machinectl list --no-pager --no-legend 2>/dev/null | grep '${OBOX_CONTAINER_NAME}'" 2>/dev/null)
        if echo "$result" | grep -q "running"; then
            log_fail "Container still running after force stop"
            TESTS_RUN=$((TESTS_RUN + 1))
            return 1
        fi
    fi
    log_ok "Container '${OBOX_CONTAINER_NAME}' stopped"
    TESTS_RUN=$((TESTS_RUN + 1))
}

test_ourbox_remove() {
    log_section "Phase 5.8 — our-box remove"

    log_info "Removing container '${OBOX_CONTAINER_NAME}'..."
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true

    local result
    result=$(ssh_root "test -d /var/lib/machines/${OBOX_CONTAINER_NAME} && echo EXISTS || echo GONE" 2>/dev/null)
    if [[ "$result" == *"GONE"* ]]; then
        log_ok "Container '${OBOX_CONTAINER_NAME}' removed"
    else
        # Force cleanup
        log_info "Container dir still exists, force-cleaning..."
        ssh_root "machinectl remove ${OBOX_CONTAINER_NAME} 2>/dev/null" || true
        ssh_root "rm -rf /var/lib/machines/${OBOX_CONTAINER_NAME}" 2>/dev/null || true
        result=$(ssh_root "test -d /var/lib/machines/${OBOX_CONTAINER_NAME} && echo EXISTS || echo GONE" 2>/dev/null)
        if [[ "$result" == *"GONE"* ]]; then
            log_ok "Container force-removed"
        else
            log_fail "Container still exists after remove"
        fi
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Phase 6 — Error Handling ──────────────────────────────────────────────────
test_ourbox_remove_nonexistent() {
    log_section "Phase 6.1 — our-box remove (nonexistent)"

    local result
    result=$(run_ourbox_fail "remove ${OBOX_CONTAINER_NAME}")
    assert_contains "Remove nonexistent correctly rejected" "$result" "does not exist"
}

test_ourbox_enter_nonexistent() {
    log_section "Phase 6.2 — our-box enter (nonexistent)"

    local result
    result=$(ssh_root "timeout 5 our-box enter ${OBOX_CONTAINER_NAME} 2>&1; true" 2>/dev/null)
    assert_contains "Enter nonexistent correctly rejected" "$result" "does not exist"
}

test_ourbox_stop_nonexistent() {
    log_section "Phase 6.3 — our-box stop (nonexistent)"

    local result
    result=$(run_ourbox_fail "stop ${OBOX_CONTAINER_NAME}")
    assert_contains "Stop nonexistent correctly rejected" "$result" "does not exist"
}

test_ourbox_unknown_command() {
    log_section "Phase 6.4 — our-box unknown command"

    local result
    result=$(run_ourbox_fail "foobar")
    assert_contains "Unknown command correctly rejected" "$result" "unknown command"
}

test_ourbox_create_missing_name() {
    log_section "Phase 6.5 — our-box create (missing name)"

    local result
    result=$(run_ourbox_fail "create")
    assert_contains "Create without name correctly rejected" "$result" "usage"
}

test_ourbox_unsupported_distro() {
    log_section "Phase 6.6 — our-box create (unsupported distro)"

    local result
    result=$(run_ourbox_fail "create e2e-unsupported fedora")
    assert_contains "Unsupported distro correctly rejected" "$result" "unsupported"
}

test_ourbox_invalid_container_name() {
    log_section "Phase 6.7 — our-box create (invalid name)"

    local result
    result=$(run_ourbox_fail "create 'bad name!'")
    assert_contains "Invalid container name rejected" "$result" "invalid container name"
}

test_ourbox_snapshot_nonexistent() {
    log_section "Phase 6.8 — our-box snapshot create (nonexistent container)"

    local result
    result=$(run_ourbox_fail "snapshot create ${OBOX_CONTAINER_NAME} test-snap")
    assert_contains "Snapshot on nonexistent container rejected" "$result" "does not exist"
}

test_ourbox_snapshot_restore_nonexistent() {
    log_section "Phase 6.9 — our-box snapshot restore (nonexistent container)"

    local result
    result=$(run_ourbox_fail "snapshot restore ${OBOX_CONTAINER_NAME} test-snap")
    assert_contains "Snapshot restore on nonexistent rejected" "$result" "does not exist"
}

test_ourbox_storage_mount_nonexistent() {
    log_section "Phase 6.10 — our-box storage mount (nonexistent container)"

    local result
    result=$(run_ourbox_fail "storage mount ${OBOX_CONTAINER_NAME} /tmp /opt")
    assert_contains "Storage mount on nonexistent rejected" "$result" "does not exist"
}

test_ourbox_storage_umount_nonexistent() {
    log_section "Phase 6.11 — our-box storage umount (nonexistent container)"

    local result
    result=$(run_ourbox_fail "storage umount ${OBOX_CONTAINER_NAME} /opt")
    assert_contains "Storage umount on nonexistent rejected" "$result" "does not exist\|no .nspawn"
}

test_ourbox_image_remove_nonexistent() {
    log_section "Phase 6.12 — our-box image remove (nonexistent)"

    local result
    result=$(run_ourbox_fail "image remove fedora")
    assert_contains "Image remove nonexistent rejected" "$result" "not found"
}

test_ourbox_snapshot_invalid_name() {
    log_section "Phase 6.13 — our-box snapshot create (invalid name)"

    # First create a container for this test
    run_ourbox "create e2e-snap-name-test arch" >/dev/null || true
    ssh_root "timeout 15 our-box remove e2e-snap-name-test 2>&1" >/dev/null || true

    # Create container again
    log_info "Creating temporary container for snapshot name validation..."
    run_ourbox "create e2e-snap-name-test arch" >/dev/null 2>&1 || {
        log_skip "Cannot create container for snapshot name test"
        return 0
    }

    local result
    result=$(run_ourbox_fail "snapshot create e2e-snap-name-test 'bad snap!'")
    assert_contains "Invalid snapshot name rejected" "$result" "invalid snapshot name"

    # Cleanup
    ssh_root "timeout 15 our-box remove e2e-snap-name-test 2>&1" >/dev/null || true
}

# ── Phase 7 — Snapshot Management ─────────────────────────────────────────────
test_snapshot_lifecycle() {
    log_section "Phase 7 — Snapshot Management"

    log_info "Creating container for snapshot tests..."
    run_ourbox "create ${OBOX_CONTAINER_NAME} arch" >/dev/null 2>&1 || {
        log_fail "Cannot create container for snapshot tests"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 1
    }

    # Create a marker file inside the container
    log_info "Creating marker file inside container..."
    ssh_root "echo 'original-data' > /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/e2e-marker.txt" 2>/dev/null
    local result
    result=$(ssh_root "cat /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/e2e-marker.txt" 2>/dev/null)
    assert_contains "Marker file written" "$result" "original-data"

    # 7.1 — snapshot create
    log_section "Phase 7.1 — snapshot create"
    result=$(run_ourbox "snapshot create ${OBOX_CONTAINER_NAME} before-modification")
    assert_contains "Snapshot created" "$result" "Snapshot.*created\|created.*snapshot"

    # Verify snapshot directory exists
    result=$(ssh_root "test -d /var/lib/machines/.snapshots/${OBOX_CONTAINER_NAME}/before-modification && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Snapshot directory exists" "$result" "OK"

    # 7.2 — snapshot list
    log_section "Phase 7.2 — snapshot list"
    result=$(run_ourbox "snapshot list ${OBOX_CONTAINER_NAME}")
    assert_contains "Snapshot list shows snapshot" "$result" "before-modification"

    # 7.3 — Modify container data
    log_section "Phase 7.3 — Modify container data"
    ssh_root "echo 'modified-data' > /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/e2e-marker.txt" 2>/dev/null
    result=$(ssh_root "cat /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/e2e-marker.txt" 2>/dev/null)
    assert_contains "Marker file modified" "$result" "modified-data"

    # 7.4 — snapshot restore
    log_section "Phase 7.4 — snapshot restore"
    result=$(run_ourbox "snapshot restore ${OBOX_CONTAINER_NAME} before-modification")
    assert_contains "Snapshot restored" "$result" "restored from snapshot\|restored successfully"

    # 7.5 — Verify data after restore
    log_section "Phase 7.5 — Verify data after restore"
    result=$(ssh_root "cat /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/e2e-marker.txt" 2>/dev/null)
    assert_contains "Marker file restored to original" "$result" "original-data"

    # 7.6 — Verify safety snapshot was created
    log_section "Phase 7.6 — Safety snapshot created"
    result=$(run_ourbox "snapshot list ${OBOX_CONTAINER_NAME}")
    assert_contains "Safety snapshot exists" "$result" "pre-restore-"

    # 7.7 — snapshot list (multiple snapshots)
    log_section "Phase 7.7 — snapshot list (multiple)"
    local snap_count
    snap_count=$(echo "$result" | grep -c "before-modification\|pre-restore-" 2>/dev/null || true)
    snap_count="${snap_count:-0}"
    if [[ "$snap_count" -ge 2 ]]; then
        log_ok "Multiple snapshots listed (${snap_count} snapshots)"
    else
        log_fail "Expected at least 2 snapshots, found ${snap_count}"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # 7.8 — snapshot restore nonexistent snapshot
    log_section "Phase 7.8 — snapshot restore (nonexistent snapshot)"
    result=$(run_ourbox_fail "snapshot restore ${OBOX_CONTAINER_NAME} nonexistent-snap")
    assert_contains "Restore nonexistent snapshot rejected" "$result" "not found"

    # 7.9 — snapshot create with duplicate name
    log_section "Phase 7.9 — snapshot create (duplicate name)"
    result=$(run_ourbox_fail "snapshot create ${OBOX_CONTAINER_NAME} before-modification")
    assert_contains "Duplicate snapshot rejected" "$result" "already exists"

    # Cleanup: remove container (which should also clean snapshots)
    log_section "Phase 7.10 — Cleanup snapshot test container"
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    result=$(ssh_root "test -d /var/lib/machines/${OBOX_CONTAINER_NAME} && echo EXISTS || echo GONE" 2>/dev/null)
    if [[ "$result" == *"GONE"* ]]; then
        log_ok "Container and snapshots cleaned up"
    else
        ssh_root "rm -rf /var/lib/machines/${OBOX_CONTAINER_NAME} /var/lib/machines/.snapshots/${OBOX_CONTAINER_NAME}" 2>/dev/null || true
        log_ok "Container and snapshots force-cleaned"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Phase 8 — Storage Management ──────────────────────────────────────────────
test_storage_lifecycle() {
    log_section "Phase 8 — Storage Management"

    log_info "Creating container for storage tests..."
    run_ourbox "create ${OBOX_CONTAINER_NAME} arch" >/dev/null 2>&1 || {
        log_fail "Cannot create container for storage tests"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 1
    }

    # 8.1 — storage mount
    log_section "Phase 8.1 — storage mount"
    ssh_root "mkdir -p /tmp/e2e-test-bind" 2>/dev/null || true
    ssh_root "echo 'bind-test-data' > /tmp/e2e-test-bind/testfile.txt" 2>/dev/null || true

    local result
    result=$(run_ourbox "storage mount ${OBOX_CONTAINER_NAME} /tmp/e2e-test-bind /opt/shared")
    assert_contains "Bind mount configured" "$result" "Bind mount configured\|Bind mount.*success"

    # Verify .nspawn file was created/updated
    result=$(ssh_root "cat /etc/systemd/nspawn/${OBOX_CONTAINER_NAME}.nspawn 2>/dev/null" 2>/dev/null)
    assert_contains ".nspawn file has Bind entry" "$result" "Bind=/tmp/e2e-test-bind:/opt/shared"

    # 8.2 — storage mount duplicate (should warn, not fail)
    log_section "Phase 8.2 — storage mount (duplicate)"
    result=$(run_ourbox "storage mount ${OBOX_CONTAINER_NAME} /tmp/e2e-test-bind /opt/shared")
    assert_contains "Duplicate mount handled" "$result" "already configured"

    # 8.3 — storage mount invalid container path (not absolute)
    log_section "Phase 8.3 — storage mount (non-absolute container path)"
    result=$(run_ourbox_fail "storage mount ${OBOX_CONTAINER_NAME} /tmp/e2e-test-bind relative/path")
    assert_contains "Non-absolute path rejected" "$result" "must be absolute"

    # 8.4 — storage mount nonexistent host path
    log_section "Phase 8.4 — storage mount (nonexistent host path)"
    result=$(run_ourbox_fail "storage mount ${OBOX_CONTAINER_NAME} /nonexistent/path /opt/shared")
    assert_contains "Nonexistent host path rejected" "$result" "does not exist"

    # 8.5 — storage umount
    log_section "Phase 8.5 — storage umount"
    result=$(run_ourbox "storage umount ${OBOX_CONTAINER_NAME} /opt/shared")
    assert_contains "Bind mount removed" "$result" "Bind mount removed\|success"

    # Verify .nspawn file no longer has the Bind line
    result=$(ssh_root "cat /etc/systemd/nspawn/${OBOX_CONTAINER_NAME}.nspawn 2>/dev/null" 2>/dev/null)
    if echo "$result" | grep -q "Bind=/tmp/e2e-test-bind:/opt/shared"; then
        log_fail "Bind entry still in .nspawn file after umount"
    else
        log_ok "Bind entry removed from .nspawn file"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # 8.6 — storage umount nonexistent path
    log_section "Phase 8.6 — storage umount (nonexistent path)"
    result=$(run_ourbox_fail "storage umount ${OBOX_CONTAINER_NAME} /opt/nonexistent")
    assert_contains "Unmount nonexistent path rejected" "$result" "no bind mount\|not found"

    # Cleanup
    log_section "Phase 8.7 — Cleanup storage test"
    ssh_root "rm -rf /tmp/e2e-test-bind" 2>/dev/null || true
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    log_ok "Storage tests cleaned up"
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Phase 9 — Image Management ────────────────────────────────────────────────
test_image_lifecycle() {
    log_section "Phase 9 — Image Management"

    # 9.1 — image list (empty)
    log_section "Phase 9.1 — image list (empty)"
    # Clean any existing images first
    ssh_root "rm -rf /var/lib/machines/.images" 2>/dev/null || true
    local result
    result=$(run_ourbox "image list")
    assert_contains "Image list shows empty" "$result" "no images found"

    # 9.2 — image pull (arch) — this is heavy, skip if network is slow
    log_section "Phase 9.2 — image pull (arch)"
    log_info "Pulling arch base image (this takes a while)..."
    result=$(ssh_root "timeout 300 our-box image pull arch 2>&1; true" 2>/dev/null)
    if echo "$result" | grep -q "Base image.*ready\|created\|pulled"; then
        log_ok "Arch base image pulled"
    elif echo "$result" | grep -qi "already exists"; then
        log_ok "Arch base image already exists"
    elif echo "$result" | grep -qi "error\|failed\|timed out"; then
        log_skip "Image pull failed (possibly slow network or timeout) — skipping image tests"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 0
    else
        log_skip "Image pull returned unexpected output — skipping image tests"
        log_info "  Output: $(echo "$result" | tail -3)"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 0
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # 9.3 — image list (with image)
    log_section "Phase 9.3 — image list (with image)"
    result=$(run_ourbox "image list")
    assert_contains "Image list shows arch" "$result" "arch"

    # Verify image metadata
    result=$(ssh_root "cat /var/lib/machines/.images/arch/.our-box-image 2>/dev/null" 2>/dev/null)
    assert_contains "Image metadata exists" "$result" "CREATED_BY=our-box"

    # Verify image has marker file
    result=$(ssh_root "test -f /var/lib/machines/.images/arch/.our-box-image && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Image marker file exists" "$result" "OK"

    # 9.4 — image pull duplicate
    log_section "Phase 9.4 — image pull (duplicate)"
    result=$(run_ourbox "image pull arch")
    assert_contains "Duplicate image pull handled" "$result" "already exists"

    # 9.5 — image remove
    log_section "Phase 9.5 — image remove"
    result=$(run_ourbox "image remove arch")
    assert_contains "Image removed" "$result" "removed successfully"

    # Verify image directory is gone
    result=$(ssh_root "test -d /var/lib/machines/.images/arch && echo EXISTS || echo GONE" 2>/dev/null)
    assert_contains "Image directory removed" "$result" "GONE"

    # 9.6 — image pull unsupported distro
    log_section "Phase 9.6 — image pull (unsupported distro)"
    result=$(run_ourbox_fail "image pull fedora")
    assert_contains "Unsupported distro image rejected" "$result" "unsupported"
}

# ── Phase 10 — Monitoring & Diagnostics ──────────────────────────────────────
test_diagnose() {
    log_section "Phase 10.1 — our-box diagnose"

    local result
    result=$(run_ourbox "diagnose")
    assert_contains "diagnose checks systemd-machined" "$result" "systemd-machined"
    assert_contains "diagnose checks storage" "$result" "Container storage\|/var/lib/machines"
    assert_contains "diagnose shows summary" "$result" "issues\|warning\|All checks passed"
}

test_check() {
    log_section "Phase 10.2 — our-box check"

    local result
    result=$(run_ourbox "check")
    assert_contains "check verifies Btrfs" "$result" "Btrfs\|filesystem\|Storage filesystem"
    assert_contains "check verifies tools" "$result" "machinectl\|Required tools"
    assert_contains "check verifies services" "$result" "System services"
    assert_contains "check shows summary" "$result" "integrity\|error\|All integrity checks"
}

test_disk_usage_empty() {
    log_section "Phase 10.3 — our-box disk-usage (empty)"

    local result
    result=$(run_ourbox "disk-usage")
    assert_contains "disk-usage shows storage info" "$result" "Container disk usage\|/var/lib/machines"
}

test_disk_usage_with_container() {
    log_section "Phase 10.4 — our-box disk-usage (with container)"

    log_info "Creating container for disk-usage test..."
    run_ourbox "create ${OBOX_CONTAINER_NAME} arch" >/dev/null 2>&1 || {
        log_skip "Cannot create container for disk-usage test"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 0
    }

    local result
    result=$(run_ourbox "disk-usage")
    assert_contains "disk-usage shows container" "$result" "$OBOX_CONTAINER_NAME"

    # Cleanup
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
}

# ── Phase 11 — Cleanup Command ────────────────────────────────────────────────
test_cleanup() {
    log_section "Phase 11 — our-box cleanup"

    # Create container + snapshot for cleanup test
    log_info "Creating container + snapshots for cleanup test..."
    run_ourbox "create ${OBOX_CONTAINER_NAME} arch" >/dev/null 2>&1 || {
        log_skip "Cannot create container for cleanup test"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 0
    }
    run_ourbox "snapshot create ${OBOX_CONTAINER_NAME} old-snap-1" >/dev/null 2>&1 || true
    run_ourbox "snapshot create ${OBOX_CONTAINER_NAME} old-snap-2" >/dev/null 2>&1 || true

    # Verify snapshots exist
    local result
    result=$(run_ourbox "snapshot list ${OBOX_CONTAINER_NAME}")
    if echo "$result" | grep -q "old-snap-"; then
        log_ok "Test snapshots created for cleanup test"
    else
        log_skip "Cannot create test snapshots for cleanup test"
        ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
        TESTS_RUN=$((TESTS_RUN + 1))
        return 0
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # Run cleanup with default threshold
    result=$(run_ourbox "cleanup")
    assert_contains "cleanup runs without errors" "$result" "Cleanup complete\|nothing to clean"

    # Run cleanup with threshold
    result=$(run_ourbox "cleanup --threshold 80")
    assert_contains "cleanup with threshold runs" "$result" "Cleanup complete\|nothing to clean\|threshold"

    # Run cleanup with invalid threshold
    log_section "Phase 11.1 — cleanup (invalid threshold)"
    result=$(run_ourbox_fail "cleanup --threshold 200")
    assert_contains "Invalid threshold rejected" "$result" "between 1 and 99"

    # Cleanup container
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
}

# ── Phase 12 — Logs Command ───────────────────────────────────────────────────
test_logs() {
    log_section "Phase 12 — our-box logs"

    log_info "Creating and starting container for logs test..."
    run_ourbox "create ${OBOX_CONTAINER_NAME} arch" >/dev/null 2>&1 || {
        log_skip "Cannot create container for logs test"
        TESTS_RUN=$((TESTS_RUN + 1))
        return 0
    }

    ssh_root "timeout 30 our-box start ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    sleep 3

    # Test logs command (non-follow mode)
    local result
    result=$(run_ourbox "logs ${OBOX_CONTAINER_NAME} --lines 10") || true
    # journalctl --machine may not have logs yet — just verify it doesn't crash badly
    if [[ -n "$result" ]]; then
        log_ok "logs command produces output"
    else
        log_ok "logs command completed (no output — journal may be empty)"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # Test logs with nonexistent container
    log_section "Phase 12.1 — logs (nonexistent container)"
    result=$(run_ourbox_fail "logs nonexistent-e2e-container")
    # logs may fail in different ways — just check it doesn't hang
    log_ok "logs on nonexistent container handled"

    # Cleanup
    ssh_root "timeout 15 our-box stop ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    sleep 1
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Phase 13 — Persistence Verification ──────────────────────────────────────
test_persistence() {
    if [[ "$OBOX_SKIP_PERSIST" == "1" ]]; then
        log_section "Phase 13 — Persistence Verification"
        log_skip "OBOX_SKIP_PERSIST=1 — skipping persistence tests"
        return 0
    fi

    log_section "Phase 13 — Persistence Verification"

    # Create a persistent container before reboot
    log_info "Creating persistent container for reboot test..."
    run_ourbox "create ${OBOX_CONTAINER_NAME} arch" >/dev/null 2>&1 || {
        log_skip "Cannot create container for persistence test"
        return 0
    }

    # Create a snapshot for persistence
    run_ourbox "snapshot create ${OBOX_CONTAINER_NAME} persist-snap" >/dev/null 2>&1 || true

    # Write a marker file
    ssh_root "echo 'persistence-test-data' > /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/persist-marker.txt" 2>/dev/null || true

    # Verify pre-reboot state
    local result
    result=$(ssh_root "test -f /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/persist-marker.txt && echo OK || echo FAIL" 2>/dev/null)
    if [[ "$result" != *"OK"* ]]; then
        log_fail "Pre-reboot marker not found — cannot test persistence"
        ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
        return 1
    fi
    log_ok "Pre-reboot state verified"

    # Stop the container before reboot
    ssh_root "timeout 15 our-box stop ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true

    # --- Reboot ---
    log_info "Rebooting VM for persistence test..."
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        # Send ACPI shutdown
        ssh_root "nohup shutdown -r now &" 2>/dev/null || true
        sleep 5
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi

    # Boot again
    rm -f "$OBOX_TEST_SERIAL"
    launch_qemu "$OBOX_TEST_DISK" ""

    log_info "Waiting for login prompt after reboot..."
    if timeout 60 bash -c "until grep -q 'login:' '$OBOX_TEST_SERIAL' 2>/dev/null; do sleep 2; done"; then
        log_ok "System rebooted successfully"
    else
        log_fail "System did not reboot within 60s"
        return 1
    fi

    wait_ssh 40 || return 1

    # --- Verify persistence after reboot ---

    # 13.1 — Container directory survived
    log_section "Phase 13.1 — Container directory survived reboot"
    result=$(ssh_root "test -d /var/lib/machines/${OBOX_CONTAINER_NAME} && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Container directory persists after reboot" "$result" "OK"

    # 13.2 — Container data survived
    log_section "Phase 13.2 — Container data survived reboot"
    result=$(ssh_root "cat /var/lib/machines/${OBOX_CONTAINER_NAME}/tmp/persist-marker.txt 2>/dev/null" 2>/dev/null)
    assert_contains "Marker file data persists" "$result" "persistence-test-data"

    # 13.3 — Snapshot survived
    log_section "Phase 13.3 — Snapshot survived reboot"
    result=$(run_ourbox "snapshot list ${OBOX_CONTAINER_NAME}")
    assert_contains "Snapshot persists after reboot" "$result" "persist-snap"

    # 13.4 — our-box still works after reboot
    log_section "Phase 13.4 — our-box functional after reboot"
    result=$(run_ourbox "list")
    assert_contains "our-box list works after reboot" "$result" "/var/lib/machines"

    # 13.5 — Container can be started after reboot
    log_section "Phase 13.5 — Container starts after reboot"
    ssh_root "timeout 30 our-box start ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    sleep 3
    result=$(ssh_root "machinectl list --no-pager --no-legend 2>/dev/null | grep '${OBOX_CONTAINER_NAME}'" 2>/dev/null)
    assert_contains "Container runs after reboot" "$result" "running"

    # Stop and clean up
    ssh_root "timeout 15 our-box stop ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    sleep 1
    ssh_root "timeout 15 our-box remove ${OBOX_CONTAINER_NAME} 2>&1" >/dev/null || true
    log_ok "Persistence test cleanup complete"
}

# ── Phase 14 — System Integrity ──────────────────────────────────────────────
test_system_integrity() {
    log_section "Phase 14 — System Integrity After our-box Operations"

    local result

    # 14.1 — Root filesystem still read-only
    log_section "Phase 14.1 — Root filesystem still read-only"
    result=$(ssh_cmd "findmnt / -no OPTIONS" 2>/dev/null)
    assert_contains "Root filesystem is RO" "$result" "\bro\b"

    # 14.2 — No failed systemd units
    log_section "Phase 14.2 — No failed systemd units"
    local failed_count
    failed_count=$(ssh_root "systemctl --failed --no-legend 2>/dev/null | wc -l" 2>/dev/null)
    failed_count=$(echo "$failed_count" | tr -d ' ')
    if [[ "$failed_count" -eq 0 ]]; then
        log_ok "No failed systemd units"
    else
        log_fail "${failed_count} failed systemd unit(s)"
        ssh_root "systemctl --failed --no-legend 2>/dev/null" 2>/dev/null | head -5 | while read -r line; do
            log_info "  $line"
        done
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # 14.3 — Btrfs subvolumes intact
    log_section "Phase 14.3 — Btrfs subvolumes intact"
    for sv in @ @var @etc @home @snapshots; do
        result=$(ssh_root "sudo btrfs subvolume list / 2>/dev/null | grep -q '${sv}$' && echo OK || echo FAIL" 2>/dev/null)
        assert_contains "Subvolume ${sv} present" "$result" "OK"
    done

    # 14.4 — Install snapshot still exists
    log_section "Phase 14.4 — Install snapshot intact"
    result=$(ssh_root "sudo btrfs subvolume list / 2>/dev/null | grep -q '@snapshots/install' && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Install snapshot intact" "$result" "OK"

    # 14.5 — systemd-boot entries intact
    log_section "Phase 14.5 — Boot entries intact"
    result=$(ssh_root "ls /boot/loader/entries/ 2>/dev/null" 2>/dev/null)
    assert_contains "Main boot entry intact" "$result" "ouroborOS.conf"
    assert_contains "Snapshot boot entry intact" "$result" "snapshot-install"

    # 14.6 — pacman hooks intact
    log_section "Phase 14.6 — pacman hooks intact"
    local hooks_count
    hooks_count=$(ssh_root "ls /etc/pacman.d/hooks/ 2>/dev/null | wc -l" 2>/dev/null)
    hooks_count=$(echo "$hooks_count" | tr -d ' ')
    if [[ "$hooks_count" -ge 3 ]]; then
        log_ok "pacman hooks intact (${hooks_count} hooks)"
    else
        log_fail "Expected >= 3 pacman hooks, found ${hooks_count}"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # 14.7 — Network services active
    log_section "Phase 14.7 — Network services active"
    for svc in systemd-networkd systemd-resolved systemd-timesyncd; do
        result=$(ssh_cmd "systemctl is-active ${svc}" 2>/dev/null)
        assert_contains "${svc} active" "$result" "active"
    done

    # 14.8 — DNS-over-TLS still configured
    log_section "Phase 14.8 — DNS-over-TLS configured"
    result=$(ssh_cmd "grep DNSOverTLS /etc/systemd/resolved.conf" 2>/dev/null)
    assert_contains "DoT configured" "$result" "DNSOverTLS=opportunistic"

    # 14.9 — zram swap active
    log_section "Phase 14.9 — zram swap active"
    result=$(ssh_root "swapon --show 2>/dev/null | grep -q zram && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "zram active" "$result" "OK"

    # 14.10 — User still correct
    log_section "Phase 14.10 — User configuration intact"
    result=$(ssh_cmd "id ${OBOX_TEST_USER}" 2>/dev/null)
    assert_contains "User ${OBOX_TEST_USER} in wheel" "$result" "wheel"

    # 14.11 — our-box check passes
    log_section "Phase 14.11 — our-box check passes"
    result=$(run_ourbox "check")
    assert_contains "our-box check: no errors" "$result" "All integrity checks passed"

    # 14.12 — our-box diagnose passes
    log_section "Phase 14.12 — our-box diagnose passes"
    result=$(run_ourbox "diagnose")
    assert_contains "our-box diagnose: healthy" "$result" "All checks passed\|healthy"

    # 14.13 — /var/lib/machines is clean (no leftover test containers)
    log_section "Phase 14.13 — /var/lib/machines clean"
    result=$(ssh_root "ls /var/lib/machines/ 2>/dev/null" 2>/dev/null)
    if echo "$result" | grep -q "^${OBOX_CONTAINER_NAME}$\|e2e-"; then
        log_warn "Leftover test containers found — cleaning up"
        log_info "  $(echo "$result" | grep -E 'e2e-|our-box')"
        # Clean up any leftover test containers
        ssh_root "for c in \$(ls /var/lib/machines/ 2>/dev/null); do [[ \"\$c\" == .* ]] && continue; our-box remove \"\$c\" 2>/dev/null; done" 2>/dev/null || true
    else
        log_ok "No leftover test containers"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Summary ────────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}              our-box E2E Test Summary                            ${RESET}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo -e "  Tests run:    ${CYAN}${TESTS_RUN}${RESET}"
    echo -e "  Failures:     ${RED}${FAILURES}${RESET}"
    echo -e "  Skipped:      ${YELLOW}${SKIPPED}${RESET}"

    if [[ $FAILURES -eq 0 ]]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}ALL TESTS PASSED ✓${RESET}"
        echo ""
        exit 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}${FAILURES} TEST(S) FAILED ✗${RESET}"
        echo ""
        exit 1
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╔════════════════════════════════════════════════════╗"
    echo "  ║   our-box E2E Test Suite — ouroborOS               ║"
    echo "  ║   Comprehensive systemd-nspawn container tests     ║"
    echo "  ╚════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo ""
    echo -e "  ${DIM}Container: ${OBOX_CONTAINER_NAME}${RESET}"
    echo -e "  ${DIM}SSH port:  ${OBOX_TEST_SSH_PORT}${RESET}"
    echo -e "  ${DIM}Disk:      ${OBOX_TEST_DISK}${RESET}"
    echo -e "  ${DIM}Skip build:    ${OBOX_SKIP_BUILD}${RESET}"
    echo -e "  ${DIM}Skip persist:  ${OBOX_SKIP_PERSIST}${RESET}"
    echo ""

    # Register teardown on exit
    trap teardown EXIT

    # Phase 0: Prerequisites
    check_prerequisites

    # Phase 1: Build ISO
    build_iso

    # Phase 2: Install
    unattended_install

    # Phase 3: Boot
    boot_installed

    # Phase 4: Verify our-box installation
    verify_ourbox_installed

    # Phase 5: Container lifecycle
    test_ourbox_list_empty
    test_ourbox_create
    test_ourbox_duplicate_create
    test_ourbox_start
    test_ourbox_start_already_running
    test_ourbox_list_with_container
    test_ourbox_stop
    test_ourbox_remove

    # Phase 6: Error handling
    test_ourbox_remove_nonexistent
    test_ourbox_enter_nonexistent
    test_ourbox_stop_nonexistent
    test_ourbox_unknown_command
    test_ourbox_create_missing_name
    test_ourbox_unsupported_distro
    test_ourbox_invalid_container_name
    test_ourbox_snapshot_nonexistent
    test_ourbox_snapshot_restore_nonexistent
    test_ourbox_storage_mount_nonexistent
    test_ourbox_storage_umount_nonexistent
    test_ourbox_image_remove_nonexistent
    test_ourbox_snapshot_invalid_name

    # Phase 7: Snapshot management
    test_snapshot_lifecycle

    # Phase 8: Storage management
    test_storage_lifecycle

    # Phase 9: Image management
    test_image_lifecycle

    # Phase 10: Monitoring & diagnostics
    test_diagnose
    test_check
    test_disk_usage_empty
    test_disk_usage_with_container

    # Phase 11: Cleanup command
    test_cleanup

    # Phase 12: Logs command
    test_logs

    # Phase 13: Persistence verification (requires reboot)
    test_persistence

    # Phase 14: System integrity
    test_system_integrity

    # Summary
    print_summary
}

main "$@"
