#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# run-pytest.sh — Run Python test suite with coverage
# =============================================================================
# Behavior:
#   - If installer/ does not exist → exit 0 with informational message (Phase 1)
#   - If installer/ exists → run pytest with coverage, enforce ≥ 70% gate
#   - Always validates Python version ≥ 3.11 and key dependencies
#
# Exit codes:
#   0 — tests pass (or phase-gated skip)
#   1 — tests fail or coverage below gate
# =============================================================================

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_fail()    { echo -e "${RED}[FAIL]${RESET}  $*"; }
log_skip()    { echo -e "${YELLOW}[SKIP]${RESET}  $*"; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────────────${RESET}"; }

WORKSPACE="${WORKSPACE:-/workspace}"
COVERAGE_GATE=70
FAILURES=0

# ── Python version check ──────────────────────────────────────────────────────
log_section "Python version"

PY_VERSION=$(python --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ $PY_MAJOR -ge 3 ]] && [[ $PY_MINOR -ge 11 ]]; then
    log_ok "Python $PY_VERSION (≥ 3.11 required)"
else
    log_fail "Python $PY_VERSION — project requires Python ≥ 3.11"
    FAILURES=$((FAILURES + 1))
fi

# ── Dependency check ──────────────────────────────────────────────────────────
log_section "Python dependencies"

DEPS=("yaml" "rich" "dataclasses" "pytest")
for dep in "${DEPS[@]}"; do
    if python -c "import $dep" 2>/dev/null; then
        log_ok "import $dep"
    else
        log_fail "import $dep — not available"
        FAILURES=$((FAILURES + 1))
    fi
done

# ── Phase gate: installer/ must exist ─────────────────────────────────────────
log_section "Installer tests"

if [[ ! -d "$WORKSPACE/src/installer" ]]; then
    log_skip "src/installer/ directory does not exist yet (expected in Phase 1)"
    log_skip "Tests will run automatically once src/installer/ is created"
    echo ""
    if [[ $FAILURES -eq 0 ]]; then
        echo -e "${GREEN}${BOLD}SKIP (phase-gated) — Python environment OK.${RESET}"
        exit 0
    else
        echo -e "${RED}${BOLD}$FAILURES dependency check(s) failed.${RESET}"
        exit 1
    fi
fi

# ── Run pytest ────────────────────────────────────────────────────────────────
log_section "Running pytest"
cd "$WORKSPACE"

if ! pytest src/installer/tests/ \
        -v \
        --tb=short \
        --cov=src/installer \
        --cov-report=term-missing \
        --cov-report=xml:coverage.xml \
        2>&1; then
    log_fail "pytest reported test failures"
    FAILURES=$((FAILURES + 1))
fi

# ── Coverage gate ─────────────────────────────────────────────────────────────
log_section "Coverage gate (≥ ${COVERAGE_GATE}%)"

if [[ -f "$WORKSPACE/coverage.xml" ]]; then
    # Extract line-rate from coverage.xml and convert to percentage
    LINE_RATE=$(python -c "
import xml.etree.ElementTree as ET
tree = ET.parse('coverage.xml')
root = tree.getroot()
rate = float(root.attrib.get('line-rate', '0'))
print(int(rate * 100))
")
    if [[ "$LINE_RATE" -ge $COVERAGE_GATE ]]; then
        log_ok "Coverage: ${LINE_RATE}% (gate: ${COVERAGE_GATE}%)"
    else
        log_fail "Coverage: ${LINE_RATE}% — below gate of ${COVERAGE_GATE}%"
        FAILURES=$((FAILURES + 1))
    fi
else
    log_fail "coverage.xml not generated — cannot check coverage gate"
    FAILURES=$((FAILURES + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All pytest checks passed.${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}$FAILURES test/coverage check(s) failed.${RESET}"
    exit 1
fi
