#!/usr/bin/env bash
# =============================================================================
# validate-scripts.sh — Validate structure, permissions, and APIs of scripts
# =============================================================================
# Validates (without executing) that project scripts:
#   - Are executable
#   - Contain expected flags and functions
#   - Produce output when called with --help
#   - Have the correct log function definitions
#
# Exit codes:
#   0 — all validations pass
#   1 — one or more validation failures
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_fail()    { echo -e "${RED}[FAIL]${RESET}  $*"; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────────────────${RESET}"; }

WORKSPACE="${WORKSPACE:-/workspace}"
FAILURES=0

# Helper: assert a file exists and is executable
assert_executable() {
    local file="$1"
    local rel="${file#"$WORKSPACE/"}"
    if [[ -x "$file" ]]; then
        log_ok "$rel is executable"
    else
        log_fail "$rel is NOT executable (missing +x)"
        FAILURES=$((FAILURES + 1))
    fi
}

# Helper: assert a file contains a string
assert_contains() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    local rel="${file#"$WORKSPACE/"}"
    if grep -q "$pattern" "$file"; then
        log_ok "$rel contains: $description"
    else
        log_fail "$rel MISSING: $description"
        FAILURES=$((FAILURES + 1))
    fi
}

# Helper: assert --help produces output and exits 0
assert_help() {
    local file="$1"
    local rel="${file#"$WORKSPACE/"}"
    local output
    if output=$(bash "$file" --help 2>&1) && [[ -n "$output" ]]; then
        log_ok "$rel --help exits 0 with output"
    else
        log_fail "$rel --help did not exit 0 or produced no output"
        FAILURES=$((FAILURES + 1))
    fi
}

# ── build-iso.sh ──────────────────────────────────────────────────────────────
log_section "Validating build-iso.sh"

BUILD_ISO="$WORKSPACE/src/scripts/build-iso.sh"

if [[ ! -f "$BUILD_ISO" ]]; then
    log_fail "src/scripts/build-iso.sh not found"
    FAILURES=$((FAILURES + 1))
else
    assert_executable "$BUILD_ISO"
    assert_contains "$BUILD_ISO" "\-\-clean"    "flag --clean"
    assert_contains "$BUILD_ISO" "\-\-output"   "flag --output"
    assert_contains "$BUILD_ISO" "\-\-workdir"  "flag --workdir"
    assert_contains "$BUILD_ISO" "\-\-profile"  "flag --profile"
    assert_contains "$BUILD_ISO" "mkarchiso -v" "mkarchiso invocation"
    assert_contains "$BUILD_ISO" "sha256sum"    "SHA256 checksum generation"
    assert_contains "$BUILD_ISO" "log_info"     "log_info function call"
    assert_contains "$BUILD_ISO" "log_ok"       "log_ok function call"
    assert_contains "$BUILD_ISO" "log_error"    "log_error function call"
    assert_contains "$BUILD_ISO" "^log_info()"  "log_info function definition"
    assert_contains "$BUILD_ISO" "^log_ok()"    "log_ok function definition"
    assert_contains "$BUILD_ISO" "^log_error()" "log_error function definition"
    assert_contains "$BUILD_ISO" "RED="         "RED color variable"
    assert_contains "$BUILD_ISO" "GREEN="       "GREEN color variable"
    assert_contains "$BUILD_ISO" "RESET="       "RESET color variable"
    assert_help "$BUILD_ISO"
fi

# ── setup-dev-env.sh ──────────────────────────────────────────────────────────
log_section "Validating setup-dev-env.sh"

SETUP="$WORKSPACE/src/scripts/setup-dev-env.sh"

if [[ ! -f "$SETUP" ]]; then
    log_fail "src/scripts/setup-dev-env.sh not found"
    FAILURES=$((FAILURES + 1))
else
    assert_executable "$SETUP"
    assert_contains "$SETUP" "BUILD_DEPS"    "BUILD_DEPS array"
    assert_contains "$SETUP" "shellcheck"    "shellcheck in dependency list"
    assert_contains "$SETUP" "archiso"       "archiso in dependency list"
    assert_contains "$SETUP" "qemu"          "qemu in dependency list"
    assert_contains "$SETUP" "log_info"      "log_info function call"
    assert_contains "$SETUP" "log_ok"        "log_ok function call"
    assert_contains "$SETUP" "^log_info()"   "log_info function definition"
    assert_help "$SETUP"
fi

# ── test scripts themselves ───────────────────────────────────────────────────
log_section "Validating test scripts are executable"

TEST_SCRIPTS=(
    "$WORKSPACE/tests/scripts/test-shellcheck.sh"
    "$WORKSPACE/tests/scripts/validate-scripts.sh"
    "$WORKSPACE/tests/scripts/test-build-dry-run.sh"
    "$WORKSPACE/tests/scripts/run-pytest.sh"
    "$WORKSPACE/tests/scripts/lint-python.sh"
    "$WORKSPACE/tests/scripts/smoke-test.sh"
)

for ts in "${TEST_SCRIPTS[@]}"; do
    if [[ -f "$ts" ]]; then
        assert_executable "$ts"
    else
        log_fail "${ts#"$WORKSPACE/"} does not exist"
        FAILURES=$((FAILURES + 1))
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All script validations passed.${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}$FAILURES validation(s) failed.${RESET}"
    exit 1
fi
