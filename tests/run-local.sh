#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# run-local.sh — Build the test image and run the full test suite locally
#
# Uses podman (preferred) or docker if podman is not available.
#
# Usage:
#   bash tests/run-local.sh              # full suite
#   bash tests/run-local.sh shellcheck   # single suite
#   bash tests/run-local.sh pytest       # single suite
#   bash tests/run-local.sh build        # build image only
#
# Available suite names (pass as first argument):
#   Suites: check | validate | dry-run | lint | pytest | smoke | full (default)
#   (where 'check' runs the shellcheck suite)
# =============================================================================

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_fail()    { echo -e "${RED}[FAIL]${RESET}  $*"; }
log_info()    { echo -e "${YELLOW}[INFO]${RESET}  $*"; }
log_section() { echo -e "\n${BOLD}═══ $* ═══════════════════════════════════${RESET}"; }

# ── Detect container runtime ──────────────────────────────────────────────────
if command -v podman &>/dev/null; then
    CTR=podman
elif command -v docker &>/dev/null; then
    CTR=docker
else
    echo -e "${RED}ERROR: neither podman nor docker found.${RESET}"
    echo ""
    echo "Install podman on Arch Linux:"
    echo "  sudo pacman -S podman"
    echo ""
    echo "Optional (for rootless networking):"
    echo "  sudo pacman -S slirp4netns"
    exit 1
fi

log_info "Using container runtime: $CTR"

# ── Resolve paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE="ouroboros-test:local"

# ── Parse argument ─────────────────────────────────────────────────────────────
SUITE="${1:-full}"

# ── Build image ───────────────────────────────────────────────────────────────
log_section "Building test image ($IMAGE)"
"$CTR" build -t "$IMAGE" "$SCRIPT_DIR"
log_ok "Image built: $IMAGE"

if [[ "$SUITE" == "build" ]]; then
    log_ok "Build-only requested — done."
    exit 0
fi

# ── Helper: run a single test script in a container ──────────────────────────
run_suite() {
    local name="$1"
    local script="$2"
    local extra_flags="${3:-}"

    log_section "$name"

    # shellcheck disable=SC2086
    if "$CTR" run --rm \
        -v "$REPO_ROOT:/workspace:ro" \
        -e WORKSPACE=/workspace \
        -e TERM=xterm-256color \
        $extra_flags \
        "$IMAGE" \
        bash "/workspace/tests/scripts/$script"; then
        log_ok "$name passed"
        return 0
    else
        log_fail "$name FAILED"
        return 1
    fi
}

run_pytest() {
    log_section "pytest + coverage"

    if "$CTR" run --rm \
        -v "$REPO_ROOT:/workspace" \
        -e WORKSPACE=/workspace \
        -e TERM=xterm-256color \
        "$IMAGE" \
        bash /workspace/tests/scripts/run-pytest.sh; then
        log_ok "pytest passed"
        return 0
    else
        log_fail "pytest FAILED"
        return 1
    fi
}

TMPFS_FLAGS="--tmpfs /tmp:exec,mode=1777"

# ── Run selected suite(s) ─────────────────────────────────────────────────────
FAILURES=0

case "$SUITE" in
    shellcheck)
        run_suite "ShellCheck" "test-shellcheck.sh" || FAILURES=$((FAILURES + 1))
        ;;
    validate)
        run_suite "Validate scripts" "validate-scripts.sh" || FAILURES=$((FAILURES + 1))
        ;;
    dry-run)
        run_suite "Dry-run build" "test-build-dry-run.sh" "$TMPFS_FLAGS" || FAILURES=$((FAILURES + 1))
        ;;
    lint)
        run_suite "Python lint" "lint-python.sh" || FAILURES=$((FAILURES + 1))
        ;;
    pytest)
        run_pytest || FAILURES=$((FAILURES + 1))
        ;;
    smoke)
        run_suite "Smoke test" "smoke-test.sh" || FAILURES=$((FAILURES + 1))
        ;;
    full)
        run_suite "ShellCheck"       "test-shellcheck.sh"  ""             || FAILURES=$((FAILURES + 1))
        run_suite "Validate scripts" "validate-scripts.sh" ""             || FAILURES=$((FAILURES + 1))
        run_suite "Dry-run build"    "test-build-dry-run.sh" "$TMPFS_FLAGS" || FAILURES=$((FAILURES + 1))
        run_suite "Python lint"      "lint-python.sh"      ""             || FAILURES=$((FAILURES + 1))
        run_pytest                                                         || FAILURES=$((FAILURES + 1))
        run_suite "Smoke test"       "smoke-test.sh"       ""             || FAILURES=$((FAILURES + 1))
        ;;
    *)
        echo "Unknown suite: $SUITE"
        echo "Valid options: shellcheck | validate | dry-run | lint | pytest | smoke | full | build"
        exit 1
        ;;
esac

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All suites passed.${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}$FAILURES suite(s) failed.${RESET}"
    exit 1
fi
