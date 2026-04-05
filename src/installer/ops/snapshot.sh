#!/usr/bin/env bash
set -euo pipefail
# snapshot.sh — ouroborOS Btrfs snapshot management
#
# Provides functions for creating, listing, and pruning Btrfs snapshots.
# Snapshots live in the @snapshots subvolume, mounted at /.snapshots.
#
# Snapshot naming convention:
#   @snapshots/install      — baseline snapshot taken right after installation
#   @snapshots/YYYY-MM-DDTHHMMSS  — periodic/pre-update snapshots
#
# Boot entries for snapshots are written to the ESP under /boot/loader/entries/.
#

# --- Logging helpers --------------------------------------------------------

_log_info()  { printf '\033[0;34m[snapshot]\033[0m %s\n' "$*" >&2; }
_log_ok()    { printf '\033[0;32m[snapshot]\033[0m %s\n' "$*" >&2; }
_log_warn()  { printf '\033[0;33m[snapshot]\033[0m %s\n' "$*" >&2; }
_log_error() { printf '\033[0;31m[snapshot]\033[0m %s\n' "$*" >&2; }

# --- Core snapshot operations -----------------------------------------------

# create_snapshot SOURCE DEST [--readonly] — create a Btrfs subvolume snapshot
#
# Args:
#   SOURCE     — path to existing subvolume (e.g. /mnt/@)
#   DEST       — path for new snapshot (e.g. /mnt/.snapshots/install)
#   --readonly — create a read-only snapshot (default: read-write)
create_snapshot() {
    local source="$1"
    local dest="$2"
    local readonly=false

    shift 2
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --readonly) readonly=true; shift ;;
            *) _log_error "Unknown option: $1"; return 1 ;;
        esac
    done

    if [[ ! -d "$source" ]]; then
        _log_error "Source subvolume not found: ${source}"
        return 1
    fi

    if [[ -d "$dest" ]]; then
        _log_warn "Snapshot destination already exists: ${dest} — skipping."
        return 0
    fi

    _log_info "Creating snapshot: ${source} → ${dest}"

    if [[ "$readonly" == true ]]; then
        btrfs subvolume snapshot -r "$source" "$dest"
    else
        btrfs subvolume snapshot "$source" "$dest"
    fi

    _log_ok "Snapshot created: ${dest}"
}

# delete_snapshot PATH — delete a Btrfs snapshot subvolume
#
# Args:
#   PATH — path to snapshot subvolume
delete_snapshot() {
    local path="$1"

    if [[ ! -d "$path" ]]; then
        _log_warn "Snapshot not found (already deleted?): ${path}"
        return 0
    fi

    _log_info "Deleting snapshot: ${path}"
    btrfs subvolume delete "$path"
    _log_ok "Snapshot deleted: ${path}"
}

# list_snapshots SNAPSHOTS_DIR — list available snapshots
#
# Args:
#   SNAPSHOTS_DIR — path to .snapshots directory (e.g. /.snapshots)
list_snapshots() {
    local snapshots_dir="${1:-/.snapshots}"

    if [[ ! -d "$snapshots_dir" ]]; then
        _log_error "Snapshots directory not found: ${snapshots_dir}"
        return 1
    fi

    _log_info "Available snapshots in ${snapshots_dir}:"
    btrfs subvolume list -o "$snapshots_dir" 2>/dev/null \
        | awk '{print "  " $NF}' \
        | sort \
        || echo "  (none)"
}

# --- Installation snapshot --------------------------------------------------

# create_install_snapshot TARGET — create baseline snapshot after installation
#
# Called by the installer immediately after pacstrap + configure completes.
# Creates a read-only snapshot at TARGET/.snapshots/install
#
# Args:
#   TARGET — installation root (e.g. /mnt)
create_install_snapshot() {
    local target="$1"
    local snapshot_dir="${target}/.snapshots"
    local snapshot_path="${snapshot_dir}/install"

    _log_info "Creating installation baseline snapshot..."

    if [[ ! -d "$snapshot_dir" ]]; then
        _log_error "Snapshots directory not mounted: ${snapshot_dir}"
        _log_error "Ensure @snapshots is mounted before calling this function."
        return 1
    fi

    # The source is the @ subvolume, accessible at TARGET
    create_snapshot "$target" "$snapshot_path" --readonly

    _log_ok "Installation snapshot created at ${snapshot_path}"
}

# --- Boot entry generation --------------------------------------------------

# generate_snapshot_boot_entry SNAPSHOT_NAME ESP_PATH KERNEL_PARAMS
#   — write a systemd-boot entry for a snapshot
#
# Args:
#   SNAPSHOT_NAME  — short name, used in title and filename (e.g. "install")
#   ESP_PATH       — path to mounted ESP (e.g. /mnt/boot)
#   KERNEL_PARAMS  — extra kernel parameters (e.g. rd.luks.uuid=... quiet)
generate_snapshot_boot_entry() {
    local snapshot_name="$1"
    local esp_path="${2:-/boot}"
    local kernel_params="${3:-quiet}"
    local entries_dir="${esp_path}/loader/entries"
    local entry_file="${entries_dir}/ouroboros-snapshot-${snapshot_name}.conf"

    mkdir -p "$entries_dir"

    # Resolve root device and UUID.
    # When called from the installer (live ISO), "/" is an overlayfs with no UUID.
    # Instead, infer the target root from esp_path (e.g. /mnt/boot → /mnt) and
    # look up the device mounted there.  Fall back to "/" for the installed system.
    local root_source root_dev root_uuid
    local target_root
    target_root=$(dirname "$esp_path")  # /mnt/boot → /mnt  |  /boot → /

    root_source=$(findmnt -n -o SOURCE --target "$target_root" 2>/dev/null || true)
    root_dev="${root_source%%\[*}"

    if [[ -n "$root_dev" ]]; then
        root_uuid=$(blkid -s UUID -o value "$root_dev" 2>/dev/null || true)
    fi

    if [[ -z "$root_uuid" ]]; then
        _log_warn "Cannot determine root UUID for snapshot boot entry — skipping entry."
        return 0
    fi

    local ucode_initrd=""
    for ucode in intel-ucode.img amd-ucode.img; do
        if [[ -f "${esp_path}/${ucode}" ]]; then
            ucode_initrd+="initrd  /${ucode}
"
        fi
    done

    _log_info "Writing boot entry for snapshot '${snapshot_name}'..."

    cat > "$entry_file" << EOF
title   ouroborOS snapshot (${snapshot_name})
linux   /vmlinuz-linux-zen
${ucode_initrd}initrd  /initramfs-linux-zen.img
options root=UUID=${root_uuid} rootflags=subvol=@snapshots/${snapshot_name} ${kernel_params} ro
EOF

    _log_ok "Boot entry written: ${entry_file}"
}

# --- Snapshot rotation (pruning) --------------------------------------------

# prune_snapshots SNAPSHOTS_DIR [MAX_COUNT] [MAX_DAYS]
#   — remove old snapshots, keeping at most MAX_COUNT and no older than MAX_DAYS
#
# The 'install' baseline snapshot is NEVER pruned.
#
# Args:
#   SNAPSHOTS_DIR — path to .snapshots directory
#   MAX_COUNT     — maximum number of snapshots to keep (default: 5)
#   MAX_DAYS      — maximum age in days (default: 30)
prune_snapshots() {
    local snapshots_dir="${1:-/.snapshots}"
    local max_count="${2:-5}"
    local max_days="${3:-30}"
    local now
    now=$(date +%s)
    local cutoff=$(( now - max_days * 86400 ))

    _log_info "Pruning snapshots (keep last ${max_count}, max ${max_days} days)..."

    # Collect dated snapshots (ISO 8601 format YYYY-MM-DDTHHMMSS), exclude 'install'
    local -a snapshots=()
    while IFS= read -r -d '' entry; do
        local name
        name=$(basename "$entry")
        [[ "$name" == "install" ]] && continue
        snapshots+=("$entry")
    done < <(find "$snapshots_dir" -maxdepth 1 -mindepth 1 -type d -print0 | sort -z)

    local count=${#snapshots[@]}
    _log_info "Found ${count} pruneable snapshot(s)."

    local pruned=0
    for snap in "${snapshots[@]}"; do
        local name
        name=$(basename "$snap")
        local keep=true

        # Check age: parse YYYY-MM-DDTHHMMSS
        if [[ "$name" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}$ ]]; then
            local snap_date="${name:0:16}"  # YYYY-MM-DDTHH:MM (rearrange for date)
            local formatted_date
            # shellcheck disable=SC2001  # backreference substitution not possible with ${//}
            formatted_date=$(echo "$snap_date" | sed 's/T\(..\)\(..\)\(..\)/T\1:\2:\3/')
            local snap_epoch
            snap_epoch=$(date -d "$formatted_date" +%s 2>/dev/null || echo 0)
            if [[ $snap_epoch -lt $cutoff ]]; then
                keep=false
                _log_info "  Pruning (too old): ${name}"
            fi
        fi

        # Check count: if more than max_count, remove oldest first
        if [[ $((count - pruned)) -gt $max_count ]]; then
            keep=false
            _log_info "  Pruning (count limit): ${name}"
        fi

        if [[ "$keep" == false ]]; then
            delete_snapshot "$snap"
            pruned=$((pruned + 1))
        fi
    done

    _log_ok "Pruning complete. Removed ${pruned} snapshot(s)."
}

# --- Pre-upgrade hook -------------------------------------------------------

# pre_upgrade_snapshot — create a timestamped snapshot before pacman upgrade
#
# Intended to be called from a pacman hook (PreTransaction).
# Snapshot name: YYYY-MM-DDTHHMMSS
pre_upgrade_snapshot() {
    local snapshots_dir="/.snapshots"
    local timestamp
    timestamp=$(date +%Y-%m-%dT%H%M%S)
    local snap_path="${snapshots_dir}/${timestamp}"

    if [[ ! -d "$snapshots_dir" ]]; then
        _log_error "Snapshots directory not found: ${snapshots_dir}"
        _log_error "Is @snapshots mounted at /.snapshots?"
        return 1
    fi

    _log_info "Pre-upgrade snapshot: ${timestamp}"
    create_snapshot "/" "$snap_path" --readonly
    generate_snapshot_boot_entry "$timestamp" "/boot" "quiet ro"

    # Prune old snapshots after creating the new one
    prune_snapshots "$snapshots_dir" 5 30

    _log_ok "Pre-upgrade snapshot complete."
}

# --- CLI dispatcher ---------------------------------------------------------

if [[ "${1:-}" == "--action" ]]; then
    shift
    action="${1:?Missing action name}"
    shift

    case "$action" in
        create_install_snapshot)
            target=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --target) target="${2:?--target requires a value}"; shift 2 ;;
                    *) _log_error "Unknown option: $1"; exit 1 ;;
                esac
            done
            if [[ -z "$target" ]]; then
                _log_error "create_install_snapshot requires --target"
                exit 1
            fi
            create_install_snapshot "$target"
            generate_snapshot_boot_entry "install" "${target}/boot" "quiet ro"
            ;;
        *)
            _log_error "Unknown action: $action"
            exit 1
            ;;
    esac
fi
