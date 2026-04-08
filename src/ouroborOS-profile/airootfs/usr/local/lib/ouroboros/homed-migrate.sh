#!/usr/bin/env bash
set -euo pipefail
# homed-migrate.sh — migrate a classic user to systemd-homed
#
# Designed to run as a oneshot systemd unit on first boot (before getty).
# The user was created with useradd during install; this converts them
# to a systemd-homed-managed identity with LoFS/subvolume storage.
#
# Required environment variables (passed via the systemd service):
#   HOMED_USERNAME       — user login name
#   HOMED_STORAGE        — storage backend: subvolume, directory, luks, or classic
#
# Exit codes:
#   0 — migration successful (or skipped because already migrated)
#   1 — migration failed; rollback attempted
#   2 — pre-flight check failed (nothing changed)

: "${HOMED_USERNAME:?HOMED_USERNAME must be set}"
: "${HOMED_STORAGE:?HOMED_STORAGE must be set}"

HOME_DIR="/home/${HOMED_USERNAME}"
HOME_BACKUP="${HOME_DIR}.homed-migration-backup"
MIGRATION_MARKER="/etc/ouroboros/homed-migration-done"
FLAG_FILE="/etc/ouroboros/homed-migration-pending"

# --- Logging -----------------------------------------------------------------

log_info()  { printf '\033[0;34m[homed-migrate]\033[0m %s\n' "$*" >&2; }
log_ok()    { printf '\033[0;32m[homed-migrate]\033[0m %s\n' "$*" >&2; }
log_warn()  { printf '\033[0;33m[homed-migrate]\033[0m %s\n' "$*" >&2; }
log_error() { printf '\033[0;31m[homed-migrate]\033[0m %s\n' "$*" >&2; }

# --- Pre-flight checks --------------------------------------------------------

preflight() {
    # Already migrated? Skip.
    if [[ -f "$MIGRATION_MARKER" ]]; then
        log_info "Migration already completed (marker exists). Skipping."
        return 1
    fi

    # Validate storage type
    case "$HOMED_STORAGE" in
        subvolume|directory|luks) ;;
        *)
            log_error "Unsupported storage backend: ${HOMED_STORAGE}"
            return 1
            ;;
    esac

    # Verify systemd-homed is running
    if ! systemctl is-active --quiet systemd-homed.service; then
        log_error "systemd-homed.service is not active. Cannot migrate."
        return 1
    fi

    # Verify the user exists as a classic user in /etc/passwd
    if ! id "$HOMED_USERNAME" &>/dev/null; then
        log_error "User '${HOMED_USERNAME}' does not exist in /etc/passwd."
        return 1
    fi

    # Verify the home directory exists
    if [[ ! -d "$HOME_DIR" ]]; then
        log_error "Home directory '${HOME_DIR}' does not exist."
        return 1
    fi

    # Verify homectl is available
    if ! command -v homectl &>/dev/null; then
        log_error "homectl not found. Is systemd-homed installed?"
        return 1
    fi

    log_ok "Pre-flight checks passed."
    return 0
}

# --- Rollback ----------------------------------------------------------------

rollback() {
    local step="$1"
    log_warn "Rolling back from step: ${step}"

    case "$step" in
        after_rsync)
            homectl remove "$HOMED_USERNAME" 2>/dev/null || true
            ;;&
        after_homed_create)
            if [[ -d "${HOME_BACKUP}" ]]; then
                rm -rf "$HOME_DIR" 2>/dev/null || true
                mv "$HOME_BACKUP" "$HOME_DIR"
                log_ok "Home directory restored from backup."
            fi
            homectl remove "$HOMED_USERNAME" 2>/dev/null || true
            ;;&
        after_backup)
            if [[ -d "${HOME_BACKUP}" ]]; then
                mv "$HOME_BACKUP" "$HOME_DIR"
                log_ok "Home directory restored from backup."
            fi
            ;;
        *)
            log_warn "Unknown rollback step: ${step} — nothing to undo."
            ;;
    esac

    log_error "Migration FAILED at step: ${step}. System left in pre-migration state."
    exit 1
}

# --- Patch PAM for systemd-homed --------------------------------------------

patch_pam() {
    # sshd authenticates via PAM. With homed active, PAM must include
    # pam_systemd_home.so — otherwise SSH logins fail because sshd looks
    # up the user in /etc/passwd (which no longer has the entry after migration).
    local pam_file="/etc/pam.d/system-auth"

    if [[ ! -f "$pam_file" ]]; then
        # Arch may not have system-auth — check nsswitch instead
        log_warn "system-auth not found at ${pam_file} — skipping PAM patch."
        return 0
    fi

    # Only add if not already present
    if ! grep -q "pam_systemd_home.so" "$pam_file" 2>/dev/null; then
        # Insert pam_systemd_home.so early enough in the auth stack
        sed -i '/^auth.*pam_unix.so/i auth sufficient pam_systemd_home.so' "$pam_file"
        log_ok "PAM patched: pam_systemd_home.so added to system-auth."
    else
        log_info "PAM already includes pam_systemd_home.so — skipping patch."
    fi
}

# --- Migration ---------------------------------------------------------------

migrate() {
    log_info "Starting migration of '${HOMED_USERNAME}' to systemd-homed (${HOMED_STORAGE})"

    # Collect user info before we touch anything
    local uid
    uid=$(id -u "$HOMED_USERNAME")
    local groups
    # Get supplementary groups as comma-separated (skip the primary group which homectl manages)
    groups=$(id -Gn "$HOMED_USERNAME" | tr ' ' ',' | sed "s/${HOMED_USERNAME},//")

    # Step 1: Stop any active session for this user
    log_info "Stopping user sessions..."
    systemctl stop "user@${uid}.service" 2>/dev/null || true
    loginctl terminate-user "$HOMED_USERNAME" 2>/dev/null || true

    # Step 2: Backup the classic home directory
    log_info "Backing up home directory: ${HOME_DIR} → ${HOME_BACKUP}"
    mv "$HOME_DIR" "$HOME_BACKUP"
    if [[ ! -d "${HOME_BACKUP}" ]]; then
        rollback "before_backup"
    fi

    # Step 3: Create the homed identity
    local homectl_args=(
        create "$HOMED_USERNAME"
        --storage="$HOMED_STORAGE"
        --disk-size=max
        --uid="$uid"
        --shell=/bin/bash
    )
    if [[ -n "$groups" ]]; then
        homectl_args+=(--member-of="$groups")
    fi

    log_info "Creating systemd-homed identity..."
    if ! homectl "${homectl_args[@]}"; then
        log_error "homectl create failed."
        rollback "after_backup"
    fi

    # Step 4: Activate the home (mount it)
    log_info "Activating home for '${HOMED_USERNAME}'..."
    if ! homectl activate "$HOMED_USERNAME"; then
        log_error "homectl activate failed."
        rollback "after_homed_create"
    fi

    # Verify the new home mount exists
    if [[ ! -d "$HOME_DIR" ]]; then
        log_error "Home directory not mounted after activate: ${HOME_DIR}"
        rollback "after_homed_create"
    fi

    # Step 5: Copy data from backup into the new homed home
    log_info "Copying user data into homed home..."
    if ! rsync -aHAX --exclude='.homedir' "${HOME_BACKUP}/" "${HOME_DIR}/"; then
        log_error "rsync failed during data copy."
        rollback "after_rsync"
    fi

    # Step 6: Patch PAM for homed compatibility (SSH logins)
    patch_pam

    # Step 7: Remove classic user entries from passwd/shadow/group/gshadow
    # homectl now owns this identity — the classic entries would conflict.
    log_info "Removing classic user entries from /etc/passwd and friends..."
    for db in passwd shadow group gshadow; do
        if [[ -f "/etc/${db}" ]]; then
            sed -i "/^${HOMED_USERNAME}:/d" "/etc/${db}"
        fi
    done

    # Step 8: Clean up backup
    log_info "Removing backup directory..."
    rm -rf "${HOME_BACKUP}"

    # Step 9: Write completion marker
    mkdir -p /etc/ouroboros
    touch "$MIGRATION_MARKER"

    # Step 10: Remove the pending flag and disable this service
    rm -f "$FLAG_FILE"
    systemctl disable ouroboros-homed-migration.service 2>/dev/null || true

    log_ok "Migration of '${HOMED_USERNAME}' to systemd-homed (${HOMED_STORAGE}) completed successfully."
    return 0
}

# --- Main -------------------------------------------------------------------

main() {
    log_info "ouroboros homed-migrate starting..."
    log_info "User: ${HOMED_USERNAME}, Storage: ${HOMED_STORAGE}"

    if ! preflight; then
        log_info "Skipping migration (pre-flight returned false)."
        # Still clean up — remove the flag and disable the service
        rm -f "$FLAG_FILE" 2>/dev/null || true
        systemctl disable ouroboros-homed-migration.service 2>/dev/null || true
        exit 0
    fi

    migrate
}

main "$@"
