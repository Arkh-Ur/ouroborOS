#!/usr/bin/env bash
set -euo pipefail
# disk.sh — ouroborOS disk operations library
#
# Provides functions for partitioning, formatting, mounting, and generating
# fstab for an ouroborOS installation. All operations target Btrfs with
# an immutable root subvolume layout.
#
# Usage: source this file and call individual functions.
# All functions require root privileges.
#
# Subvolume layout:
#   @          → /        (mounted ro in installed system)
#   @var       → /var
#   @etc       → /etc
#   @home      → /home
#   @snapshots → /.snapshots
#
# Partition layout (GPT):
#   1: ESP  — 512 MiB  — FAT32
#   2: root — remaining — Btrfs
#
set -euo pipefail

# --- Logging helpers --------------------------------------------------------

_log_info()  { printf '\033[0;34m[disk]\033[0m %s\n' "$*" >&2; }
_log_ok()    { printf '\033[0;32m[disk]\033[0m %s\n' "$*" >&2; }
_log_warn()  { printf '\033[0;33m[disk]\033[0m %s\n' "$*" >&2; }
_log_error() { printf '\033[0;31m[disk]\033[0m %s\n' "$*" >&2; }

# --- Preflight checks -------------------------------------------------------

# check_root — abort if not running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        _log_error "Disk operations require root privileges."
        return 1
    fi
}

# check_tools — verify required tools are present
check_tools() {
    local tools=(sgdisk mkfs.fat mkfs.btrfs mount umount genfstab btrfs blkid)
    local missing=()
    for t in "${tools[@]}"; do
        if ! command -v "$t" &>/dev/null; then
            missing+=("$t")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        _log_error "Missing required tools: ${missing[*]}"
        return 1
    fi
}

# assert_block_device DEVICE — abort if DEVICE is not a block device
assert_block_device() {
    local device="$1"
    if [[ ! -b "$device" ]]; then
        _log_error "'${device}' is not a block device."
        return 1
    fi
}

# assert_root_device DEVICE — allow block devices or dm-crypt mapper devices
assert_root_device() {
    local device="$1"
    # Allow physical block devices (/dev/sda, /dev/vda2, /dev/nvme0n1p2)
    if [[ -b "$device" ]]; then
        return 0
    fi
    # Allow dm-crypt mapper devices (/dev/mapper/ouroboros-root)
    if [[ "$device" =~ ^/dev/mapper/ ]]; then
        # Verify device exists in dmsetup
        if dmsetup ls "$device" >/dev/null 2>&1; then
            return 0
        fi
        _log_error "dm-crypt device '${device}' not found in dmsetup."
        return 1
    fi
    _log_error "'${device}' is not a valid root device (block device or dm-crypt mapper)."
    return 1
}

# --- Partitioning -----------------------------------------------------------

# partition_auto DISK — wipe and partition DISK with GPT
#   Partition 1: 512 MiB ESP (EF00)
#   Partition 2: remaining root (8300)
#
# Args:
#   DISK — block device path (e.g. /dev/sda or /dev/nvme0n1)
partition_auto() {
    local disk="$1"
    check_root
    assert_block_device "$disk"

    _log_info "Partitioning ${disk} (GPT: 512M ESP + remaining root)..."

    # Zap all existing partition data
    sgdisk --zap-all "$disk"

    # Create ESP (512 MiB, type EF00)
    sgdisk \
        --new=1:0:+512M \
        --typecode=1:EF00 \
        --change-name=1:"ESP" \
        "$disk"

    # Create root partition (remaining space, type 8300)
    sgdisk \
        --new=2:0:0 \
        --typecode=2:8300 \
        --change-name=2:"ouroborOS-root" \
        "$disk"

    # Inform kernel of partition table changes
    partprobe "$disk" 2>/dev/null || true
    sleep 1

    _log_ok "Partitioning complete."
}

# --- Device name helpers ----------------------------------------------------

# _esp_device DISK — print the ESP partition device path
_esp_device() {
    local disk="$1"
    # Handle NVMe (nvme0n1 → nvme0n1p1) vs SATA/virtio (sda → sda1)
    if [[ "$disk" =~ nvme|mmcblk ]]; then
        echo "${disk}p1"
    else
        echo "${disk}1"
    fi
}

# _root_device DISK — print the root partition device path
_root_device() {
    local disk="$1"
    if [[ "$disk" =~ nvme|mmcblk ]]; then
        echo "${disk}p2"
    else
        echo "${disk}2"
    fi
}

# --- Formatting -------------------------------------------------------------

# format_esp DEVICE — format partition as FAT32 ESP
#
# Args:
#   DEVICE — ESP partition device (e.g. /dev/sda1)
format_esp() {
    local device="$1"
    check_root
    assert_block_device "$device"

    _log_info "Formatting ${device} as FAT32 (ESP)..."
    mkfs.fat -F32 -n "ESP" "$device"
    _log_ok "ESP formatted."
}

# format_btrfs DEVICE LABEL — format partition as Btrfs
#
# Args:
#   DEVICE — root partition device (e.g. /dev/sda2)
#   LABEL  — filesystem label (default: ouroborOS)
format_btrfs() {
    local device="$1"
    local label="${2:-ouroborOS}"
    check_root
    assert_block_device "$device"

    _log_info "Formatting ${device} as Btrfs (label: ${label})..."
    mkfs.btrfs --force --label "$label" "$device"
    _log_ok "Btrfs formatted."
}

# --- Subvolume creation -----------------------------------------------------

# create_subvolumes DEVICE — create the ouroborOS Btrfs subvolume layout
#
# Temporarily mounts the filesystem, creates subvolumes, then unmounts.
#
# Subvolumes created:
#   @          (root — will be mounted ro)
#   @var
#   @etc
#   @home
#   @snapshots
#
# Args:
#   DEVICE — formatted Btrfs device
create_subvolumes() {
    local device="$1"
    local tmp_mount
    tmp_mount=$(mktemp -d)

    check_root
    assert_block_device "$device"

    _log_info "Creating Btrfs subvolumes on ${device}..."

    mount -t btrfs -o compress=zstd "$device" "$tmp_mount"

    local subvols=("@" "@var" "@etc" "@home" "@snapshots")
    for sv in "${subvols[@]}"; do
        btrfs subvolume create "${tmp_mount}/${sv}"
        _log_info "  Created subvolume: ${sv}"
    done

    umount "$tmp_mount"
    rmdir "$tmp_mount"

    _log_ok "Subvolumes created."
}

# --- Mounting ---------------------------------------------------------------

# mount_subvolumes DEVICE TARGET — mount all subvolumes under TARGET
#
# Mount options:
#   @          → TARGET/        rw initially (installer writes files), then
#                               fstab is written with ro — root is ro at boot
#   @var       → TARGET/var     rw,compress=zstd,noatime
#   @etc       → TARGET/etc     rw,compress=zstd,noatime
#   @home      → TARGET/home    rw,compress=zstd,noatime
#   @snapshots → TARGET/.snapshots rw,compress=zstd,noatime
#
# Args:
#   DEVICE — Btrfs root partition
#   TARGET — mount point (e.g. /mnt)
mount_subvolumes() {
    local device="$1"
    local target="$2"
    local btrfs_opts="compress=zstd,noatime"

    check_root
    assert_block_device "$device"

    _log_info "Mounting subvolumes to ${target}..."

    # Root — rw during install; fstab will set ro at boot
    mount -t btrfs -o "subvol=@,${btrfs_opts},rw" "$device" "$target"

    mkdir -p "${target}/var" "${target}/etc" "${target}/home" "${target}/.snapshots"

    mount -t btrfs -o "subvol=@var,${btrfs_opts}" "$device" "${target}/var"
    mount -t btrfs -o "subvol=@etc,${btrfs_opts}" "$device" "${target}/etc"
    mount -t btrfs -o "subvol=@home,${btrfs_opts}" "$device" "${target}/home"
    mount -t btrfs -o "subvol=@snapshots,${btrfs_opts}" "$device" "${target}/.snapshots"

    _log_ok "Subvolumes mounted."
}

# mount_esp DEVICE TARGET — mount the ESP partition
#
# Args:
#   DEVICE — ESP partition device
#   TARGET — mount point prefix (ESP mounted at TARGET/boot)
mount_esp() {
    local device="$1"
    local target="$2"

    check_root
    assert_block_device "$device"

    mkdir -p "${target}/boot"
    mount "$device" "${target}/boot"
    _log_ok "ESP mounted at ${target}/boot."
}

# --- Unmounting -------------------------------------------------------------

# unmount_all TARGET — safely unmount all ouroborOS subvolumes (reverse order)
#
# Args:
#   TARGET — mount point root (e.g. /mnt)
unmount_all() {
    local target="$1"

    check_root
    _log_info "Unmounting all subvolumes from ${target}..."

    # Reverse order to handle nested mounts
    local -a mounts=(
        "${target}/boot"
        "${target}/.snapshots"
        "${target}/home"
        "${target}/etc"
        "${target}/var"
        "${target}"
    )

    for mp in "${mounts[@]}"; do
        if mountpoint -q "$mp" 2>/dev/null; then
            umount "$mp"
            _log_info "  Unmounted: ${mp}"
        fi
    done

    _log_ok "All subvolumes unmounted."
}

# --- fstab generation -------------------------------------------------------

# generate_fstab TARGET — generate fstab for mounted subvolumes
#
# Writes /etc/fstab using UUID references (never /dev/sdX).
# Root subvolume gets the 'ro' mount option.
#
# Args:
#   TARGET — currently-mounted install target (e.g. /mnt)
generate_fstab() {
    local target="$1"
    local root_device="$2"

    check_root
    assert_root_device "$root_device"

    mkdir -p "${target}/etc"
    genfstab -U "$target" > "${target}/etc/fstab"

    validate_fstab "${target}/etc/fstab"

    sed -i '/[sS]ubvol[sS]*=\/@[^a-z]\|[sS]ubvol[sS]*=@[^a-z]/s/\brw\b/ro/' "${target}/etc/fstab"

    _log_ok "fstab generated: ${target}/etc/fstab"
}

# copy_fstab_to_root TARGET ROOT_DEVICE
#
# ${target}/etc is currently @etc mounted over @'s /etc.
# systemd reads /etc/fstab from @ (the root subvol) to mount subvolumes.
# This function mounts @ on a temp dir, copies fstab into it, then unmounts.
# Uses a temp mount to avoid "target is busy" errors from pacstrap.
#
# Args:
#   TARGET       — install mount point (e.g. /mnt)
#   ROOT_DEVICE  — btrfs block device (e.g. /dev/vda2)
copy_fstab_to_root() {
    local target="$1"
    local root_device="$2"
    local fstab="${target}/etc/fstab"

    [[ -f "$fstab" ]] || return 1

    _log_info "Copying fstab into root subvolume (@)..."

    local tmp_root
    tmp_root=$(mktemp -d)

    mount -t btrfs -o "subvol=@,compress=zstd,noatime" "$root_device" "$tmp_root" || {
        _log_warn "Could not mount @ subvolume on $tmp_root"
        rmdir "$tmp_root"
        return 1
    }

    mkdir -p "${tmp_root}/etc"
    cp "$fstab" "${tmp_root}/etc/fstab"

    umount "$tmp_root"
    rmdir "$tmp_root"

    _log_ok "fstab available in both @ and @etc subvolumes."
}

# validate_fstab FSTAB_FILE — check that fstab is valid and has required entries
#
# Exits non-zero if fstab is empty or missing critical entries.
#
# Args:
#   FSTAB_FILE — path to the fstab file
validate_fstab() {
    local fstab="$1"

    if [[ ! -f "$fstab" ]]; then
        _log_error "fstab not found: ${fstab}"
        return 1
    fi

    if [[ ! -s "$fstab" ]]; then
        _log_error "fstab is empty: ${fstab}"
        return 1
    fi

    # Must reference UUIDs, not /dev/sdX
    if grep -qP '^/dev/sd[a-z]' "$fstab"; then
        _log_error "fstab contains hardcoded /dev/sdX paths — use UUIDs."
        return 1
    fi

    _log_ok "fstab validation passed."
}

# --- LUKS encryption --------------------------------------------------------

# encrypt_partition DEVICE PASSPHRASE — LUKS-format a partition and open it
#
# After this call, the decrypted device is available at /dev/mapper/ouroboros-root
#
# Args:
#   DEVICE     — block device to encrypt
#   PASSPHRASE — LUKS passphrase (use a file via stdin for production)
encrypt_partition() {
    local device="$1"
    local passphrase="$2"
    local dm_name="ouroboros-root"

    check_root
    assert_block_device "$device"

    _log_warn "Encrypting ${device} with LUKS2..."

    echo -n "$passphrase" | cryptsetup luksFormat \
        --type luks2 \
        --cipher aes-xts-plain64 \
        --key-size 512 \
        --hash sha512 \
        --pbkdf argon2id \
        --batch-mode \
        "$device" -

    echo -n "$passphrase" | cryptsetup open "$device" "$dm_name" -

    _log_ok "LUKS device opened at /dev/mapper/${dm_name}"
}

# generate_crypttab TARGET DEVICE — write /etc/crypttab for LUKS device
#
# Args:
#   TARGET — install target (e.g. /mnt)
#   DEVICE — LUKS device (e.g. /dev/sda2)
generate_crypttab() {
    local target="$1"
    local device="$2"
    local dm_name="ouroboros-root"
    local uuid

    uuid=$(blkid -s UUID -o value "$device")

    _log_info "Writing crypttab (UUID=${uuid})..."

    mkdir -p "${target}/etc"
    printf '%s UUID=%s none luks,discard\n' "$dm_name" "$uuid" \
        >> "${target}/etc/crypttab"

    _log_ok "crypttab written."
}

# --- Full installation prep -------------------------------------------------

# prepare_disk DISK TARGET [--luks PASSPHRASE] — end-to-end disk preparation
#
# Convenience wrapper: partition → format → subvolumes → mount → fstab
#
# Args:
#   DISK   — target disk (e.g. /dev/sda)
#   TARGET — install mount point (e.g. /mnt)
#   Optional: --luks PASSPHRASE — enable LUKS encryption on root partition
prepare_disk() {
    local disk="$1"
    local target="$2"
    local use_luks=false
    local luks_pass=""
    local root_device

    shift 2
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --luks)
                use_luks=true
                luks_pass="${2:?'--luks requires a passphrase'}"
                shift 2
                ;;
            *)
                _log_error "Unknown option: $1"
                return 1
                ;;
        esac
    done

    check_root
    check_tools
    assert_block_device "$disk"

    local esp_dev root_part
    esp_dev=$(_esp_device "$disk")
    root_part=$(_root_device "$disk")

    # Step 1: Partition
    partition_auto "$disk"

    # Step 2: Format ESP
    format_esp "$esp_dev"

    # Step 3: Format root (with optional LUKS)
    if [[ "$use_luks" == true ]]; then
        encrypt_partition "$root_part" "$luks_pass"
        root_device="/dev/mapper/ouroboros-root"
    else
        root_device="$root_part"
    fi

    format_btrfs "$root_device" "ouroborOS"

    # Step 4: Create subvolumes
    create_subvolumes "$root_device"

    # Step 5: Mount everything
    mount_subvolumes "$root_device" "$target"
    mount_esp "$esp_dev" "$target"

    generate_fstab "$target" "$root_device"

    copy_fstab_to_root "$target" "$root_device"

    if [[ "$use_luks" == true ]]; then
        generate_crypttab "$target" "$root_part"
    fi

    _log_ok "Disk preparation complete. System is ready for pacstrap."
}

# --- CLI dispatcher ---------------------------------------------------------

_cli_usage() {
    echo "Usage: $0 --action ACTION [options]" >&2
    echo "Actions: prepare_disk, regenerate_fstab" >&2
    echo "Options for prepare_disk:" >&2
    echo "  --disk DEVICE   Target disk (e.g. /dev/vda)" >&2
    echo "  --target PATH   Mount point (e.g. /mnt)" >&2
    echo "  --luks PASS     Enable LUKS with passphrase" >&2
    echo "Options for regenerate_fstab:" >&2
    echo "  --target PATH       Mount point (e.g. /mnt)" >&2
    echo "  --root-device DEV   Root block device (e.g. /dev/vda2)" >&2
}

if [[ "${1:-}" == "--action" ]]; then
    shift
    action="${1:?Missing action name}"
    shift

    case "$action" in
        regenerate_fstab)
            target=""
            root_dev=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --target)       target="${2:?--target requires a value}"; shift 2 ;;
                    --root-device)  root_dev="${2:?--root-device requires a value}"; shift 2 ;;
                    *)              _log_error "Unknown option: $1"; _cli_usage; exit 1 ;;
                esac
            done
            if [[ -z "$target" || -z "$root_dev" ]]; then
                _log_error "regenerate_fstab requires --target and --root-device"
                exit 1
            fi
            generate_fstab "$target" "$root_dev"
            copy_fstab_to_root "$target" "$root_dev"
            ;;
        prepare_disk)
            disk=""
            target=""
            luks_pass=""
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --disk)     disk="${2:?--disk requires a value}"; shift 2 ;;
                    --target)   target="${2:?--target requires a value}"; shift 2 ;;
                    --luks)     luks_pass="${2:?--luks requires a value}"; shift 2 ;;
                    *)          _log_error "Unknown option: $1"; _cli_usage; exit 1 ;;
                esac
            done
            if [[ -z "$disk" || -z "$target" ]]; then
                _log_error "prepare_disk requires --disk and --target"
                exit 1
            fi
            if [[ -n "$luks_pass" ]]; then
                prepare_disk "$disk" "$target" --luks "$luks_pass"
            else
                prepare_disk "$disk" "$target"
            fi
            ;;
        *)
            _log_error "Unknown action: $action"
            _cli_usage
            exit 1
            ;;
    esac
fi
