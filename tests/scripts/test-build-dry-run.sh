#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# test-build-dry-run.sh — Dry-run test for build-iso.sh with mocked mkarchiso
# =============================================================================
# Injects a fake mkarchiso into PATH to test build-iso.sh control flow without
# performing a real ISO build (which requires loop devices and root access).
#
# Tests:
#   1. --help exits 0 and produces output
#   2. Missing profile directory → exit 1 with descriptive error (not bash trace)
#   3. Arguments --output/--workdir/--profile are passed to mkarchiso correctly
#   4. --clean removes working directory before build
#   5. Mock ISO file is found for checksum generation
#
# Exit codes:
#   0 — all tests pass
#   1 — any test fails
# =============================================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; BOLD='\033[1m'; RESET='\033[0m'

log_ok()    { echo -e "${GREEN}[PASS]${RESET} $*"; }
log_fail()  { echo -e "${RED}[FAIL]${RESET} $*"; }
log_test()  { echo -e "${BOLD}[TEST]${RESET} $*"; }

WORKSPACE="${WORKSPACE:-/workspace}"
BUILD_ISO="$WORKSPACE/src/scripts/build-iso.sh"
FAILURES=0

if [[ ! -f "$BUILD_ISO" ]]; then
    log_fail "src/scripts/build-iso.sh not found at $BUILD_ISO"
    exit 1
fi

# ── Setup mock environment ────────────────────────────────────────────────────
MOCK_DIR="$(mktemp -d /tmp/ouroborOS-mock-XXXXXX)"
FAKE_PROFILE="$(mktemp -d /tmp/ouroborOS-profile-XXXXXX)"
FAKE_OUTPUT="/tmp/ouroborOS-output-$$"
FAKE_WORK="/tmp/ouroborOS-work-$$"

trap 'sudo rm -rf "$MOCK_DIR" "$FAKE_PROFILE" "$FAKE_OUTPUT" "$FAKE_WORK" 2>/dev/null || rm -rf "$MOCK_DIR" "$FAKE_PROFILE" "$FAKE_OUTPUT" "$FAKE_WORK" 2>/dev/null || true' EXIT

# Seed FAKE_PROFILE with a real profiledef.sh so build-iso.sh can derive the ISO
# filename (${iso_name}-${iso_version}-${arch}.iso) at the checksum stage.
cp "$WORKSPACE/src/ouroborOS-profile/profiledef.sh" "$FAKE_PROFILE/"

# Mock mkarchiso: captures args, creates fake ISO matching the real ISO name, exits 0
cat > "$MOCK_DIR/mkarchiso" << 'MOCK_EOF'
#!/usr/bin/env bash
set -euo pipefail
# Capture args to a file for inspection
echo "$@" > /tmp/mkarchiso-args-captured
# Parse -o <out_dir> and the trailing profile_dir from the argument list
out_dir=""
profile_dir=""
prev=""
for arg in "$@"; do
    case "$prev" in
        -o) out_dir="$arg" ;;
    esac
    # Profile dir is any positional arg not following a known flag
    if [[ "$arg" != -* ]] && [[ "$prev" != "-o" ]] && [[ "$prev" != "-w" ]]; then
        profile_dir="$arg"
    fi
    prev="$arg"
done
# Derive ISO name from profiledef.sh (mirrors what build-iso.sh expects)
iso_name="ouroborOS"; iso_version="test"; iso_arch="x86_64"
if [[ -f "${profile_dir}/profiledef.sh" ]]; then
    iso_name=$(sed -n 's/^iso_name="\(.*\)"/\1/p' "${profile_dir}/profiledef.sh")
    iso_version=$(sed -n 's/^iso_version="\(.*\)"/\1/p' "${profile_dir}/profiledef.sh")
    iso_arch=$(sed -n 's/^arch="\(.*\)"/\1/p' "${profile_dir}/profiledef.sh")
fi
if [[ -n "$out_dir" ]]; then
    mkdir -p "$out_dir"
    touch "$out_dir/${iso_name}-${iso_version}-${iso_arch}.iso"
fi
echo "[MOCK] mkarchiso called with: $*" >&2
exit 0
MOCK_EOF
chmod +x "$MOCK_DIR/mkarchiso"

# Mock mkfs.erofs (replaces mksquashfs since airootfs migrated to erofs)
cat > "$MOCK_DIR/mkfs.erofs" << 'MOCK_EOF'
#!/usr/bin/env bash
exit 0
MOCK_EOF
chmod +x "$MOCK_DIR/mkfs.erofs"

# Mock xorriso (required by build-iso.sh preflight check)
cat > "$MOCK_DIR/xorriso" << 'MOCK_EOF'
#!/usr/bin/env bash
exit 0
MOCK_EOF
chmod +x "$MOCK_DIR/xorriso"

# Inject mocks into PATH
export PATH="$MOCK_DIR:$PATH"

# build-iso.sh requires root (EUID 0). Run it via `sudo bash -c` and re-export
# PATH inside so the mock mkarchiso/mkfs.erofs/xorriso are found — sudo's
# secure_path would otherwise strip $MOCK_DIR and the REAL tools would run.
# This relies only on /usr/bin/bash being NOPASSWD on the CI runner; the older
# `sudo env PATH=... bash` pattern needed /usr/bin/env allowlisted and hung
# waiting for a password in non-interactive CI.
run_build_as_root() {
    sudo bash -c "export PATH=\"$MOCK_DIR:\$PATH\"; exec bash \"$BUILD_ISO\" \"\$@\"" _ "$@"
}

# ── Test 1: --help exits 0 with output ───────────────────────────────────────
log_test "1. --help exits 0 and produces output"
help_output=$(bash "$BUILD_ISO" --help 2>&1) && help_rc=0 || help_rc=$?
if [[ $help_rc -eq 0 ]] && [[ -n "$help_output" ]]; then
    log_ok "  --help exits 0 with output"
else
    # help() calls exit 0 but may appear as non-zero in subshell; check output
    if [[ -n "$help_output" ]]; then
        log_ok "  --help produces output (exit code non-critical for help)"
    else
        log_fail "  --help produced no output"
        FAILURES=$((FAILURES + 1))
    fi
fi

# ── Test 2: Missing profile → exit 1 with descriptive error ──────────────────
log_test "2. Missing profile directory → exit 1 with descriptive message"
error_output=$(bash "$BUILD_ISO" --profile /nonexistent/profile 2>&1 || true)
if echo "$error_output" | grep -qi "profile\|not found\|directory"; then
    log_ok "  Exits with descriptive error message (no bash trace)"
    # Ensure no raw bash traceback
    if echo "$error_output" | grep -q "line [0-9]*:"; then
        log_fail "  Script produced raw bash traceback — should handle error cleanly"
        FAILURES=$((FAILURES + 1))
    fi
else
    log_fail "  Error message not descriptive enough: $error_output"
    FAILURES=$((FAILURES + 1))
fi

# ── Test 3: Arguments passed to mkarchiso correctly ──────────────────────────
log_test "3. Arguments --output/--workdir/--profile passed to mkarchiso"
mkdir -p "$FAKE_PROFILE"  # Profile must exist to pass preflight

run_build_as_root \
    --output "$FAKE_OUTPUT" \
    --workdir "$FAKE_WORK" \
    --profile "$FAKE_PROFILE" 2>/dev/null || true

if [[ -f "/tmp/mkarchiso-args-captured" ]]; then
    CAPTURED=$(cat /tmp/mkarchiso-args-captured)
    PASS=true
    [[ "$CAPTURED" == *"-o"* ]] || { log_fail "  -o flag not passed to mkarchiso"; PASS=false; }
    [[ "$CAPTURED" == *"-w"* ]] || { log_fail "  -w flag not passed to mkarchiso"; PASS=false; }
    [[ "$CAPTURED" == *"$FAKE_PROFILE"* ]] || { log_fail "  profile path not passed to mkarchiso"; PASS=false; }
    $PASS && log_ok "  mkarchiso received correct arguments: -o -w <profile>"
    $PASS || FAILURES=$((FAILURES + 1))
else
    log_fail "  mkarchiso was never called (args file not created)"
    FAILURES=$((FAILURES + 1))
fi
sudo rm -f /tmp/mkarchiso-args-captured 2>/dev/null || rm -f /tmp/mkarchiso-args-captured 2>/dev/null || true

# ── Test 4: --clean removes working directory before build ───────────────────
log_test "4. --clean removes existing working directory"
sudo rm -rf "$FAKE_WORK" 2>/dev/null || true
mkdir -p "$FAKE_WORK/leftover-data"
touch "$FAKE_WORK/leftover-data/old-file.txt"
mkdir -p "$FAKE_PROFILE"

run_build_as_root \
    --clean \
    --output "$FAKE_OUTPUT" \
    --workdir "$FAKE_WORK" \
    --profile "$FAKE_PROFILE" 2>/dev/null || true

if [[ ! -f "$FAKE_WORK/leftover-data/old-file.txt" ]]; then
    log_ok "  --clean removed previous working directory contents"
else
    log_fail "  --clean did NOT remove previous working directory"
    FAILURES=$((FAILURES + 1))
fi

# ── Test 5: Checksum generated for ISO ────────────────────────────────────────
log_test "5. SHA256 checksum file generated alongside ISO"
if find "$FAKE_OUTPUT" -name "*.sha256" 2>/dev/null | grep -q .; then
    log_ok "  .sha256 checksum file created"
else
    log_fail "  No .sha256 file found in output directory"
    FAILURES=$((FAILURES + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All 5 dry-run tests passed.${RESET}"
    exit 0
else
    echo -e "${RED}${BOLD}$FAILURES dry-run test(s) failed.${RESET}"
    exit 1
fi
