#!/usr/bin/env bash
# =============================================================================
# test_dots_e2e.sh — E2E tests for ouroborOS dotfiles packs
# =============================================================================
# Runs on a live ouroborOS system (VM or bare metal).
# Verifies install → verify → uninstall → re-install for each pack.
#
# Usage:
#   ./test_dots_e2e.sh --all [--verbose] [--json]
#   ./test_dots_e2e.sh --pack <id> [--verbose] [--json]
#
# Exit codes:
#   0 = all passed
#   1 = one or more failures
# =============================================================================
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
readonly MANIFEST_DIR="/usr/local/lib/ouroboros/dots/packs"
readonly OUR_DOTS="/usr/local/bin/our-dots"
readonly ALL_PACKS=(noctalia ml4w caelestia danklinux illogical-impulse omarchy ambxst)
readonly RESULTS_DIR="/tmp/ouroboros-e2e-results"

# ── Color output ──────────────────────────────────────────────────────────────
if [[ -n "${NO_COLOR:-}" ]]; then
    RED='' GREEN='' YELLOW='' BOLD='' RESET=''
else
    RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' BOLD='\033[1m' RESET='\033[0m'
fi

VERBOSE=false
JSON_OUTPUT=false
PACKS_TO_TEST=()

# ── Args parsing ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)       PACKS_TO_TEST=("${ALL_PACKS[@]}"); shift ;;
        --pack)      PACKS_TO_TEST+=("$2"); shift 2 ;;
        --verbose)   VERBOSE=true; shift ;;
        --json)      JSON_OUTPUT=true; shift ;;
        -h|--help)
            echo "Usage: $0 --all [--verbose] [--json]"
            echo "       $0 --pack <id> [--pack <id2> ...] [--verbose] [--json]"
            echo ""
            echo "Packs: ${ALL_PACKS[*]}"
            exit 0 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [[ ${#PACKS_TO_TEST[@]} -eq 0 ]]; then
    echo "ERROR: specify --all or --pack <id>"
    exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
log_pass()  { echo -e "  ${GREEN}✅ PASS${RESET} — $1"; }
log_fail()  { echo -e "  ${RED}❌ FAIL${RESET} — $1"; }
log_skip()  { echo -e "  ${YELLOW}⏭  SKIP${RESET} — $1"; }
log_info()  { $VERBOSE && echo -e "  ${BOLD}ℹ️ INFO${RESET} — $1" || true; }

total_pass=0
total_fail=0
total_skip=0
json_results=()

# ── Pre-flight checks ─────────────────────────────────────────────────────────
preflight() {
    echo ""
    echo -e "${BOLD}═══ ouroborOS Dots Packs — E2E Tests ═══${RESET}"
    echo ""

    if ! command -v our-dots &>/dev/null; then
        echo "FATAL: our-dots not found. Run on a live ouroborOS system."
        exit 1
    fi

    if [[ ! -d "$MANIFEST_DIR" ]]; then
        echo "FATAL: manifest dir $MANIFEST_DIR not found."
        exit 1
    fi

    local version
    version=$(our-dots --version 2>/dev/null || echo "unknown")
    echo "our-dots version: $version"
    echo "Packs to test: ${PACKS_TO_TEST[*]}"
    echo "Manifests: $(ls "$MANIFEST_DIR"/*.yaml 2>/dev/null | wc -l) found"
    echo ""

    # Ensure OUROBOROS_ALLOW_CRITICAL for unattended CRITICAL packs
    export OUROBOROS_ALLOW_CRITICAL=1

    # When running as root without SUDO_USER, set SUDO_USER to first regular user
    # so post_deploy scripts that refuse root can run as a normal user.
    if [[ $EUID -eq 0 ]] && [[ -z "${SUDO_USER:-}" ]]; then
        local regular_user
        regular_user=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1; exit}')
        if [[ -n "${regular_user}" ]]; then
            export SUDO_USER="${regular_user}"
            echo "E2E: running post_deploy as ${SUDO_USER} (detected regular user)"
        fi
    fi

    mkdir -p "$RESULTS_DIR"
}

# ── Single test runner ────────────────────────────────────────────────────────
run_test() {
    local test_name="$1" test_cmd="$2" expect="${3:-pass}"
    local start end rc=0
    start=$(date +%s)
    eval "$test_cmd" &>/tmp/ouroboros-e2e-test.log || rc=$?
    end=$(date +%s)

    if [[ "$expect" == "pass" && $rc -eq 0 ]]; then
        log_pass "$test_name ($(( end - start ))s)"
        (( total_pass++ )) || true
        return 0
    elif [[ "$expect" == "skip" && $rc -ne 0 ]]; then
        log_skip "$test_name"
        (( total_skip++ )) || true
        return 0
    else
        log_fail "$test_name (exit=$rc, $(( end - start ))s)"
        $VERBOSE && cat /tmp/ouroboros-e2e-test.log 2>/dev/null
        (( total_fail++ )) || true
        return 1
    fi
}

# ── Test suite for one pack ──────────────────────────────────────────────────
test_pack() {
    local id="$1"
    local manifest="$MANIFEST_DIR/${id}.yaml"
    local pack_pass=0 pack_fail=0

    echo -e "${BOLD}━━━ Testing pack: $id ━━━${RESET}"

    # T1: Manifest exists and schema is valid
    run_test "T1: Manifest schema valid" \
        "our-dots -Si '$id' >/dev/null 2>&1" || true

    # T2: Pack info works
    local info_output
    info_output=$(our-dots -Si "$id" 2>&1) || true
    if echo "$info_output" | grep -qi "name\|description"; then
        log_pass "T2: Pack info works"
        (( total_pass++ )) || true
    else
        log_fail "T2: Pack info works (empty output)"
        (( total_fail++ )) || true
    fi

    # T3: Pack appears in available list
    local list_output
    list_output=$(our-dots list 2>&1 || our-dots -Q 2>&1) || true
    if echo "$list_output" | grep -q "$id"; then
        log_pass "T3: Pack appears in list"
        (( total_pass++ )) || true
    else
        log_fail "T3: Pack not found in list"
        (( total_fail++ )) || true
    fi

    # T4: Install succeeds
    run_test "T4: Install succeeds" \
        "our-dots -S '$id' --noconfirm" || true

    # T5: Pack marked as installed
    local installed_output
    installed_output=$(our-dots list 2>&1 || our-dots -Q 2>&1) || true
    if echo "$installed_output" | grep -qE "${id}.*\[installed\]|installed.*${id}"; then
        log_pass "T5: Pack marked installed"
        (( total_pass++ )) || true
    else
        # Fallback: check system.yaml directly
        if grep -q "$id" /etc/ouroboros/system.yaml 2>/dev/null; then
            log_pass "T5: Pack in system.yaml (installed)"
            (( total_pass++ )) || true
        else
            log_fail "T5: Pack not marked as installed"
            (( total_fail++ )) || true
        fi
    fi

    # T6: Verify packages from manifest exist in system
    local packages_missing=0
    local pkg
    for pkg in $(python3 - "$manifest" <<'PYEOF' 2>/dev/null
import yaml, sys
d = yaml.safe_load(open(sys.argv[1])) or {}
channel = "stable"
variants = d.get("variants", {})
if not variants.get("stable") and variants.get("git"):
    channel = "git"
block = variants.get(channel, {})
for p in block.get("packages", []):
    print(p)
PYEOF
    ); do
        if ! pacman -Q "$pkg" &>/dev/null; then
            log_info "T6: package '$pkg' not found in pacman"
            packages_missing=$(( packages_missing + 1 ))
        fi
    done

    if [[ $packages_missing -eq 0 ]]; then
        log_pass "T6: All packages installed"
        (( total_pass++ )) || true
    else
        log_fail "T6: $packages_missing package(s) missing"
        (( total_fail++ )) || true
    fi

    # T7: Verify AUR packages from manifest exist in system
    local aur_missing=0
    for pkg in $(python3 - "$manifest" <<'PYEOF' 2>/dev/null
import yaml, sys
d = yaml.safe_load(open(sys.argv[1])) or {}
channel = "stable"
variants = d.get("variants", {})
if not variants.get("stable") and variants.get("git"):
    channel = "git"
block = variants.get(channel, {})
for p in block.get("aur", []):
    print(p)
PYEOF
    ); do
        if ! pacman -Q "$pkg" &>/dev/null && \
           ! [[ -f "/var/lib/our-aur/packages/${pkg}.json" ]]; then
            log_info "T7: AUR package '$pkg' not found"
            aur_missing=$(( aur_missing + 1 ))
        fi
    done

    if [[ $aur_missing -eq 0 ]]; then
        log_pass "T7: All AUR packages installed"
        (( total_pass++ )) || true
    else
        log_fail "T7: $aur_missing AUR package(s) missing"
        (( total_fail++ )) || true
    fi

    # T8: Uninstall succeeds
    run_test "T8: Uninstall succeeds" \
        "our-dots -R '$id' --noconfirm" || true

    # T9: Pack no longer marked installed
    local installed_after
    installed_after=$(our-dots list 2>&1 || our-dots -Q 2>&1) || true
    if echo "$installed_after" | grep -qE "${id}.*\[installed\]"; then
        log_fail "T9: Pack still marked installed after remove"
        (( total_fail++ )) || true
    else
        log_pass "T9: Pack removed from installed list"
        (( total_pass++ )) || true
    fi

    # T10: Uninstall packages removed
    local uninstall_pkgs
    uninstall_pkgs=$(python3 - "$manifest" <<'PYEOF' 2>/dev/null
import yaml, sys
d = yaml.safe_load(open(sys.argv[1])) or {}
uninstall = d.get("uninstall", {})
for p in uninstall.get("packages", []):
    print(p)
PYEOF
    )
    local still_installed=0
    for pkg in $uninstall_pkgs; do
        if pacman -Q "$pkg" &>/dev/null; then
            log_info "T10: package '$pkg' still installed after uninstall"
            still_installed=$(( still_installed + 1 ))
        fi
    done

    if [[ $still_installed -eq 0 ]]; then
        log_pass "T10: Uninstall packages removed"
        (( total_pass++ )) || true
    else
        log_fail "T10: $still_installed package(s) still installed"
        (( total_fail++ )) || true
    fi

    # T11: Re-install (idempotent)
    run_test "T11: Re-install (idempotent)" \
        "our-dots -S '$id' --noconfirm" || true

    # Cleanup: remove pack again to leave system clean for next test
    our-dots -R "$id" --noconfirm &>/dev/null || true

    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
preflight

for pack in "${PACKS_TO_TEST[@]}"; do
    test_pack "$pack"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}═══ Summary ═══${RESET}"
echo -e "  ✅ Passed: ${GREEN}${total_pass}${RESET}"
echo -e "  ❌ Failed: ${RED}${total_fail}${RESET}"
echo -e "  ⏭  Skipped: ${YELLOW}${total_skip}${RESET}"
echo ""

if [[ $total_fail -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}ALL TESTS PASSED${RESET}"
else
    echo -e "${RED}${BOLD}$total_fail TEST(S) FAILED${RESET}"
fi

# JSON output for CI/Hermes
if $JSON_OUTPUT; then
    echo "{\"passed\": $total_pass, \"failed\": $total_fail, \"skipped\": $total_skip, \"packs\": ["
    first=true
    for pack in "${PACKS_TO_TEST[@]}"; do
        $first || echo -n ","
        first=false
        echo -n "\"$pack\""
    done
    echo "]}"
fi

exit $(( total_fail > 0 ? 1 : 0 ))
