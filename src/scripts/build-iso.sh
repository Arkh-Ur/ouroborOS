#!/usr/bin/env bash
set -euo pipefail
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
#   --with-cache         Pre-download packages into ISO for offline installation
#   --e2e-config=PATH    Inject unattended test config (for CI/E2E only; not for production)
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
PROFILE_DIR=""
CLEAN_BUILD=false
SIGN_ISO=false
E2E_CONFIG=""
VERSION=""
WITH_CACHE=false

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
        --workdir=*)         WORK_DIR="${1#*=}"; shift ;;
        -p|--profile) PROFILE_DIR="$2"; shift 2 ;;
        --profile=*)         PROFILE_DIR="${1#*=}"; shift ;;
        --output=*)          OUTPUT_DIR="${1#*=}"; shift ;;
        -c|--clean)          CLEAN_BUILD=true; shift ;;
        -s|--sign)           SIGN_ISO=true; shift ;;
        --with-cache)        WITH_CACHE=true; shift ;;
        --version=*)         VERSION="${1#*=}"; shift ;;
        --e2e-config=*)      E2E_CONFIG="${1#*=}"; shift ;;
        --e2e-config)        E2E_CONFIG="$2"; shift 2 ;;
        -h|--help)           usage ;;
        *) log_error "Unknown option: $1"; usage ;;
    esac
done

# ── Profile directory ──────────────────────────────────────────────────────────
[[ -z "$PROFILE_DIR" ]] && PROFILE_DIR="$REPO_ROOT/src/ouroborOS-profile"

# ── Preflight checks ──────────────────────────────────────────────────────────
log_section "Preflight Checks"

log_info "Profile directory: ${PROFILE_DIR}"

if [[ "$EUID" -ne 0 ]]; then
    log_error "This script must be run as root."
    exit 1
fi
log_ok "Running as root"

for cmd in mkarchiso mkfs.erofs xorriso; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command not found: $cmd"
        log_error "Install with: pacman -S archiso erofs-utils libisoburn"
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

# ── Pre-build cleanup ─────────────────────────────────────────────────────────
log_section "Pre-build Cleanup"

# Clean old snapper snapshots (keep only the current one per config)
if command -v snapper &>/dev/null; then
    while IFS= read -r cfg; do
        [[ -z "$cfg" ]] && continue
        mapfile -t SNAP_IDS < <(
            snapper -c "$cfg" list -t number 2>/dev/null \
                | tail -n +3 \
                | awk '{gsub(/[^0-9]/,"",$1); print $1}' \
                | grep -v '^$'
        )
        TOTAL=${#SNAP_IDS[@]}
        if [[ $TOTAL -gt 1 ]]; then
            FIRST="${SNAP_IDS[0]}"
            DEL_END="${SNAP_IDS[$((TOTAL-2))]}"
            if [[ "$FIRST" -le "$DEL_END" ]] 2>/dev/null; then
                if snapper -c "$cfg" delete "$FIRST-$DEL_END" 2>/dev/null; then
                    log_ok "Cleaned snapper '$cfg': removed $((TOTAL-1)) old snapshots"
                else
                    log_warn "Partial snapper cleanup for '$cfg'"
                fi
            fi
        fi
    done < <(snapper list-configs 2>/dev/null | tail -n +3 | awk '{print $1}')
else
    log_info "snapper not installed — skipping snapshot cleanup"
fi

# Clean pacman cache (only if >100MB to avoid unnecessary work)
if [[ -d /var/cache/pacman/pkg ]]; then
    CACHE_MB=$(du -sm /var/cache/pacman/pkg 2>/dev/null | awk '{print $1}')
    if [[ "${CACHE_MB:-0}" -gt 100 ]]; then
        rm -rf /var/cache/pacman/pkg/*
        log_ok "Cleaned pacman cache (~${CACHE_MB}MB)"
    else
        log_info "Pacman cache is small (${CACHE_MB}MB) — skipping"
    fi
fi

# Remove old build workdir unconditionally
if [[ -d "$WORK_DIR" ]]; then
    rm -rf "$WORK_DIR"
    log_ok "Removed old build workdir: $WORK_DIR"
fi

# Re-check available space after cleanup
AVAILABLE_KB=$(df -k "$WORK_PARENT" | awk 'NR==2 {print $4}')
if [[ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]]; then
    log_warn "Still less than 10 GB available after cleanup (have $((AVAILABLE_KB/1024))MB)."
    log_warn "Build may fail — consider freeing disk space manually."
else
    log_ok "Disk space after cleanup: $((AVAILABLE_KB/1024))MB available"
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

# ── E2E config injection (test builds only) ───────────────────────────────────
_E2E_DROPIN_DIR="${PROFILE_DIR}/airootfs/etc/systemd/system/ouroborOS-installer.service.d"
_E2E_CONFIG_DST="${PROFILE_DIR}/airootfs/etc/ouroborOS/e2e-config.yaml"

_cleanup_e2e() {
    rm -f "$_E2E_CONFIG_DST" "${_E2E_DROPIN_DIR}/e2e-unattended.conf"
    rmdir "$_E2E_DROPIN_DIR" 2>/dev/null || true
    rmdir "${PROFILE_DIR}/airootfs/etc/ouroborOS" 2>/dev/null || true
}

# Always clean residual E2E artifacts from previous builds BEFORE injection.
# This prevents stale configs from a prior --e2e-config build leaking into
# subsequent builds that use airootfs/tmp/ouroborOS-config.yaml directly.
_cleanup_e2e
log_info "Cleaned residual E2E artifacts (if any)"

if [[ -n "$E2E_CONFIG" ]]; then
    log_section "E2E Config Injection"
    if [[ ! -f "$E2E_CONFIG" ]]; then
        log_error "--e2e-config: file not found: ${E2E_CONFIG}"
        exit 1
    fi
    mkdir -p "${PROFILE_DIR}/airootfs/etc/ouroborOS" "$_E2E_DROPIN_DIR"
    cp "$E2E_CONFIG" "$_E2E_CONFIG_DST"
    cat > "${_E2E_DROPIN_DIR}/e2e-unattended.conf" << 'EOF'
[Service]
ExecStartPre=/usr/bin/cp /etc/ouroborOS/e2e-config.yaml /tmp/ouroborOS-config.yaml
EOF
    trap '_cleanup_e2e' EXIT
    log_ok "E2E config injected from: ${E2E_CONFIG}"
    log_warn "This ISO is for testing only — NOT for production use."
fi

# ── Sync installer modules to profile ──────────────────────────────────────
INSTALLER_SRC="$REPO_ROOT/src/installer"
INSTALLER_DST="$PROFILE_DIR/airootfs/usr/lib/ouroborOS/installer"

if [[ -d "$INSTALLER_SRC" ]]; then
    log_info "Syncing installer modules to profile airootfs..."
    rm -rf "$INSTALLER_DST"
    mkdir -p "$INSTALLER_DST/ops"

    find "$INSTALLER_SRC" -maxdepth 1 -type f \( -name '*.py' -o -name '*.yaml' \) \
        -exec cp -t "$INSTALLER_DST/" {} +
    find "$INSTALLER_SRC/ops" -type f \( -name '*.py' -o -name '*.sh' \) \
        -exec cp -t "$INSTALLER_DST/ops/" {} +

    # Copy profiledef.sh so _read_iso_version() can find it at runtime
    if [[ -f "$PROFILE_DIR/profiledef.sh" ]]; then
        cp "$PROFILE_DIR/profiledef.sh" "$INSTALLER_DST/profiledef.sh"
    fi

    # Sync locale directory and compile .po → .mo
    if [[ -d "$INSTALLER_SRC/locale" ]]; then
        log_info "Compiling locale files (.po → .mo)..."
        while IFS= read -r -d '' po_file; do
            lang_dir="$(dirname "$po_file")"
            lang="$(basename "$(dirname "$lang_dir")")"
            mo_dir="$INSTALLER_DST/locale/${lang}/LC_MESSAGES"
            mkdir -p "$mo_dir"
            if msgfmt -o "${mo_dir}/installer.mo" "$po_file"; then
                log_ok "Compiled locale: ${lang}"
            else
                log_warn "msgfmt failed for ${lang} — installer will fall back to English"
            fi
        done < <(find "$INSTALLER_SRC/locale" -name 'installer.po' -print0)
    fi

    chmod 0755 "$INSTALLER_DST/ops/"*.sh
    log_ok "Installer modules synced: $(find "$INSTALLER_DST" -type f | wc -l) files"
else
    log_warn "Installer source not found at $INSTALLER_SRC — skipping sync"
fi

# ── Version injection ─────────────────────────────────────────────────────────
inject_version() {
    [[ -z "$VERSION" ]] && return 0
    local profiledef="${PROFILE_DIR}/profiledef.sh"
    local osrelease="${PROFILE_DIR}/airootfs/etc/os-release"
    local entry1="${PROFILE_DIR}/efiboot/loader/entries/01-ouroborOS.conf"
    local entry2="${PROFILE_DIR}/efiboot/loader/entries/02-ouroborOS-accessibility.conf"

    if [[ ! -f "$profiledef" ]]; then
        log_error "profiledef.sh not found: $profiledef"
        exit 1
    fi

    sed -i "s/^iso_version=.*/iso_version=\"${VERSION}\"/" "$profiledef"
    log_ok "profiledef.sh: iso_version → ${VERSION}"

    if [[ -f "$osrelease" ]]; then
        sed -i "s/^VERSION_ID=.*/VERSION_ID=\"${VERSION}\"/" "$osrelease"
        sed -i "s/^PRETTY_NAME=.*/PRETTY_NAME=\"ouroborOS ${VERSION}\"/" "$osrelease"
        log_ok "os-release: VERSION_ID + PRETTY_NAME → ${VERSION}"
    fi

    if [[ -f "$entry1" ]]; then
        sed -i "s/^title   ouroborOS [^(]*/title   ouroborOS ${VERSION} /" "$entry1"
        sed -i 's/  $//' "$entry1"
        log_ok "boot entry 01: title → ouroborOS ${VERSION}"
    fi

    if [[ -f "$entry2" ]]; then
        sed -i "s/^title   ouroborOS [0-9.]* (accessibility)/title   ouroborOS ${VERSION} (accessibility)/" "$entry2"
        log_ok "boot entry 02: title → ouroborOS ${VERSION} (accessibility)"
    fi
}
inject_version

# ── Offline Package Cache ─────────────────────────────────────────────────────
# Pre-downloads packages into the airootfs so the installer can work
# without an internet connection. Opt-in via --with-cache.
build_offline_cache() {
    # /var/cache/pacman/pkg is wiped by mkarchiso's _cleanup_pacstrap_dir()
    # so we use a separate path that survives the cleanup phase.
    local cache_dest="${PROFILE_DIR}/airootfs/var/cache/ouroboros-offline"
    local pkg_list="${PROFILE_DIR}/packages.x86_64"
    local tmp_cache="/var/cache/pacman/ouroboros-offline-cache"

    [[ -f "$pkg_list" ]] || { log_warn "--with-cache: packages.x86_64 not found — skipping cache"; return 0; }

    log_section "Building Offline Package Cache"
    log_info "Downloading packages for offline install..."

    mkdir -p "$tmp_cache" "$cache_dest"
    chown alpm:alpm "$tmp_cache" 2>/dev/null || true
    chmod 755 "$tmp_cache"

    local pkgs=()

    # 1) ISO live packages
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        pkgs+=("$line")
    done < "$pkg_list"

    # 2) Installer target packages not already in packages.x86_64.
    #    pacman -Syw base does NOT download deps of the already-installed
    #    base metapackage, so every package that _handle_install() passes
    #    to pacstrap must be listed here explicitly.
    #    Source of truth: _handle_install() in state_machine.py
    local installer_pkgs=(
        systemd
        which
        linux-zen-headers
        sudo
        zram-generator
    )
    pkgs+=("${installer_pkgs[@]}")

    # 3) Extra packages from manifest (profiles, DMs, shells, etc.)
    #    Optional: create packages.offline in the profile dir to extend the cache.
    local offline_manifest="${PROFILE_DIR}/packages.offline"
    if [[ -f "$offline_manifest" ]]; then
        while IFS= read -r line; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            pkgs+=("$line")
        done < "$offline_manifest"
        log_info "Including packages from packages.offline manifest"
    fi

    pacman --noconfirm --cachedir "$tmp_cache" -Syw "${pkgs[@]}"

    find "$tmp_cache" -name "*.pkg.tar.zst" -exec cp {} "$cache_dest/" \;

    # --cachedir is additive: packages already in the default cache are NOT
    # re-downloaded to $tmp_cache.  Merge anything present in the default
    # cache so the offline cache is self-contained.
    if [[ -d /var/cache/pacman/pkg ]]; then
        for f in /var/cache/pacman/pkg/*.pkg.tar.zst; do
            [[ -f "$f" ]] || continue
            [[ -f "$cache_dest/$(basename "$f")" ]] || cp "$f" "$cache_dest/"
        done
    fi

    rm -rf "$tmp_cache"

    local count
    count=$(find "$cache_dest" -name "*.pkg.tar.zst" | wc -l)
    log_ok "Offline cache: ${count} packages at ${cache_dest}"
}

if [[ "$WITH_CACHE" == true ]]; then
    build_offline_cache
fi

# ── Build ─────────────────────────────────────────────────────────────────────
log_section "Building ISO"
log_info "Profile:  $PROFILE_DIR"
log_info "Work dir: $WORK_DIR"
log_info "Output:   $OUTPUT_DIR"
[[ "$WITH_CACHE" == true ]] && log_info "Mode:     offline cache enabled"
echo ""

BUILD_START=$(date +%s)

# Redirect bash/mkarchiso temp files to WORK_DIR to avoid filling /tmp (tmpfs)
export TMPDIR="$WORK_DIR/tmp"
mkdir -p "$TMPDIR"

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
ISO_SIZE=$(du -sh "$ISO_BASENAME" | cut -f1)
echo -e "  ${BOLD}ISO:${RESET}      $(pwd)/$ISO_BASENAME"
echo -e "  ${BOLD}Size:${RESET}     $ISO_SIZE"
echo -e "  ${BOLD}SHA256:${RESET}   $(cat "${ISO_BASENAME}.sha256" | cut -d' ' -f1)"
echo -e "  ${BOLD}Duration:${RESET} ${BUILD_DURATION}s"
echo ""
log_ok "ouroborOS ISO ready."
echo ""
echo -e "${BOLD}── Próximos pasos ──────────────────────────────${RESET}"
echo ""
echo -e "  ${BOLD}Ruta del ISO:${RESET}"
echo "    $ISO_FILE"
echo ""
echo -e "  ${BOLD}Grabar en USB (instalador físico):${RESET}"
echo "    sudo bash ${SCRIPT_DIR}/flash-usb.sh --iso \"$ISO_FILE\""
echo ""
echo -e "  ${BOLD}Probar en GNOME Boxes:${RESET}"
echo "    1. Abre GNOME Boxes → '+' → 'Elegir un archivo'"
echo "    2. Selecciona: $ISO_FILE"
echo "    3. RAM mínima: 2 GB | Disco: 20 GB | Firmware: UEFI"
echo ""
echo -e "  ${BOLD}Probar en QEMU (terminal):${RESET}"
echo "    qemu-system-x86_64 -enable-kvm -m 2048 \\"
echo "      -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \\"
echo "      -cdrom \"$ISO_FILE\" -boot d"
