#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# flash-usb.sh — ouroborOS live USB writer
# =============================================================================
# Safely writes an ouroborOS ISO to a USB drive using dd.
#
# Usage:
#   sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso
#   sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso --device /dev/sdb
#   sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso --device /dev/sdb --yes
#
# Options:
#   -i, --iso FILE       Path to the .iso file (required)
#   -d, --device PATH    Target USB device, e.g. /dev/sdb (interactive if omitted)
#   -y, --yes            Skip the YES confirmation prompt (use in scripts)
#   -h, --help           Show this help message
#
# Safety measures:
#   - Requires root privileges
#   - Validates the ISO file exists and is readable
#   - Verifies SHA256 checksum if a .sha256 file is found alongside the ISO
#   - Detects and rejects the system root disk
#   - Lists only removable/hotplug devices in interactive mode
#   - Unmounts all partitions on the target device before writing
#   - Requires typing "YES" (all caps) to confirm unless --yes is passed
#   - Runs sync after dd to ensure all data is flushed
#
# =============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Logging ───────────────────────────────────────────────────────────────────
log_info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────────${RESET}"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
ISO_FILE=""
TARGET_DEVICE=""
SKIP_CONFIRM=false

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
    sed -n '/^# Usage/,/^# =====/p' "$0" | grep -v '^# =====' | sed 's/^# //'
    exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--iso)     ISO_FILE="$2"; shift 2 ;;
        -d|--device)  TARGET_DEVICE="$2"; shift 2 ;;
        -y|--yes)     SKIP_CONFIRM=true; shift ;;
        -h|--help)    usage ;;
        *) log_error "Unknown option: $1"; usage ;;
    esac
done

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root."
    log_error "Try: sudo bash $0 $*"
    exit 1
fi

# ── ISO validation ────────────────────────────────────────────────────────────
log_section "Validating ISO"

if [[ -z "$ISO_FILE" ]]; then
    log_error "--iso is required."
    echo ""
    usage
fi

if [[ ! -f "$ISO_FILE" ]]; then
    log_error "ISO file not found: ${ISO_FILE}"
    exit 1
fi

if [[ ! -r "$ISO_FILE" ]]; then
    log_error "ISO file is not readable: ${ISO_FILE}"
    exit 1
fi

ISO_SIZE=$(du -sh "$ISO_FILE" | cut -f1)
log_ok "ISO: ${ISO_FILE} (${ISO_SIZE})"

# ── SHA256 verification ───────────────────────────────────────────────────────
SHA256_FILE="${ISO_FILE}.sha256"
if [[ -f "$SHA256_FILE" ]]; then
    log_info "Verifying SHA256 checksum..."
    if sha256sum --check --status "$SHA256_FILE"; then
        log_ok "SHA256 checksum verified."
    else
        log_error "SHA256 checksum FAILED. The ISO may be corrupt."
        log_error "Delete it and rebuild with: sudo bash src/scripts/build-iso.sh --clean"
        exit 1
    fi
else
    log_warn "No .sha256 file found alongside ISO — skipping checksum verification."
    log_warn "Expected: ${SHA256_FILE}"
fi

# ── USB device detection ──────────────────────────────────────────────────────
log_section "USB Device Selection"

# Get list of removable (hotplug) disk devices
_list_usb_devices() {
    # lsblk with JSON output; filter type=disk + hotplug=1
    local lsblk_out
    lsblk_out=$(lsblk --json --output NAME,SIZE,MODEL,TYPE,HOTPLUG,TRAN 2>/dev/null || echo '{}')

    python3 - "$lsblk_out" << 'PYEOF'
import json, sys
data = json.loads(sys.argv[1])
for dev in data.get("blockdevices", []):
    if dev.get("type") == "disk" and dev.get("hotplug"):
        model = (dev.get("model") or "Unknown device").strip()
        print(f"/dev/{dev['name']}\t{dev['size']:>8}\t{model}")
PYEOF
}

if [[ -z "$TARGET_DEVICE" ]]; then
    # Interactive mode: list USB devices and ask
    mapfile -t USB_DEVS < <(_list_usb_devices)

    if [[ ${#USB_DEVS[@]} -eq 0 ]]; then
        log_error "No removable USB devices detected."
        log_error "Plug in a USB drive and run again."
        log_error ""
        log_error "Available block devices (all types):"
        lsblk -o NAME,SIZE,MODEL,TYPE,HOTPLUG,TRAN
        exit 1
    fi

    echo ""
    echo -e "${BOLD}Available USB devices:${RESET}"
    echo ""
    for i in "${!USB_DEVS[@]}"; do
        printf "  %d) %s\n" "$((i + 1))" "${USB_DEVS[$i]}"
    done
    echo ""

    while true; do
        read -r -p "Enter device number (1-${#USB_DEVS[@]}): " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && \
           [[ "$choice" -ge 1 ]] && \
           [[ "$choice" -le ${#USB_DEVS[@]} ]]; then
            TARGET_DEVICE=$(echo "${USB_DEVS[$((choice - 1))]}" | cut -f1)
            break
        fi
        log_warn "Invalid choice. Enter a number between 1 and ${#USB_DEVS[@]}."
    done
fi

# ── Device validation ─────────────────────────────────────────────────────────
log_section "Device Validation"

if [[ ! -b "$TARGET_DEVICE" ]]; then
    log_error "Not a block device: ${TARGET_DEVICE}"
    exit 1
fi

log_info "Target device: ${TARGET_DEVICE}"

# Reject the system root disk
ROOT_DEV=$(findmnt -n -o SOURCE / | sed 's/[0-9]*$//' | sed 's/p[0-9]*$//')
if [[ "$TARGET_DEVICE" == "$ROOT_DEV" ]]; then
    log_error "SAFETY ABORT: ${TARGET_DEVICE} is the system root disk!"
    log_error "Writing the ISO here would destroy your operating system."
    exit 1
fi

# Show device info
DEVICE_INFO=$(lsblk -o NAME,SIZE,MODEL,TYPE,HOTPLUG,MOUNTPOINT "$TARGET_DEVICE" 2>/dev/null || true)
echo ""
echo "$DEVICE_INFO"
echo ""

# ── Unmount partitions ────────────────────────────────────────────────────────
log_section "Unmounting Partitions"

MOUNTED=()
while IFS= read -r mp; do
    [[ -n "$mp" ]] && MOUNTED+=("$mp")
done < <(lsblk -o MOUNTPOINT -n "$TARGET_DEVICE" 2>/dev/null | grep -v '^$' || true)

if [[ ${#MOUNTED[@]} -gt 0 ]]; then
    for mp in "${MOUNTED[@]}"; do
        log_info "Unmounting: ${mp}"
        umount "$mp" || {
            log_error "Failed to unmount ${mp}. Close any programs using it and retry."
            exit 1
        }
    done
    log_ok "All partitions unmounted."
else
    log_ok "No mounted partitions found on ${TARGET_DEVICE}."
fi

# ── Confirmation ──────────────────────────────────────────────────────────────
log_section "Final Confirmation"

echo -e "${RED}${BOLD}WARNING: ALL DATA ON ${TARGET_DEVICE} WILL BE PERMANENTLY DESTROYED.${RESET}"
echo ""
echo -e "  ISO:     ${ISO_FILE} (${ISO_SIZE})"
echo -e "  Device:  ${TARGET_DEVICE}"
echo ""

if [[ "$SKIP_CONFIRM" == false ]]; then
    read -r -p "Type YES (all caps) to confirm: " confirm
    if [[ "$confirm" != "YES" ]]; then
        log_warn "Aborted. Nothing was written."
        exit 0
    fi
fi

# ── Write ISO ─────────────────────────────────────────────────────────────────
log_section "Writing ISO to USB"
log_info "This may take several minutes depending on ISO size and USB speed."
echo ""

WRITE_START=$(date +%s)

dd \
    if="$ISO_FILE" \
    of="$TARGET_DEVICE" \
    bs=4M \
    status=progress \
    oflag=sync \
    conv=fsync

WRITE_END=$(date +%s)
WRITE_DURATION=$((WRITE_END - WRITE_START))

echo ""
log_info "Flushing write buffers (sync)..."
sync

# ── Summary ───────────────────────────────────────────────────────────────────
log_section "Done"

log_ok "ISO successfully written to ${TARGET_DEVICE} in ${WRITE_DURATION}s."
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo "  1. Safely remove the USB drive."
echo "  2. Plug it into the target machine."
echo "  3. Boot from USB (select it in UEFI firmware boot menu, usually F12 or F2)."
echo "  4. Run 'ouroborOS-installer' from the live environment."
echo ""
