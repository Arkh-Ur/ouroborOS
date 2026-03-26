#!/usr/bin/env bash
# =============================================================================
# smoke-test.sh — Validate archiso profile structure (ouroborOS-profile/)
# =============================================================================
# When ouroborOS-profile/ does not exist: exits 0 with informational message.
# When it exists: validates that all files required by mkarchiso are present
# and contain the correct content.
#
# Checks derived from skills/archiso-builder.md and the ouroborOS design constraints.
#
# Exit codes:
#   0 — all checks pass (or profile not yet created)
#   1 — one or more profile structure violations
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_fail()    { echo -e "${RED}[FAIL]${RESET}  $*"; }
log_skip()    { echo -e "${YELLOW}[SKIP]${RESET}  $*"; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────────────${RESET}"; }

WORKSPACE="${WORKSPACE:-/workspace}"
PROFILE="$WORKSPACE/ouroborOS-profile"
FAILURES=0

# Helper: assert file exists and is non-empty
assert_file() {
    local file="$1"
    local desc="$2"
    local rel="${file#"$WORKSPACE/"}"
    if [[ -f "$file" ]] && [[ -s "$file" ]]; then
        log_ok "$rel ($desc)"
    elif [[ -f "$file" ]]; then
        log_fail "$rel exists but is EMPTY ($desc)"
        FAILURES=$((FAILURES + 1))
    else
        log_fail "$rel NOT FOUND ($desc)"
        FAILURES=$((FAILURES + 1))
    fi
}

# Helper: assert file is executable
assert_executable() {
    local file="$1"
    local rel="${file#"$WORKSPACE/"}"
    if [[ -x "$file" ]]; then
        log_ok "$rel is executable"
    else
        log_fail "$rel is NOT executable"
        FAILURES=$((FAILURES + 1))
    fi
}

# Helper: assert file contains pattern
assert_contains() {
    local file="$1"
    local pattern="$2"
    local desc="$3"
    local rel="${file#"$WORKSPACE/"}"
    if [[ -f "$file" ]] && grep -q "$pattern" "$file"; then
        log_ok "$rel contains: $desc"
    else
        log_fail "$rel MISSING: $desc"
        FAILURES=$((FAILURES + 1))
    fi
}

# Helper: assert file does NOT contain pattern (architectural compliance)
assert_not_contains() {
    local file="$1"
    local pattern="$2"
    local desc="$3"
    local rel="${file#"$WORKSPACE/"}"
    if [[ -f "$file" ]] && grep -qi "$pattern" "$file"; then
        log_fail "$rel VIOLATION: contains '$desc' (forbidden)"
        FAILURES=$((FAILURES + 1))
    else
        log_ok "$rel does not contain forbidden: $desc"
    fi
}

# ── Phase gate ────────────────────────────────────────────────────────────────
if [[ ! -d "$PROFILE" ]]; then
    log_skip "ouroborOS-profile/ directory does not exist yet"
    log_skip "Smoke test will run automatically once the profile is created (Phase 1)"
    echo ""
    echo -e "${YELLOW}${BOLD}SKIP — archiso profile not yet created.${RESET}"
    exit 0
fi

# ── profiledef.sh ─────────────────────────────────────────────────────────────
log_section "profiledef.sh"
assert_file       "$PROFILE/profiledef.sh" "main profile definition"
assert_executable "$PROFILE/profiledef.sh"
assert_contains   "$PROFILE/profiledef.sh" "iso_name="    "iso_name definition"
assert_contains   "$PROFILE/profiledef.sh" "iso_label="   "iso_label definition"
assert_contains   "$PROFILE/profiledef.sh" "bootmodes="   "bootmodes definition"
assert_not_contains "$PROFILE/profiledef.sh" "grub"       "GRUB (architectural violation)"

# ── packages.x86_64 ───────────────────────────────────────────────────────────
log_section "packages.x86_64"
assert_file     "$PROFILE/packages.x86_64" "package list"
assert_contains "$PROFILE/packages.x86_64" "^base$"         "base package"
assert_contains "$PROFILE/packages.x86_64" "^linux-zen$"    "linux-zen kernel"
assert_contains "$PROFILE/packages.x86_64" "^btrfs-progs$"  "btrfs-progs"
assert_contains "$PROFILE/packages.x86_64" "^python$"       "python interpreter"

# ── pacman.conf ───────────────────────────────────────────────────────────────
log_section "pacman.conf"
assert_file "$PROFILE/pacman.conf" "pacman configuration"

# ── mkinitcpio.conf ───────────────────────────────────────────────────────────
log_section "mkinitcpio.conf (if present)"
MKINIT="$PROFILE/airootfs/etc/mkinitcpio.conf"
if [[ -f "$MKINIT" ]]; then
    assert_contains "$MKINIT" "btrfs" "btrfs in MODULES or HOOKS"
    # Specifically check MODULES line and HOOKS line
    if grep -q "^MODULES=.*btrfs" "$MKINIT"; then
        log_ok "mkinitcpio.conf: btrfs in MODULES"
    else
        log_fail "mkinitcpio.conf: btrfs NOT in MODULES line"
        FAILURES=$((FAILURES + 1))
    fi
    if grep -q "^HOOKS=.*btrfs" "$MKINIT"; then
        log_ok "mkinitcpio.conf: btrfs in HOOKS"
    else
        log_fail "mkinitcpio.conf: btrfs NOT in HOOKS line"
        FAILURES=$((FAILURES + 1))
    fi
else
    log_skip "airootfs/etc/mkinitcpio.conf not yet created (will be required before build)"
fi

# ── EFI boot entries ──────────────────────────────────────────────────────────
log_section "EFI boot configuration (if present)"
LOADER_CONF="$PROFILE/efiboot/loader/loader.conf"
if [[ -f "$LOADER_CONF" ]]; then
    assert_contains "$LOADER_CONF" "default" "default entry defined"
    assert_not_contains "$LOADER_CONF" "editor yes" "editor should be disabled (security)"
else
    log_skip "efiboot/loader/loader.conf not yet created"
fi

# ── Architectural compliance ──────────────────────────────────────────────────
log_section "Architectural compliance"
# Check entire profile for forbidden references
find "$PROFILE" -type f | while read -r file; do
    if grep -qi "networkmanager" "$file" 2>/dev/null; then
        echo -e "${RED}[FAIL]${RESET}  $(basename "$file") contains NetworkManager reference"
        echo "1" > /tmp/arch-compliance-failed
    fi
done
if [[ -f /tmp/arch-compliance-failed ]]; then
    FAILURES=$((FAILURES + 1))
    rm -f /tmp/arch-compliance-failed
else
    log_ok "No NetworkManager references in profile"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All archiso profile smoke tests passed.${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}$FAILURES smoke test(s) failed. Fix before running mkarchiso.${RESET}"
    exit 1
fi
