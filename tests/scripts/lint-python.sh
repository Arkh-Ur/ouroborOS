#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# lint-python.sh — Run ruff linter on all Python files
# =============================================================================
# Rules enforced:
#   E    — pycodestyle errors
#   W    — pycodestyle warnings
#   F    — pyflakes (undefined names, unused imports)
#   I    — isort (import ordering)
#   UP   — pyupgrade (modern Python syntax)
#   ANN  — type annotation requirements (ANN001: missing arg type, ANN201: return type)
#   E722 — bare except clauses
#
# Behavior:
#   - No .py files found → exit 0 with informational message
#   - Files found → ruff check; exit 1 if any violations
#
# Exit codes:
#   0 — no violations (or no Python files)
#   1 — ruff violations found
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_fail()    { echo -e "${RED}[FAIL]${RESET}  $*"; }
log_info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
log_skip()    { echo -e "${YELLOW}[SKIP]${RESET}  $*"; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────────────${RESET}"; }

WORKSPACE="${WORKSPACE:-/workspace}"

# ── Find Python files ─────────────────────────────────────────────────────────
log_section "Discovering Python files"

mapfile -t PY_FILES < <(
    find "$WORKSPACE" \
        -not -path "$WORKSPACE/.git/*" \
        -name "*.py" \
        -type f \
        | sort
)

if [[ ${#PY_FILES[@]} -eq 0 ]]; then
    log_skip "No .py files found in repository"
    log_skip "Python lint will run automatically once .py files are added"
    echo ""
    echo -e "${YELLOW}${BOLD}SKIP — no Python files exist yet.${RESET}"
    exit 0
fi

log_info "Found ${#PY_FILES[@]} Python file(s):"
for f in "${PY_FILES[@]}"; do
    log_info "  ${f#"$WORKSPACE/"}"
done

# ── Run ruff ──────────────────────────────────────────────────────────────────
log_section "Running ruff check"

cd "$WORKSPACE"

# Select rules: E,W,F (pycodestyle+pyflakes), I (isort), UP (pyupgrade),
# ANN001/ANN201 (type annotations on args and return), E722 (bare except)
RUFF_RULES="E,W,F,I,UP,ANN001,ANN201,E722"

if ruff check \
    --select "$RUFF_RULES" \
    --output-format grouped \
    "${PY_FILES[@]}" 2>&1; then
    log_ok "ruff: all ${#PY_FILES[@]} file(s) pass (0 violations)"
    echo ""
    echo -e "${GREEN}${BOLD}Python lint passed.${RESET}"
    exit 0
else
    log_fail "ruff found violations in one or more files"
    echo ""
    echo -e "${RED}${BOLD}Python lint failed. Fix the violations above before merging.${RESET}"
    exit 1
fi
