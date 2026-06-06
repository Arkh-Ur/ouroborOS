#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# launch-vm.sh — ouroborOS QEMU Development VM Launcher
# =============================================================================
# Boots the latest ouroborOS ISO in QEMU for manual testing and development.
# The VM exposes VNC on :3 (port 5903) and SSH on port 2225.
#
# Usage:
#   bash src/scripts/launch-vm.sh [OPTIONS]
#
# Options:
#   -i, --iso PATH       ISO to boot (default: latest in ./out/)
#   -d, --disk PATH      QEMU disk image (default: ~/ouroboros-dev.qcow2)
#   --disk-size SIZE     Disk size if creating new image (default: 20G)
#   --ram MB             RAM in megabytes (default: 4096)
#   --cpus N             vCPU count (default: 2)
#   --vnc-port N         VNC display number; port = 5900+N (default: 3)
#   --ssh-port N         Host SSH forward port (default: 2225)
#   --fresh              Recreate the disk image from scratch
#   --screenshot [FILE]  Take a screenshot via QEMU monitor and exit
#                        FILE defaults to /tmp/ouroboros-screen.ppm
#   -h, --help           Show this help message
#
# Requirements:
#   qemu-system-x86_64, OVMF firmware, socat (for --screenshot)
#
# Connection:
#   VNC   → connect your VNC viewer to localhost:5903 (or display :3)
#   SSH   → ssh -p 2225 root@localhost   (password: toor)
#   QEMU  → monitor socket at /tmp/ouroboros-qemu.sock
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
ISO_PATH=""
DISK_PATH="${HOME}/ouroboros-dev.qcow2"
DISK_SIZE="20G"
RAM_MB=4096
VCPUS=2
VNC_PORT=3
SSH_PORT=2225
MONITOR_SOCK="/tmp/ouroboros-qemu.sock"
FRESH_DISK=false
SCREENSHOT_MODE=false
SCREENSHOT_FILE="/tmp/ouroboros-screen.ppm"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────${RESET}"; }

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
    sed -n '/^# Usage/,/^# =====/p' "$0" | grep -v '^# =====' | sed 's/^# //'
    exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--iso)          ISO_PATH="$2"; shift 2 ;;
        --iso=*)           ISO_PATH="${1#*=}"; shift ;;
        -d|--disk)         DISK_PATH="$2"; shift 2 ;;
        --disk=*)          DISK_PATH="${1#*=}"; shift ;;
        --disk-size=*)     DISK_SIZE="${1#*=}"; shift ;;
        --disk-size)       DISK_SIZE="$2"; shift 2 ;;
        --ram=*)           RAM_MB="${1#*=}"; shift ;;
        --ram)             RAM_MB="$2"; shift 2 ;;
        --cpus=*)          VCPUS="${1#*=}"; shift ;;
        --cpus)            VCPUS="$2"; shift 2 ;;
        --vnc-port=*)      VNC_PORT="${1#*=}"; shift ;;
        --vnc-port)        VNC_PORT="$2"; shift 2 ;;
        --ssh-port=*)      SSH_PORT="${1#*=}"; shift ;;
        --ssh-port)        SSH_PORT="$2"; shift 2 ;;
        --fresh)           FRESH_DISK=true; shift ;;
        --screenshot)
            SCREENSHOT_MODE=true
            if [[ $# -gt 1 && ! "$2" =~ ^- ]]; then
                SCREENSHOT_FILE="$2"; shift
            fi
            shift
            ;;
        --screenshot=*)    SCREENSHOT_MODE=true; SCREENSHOT_FILE="${1#*=}"; shift ;;
        -h|--help)         usage ;;
        *) log_error "Unknown option: $1"; usage ;;
    esac
done

# ── Screenshot mode (no VM launch needed) ─────────────────────────────────────
if [[ "${SCREENSHOT_MODE}" == true ]]; then
    log_section "QEMU Screenshot"
    if [[ ! -S "${MONITOR_SOCK}" ]]; then
        log_error "QEMU monitor socket not found: ${MONITOR_SOCK}"
        log_error "Is the VM running? Start it first without --screenshot."
        exit 1
    fi
    if ! command -v socat &>/dev/null; then
        log_error "socat is required for --screenshot. Install: pacman -S socat"
        exit 1
    fi
    log_info "Taking screenshot via QEMU monitor..."
    printf 'screendump %s\n' "${SCREENSHOT_FILE}" | socat - "UNIX-CONNECT:${MONITOR_SOCK}" > /dev/null 2>&1
    # Wait up to 2s for screendump to write the file
    local_retries=0
    until [[ -f "${SCREENSHOT_FILE}" ]] || [[ ${local_retries} -ge 10 ]]; do
        sleep 0.2
        local_retries=$((local_retries + 1))
    done
    if [[ -f "${SCREENSHOT_FILE}" ]]; then
        log_ok "Screenshot saved: ${SCREENSHOT_FILE}"
        # Convert PPM → PNG if ImageMagick or python is available
        PNG_FILE="${SCREENSHOT_FILE%.ppm}.png"
        if command -v magick &>/dev/null; then
            magick "${SCREENSHOT_FILE}" "${PNG_FILE}" && log_ok "PNG: ${PNG_FILE}"
        elif command -v convert &>/dev/null; then
            convert "${SCREENSHOT_FILE}" "${PNG_FILE}" && log_ok "PNG: ${PNG_FILE}"
        elif command -v python3 &>/dev/null; then
            python3 - "${SCREENSHOT_FILE}" "${PNG_FILE}" << 'PYEOF'
import sys
from PIL import Image
Image.open(sys.argv[1]).save(sys.argv[2])
PYEOF
            log_ok "PNG: ${PNG_FILE}"
        fi
    else
        log_error "Screenshot file not found after capture: ${SCREENSHOT_FILE}"
        exit 1
    fi
    exit 0
fi

# ── Preflight ─────────────────────────────────────────────────────────────────
log_section "Preflight"

if ! command -v qemu-system-x86_64 &>/dev/null; then
    log_error "qemu-system-x86_64 not found. Install: pacman -S qemu-system-x86_64"
    exit 1
fi
log_ok "qemu-system-x86_64 found"

# Find OVMF firmware
OVMF_CODE=""
for candidate in \
    /usr/share/edk2/x64/OVMF_CODE.4m.fd \
    /usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
    /usr/share/ovmf/x64/OVMF_CODE.fd; do
    if [[ -f "${candidate}" ]]; then
        OVMF_CODE="${candidate}"
        break
    fi
done
if [[ -z "${OVMF_CODE}" ]]; then
    log_error "OVMF firmware not found. Install: pacman -S edk2-ovmf"
    exit 1
fi
log_ok "OVMF: ${OVMF_CODE}"

# Find ISO
if [[ -z "${ISO_PATH}" ]]; then
    ISO_PATH="$(find "${REPO_ROOT}/out" -maxdepth 1 -name 'ouroborOS-*.iso' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)"
fi
if [[ -z "${ISO_PATH}" || ! -f "${ISO_PATH}" ]]; then
    log_error "No ISO found in ${REPO_ROOT}/out/. Build one first:"
    log_error "  sudo bash src/scripts/build-iso.sh --clean"
    exit 1
fi
log_ok "ISO: ${ISO_PATH}"

# ── Disk image ────────────────────────────────────────────────────────────────
log_section "Disk Image"

if [[ "${FRESH_DISK}" == true && -f "${DISK_PATH}" ]]; then
    log_warn "Removing existing disk: ${DISK_PATH}"
    rm -f "${DISK_PATH}"
fi

if [[ ! -f "${DISK_PATH}" ]]; then
    log_info "Creating new disk image: ${DISK_PATH} (${DISK_SIZE})"
    qemu-img create -f qcow2 "${DISK_PATH}" "${DISK_SIZE}"
    log_ok "Disk created"
else
    DISK_ACTUAL="$(qemu-img info "${DISK_PATH}" 2>/dev/null | awk '/^disk size:/{print $3,$4}' || echo "unknown")"
    log_ok "Reusing existing disk: ${DISK_PATH} (used: ${DISK_ACTUAL})"
fi

# ── Kill stale QEMU processes ─────────────────────────────────────────────────
log_section "Cleanup"

HOST_VNC_PORT=$((5900 + VNC_PORT))
fuser -k "${SSH_PORT}/tcp" 2>/dev/null && log_warn "Killed process on SSH port ${SSH_PORT}" || true
fuser -k "${HOST_VNC_PORT}/tcp" 2>/dev/null && log_warn "Killed process on VNC port ${HOST_VNC_PORT}" || true
rm -f "${MONITOR_SOCK}"
log_ok "Ports clear"

# ── Launch QEMU ───────────────────────────────────────────────────────────────
log_section "Launching VM"

log_info "RAM: ${RAM_MB} MB  vCPUs: ${VCPUS}  VNC: :${VNC_PORT} (port ${HOST_VNC_PORT})  SSH: ${SSH_PORT}"

setsid qemu-system-x86_64 \
    -enable-kvm \
    -m "${RAM_MB}" \
    -smp "${VCPUS}" \
    -drive "if=pflash,format=raw,readonly=on,file=${OVMF_CODE}" \
    -drive "file=${DISK_PATH},format=qcow2" \
    -cdrom "${ISO_PATH}" \
    -boot d \
    -device e1000,netdev=net0 \
    -netdev "user,id=net0,hostfwd=tcp::${SSH_PORT}-:22" \
    -display none \
    -vga std \
    -vnc ":${VNC_PORT}" \
    -monitor "unix:${MONITOR_SOCK},server,nowait" \
    > /tmp/ouroboros-qemu.log 2>&1 &

sleep 1

# Verify QEMU actually started
QEMU_PID="$(pgrep -f "qemu-system-x86_64.*${DISK_PATH}" | head -1 || true)"
if [[ -z "${QEMU_PID}" ]]; then
    log_error "QEMU failed to start. Check /tmp/ouroboros-qemu.log"
    exit 1
fi
log_ok "QEMU running (PID ${QEMU_PID})"

# ── Connection info ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  ouroborOS VM ready${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${GREEN}VNC${RESET}      localhost:${HOST_VNC_PORT}  (display :${VNC_PORT})"
echo -e "  ${GREEN}SSH${RESET}      ssh -p ${SSH_PORT} root@localhost  (pass: toor)"
echo -e "  ${GREEN}Monitor${RESET}  ${MONITOR_SOCK}"
echo -e "  ${GREEN}Log${RESET}      /tmp/ouroboros-qemu.log"
echo ""
echo -e "  ${YELLOW}Screenshot:${RESET}"
echo -e "    bash src/scripts/launch-vm.sh --screenshot /tmp/screen.ppm"
echo ""
echo -e "  ${YELLOW}Stop VM:${RESET}"
echo -e "    kill ${QEMU_PID}"
echo ""

# Persist PID for convenience
echo "${QEMU_PID}" > /tmp/ouroboros-qemu.pid
log_ok "PID saved to /tmp/ouroboros-qemu.pid"
