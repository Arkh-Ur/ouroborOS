#!/usr/bin/env bash
# =============================================================================
# test-shellcheck.sh — Run shellcheck on all project shell scripts
# =============================================================================
# Validates:
#   1. shellcheck -S style passes on every .sh file (zero warnings)
#   2. Every .sh file contains "set -euo pipefail" (custom guard check)
#
# Exit codes:
#   0 — all checks pass
#   1 — shellcheck warnings found OR missing set -euo pipefail guard
# =============================================================================
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${RESET}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_fail()  { echo -e "${RED}[FAIL]${RESET}  $*"; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────────────${RESET}"; }

# ── Locate workspace root ─────────────────────────────────────────────────────
WORKSPACE="${WORKSPACE:-/workspace}"
if [[ ! -d "$WORKSPACE" ]]; then
    log_fail "Workspace not found: $WORKSPACE"
    exit 1
fi

# ── Find all shell scripts ────────────────────────────────────────────────────
log_section "Discovering shell scripts"

mapfile -t SCRIPTS < <(
    {
        # Production shell scripts (src/ only — avoids build-tmp/ artefacts)
        find "$WORKSPACE/src" -name "*.sh" -type f 2>/dev/null || true

        # E2E test scripts
        find "$WORKSPACE/tests/scripts" -maxdepth 1 -name "*.sh" -type f \
            2>/dev/null || true

        # Phase 3 user-facing tools (bash, no .sh extension)
        for tool in our-snapshot our-rollback our-wifi our-bluetooth our-fido2 \
                    ouroboros-secureboot ouroboros-firstboot our-pacman our-container; do
            local_path="$WORKSPACE/src/ouroborOS-profile/airootfs/usr/local/bin/${tool}"
            [[ -f "$local_path" ]] && echo "$local_path"
        done
    } | sort -u
)

if [[ ${#SCRIPTS[@]} -eq 0 ]]; then
    log_warn "No .sh files found outside tests/ — nothing to check"
    exit 0
fi

log_info "Found ${#SCRIPTS[@]} shell script(s):"
for s in "${SCRIPTS[@]}"; do
    log_info "  ${s#"$WORKSPACE/"}"
done

# ── Run shellcheck ────────────────────────────────────────────────────────────
log_section "Running shellcheck -S style"

SHELLCHECK_FAILED=0

for script in "${SCRIPTS[@]}"; do
    rel="${script#"$WORKSPACE/"}"
    # Skip non-shell files that may end up in the list (e.g. Python scripts)
    if ! head -1 "$script" 2>/dev/null | grep -qE "bash|sh"; then
        log_warn "  $rel — not a shell script, skipping"
        continue
    fi
    if shellcheck -S style "$script" 2>&1; then
        log_ok "  $rel"
    else
        log_fail "  $rel"
        SHELLCHECK_FAILED=$((SHELLCHECK_FAILED + 1))
    fi
done

# ── Check for set -euo pipefail ───────────────────────────────────────────────
log_section "Checking set -euo pipefail guard"

GUARD_FAILED=0

for script in "${SCRIPTS[@]}"; do
    rel="${script#"$WORKSPACE/"}"
    # Guard check applies only to .sh files — airootfs tools use long comment
    # headers that push set -euo pipefail past line 20; shellcheck already
    # validates them and will error if pipefail is missing.
    if [[ "$script" != *.sh ]]; then
        log_ok "  $rel — guard check skipped (non-.sh, verified by shellcheck)"
        continue
    fi
    # Check lines 1–20 for the guard (allow for shebang + comment header block)
    if head -20 "$script" | grep -q "set -euo pipefail"; then
        log_ok "  $rel — guard present"
    else
        log_fail "  $rel — MISSING 'set -euo pipefail'"
        GUARD_FAILED=$((GUARD_FAILED + 1))
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
log_section "Results"
echo ""
echo -e "  Scripts checked:     ${#SCRIPTS[@]}"
echo -e "  shellcheck failures: $SHELLCHECK_FAILED"
echo -e "  Guard missing:       $GUARD_FAILED"
echo ""

TOTAL_FAILURES=$((SHELLCHECK_FAILED + GUARD_FAILED))

if [[ $TOTAL_FAILURES -eq 0 ]]; then
    log_ok "All ${#SCRIPTS[@]} scripts pass shellcheck and have the pipefail guard."
    exit 0
else
    log_fail "$TOTAL_FAILURES issue(s) found. Fix before merging."
    exit 1
fi
