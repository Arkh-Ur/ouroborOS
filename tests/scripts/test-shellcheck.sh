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
    find "$WORKSPACE" \
        -not -path "$WORKSPACE/.git/*" \
        -not -path "$WORKSPACE/tests/*" \
        -name "*.sh" \
        -type f \
        | sort
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
    # Check lines 1–5 for the guard (allow for shebang + blank line)
    if head -5 "$script" | grep -q "set -euo pipefail"; then
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
