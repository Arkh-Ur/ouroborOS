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
#   HOMED_PASSWORD       — plaintext password for non-interactive homectl create/activate
#
# Exit codes:
#   0 — migration successful (or skipped because already migrated)
#   1 — migration failed; rollback attempted
#   2 — pre-flight check failed (nothing changed)

: "${HOMED_USERNAME:?HOMED_USERNAME must be set}"
: "${HOMED_STORAGE:?HOMED_STORAGE must be set}"
: "${HOMED_PASSWORD:?HOMED_PASSWORD must be set}"

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
    log_warn "User '${HOMED_USERNAME}' remains as a classic /etc/passwd user."
    log_warn "Home directory: /home/${HOMED_USERNAME} (unchanged, no data loss)."
    log_warn "Known issue: homectl create fails when /home is a Btrfs subvolume (@home)."
    log_warn "See: https://github.com/systemd/systemd/issues/15121"
    log_warn "The system is fully functional — login works normally as a classic user."
    exit 1
}

# --- Patch PAM for systemd-homed --------------------------------------------

patch_pam() {
    # sshd authenticates via PAM. With homed active, PAM must include
    # pam_systemd_home.so — otherwise SSH logins fail because sshd looks
    # up the user in /etc/passwd (which no longer has the entry after migration).
    #
    # On Arch Linux, sshd uses /etc/pam.d/sshd directly (no system-auth include).
    # We patch both files to cover Arch and generic Linux distributions.
    local patched=0

    # Arch Linux / direct sshd PAM
    local sshd_pam="/etc/pam.d/sshd"
    if [[ -f "$sshd_pam" ]] && ! grep -q "pam_systemd_home.so" "$sshd_pam" 2>/dev/null; then
        sed -i '/^auth.*include.*system-auth\|^auth.*required.*pam_unix/i auth       sufficient   pam_systemd_home.so' "$sshd_pam"
        log_ok "PAM patched: pam_systemd_home.so added to /etc/pam.d/sshd."
        patched=1
    fi

    # Generic Linux: patch system-auth if present
    local system_auth="/etc/pam.d/system-auth"
    if [[ -f "$system_auth" ]] && ! grep -q "pam_systemd_home.so" "$system_auth" 2>/dev/null; then
        sed -i '/^auth.*pam_unix.so/i auth sufficient pam_systemd_home.so' "$system_auth"
        log_ok "PAM patched: pam_systemd_home.so added to /etc/pam.d/system-auth."
        patched=1
    fi

    [[ $patched -eq 0 ]] && log_warn "No PAM files patched — pam_systemd_home.so may not load for SSH."
    return 0
}

# --- Update NSS for homed user resolution ------------------------------------

update_nsswitch() {
    # SSH needs NSS to resolve homed users (not in /etc/passwd after migration).
    # Add 'systemd' to the passwd and group lines in nsswitch.conf.
    local nss="/etc/nsswitch.conf"
    [[ -f "$nss" ]] || { log_warn "nsswitch.conf not found — skipping NSS update."; return 0; }

    sed -i '/^passwd:/ { /systemd/! s/$/ systemd/ }' "$nss"
    sed -i '/^group:/  { /systemd/! s/$/ systemd/ }' "$nss"
    log_ok "nsswitch.conf updated: 'systemd' added to passwd/group lookup."
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

    # Step 3: Create the homed identity with JSON identity (non-interactive)
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

    # Create a JSON identity file with the password for non-interactive create
    local identity_json
    identity_json=$(mktemp /tmp/homed-identity.XXXXXX.json)
    chmod 600 "$identity_json"
    # Build JSON identity — homectl --identity reads user record from file
    cat > "$identity_json" << IDENTITY_EOF
{"userName":"${HOMED_USERNAME}","secret":{"password":["${HOMED_PASSWORD}"]}}
IDENTITY_EOF

    log_info "Creating systemd-homed identity (non-interactive)..."
    local homectl_out
    if ! homectl_out=$(homectl "${homectl_args[@]}" --identity="$identity_json" 2>&1); then
        rm -f "$identity_json"
        log_error "homectl create failed: ${homectl_out}"
        rollback "after_backup"
    fi
    rm -f "$identity_json"

    # Step 4: Activate the home via D-Bus (bypasses TTY password prompt)
    log_info "Activating home for '${HOMED_USERNAME}' (via D-Bus)..."
    if ! busctl call org.freedesktop.home1 /org/freedesktop/home1 \
        org.freedesktop.home1.Manager ActivateHome ss "$HOMED_USERNAME" "$HOMED_PASSWORD" 2>/dev/null; then
        log_warn "D-Bus activation failed, trying homectl activate with pipe..."
        # Fallback: pipe password to homectl (may work if stdin is read)
        if ! printf '%s\n' "$HOMED_PASSWORD" | homectl activate "$HOMED_USERNAME" 2>/dev/null; then
            log_error "homectl activate failed."
            rollback "after_homed_create"
        fi
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

    # Step 7b: Update NSS so SSH can resolve the homed user
    update_nsswitch

    # Step 8: Clean up backup
    log_info "Removing backup directory..."
    rm -rf "${HOME_BACKUP}"

    # Step 9: Write completion marker
    mkdir -p /etc/ouroboros
    touch "$MIGRATION_MARKER"

    # Step 10: Remove password from migration conf (security cleanup)
    if [[ -f /etc/ouroboros/homed-migration.conf ]]; then
        sed -i '/^HOMED_PASSWORD=/d' /etc/ouroboros/homed-migration.conf
    fi

    # Step 11: Remove the pending flag and disable this service
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
