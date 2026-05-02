#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail
# =============================================================================
# e2e-common.sh — Shared infrastructure for E2E test scripts
# =============================================================================
# Source this file from e2e-phase3.sh, e2e-phase4.sh, etc.
# Inherits set -euo pipefail from the caller.
#
# Requirements (set before sourcing):
#   E2E_PREFIX   — variable prefix, e.g. "P3" or "P4"
#
# After sourcing, these variables must exist:
#   ${E2E_PREFIX}_TEST_USER
#   ${E2E_PREFIX}_TEST_PASSWORD
#   ${E2E_PREFIX}_TEST_SSH_PORT
#   ${E2E_PREFIX}_VNC_DISPLAY
#
# The following are also used but have defaults:
#   FAILURES, SKIPPED, TESTS_RUN (initialized by caller)
#   WORKSPACE (initialized by caller)
#   QEMU_PID (initialized by caller)
#   OVMF_PATH (initialized by caller)
# =============================================================================

# Validate prefix is set
if [[ -z "${E2E_PREFIX:-}" ]]; then
    echo "FATAL: e2e-common.sh requires E2E_PREFIX to be set (e.g. P3, P4)" >&2
    exit 2
fi

# ── Dynamic variable accessors ────────────────────────────────────────────────
# These functions resolve the prefixed variable at runtime.
_e2e_var() {
    local var_name="${E2E_PREFIX}_${1}"
    echo "${!var_name}"
}

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

# ── SSH helpers ────────────────────────────────────────────────────────────────
ssh_cmd() {
    local password user port
    password=$(_e2e_var TEST_PASSWORD)
    user=$(_e2e_var TEST_USER)
    port=$(_e2e_var TEST_SSH_PORT)
    sshpass -p "$password" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$port" \
        "${user}@localhost" "$@"
}

ssh_root() {
    local password
    password=$(_e2e_var TEST_PASSWORD)
    local safe_password safe_cmd
    safe_password=$(printf '%q' "$password")
    # shellcheck disable=SC2059
    printf -v safe_cmd '%q' "$*"
    ssh_cmd "echo ${safe_password} | sudo -S bash -c '${safe_cmd}'"
}

ssh_out() {
    ssh_cmd "$@" 2>/dev/null || { log_warn "ssh_out failed: $*"; true; }
}

ssh_root_out() {
    ssh_root "$@" 2>/dev/null || { log_warn "ssh_root_out failed: $*"; true; }
}

wait_ssh() {
    local max_attempts="${1:-40}"
    local attempt=1
    local port
    port=$(_e2e_var TEST_SSH_PORT)
    log_info "Waiting for SSH on port ${port}..."
    while ! ssh_cmd true 2>/dev/null; do
        if [[ $attempt -ge $max_attempts ]]; then
            log_die "SSH did not become available after ${max_attempts} attempts"
        fi
        sleep 3
        attempt=$((attempt + 1))
    done
    log_ok "SSH available on port ${port}"
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
    local safe_path
    safe_path=$(printf '%q' "$path")
    if ssh_root_out "test -e ${safe_path} && echo yes" | grep -q "yes"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Path not found: ${path}"
    fi
}

assert_file_executable() {
    local description="$1"
    local path="$2"
    TESTS_RUN=$((TESTS_RUN + 1))
    local safe_path
    safe_path=$(printf '%q' "$path")
    if ssh_root_out "test -x ${safe_path} && echo yes" | grep -q "yes"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  File not executable: ${path}"
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

# ── QEMU helpers ───────────────────────────────────────────────────────────────
launch_qemu() {
    local disk="$1"
    local iso="${2:-}"
    local serial="$3"
    local config_iso="${4:-}"
    local memory vnc_display

    memory=$(_e2e_var QEMU_MEMORY)
    vnc_display=$(_e2e_var VNC_DISPLAY)
    local port
    port=$(_e2e_var TEST_SSH_PORT)

    kill_qemu

    # shellcheck disable=SC2054
    local qemu_args=(
        -enable-kvm
        -cpu host
        -smp 2
        -m "$memory"
        -drive "if=pflash,format=raw,readonly=on,file=${OVMF_PATH}"
        -drive "file=${disk},format=qcow2,if=virtio,cache=writeback"
        -netdev "user,id=net0,hostfwd=tcp::${port}-:22"
        -device "e1000,netdev=net0"
        -rtc base=utc,clock=host
        -serial "file:${serial}"
        -vga virtio
        -display none
        -vnc ":${vnc_display}"
    )

    [[ -n "$iso" ]]        && qemu_args+=(-cdrom "$iso" -boot d)
    [[ -n "$config_iso" ]] && qemu_args+=(-drive "file=${config_iso},format=raw,media=cdrom,readonly=on")

    setsid qemu-system-x86_64 "${qemu_args[@]}" &>/dev/null &
    sleep 1
    QEMU_PID=$(pgrep -f "qemu-system-x86_64.*${disk}" | tail -1)
    if [[ -z "$QEMU_PID" ]]; then
        log_die "Failed to detect QEMU process after launch"
    fi
    log_info "QEMU PID: ${QEMU_PID} — VNC: vncviewer localhost:590${vnc_display}"
}

kill_qemu() {
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    QEMU_PID=""
}

wait_qemu_exit() {
    local timeout_secs
    local install_timeout
    install_timeout=$(_e2e_var INSTALL_TIMEOUT)
    timeout_secs="${1:-${install_timeout}}"
    log_info "Waiting for QEMU to finish (timeout: ${timeout_secs}s)..."
    if timeout "$timeout_secs" bash -c "while kill -0 ${QEMU_PID:?} 2>/dev/null; do sleep 3; done"; then
        log_ok "QEMU exited cleanly"
    else
        log_fail "QEMU timed out after ${timeout_secs}s"
        kill_qemu
        return 1
    fi
}
