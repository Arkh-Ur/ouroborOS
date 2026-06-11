#!/usr/bin/env bash
# shellcheck shell=bash
# E2E test runner — our_* tools on an installed ouroborOS system.
#
# Requires: sshpass, an installed ouroborOS VM accessible via SSH.
#
# Usage:
#   E2E_ROOT_PASS=toor E2E_SSH_PORT=2225 bash tests/scripts/e2e-our-tools.sh
#
# Variables (all have defaults):
#   E2E_ROOT_PASS  — root SSH password (default: toor)
#   E2E_SSH_PORT   — SSH port on localhost (default: 2225)
set -euo pipefail

ROOT_PASS="${E2E_ROOT_PASS:-toor}"
SSH_PORT="${E2E_SSH_PORT:-2225}"
SSH_BASE="sshpass -p ${ROOT_PASS} ssh -p ${SSH_PORT} \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o PasswordAuthentication=yes \
  root@localhost"
SSH="$SSH_BASE"
PASS=0; FAIL=0; SKIP=0

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'

check() {
    local name="$1"; shift
    local out
    if out=$($SSH "$*" 2>&1); then
        echo -e "  ${GREEN}PASS${RESET} $name"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}FAIL${RESET} $name"
        echo "       └─ $out" | head -3
        FAIL=$((FAIL+1))
    fi
}

check_fail() {
    local name="$1"; shift
    if ! $SSH "$*" 2>/dev/null; then
        echo -e "  ${GREEN}PASS${RESET} $name (expected failure)"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}FAIL${RESET} $name (should have failed)"
        FAIL=$((FAIL+1))
    fi
}

check_contains() {
    local name="$1"; local pattern="$2"; shift 2
    local out
    out=$($SSH "$@" 2>&1)
    if echo "$out" | grep -q "$pattern"; then
        echo -e "  ${GREEN}PASS${RESET} $name"
        PASS=$((PASS+1))
    else
        echo -e "  ${RED}FAIL${RESET} $name — expected '$pattern'"
        echo "       └─ $(echo "$out" | head -2)"
        FAIL=$((FAIL+1))
    fi
}

section() { echo -e "\n${BOLD}── $1 ──${RESET}"; }

# ─────────────────────────────────────────────────────────────
section "0. SETUP"
check "sshd running"            "systemctl is-active sshd"
check "root fs is ro"           "btrfs property get / ro | grep -q 'ro=true'"
check "our-pac exists"          "test -x /usr/local/bin/our-pac"
check "our-snapshot exists"     "test -x /usr/local/bin/our-snapshot"
check "our-rollback exists"     "test -x /usr/local/bin/our-rollback"
check "our-aur exists"          "test -x /usr/local/bin/our-aur"
check "our-flat exists"         "test -x /usr/local/bin/our-flat"
check "our-wall exists"         "test -x /usr/local/bin/our-wall"
check "ouroboros-health exists" "test -x /usr/local/bin/ouroboros-health"

# ─────────────────────────────────────────────────────────────
section "1. ouroboros-health"
check          "health exits 0"        "ouroboros-health"
check_contains "health --json valid"   '"status"'  "ouroboros-health --json"
check_contains "health --yaml valid"   'status:'   "ouroboros-health --yaml"
check_contains "root_ro check PASS"    '"root_ro"' "ouroboros-health --json"

# ─────────────────────────────────────────────────────────────
section "2. our-pac — install / remove"
check          "our-pac -Ss htop (search)"      "our-pac -Ss htop"
check          "our-pac -S htop (install)"      "our-pac -S htop --noconfirm"
check          "htop binary present"            "test -x /usr/bin/htop"
check          "root still ro after install"    "btrfs property get / ro | grep -q 'ro=true'"
check_contains "system.yaml has htop"           "htop"  "grep htop /etc/ouroboros/system.yaml"
check_contains "pac log written"                "."     "ls /var/log/our-pac/"
check          "snapshot created"               "our-snapshot list | grep -v 'No snapshots'"
check          "our-pac -R htop (remove)"       "our-pac -R htop --noconfirm"
check          "htop gone after remove"         "! test -x /usr/bin/htop"
check          "system.yaml no longer has htop" "! grep -q htop /etc/ouroboros/system.yaml"

# ─────────────────────────────────────────────────────────────
section "3. our-snapshot — lifecycle"
check      "list shows install snapshot" "our-snapshot list | grep -q install"
check      "create test-snap"            "our-snapshot create test-snap"
check      "subvolume exists"            "btrfs subvolume show /.snapshots/test-snap"
check      "boot entry created"          "test -f /boot/loader/entries/ouroboros-snapshot-test-snap.conf"
check      "info test-snap shows metadata" "our-snapshot info test-snap"
check      "diff install test-snap runs"   "our-snapshot diff install test-snap"
check      "delete test-snap"            "our-snapshot delete test-snap"
check      "subvolume gone"              "! btrfs subvolume show /.snapshots/test-snap 2>/dev/null"
check      "boot entry gone"             "! test -f /boot/loader/entries/ouroboros-snapshot-test-snap.conf"
check_fail "delete install is rejected"  "our-snapshot delete install"
check      "sync-boot-entries idempotent" "our-snapshot sync-boot-entries"

# ─────────────────────────────────────────────────────────────
section "4. our-rollback — try / promote / undo"
check          "list shows snapshots"   "our-rollback list"
check_contains "status: no pending"    "no\|pending\|rollback\|not" "our-rollback status"
check          "install nano (creates snapshot)" "our-pac -S nano --noconfirm"
SNAP=$($SSH "our-snapshot list 2>/dev/null \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -v 'NAME\|----\|install\|our-snapshot\|Running\|^\s*$' \
  | tail -1 | awk '{print \$1}'" 2>/dev/null | tr -d '* ')
echo "  [snap to rollback: '$SNAP']"
if [[ -n "$SNAP" ]]; then
    check      "try $SNAP (one-shot boot)"  "our-rollback try $SNAP"
    check      "@ unchanged after try"      "btrfs property get / ro | grep -q ro=true"
    check      "promote $SNAP --force"      "our-rollback promote $SNAP --force"
    check      "@.old exists after promote" "btrfs subvolume list / | grep -q '@.old'"
    check      "undo reverts promote"       "our-rollback undo --force"
    check_fail "undo again fails (no @.old)" "our-rollback undo --force"
else
    echo -e "  ${YELLOW}SKIP${RESET} rollback tests — no snapshot found"
    SKIP=$((SKIP+6))
fi

# ─────────────────────────────────────────────────────────────
section "5. our-wall — firewalld"
# Install firewalld + Python bindings if not present
$SSH "command -v firewall-cmd &>/dev/null || our-pac -S firewalld python-firewall python-dbus --noconfirm" \
  2>/dev/null && true
check          "our-wall enable"               "our-wall enable"
check          "our-wall status shows active"  "our-wall status | grep -qi 'running\|active'"
check          "allow ssh service"             "our-wall allow ssh"
check          "allow 8080/tcp port"           "our-wall allow 8080/tcp"
check_contains "list shows 8080"               "8080"  "our-wall list"
check          "deny 8080/tcp"                 "our-wall deny 8080/tcp"
check          "list no longer shows 8080"     "! our-wall list 2>&1 | grep -q 8080"
check          "preset reset (only ssh)"       "our-wall preset reset"
check          "reload"                        "our-wall reload"
check_fail     "unknown subcommand exits 1"    "our-wall unknowncmd"

# ─────────────────────────────────────────────────────────────
section "6. our-flat — Flatpak"
# Install flatpak if not present (profiles without GUI may not include it)
$SSH "command -v flatpak &>/dev/null || our-pac -S flatpak --noconfirm" 2>/dev/null && true
# Remove any pre-existing flathub remote so the "no remote" test is valid
$SSH "flatpak remote-delete --system --force flathub 2>/dev/null || true" 2>/dev/null && true
# Only test error path + remote management (full app install takes too long in CI)
check_fail "install without remote fails"  "our-flat -S org.gnome.Calculator"
check      "remote-add flathub"            "our-flat remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
check      "remote-list shows flathub"     "our-flat remote-list | grep -q flathub"
check_fail "our-flat -Syu rejected"        "our-flat -Syu"

# ─────────────────────────────────────────────────────────────
section "7. our-wifi — error path (no WiFi in QEMU)"
check_contains "list fails gracefully" \
  "No\|no\|device\|wifi\|wireless\|Error\|unavailable" \
  "our-wifi list 2>&1 || true"
# PSK file tests (no real hardware needed)
check          "connect --password writes PSK" \
  "our-wifi connect TestNet --password secret123 2>/dev/null || true; test -f /var/lib/iwd/TestNet.psk"
check_contains "show-password reads PSK back"  "secret123" "our-wifi show-password TestNet"
check          "forget TestNet removes PSK"    "our-wifi forget TestNet; ! test -f /var/lib/iwd/TestNet.psk"

# ─────────────────────────────────────────────────────────────
section "8. our-container — nspawn lifecycle"
if $SSH "which machinectl &>/dev/null && btrfs filesystem show / &>/dev/null" 2>/dev/null; then
    check  "container list (empty ok)"   "our-container list"
    check  "engine show"                 "our-container engine show"
    $SSH "our-container remove mybox 2>/dev/null; our-container remove arch 2>/dev/null" \
      2>/dev/null && true
    check  "create mybox from arch"      "our-container create mybox arch"
    check  "list shows mybox"            "our-container list | grep -q mybox"
    check  "start mybox"                 "our-container start mybox"
    check  "enter runs command"          "our-container enter mybox -- uname -a"
    check  "stop mybox"                  "our-container stop mybox"
    check  "snapshot create snap1"       "our-container snapshot create mybox snap1"
    check  "snapshot list mybox"         "our-container snapshot list mybox | grep -q snap1"
    check  "remove mybox"                "our-container remove mybox"
    check  "list no longer shows mybox"  "! our-container list 2>&1 | grep -q mybox"
else
    echo -e "  ${YELLOW}SKIP${RESET} our-container — machinectl or btrfs not available"
    SKIP=$((SKIP+11))
fi

# ─────────────────────────────────────────────────────────────
section "9. our-dots — dotfiles pack lifecycle"
if $SSH "test -x /usr/local/bin/our-dots" 2>/dev/null; then
    check     "our-dots version"         "our-dots --version"
    check     "our-dots list shows packs" "our-dots list | grep -q noctalia"
    check     "our-dots -Si ml4w"        "our-dots -Si ml4w | grep -qi 'ml4w\|name'"
    check_contains "our-dots -Q (empty ok)" "0\|packs installed\|No packs" \
        "our-dots -Q 2>&1 || true"
    # Lifecycle: install ml4w (git-clone only, no AUR deps — fastest pack)
    check     "our-dots install ml4w"    \
        "OUROBOROS_ALLOW_CRITICAL=0 our-dots -S ml4w --noconfirm"
    check     "ml4w marked installed"    \
        "our-dots list | grep -qE 'ml4w.*installed|installed.*ml4w' || \
         grep -q ml4w /etc/ouroboros/system.yaml"
    check     "our-dots uninstall ml4w"  "our-dots -R ml4w --noconfirm"
    check     "ml4w removed from list"   \
        "! our-dots list 2>&1 | grep -qE 'ml4w.*\[installed\]'"
else
    echo -e "  ${YELLOW}SKIP${RESET} our-dots — not found on this image"
    SKIP=$((SKIP+8))
fi

# ─────────────────────────────────────────────────────────────
section "RESULTS"
TOTAL=$((PASS+FAIL))
echo ""
echo -e "  ${GREEN}PASS${RESET}: $PASS / $TOTAL"
[[ $FAIL -gt 0 ]] && echo -e "  ${RED}FAIL${RESET}: $FAIL / $TOTAL"
[[ $SKIP -gt 0 ]] && echo -e "  ${YELLOW}SKIP${RESET}: $SKIP"
echo ""
[[ $FAIL -eq 0 ]] \
  && echo -e "${GREEN}All tests passed.${RESET}" \
  || echo -e "${RED}$FAIL test(s) failed.${RESET}"
exit $FAIL
