#!/usr/bin/env bash
# =============================================================================
# build-iso.sh — ouroborOS ISO Build Script
# =============================================================================
# Builds the ouroborOS live/installer ISO using archiso.
#
# Usage:
#   sudo bash docs/scripts/build-iso.sh [OPTIONS]
#
# Options:
#   -o, --output DIR     Output directory (default: ./out)
#   -w, --workdir DIR    Build working directory (default: /tmp/ouroborOS-build)
#   -p, --profile DIR    Archiso profile directory (default: ./ouroborOS-profile)
#   -c, --clean          Clean working directory before build
#   -s, --sign           GPG-sign the ISO after build
#   -h, --help           Show this help message
#
# Requirements:
#   - Root privileges
#   - Packages: archiso dosfstools e2fsprogs squashfs-tools libisoburn
#
# =============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/out"
WORK_DIR="/tmp/ouroborOS-build"
PROFILE_DIR="$REPO_ROOT/ouroborOS-profile"
CLEAN_BUILD=false
SIGN_ISO=false

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

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
    sed -n '/^# Usage/,/^# =====/p' "$0" | grep -v '^# =====' | sed 's/^# //'
    exit 0
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output)  OUTPUT_DIR="$2"; shift 2 ;;
        -w|--workdir) WORK_DIR="$2"; shift 2 ;;
        -p|--profile) PROFILE_DIR="$2"; shift 2 ;;
        -c|--clean)   CLEAN_BUILD=true; shift ;;
        -s|--sign)    SIGN_ISO=true; shift ;;
        -h|--help)    usage ;;
        *) log_error "Unknown option: $1"; usage ;;
    esac
done

# ── Preflight checks ──────────────────────────────────────────────────────────
log_section "Preflight Checks"

if [[ "$EUID" -ne 0 ]]; then
    log_error "This script must be run as root."
    exit 1
fi
log_ok "Running as root"

for cmd in mkarchiso mksquashfs xorriso; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command not found: $cmd"
        log_error "Install with: pacman -S archiso squashfs-tools libisoburn"
        exit 1
    fi
done
log_ok "All required tools found"

if [[ ! -d "$PROFILE_DIR" ]]; then
    log_error "Profile directory not found: $PROFILE_DIR"
    log_error "Expected the archiso profile at: $PROFILE_DIR"
    exit 1
fi
log_ok "Profile directory found: $PROFILE_DIR"

# Check disk space (need at least 10G in WORK_DIR parent)
WORK_PARENT="$(dirname "$WORK_DIR")"
AVAILABLE_KB=$(df -k "$WORK_PARENT" | awk 'NR==2 {print $4}')
REQUIRED_KB=$((10 * 1024 * 1024))  # 10 GB
if [[ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]]; then
    log_warn "Less than 10 GB available in $WORK_PARENT. Build may fail."
fi

# ── Clean ─────────────────────────────────────────────────────────────────────
if [[ "$CLEAN_BUILD" == true ]]; then
    log_section "Cleaning Working Directory"
    if [[ -d "$WORK_DIR" ]]; then
        rm -rf "$WORK_DIR"
        log_ok "Removed: $WORK_DIR"
    fi
fi

# ── Setup directories ─────────────────────────────────────────────────────────
log_section "Setting Up Directories"
mkdir -p "$OUTPUT_DIR" "$WORK_DIR"
log_ok "Output dir: $OUTPUT_DIR"
log_ok "Work dir:   $WORK_DIR"

# ── Build ─────────────────────────────────────────────────────────────────────
log_section "Building ISO"
log_info "Profile:  $PROFILE_DIR"
log_info "Work dir: $WORK_DIR"
log_info "Output:   $OUTPUT_DIR"
echo ""

BUILD_START=$(date +%s)

mkarchiso -v \
    -w "$WORK_DIR/work" \
    -o "$OUTPUT_DIR" \
    "$PROFILE_DIR"

BUILD_END=$(date +%s)
BUILD_DURATION=$((BUILD_END - BUILD_START))

log_ok "Build completed in ${BUILD_DURATION}s"

# ── Checksums ─────────────────────────────────────────────────────────────────
log_section "Generating Checksums"
ISO_FILE=$(find "$OUTPUT_DIR" -name "ouroborOS-*.iso" -newer "$SCRIPT_DIR" | head -1)

if [[ -z "$ISO_FILE" ]]; then
    log_error "Could not find newly built ISO in $OUTPUT_DIR"
    exit 1
fi

ISO_BASENAME=$(basename "$ISO_FILE")
cd "$OUTPUT_DIR"
sha256sum "$ISO_BASENAME" > "${ISO_BASENAME}.sha256"
log_ok "SHA256: ${ISO_BASENAME}.sha256"

# ── GPG Sign ──────────────────────────────────────────────────────────────────
if [[ "$SIGN_ISO" == true ]]; then
    log_section "Signing ISO"
    if ! command -v gpg &>/dev/null; then
        log_warn "gpg not found, skipping signature"
    else
        gpg --detach-sign "$ISO_BASENAME"
        log_ok "Signature: ${ISO_BASENAME}.sig"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log_section "Build Summary"
ISO_SIZE=$(du -sh "$ISO_FILE" | cut -f1)
echo -e "  ${BOLD}ISO:${RESET}      $ISO_FILE"
echo -e "  ${BOLD}Size:${RESET}     $ISO_SIZE"
echo -e "  ${BOLD}SHA256:${RESET}   $(cat "${ISO_BASENAME}.sha256" | cut -d' ' -f1)"
echo -e "  ${BOLD}Duration:${RESET} ${BUILD_DURATION}s"
echo ""
log_ok "ouroborOS ISO ready."
echo ""
echo "Test with QEMU:"
echo "  qemu-system-x86_64 -enable-kvm -m 2048 \\"
echo "    -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \\"
echo "    -cdrom \"$ISO_FILE\" -boot d"
