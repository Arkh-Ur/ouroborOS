#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# e2e-desktop-profiles.sh — E2E tests for each desktop profile
# =============================================================================
# Builds the ISO once, then for EACH desktop profile (minimal, hyprland, niri,
# gnome, kde) performs:
#   Phase 0  — Prerequisites
#   Phase 1  — Build ISO (once)
#   Phase 2  — Unattended install with the profile
#   Phase 3  — Boot installed system
#   Phase 4  — Profile-specific verification via SSH
#   Phase 5  — Per-profile report
#   Phase 6  — Final summary with ✓/✗ per profile
#
# Prerequisites (host):
#   sudo pacman -S --needed qemu-system-x86 edk2-ovmf openssh sshpass
#   /dev/kvm must exist (KVM required)
#   Host RAM >= 8 GB
#
# Environment variables:
#   DP_TEST_PASSWORD    — user password for SSH (default: changeme)
#   DP_TEST_USER        — username for SSH (default: admin)
#   DP_TEST_SSH_PORT    — forwarded SSH port (default: 2222)
#   DP_TEST_DISK_SIZE   — qcow2 disk size (default: 20G)
#   DP_QEMU_MEMORY      — RAM for QEMU VM in MB (default: 2048)
#   DP_BUILD_WORKDIR    — ISO build workdir (default: /home/dp-build)
#   DP_SKIP_BUILD       — set to 1 to skip ISO build (uses existing ISO)
#   DP_KEEP_ARTIFACTS   — set to 1 to keep qcow2/logs after tests
#   DP_PROFILES         — profiles to test (default: minimal hyprland niri gnome kde)
#   DP_SERIAL_DIR       — directory for serial logs (default: /tmp/dp-serial)
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
DP_TEST_PASSWORD="${DP_TEST_PASSWORD:-changeme}"
DP_TEST_USER="${DP_TEST_USER:-admin}"
DP_TEST_SSH_PORT="${DP_TEST_SSH_PORT:-2222}"
DP_TEST_DISK_SIZE="${DP_TEST_DISK_SIZE:-20G}"
DP_QEMU_MEMORY="${DP_QEMU_MEMORY:-2048}"
DP_BUILD_WORKDIR="${DP_BUILD_WORKDIR:-/home/dp-build}"
DP_SKIP_BUILD="${DP_SKIP_BUILD:-0}"
DP_KEEP_ARTIFACTS="${DP_KEEP_ARTIFACTS:-0}"
DP_PROFILES="${DP_PROFILES:-minimal hyprland niri gnome kde}"
DP_SERIAL_DIR="${DP_SERIAL_DIR:-/tmp/dp-serial}"

readonly OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
readonly OVMF_CODE_LEGACY="/usr/share/edk2-ovmf/x64/OVMF_CODE.4m.fd"

WORKSPACE="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
FAILURES=0
SKIPPED=0
TESTS_RUN=0
QEMU_PID=""
OVMF_PATH=""
ISO_PATH=""

# Per-profile results: associative array profile -> "PASS" | "FAIL" | "SKIP"
declare -A PROFILE_RESULTS
# Per-profile failure counts
declare -A PROFILE_FAILURES

# ── SSH Helpers ────────────────────────────────────────────────────────────────
ssh_cmd() {
    sshpass -p "$DP_TEST_PASSWORD" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$DP_TEST_SSH_PORT" \
        "${DP_TEST_USER}@localhost" "$@"
}

ssh_root() {
    sshpass -p "$DP_TEST_PASSWORD" ssh \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -p "$DP_TEST_SSH_PORT" \
        "${DP_TEST_USER}@localhost" \
        "echo ${DP_TEST_PASSWORD} | sudo -S $*"
}

wait_ssh() {
    local max_attempts="${1:-40}"
    local attempt=1
    log_info "Waiting for SSH on port ${DP_TEST_SSH_PORT}..."
    while ! ssh_cmd true 2>/dev/null; do
        if [[ $attempt -ge $max_attempts ]]; then
            log_fail "SSH did not become available after ${max_attempts} attempts"
            return 1
        fi
        sleep 3
        attempt=$((attempt + 1))
    done
    log_ok "SSH available on port ${DP_TEST_SSH_PORT}"
}

wait_qemu_exit() {
    local timeout_secs="${1:-900}"
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

launch_qemu() {
    local disk_path="$1"
    local iso_path="${2:-}"
    local serial_log="$3"
    local config_iso="${4:-}"

    # Kill any existing QEMU on the same port
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi

    local qemu_args
    qemu_args=(
        -enable-kvm
        -cpu host
        -smp 2
        -m "$DP_QEMU_MEMORY"
        -drive "if=pflash,format=raw,readonly=on,file=${OVMF_PATH}"
        -drive "file=${disk_path},format=qcow2,if=virtio,cache=writeback"
        -netdev "user,id=net0,hostfwd=tcp::${DP_TEST_SSH_PORT}-:22"
        -device e1000,netdev=net0
        -rtc base=utc,clock=host
        -serial "file:${serial_log}"
        -vga virtio
        -display none
        -vnc :2
    )

    if [[ -n "$iso_path" ]]; then
        qemu_args+=(-cdrom "$iso_path" -boot d)
    fi

    # Attach config ISO as second CD-ROM drive (IDE slave on secondary channel)
    # archiso live auto-mounts all CD-ROMs under /run/media/
    if [[ -n "$config_iso" ]]; then
        qemu_args+=(-drive "file=${config_iso},format=raw,media=cdrom,readonly=on")
    fi

    qemu-system-x86_64 "${qemu_args[@]}" &
    QEMU_PID=$!
    log_info "QEMU PID: ${QEMU_PID}"
}

kill_qemu() {
    if [[ -n "$QEMU_PID" ]] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    QEMU_PID=""
}

# Assert helpers
assert_contains() {
    local description="$1"
    local output="$2"
    local pattern="$3"
    if echo "$output" | grep -qE "$pattern"; then
        log_ok "${description}"
    else
        log_fail "${description}"
        log_info "  Expected pattern: ${pattern}"
        log_info "  Output: $(echo "$output" | tail -5)"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# Generate a config YAML for a specific desktop profile
# Creates a temporary file and echoes its path
generate_profile_config() {
    local profile="$1"
    local config_file
    config_file="$(mktemp "/tmp/dp-config-${profile}.XXXXXX.yaml")"

    cat > "$config_file" <<YAML
disk:
  device: /dev/vda
  use_luks: false
  btrfs_label: ouroborOS
  swap_type: zram

locale:
  locale: en_US.UTF-8
  keymap: us
  timezone: America/Santiago

network:
  hostname: ouroboros
  enable_networkd: true
  enable_iwd: true
  enable_resolved: true

user:
  username: ${DP_TEST_USER}
  password: ${DP_TEST_PASSWORD}
  groups:
    - wheel
    - audio
    - video
    - input
  shell: /bin/bash
  homed_storage: subvolume

desktop:
  profile: ${profile}

extra_packages:
  - openssh

post_install_action: shutdown
YAML

    echo "$config_file"
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
    if [[ "$iso_count" -eq 0 ]] && [[ "$DP_SKIP_BUILD" == "1" ]]; then
        log_fail "No ISO found in out/ and DP_SKIP_BUILD=1"
        exit 2
    fi
    log_ok "ISO ready (found: ${iso_count}, skip_build: ${DP_SKIP_BUILD})"

    # Port not in use
    if ss -tlnp 2>/dev/null | grep -q ":${DP_TEST_SSH_PORT} "; then
        log_fail "Port ${DP_TEST_SSH_PORT} is already in use"
        exit 2
    fi
    log_ok "Port ${DP_TEST_SSH_PORT} available"

    # Create serial log directory
    mkdir -p "$DP_SERIAL_DIR"
    log_ok "Serial log dir: ${DP_SERIAL_DIR}"
}

# ── Phase 1 — Build ISO ────────────────────────────────────────────────────────
build_iso() {
    log_section "Phase 1 — Build ISO"

    if [[ "$DP_SKIP_BUILD" == "1" ]]; then
        log_skip "DP_SKIP_BUILD=1 — using existing ISO"
        ISO_PATH=$(find "$WORKSPACE/out" -name 'ouroborOS-*.iso' -print -quit 2>/dev/null)
        local size
        size=$(stat -c%s "$ISO_PATH" 2>/dev/null || echo 0)
        log_info "ISO: ${ISO_PATH} ($(numfmt --to=iec "$size"))"
        return 0
    fi

    log_info "Building ISO (workdir: ${DP_BUILD_WORKDIR})..."

    local build_output
    if build_output=$(echo "$DP_TEST_PASSWORD" | sudo -S bash "$WORKSPACE/src/scripts/build-iso.sh" \
        --clean --workdir "$DP_BUILD_WORKDIR" 2>&1); then
        log_ok "ISO build completed"
    else
        log_fail "ISO build failed"
        echo "$build_output" | tail -20
        exit 1
    fi

    # Verify ISO
    ISO_PATH=$(find "$WORKSPACE/out" -name 'ouroborOS-*.iso' -print -quit 2>/dev/null)
    if [[ -z "$ISO_PATH" ]]; then
        log_fail "ISO not found in out/ after build"
        exit 1
    fi

    local size
    size=$(stat -c%s "$ISO_PATH" 2>/dev/null || echo 0)
    local size_mb=$((size / 1024 / 1024))

    if [[ $size_mb -lt 800 ]]; then
        log_fail "ISO too small: ${size_mb} MB (minimum: 800 MB)"
        exit 1
    fi
    if [[ $size_mb -gt 3072 ]]; then
        log_fail "ISO too large: ${size_mb} MB (maximum: 3072 MB)"
        exit 1
    fi

    log_ok "ISO verified: ${ISO_PATH} (${size_mb} MB)"
}

# ── Test a single desktop profile ──────────────────────────────────────────────
test_profile() {
    local profile="$1"
    local disk_path="${DP_SERIAL_DIR}/${profile}-test.qcow2"
    local serial_install="${DP_SERIAL_DIR}/${profile}-serial-install.log"
    local serial_boot="${DP_SERIAL_DIR}/${profile}-serial-boot.log"
    local config_file
    local result

    # Track per-profile failures
    local profile_failures=0
    PROFILE_FAILURES["$profile"]=0

    # ── Phase 2 — Unattended Install ───────────────────────────────────────────
    log_section "Phase 2 — Install [${BOLD}${profile}${RESET}]"

    # Clean previous artifacts for this profile
    rm -f "$disk_path" "$serial_install" "$serial_boot"

    # Generate config YAML for this profile
    config_file=$(generate_profile_config "$profile")
    log_info "Generated config: ${config_file} (profile: ${profile})"

    # Create virtual disk
    log_info "Creating virtual disk (${DP_TEST_DISK_SIZE})..."
    qemu-img create -f qcow2 "$disk_path" "$DP_TEST_DISK_SIZE" >/dev/null

    # Create a small ISO9660 with ouroborOS-config.yaml as the second CD-ROM.
    # The installer discovers it via /run/media/<label>/ouroborOS-config.yaml
    # (find_unattended_config search priority #4).
    local config_iso
    config_iso="${DP_SERIAL_DIR}/${profile}-config.iso"
    rm -f "$config_iso"

    log_info "Creating config ISO..."
    local config_staging
    config_staging="${DP_SERIAL_DIR}/config-staging"
    rm -rf "$config_staging"
    mkdir -p "$config_staging"
    cp "$config_file" "${config_staging}/ouroborOS-config.yaml"

    genisoimage -J -R -V "OUROBOROS-CONFIG" -o "$config_iso" \
        -graft-points "${config_staging}/=/." >/dev/null 2>&1
    rm -rf "$config_staging"
    log_ok "Config ISO created: ${config_iso}"

    log_info "Launching QEMU for unattended install [${profile}]..."
    launch_qemu "$disk_path" "$ISO_PATH" "$serial_install" "$config_iso"

    # Wait for install to complete
    if ! wait_qemu_exit 900; then
        log_fail "Install [${profile}] — QEMU did not exit"
        PROFILE_RESULTS["$profile"]="FAIL"
        PROFILE_FAILURES["$profile"]=$((profile_failures + 1))
        rm -f "$config_file" "$config_iso"
        return 1
    fi

    # Verify install serial log
    log_info "Verifying install log [${profile}]..."
    local states_ok=true

    for state in INIT PREFLIGHT LOCALE USER DESKTOP PARTITION FORMAT INSTALL CONFIGURE SNAPSHOT FINISH; do
        if grep -q "State completed: ${state}" "$serial_install" 2>/dev/null; then
            log_ok "Install state: ${state}"
        else
            log_fail "Install state MISSING: ${state}"
            states_ok=false
            profile_failures=$((profile_failures + 1))
        fi
    done

    # No FAILED/ERROR from installer
    if grep -E "^\[.*FAILED\]|\[ERROR\]" "$serial_install" 2>/dev/null; then
        log_fail "Installer reported FAILED/ERROR lines"
        profile_failures=$((profile_failures + 1))
    else
        log_ok "No installer errors"
    fi

    # Snapshot created
    if grep -q "Snapshot created" "$serial_install" 2>/dev/null; then
        log_ok "Install snapshot created"
    else
        log_fail "Install snapshot missing"
        profile_failures=$((profile_failures + 1))
    fi

    # Boot entry written
    if grep -q "Boot entry written" "$serial_install" 2>/dev/null; then
        log_ok "Boot entry written"
    else
        log_fail "Boot entry missing"
        profile_failures=$((profile_failures + 1))
    fi

    if [[ "$states_ok" != "true" ]]; then
        PROFILE_RESULTS["$profile"]="FAIL"
        PROFILE_FAILURES["$profile"]=$profile_failures
        rm -f "$config_file" "$config_iso"
        return 1
    fi

    rm -f "$config_file" "$config_iso"

    # ── Phase 3 — Boot Installed System ───────────────────────────────────────
    log_section "Phase 3 — Boot [${BOLD}${profile}${RESET}]"

    launch_qemu "$disk_path" "" "$serial_boot"

    # Wait for login prompt
    log_info "Waiting for login prompt [${profile}]..."
    if timeout 60 bash -c "until grep -q 'login:' '$serial_boot' 2>/dev/null; do sleep 2; done"; then
        log_ok "Login prompt reached"
    else
        log_fail "Login prompt not reached within 60s"
        kill_qemu
        PROFILE_RESULTS["$profile"]="FAIL"
        PROFILE_FAILURES["$profile"]=$((profile_failures + 1))
        return 1
    fi

    # Verify clean boot
    if grep -q "FAILED" "$serial_boot" 2>/dev/null; then
        log_fail "Boot has FAILED systemd units"
        profile_failures=$((profile_failures + 1))
    else
        log_ok "Clean boot (no FAILED units in serial)"
    fi

    # Wait for SSH
    if ! wait_ssh 60; then
        log_fail "SSH not available [${profile}]"
        kill_qemu
        PROFILE_RESULTS["$profile"]="FAIL"
        PROFILE_FAILURES["$profile"]=$((profile_failures + 1))
        return 1
    fi

    # ── Phase 4 — Profile-specific Verification ───────────────────────────────
    log_section "Phase 4 — Verify [${BOLD}${profile}${RESET}]"

    # 4.1 — No failed systemd units
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
        profile_failures=$((profile_failures + 1))
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # 4.2 — Root filesystem is read-only
    result=$(ssh_cmd "findmnt / -no OPTIONS" 2>/dev/null)
    assert_contains "Root filesystem is RO" "$result" "\bro\b"

    # 4.3 — Profile-specific checks
    case "$profile" in
        minimal)
            verify_profile_minimal
            ;;
        hyprland)
            verify_profile_hyprland
            ;;
        niri)
            verify_profile_niri
            ;;
        gnome)
            verify_profile_gnome
            ;;
        kde)
            verify_profile_kde
            ;;
    esac

    # 4.4 — SSH server is running (all profiles get openssh via extra_packages)
    result=$(ssh_root "systemctl is-active sshd" 2>/dev/null)
    assert_contains "SSH server (sshd) is active" "$result" "active"

    # ── Phase 5 — Teardown this profile ──────────────────────────────────────
    kill_qemu
    rm -f "$disk_path"

    # Store result
    PROFILE_FAILURES["$profile"]=$profile_failures
    if [[ $profile_failures -eq 0 ]]; then
        PROFILE_RESULTS["$profile"]="PASS"
    else
        PROFILE_RESULTS["$profile"]="FAIL"
    fi

    log_section "Phase 5 — Profile [${BOLD}${profile}${RESET}] complete: ${PROFILE_RESULTS["$profile"]}"
}

# ── Minimal profile verification ──────────────────────────────────────────────
verify_profile_minimal() {
    local result

    log_info "Checking minimal profile specifics..."

    # No display manager should be active
    result=$(ssh_root "systemctl is-active display-manager 2>/dev/null; echo EXIT_CODE:\$?" 2>/dev/null)
    if echo "$result" | grep -qE "inactive|unknown|EXIT_CODE:[3-9]"; then
        log_ok "No display manager (TTY-only, as expected)"
    else
        log_fail "Display manager is active but minimal should be TTY-only"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # No desktop packages installed
    result=$(ssh_root "pacman -Q hyprland niri gnome-shell plasma-desktop 2>/dev/null; echo EXIT_CODE:\$?" 2>/dev/null)
    if echo "$result" | grep -q "EXIT_CODE:1"; then
        log_ok "No desktop packages installed (as expected)"
    else
        log_fail "Unexpected desktop packages found in minimal profile"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))
}

# ── Hyprland profile verification ─────────────────────────────────────────────
verify_profile_hyprland() {
    local result

    log_info "Checking hyprland profile specifics..."

    # hyprland package installed
    result=$(ssh_root "pacman -Q hyprland 2>/dev/null" 2>/dev/null)
    assert_contains "hyprland package installed" "$result" "hyprland"

    # waybar installed
    result=$(ssh_root "pacman -Q waybar 2>/dev/null" 2>/dev/null)
    assert_contains "waybar package installed" "$result" "waybar"

    # foot terminal installed
    result=$(ssh_root "pacman -Q foot 2>/dev/null" 2>/dev/null)
    assert_contains "foot package installed" "$result" "foot"

    # No display manager (hyprland launches from TTY)
    result=$(ssh_root "systemctl is-active display-manager 2>/dev/null; echo EXIT_CODE:\$?" 2>/dev/null)
    if echo "$result" | grep -qE "inactive|unknown|EXIT_CODE:[3-9]"; then
        log_ok "No display manager (hyprland launches from TTY)"
    else
        log_fail "Display manager active but hyprland should be TTY-only"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # Hyprland binary exists
    result=$(ssh_root "test -x /usr/bin/Hyprland && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "Hyprland binary exists" "$result" "OK"
}

# ── Niri profile verification ─────────────────────────────────────────────────
verify_profile_niri() {
    local result

    log_info "Checking niri profile specifics..."

    # niri package installed
    result=$(ssh_root "pacman -Q niri 2>/dev/null" 2>/dev/null)
    assert_contains "niri package installed" "$result" "niri"

    # foot terminal installed
    result=$(ssh_root "pacman -Q foot 2>/dev/null" 2>/dev/null)
    assert_contains "foot package installed" "$result" "foot"

    # fuzzel installed
    result=$(ssh_root "pacman -Q fuzzel 2>/dev/null" 2>/dev/null)
    assert_contains "fuzzel package installed" "$result" "fuzzel"

    # No display manager (niri launches from TTY)
    result=$(ssh_root "systemctl is-active display-manager 2>/dev/null; echo EXIT_CODE:\$?" 2>/dev/null)
    if echo "$result" | grep -qE "inactive|unknown|EXIT_CODE:[3-9]"; then
        log_ok "No display manager (niri launches from TTY)"
    else
        log_fail "Display manager active but niri should be TTY-only"
    fi
    TESTS_RUN=$((TESTS_RUN + 1))

    # niri binary exists
    result=$(ssh_root "test -x /usr/bin/niri && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "niri binary exists" "$result" "OK"
}

# ── GNOME profile verification ────────────────────────────────────────────────
verify_profile_gnome() {
    local result

    log_info "Checking gnome profile specifics..."

    # gnome-shell package installed
    result=$(ssh_root "pacman -Q gnome-shell 2>/dev/null" 2>/dev/null)
    assert_contains "gnome-shell package installed" "$result" "gnome-shell"

    # gnome-tweaks installed
    result=$(ssh_root "pacman -Q gnome-tweaks 2>/dev/null" 2>/dev/null)
    assert_contains "gnome-tweaks package installed" "$result" "gnome-tweaks"

    # gdm is the display manager and should be active
    result=$(ssh_root "systemctl is-active gdm 2>/dev/null" 2>/dev/null)
    assert_contains "gdm display manager is active" "$result" "active"

    # display-manager.service is gdm
    result=$(ssh_root "systemctl is-active display-manager 2>/dev/null" 2>/dev/null)
    assert_contains "display-manager alias is active" "$result" "active"

    # gnome binary exists
    result=$(ssh_root "test -x /usr/bin/gnome-shell && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "gnome-shell binary exists" "$result" "OK"
}

# ── KDE profile verification ──────────────────────────────────────────────────
verify_profile_kde() {
    local result

    log_info "Checking kde profile specifics..."

    # plasma-desktop package installed (part of plasma meta)
    result=$(ssh_root "pacman -Q plasma-desktop 2>/dev/null || pacman -Q plasma 2>/dev/null" 2>/dev/null)
    assert_contains "plasma package installed" "$result" "plasma"

    # kde-applications-meta installed
    result=$(ssh_root "pacman -Q kde-applications-meta 2>/dev/null" 2>/dev/null)
    assert_contains "kde-applications-meta package installed" "$result" "kde-applications-meta"

    # sddm is the display manager and should be active
    result=$(ssh_root "systemctl is-active sddm 2>/dev/null" 2>/dev/null)
    assert_contains "sddm display manager is active" "$result" "active"

    # display-manager.service is sddm
    result=$(ssh_root "systemctl is-active display-manager 2>/dev/null" 2>/dev/null)
    assert_contains "display-manager alias is active" "$result" "active"

    # sddm binary exists
    result=$(ssh_root "test -x /usr/bin/sddm && echo OK || echo FAIL" 2>/dev/null)
    assert_contains "sddm binary exists" "$result" "OK"
}

# ── Teardown ───────────────────────────────────────────────────────────────────
# shellcheck disable=SC2329  # invoked via 'trap teardown EXIT'
teardown() {
    log_section "Teardown"

    kill_qemu

    if [[ "$DP_KEEP_ARTIFACTS" != "1" ]]; then
        log_info "Cleaning test artifacts..."
        rm -rf "$DP_SERIAL_DIR"
        sudo rm -rf "$DP_BUILD_WORKDIR" 2>/dev/null || true
        rm -f /tmp/dp-config-*.yaml
    else
        log_info "Keeping artifacts (DP_KEEP_ARTIFACTS=1):"
        log_info "  Serial logs: ${DP_SERIAL_DIR}"
        log_info "  Build:       ${DP_BUILD_WORKDIR}"
    fi
}

# ── Summary ────────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}        Desktop Profiles E2E Test Summary                      ${RESET}"
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    # Table header
    printf "  ${BOLD}%-12s %-8s %-10s${RESET}\n" "Profile" "Status" "Failures"
    printf "  %-12s %-8s %-10s\n" "-------" "------" "--------"

    local total_pass=0
    local total_fail=0
    local total_skip=0

    for profile in $DP_PROFILES; do
        local status="${PROFILE_RESULTS[$profile]:-SKIP}"
        local failures="${PROFILE_FAILURES[$profile]:-0}"

        case "$status" in
            PASS)
                printf "  ${GREEN}%-12s %-8s %-10s${RESET}\n" "$profile" "✓ PASS" "$failures"
                total_pass=$((total_pass + 1))
                ;;
            FAIL)
                printf "  ${RED}%-12s %-8s %-10s${RESET}\n" "$profile" "✗ FAIL" "$failures"
                total_fail=$((total_fail + 1))
                ;;
            SKIP)
                printf "  ${YELLOW}%-12s %-8s %-10s${RESET}\n" "$profile" "⏭ SKIP" "$failures"
                total_skip=$((total_skip + 1))
                ;;
        esac
    done

    echo ""
    echo -e "  Total tests run:  ${CYAN}${TESTS_RUN}${RESET}"
    echo -e "  Profiles passed:  ${GREEN}${total_pass}${RESET}"
    echo -e "  Profiles failed:  ${RED}${total_fail}${RESET}"
    echo -e "  Profiles skipped: ${YELLOW}${total_skip}${RESET}"
    echo -e "  Check failures:   ${RED}${FAILURES}${RESET}"
    echo -e "  Skipped checks:   ${YELLOW}${SKIPPED}${RESET}"

    if [[ $total_fail -eq 0 ]]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}ALL PROFILES PASSED ✓${RESET}"
        echo ""
        exit 0
    else
        echo ""
        echo -e "  ${RED}${BOLD}${total_fail} PROFILE(S) FAILED ✗${RESET}"
        echo ""
        exit 1
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╔════════════════════════════════════════════════════╗"
    echo "  ║   Desktop Profiles E2E Test Suite — ouroborOS       ║"
    echo "  ║   Tests install + boot for each desktop profile    ║"
    echo "  ╚════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo ""
    echo -e "  ${DIM}Profiles:  ${DP_PROFILES}${RESET}"
    echo -e "  ${DIM}SSH port:  ${DP_TEST_SSH_PORT}${RESET}"
    echo -e "  ${DIM}User:      ${DP_TEST_USER}${RESET}"
    echo -e "  ${DIM}Skip build:    ${DP_SKIP_BUILD}${RESET}"
    echo -e "  ${DIM}Keep artifacts: ${DP_KEEP_ARTIFACTS}${RESET}"
    echo ""

    # Register teardown on exit
    trap teardown EXIT

    # Phase 0: Prerequisites
    check_prerequisites

    # Phase 1: Build ISO (once, shared by all profiles)
    build_iso

    # Test each profile
    local profile_counter=0
    local total_profiles
    # shellcheck disable=SC2086
    total_profiles=$(echo $DP_PROFILES | wc -w)

    for profile in $DP_PROFILES; do
        profile_counter=$((profile_counter + 1))
        log_section "Profile ${profile_counter}/${total_profiles}: ${BOLD}${profile}${RESET}"
        PROFILE_RESULTS["$profile"]="SKIP"
        PROFILE_FAILURES["$profile"]=0

        # Run profile test — continue to next profile even if one fails
        if ! test_profile "$profile"; then
            log_warn "Profile [${profile}] had failures — continuing with next profile"
        fi

        echo ""
    done

    # Summary
    print_summary
}

main "$@"
