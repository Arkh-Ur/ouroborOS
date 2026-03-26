#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# setup-dev-env.sh — ouroborOS Development Environment Setup
# =============================================================================
# Sets up a development environment for building and testing ouroborOS.
# Must be run on an ArchLinux system (or ArchLinux-based derivative).
#
# Usage:
#   bash docs/scripts/setup-dev-env.sh [OPTIONS]
#
# Options:
#   --no-qemu        Skip QEMU/virtualization tools installation
#   --no-aur         Skip AUR helper setup
#   --dry-run        Print what would be done without executing
#   -h, --help       Show this help message
#
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

INSTALL_QEMU=true
DRY_RUN=false

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
log_section() { echo -e "\n${BOLD}── $* ──────────────────────${RESET}"; }

run() {
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "  ${YELLOW}[dry-run]${RESET} $*"
    else
        "$@"
    fi
}

# ── Args ──────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-qemu)   INSTALL_QEMU=false; shift ;;
        --dry-run)   DRY_RUN=true; shift ;;
        -h|--help)   sed -n '/^# Usage/,/^# =====/p' "$0" | grep -v '^# =====' | sed 's/^# //'; exit 0 ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Checks ────────────────────────────────────────────────────────────────────
log_section "System Check"

if ! command -v pacman &>/dev/null; then
    log_error "pacman not found. This script requires ArchLinux or an Arch-based distro."
    exit 1
fi
log_ok "pacman found — ArchLinux-compatible system detected"

if [[ "$EUID" -ne 0 ]] && [[ "$DRY_RUN" == false ]]; then
    log_warn "Not running as root. Will use sudo for pacman commands."
    SUDO="sudo"
else
    SUDO=""
fi

# ── Core build dependencies ───────────────────────────────────────────────────
log_section "Installing Build Dependencies"

BUILD_DEPS=(
    # ISO build
    archiso
    dosfstools
    e2fsprogs
    squashfs-tools
    libisoburn

    # Btrfs
    btrfs-progs

    # Development tools
    git
    base-devel
    python
    python-pip
    python-yaml
    python-rich

    # Testing
    dialog
    parted
    arch-install-scripts

    # Code quality
    shellcheck
    shfmt
)

log_info "Installing: ${BUILD_DEPS[*]}"
run $SUDO pacman -S --needed --noconfirm "${BUILD_DEPS[@]}"
log_ok "Build dependencies installed"

# ── QEMU / Virtualization ─────────────────────────────────────────────────────
if [[ "$INSTALL_QEMU" == true ]]; then
    log_section "Installing Virtualization Tools"

    QEMU_DEPS=(
        qemu-system-x86
        qemu-img
        edk2-ovmf       # UEFI firmware for QEMU
        virt-manager    # optional GUI
    )

    log_info "Installing: ${QEMU_DEPS[*]}"
    run $SUDO pacman -S --needed --noconfirm "${QEMU_DEPS[@]}"

    # Enable KVM module
    if lsmod | grep -q kvm; then
        log_ok "KVM module already loaded"
    else
        log_info "Loading KVM module..."
        run $SUDO modprobe kvm
        run $SUDO modprobe kvm_intel 2>/dev/null || run $SUDO modprobe kvm_amd 2>/dev/null || true
    fi

    # Add user to kvm group
    if [[ -n "${SUDO_USER:-}" ]]; then
        run $SUDO usermod -aG kvm "$SUDO_USER"
        log_ok "Added $SUDO_USER to kvm group (re-login required)"
    fi

    log_ok "Virtualization tools installed"
fi

# ── Python dev dependencies ───────────────────────────────────────────────────
log_section "Installing Python Dependencies"

PYTHON_DEPS=(
    pyyaml
    rich
    pytest
    pytest-cov
)

log_info "Installing Python packages: ${PYTHON_DEPS[*]}"
run pip install --quiet "${PYTHON_DEPS[@]}"
log_ok "Python dependencies installed"

# ── Git configuration check ───────────────────────────────────────────────────
log_section "Git Configuration"

if ! git config --global user.email &>/dev/null; then
    log_warn "git user.email not set. Configure with:"
    echo "  git config --global user.email 'you@example.com'"
    echo "  git config --global user.name 'Your Name'"
else
    log_ok "git configured as: $(git config --global user.name) <$(git config --global user.email)>"
fi

# ── Repo setup ────────────────────────────────────────────────────────────────
log_section "Repository Setup"

cd "$REPO_ROOT"

# Ensure we're on dev branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "dev" ]]; then
    log_warn "Not on dev branch (currently on: $CURRENT_BRANCH)"
    log_info "Switch with: git checkout dev"
else
    log_ok "On dev branch"
fi

# Create working directories
run mkdir -p "$REPO_ROOT/out"
run mkdir -p "$REPO_ROOT/work"

log_ok "Working directories created: out/, work/"

# ── Shell scripts linting ─────────────────────────────────────────────────────
log_section "Validating Shell Scripts"

SHELL_SCRIPTS=$(find "$REPO_ROOT/docs/scripts" -name "*.sh" 2>/dev/null)
if [[ -n "$SHELL_SCRIPTS" ]]; then
    while IFS= read -r script; do
        if shellcheck "$script" 2>/dev/null; then
            log_ok "shellcheck: $script"
        else
            log_warn "shellcheck warnings in: $script"
        fi
    done <<< "$SHELL_SCRIPTS"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log_section "Setup Complete"

echo ""
echo -e "  ${BOLD}Repo:${RESET}    $REPO_ROOT"
echo -e "  ${BOLD}Branch:${RESET}  $(git branch --show-current)"
echo -e "  ${BOLD}Python:${RESET}  $(python --version)"
echo ""
echo "Next steps:"
echo "  1. Review docs/architecture/overview.md"
echo "  2. Build the ISO: sudo bash docs/scripts/build-iso.sh"
echo "  3. Test in QEMU: see docs/build/build-process.md"
echo ""
log_ok "Development environment ready."
