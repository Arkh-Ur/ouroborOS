#!/usr/bin/env bash
set -euo pipefail
# configure.sh — ouroborOS post-install chroot configuration
#
# Called by the installer after pacstrap completes.
# Runs inside the installer environment (NOT chrooted) and uses
# arch-chroot to execute operations inside the new system.
#
# Required environment variables:
#   INSTALL_TARGET        — mount point (e.g. /mnt)
#   LOCALE                — e.g. en_US.UTF-8
#   KEYMAP                — e.g. us
#   TIMEZONE              — e.g. America/New_York
#   HOSTNAME              — e.g. ouroboros
#   USERNAME              — primary user account name
#   USER_PASSWORD_HASH    — SHA-512 crypt hash
#   USER_GROUPS           — comma-separated groups (e.g. wheel,audio,video)
#   USER_SHELL            — e.g. /bin/bash
#   ENABLE_IWD            — "1" to enable iwd, "0" to skip
#   ENABLE_LUKS           — "1" if LUKS was used (add rd.luks.uuid to boot entry)
#
set -euo pipefail

# --- Validation -------------------------------------------------------------

: "${INSTALL_TARGET:?'INSTALL_TARGET must be set'}"
: "${LOCALE:?'LOCALE must be set'}"
: "${KEYMAP:?'KEYMAP must be set'}"
: "${TIMEZONE:?'TIMEZONE must be set'}"
: "${HOSTNAME:?'HOSTNAME must be set'}"
: "${USERNAME:?'USERNAME must be set'}"
: "${USER_PASSWORD_HASH:?'USER_PASSWORD_HASH must be set'}"
: "${USER_GROUPS:='wheel,audio,video,input'}"
: "${USER_SHELL:='/bin/bash'}"
: "${ENABLE_IWD:='1'}"
: "${ENABLE_LUKS:='0'}"
: "${ROOT_DEVICE:=''}"

TARGET="$INSTALL_TARGET"

# Discover the btrfs root device for temp-mount operations on subvolumes.
# Must be called AFTER disk.sh has partitioned and formatted (FORMAT state).
_ROOT_DEVICE=""
_discover_root_device() {
    if [[ -n "$_ROOT_DEVICE" ]]; then
        return 0
    fi
    if [[ -n "${ROOT_DEVICE}" ]]; then
        _ROOT_DEVICE="${ROOT_DEVICE}"
        return 0
    fi
    local src
    src=$(findmnt -n -o SOURCE --target "${TARGET}" 2>/dev/null || true)
    _ROOT_DEVICE="${src%%\[*}"
    if [[ -n "$_ROOT_DEVICE" ]]; then
        return 0
    fi
    log_error "Cannot discover root device for temp-mount operations"
    return 1
}

# write_to_root_subvolume CALLBACK [ARG...]
#
# Temp-mount the @ (root) subvolume, call CALLBACK(tmp_mount_dir [ARG...]),
# then unmount.  Used to write files that must exist on the @ subvolume
# because systemd reads them BEFORE the @etc overlay is mounted on boot.
#
# Cleanup is guaranteed via a trap — even on error the temp mount is released.
write_to_root_subvolume() {
    local callback="$1"; shift
    _discover_root_device

    local tmp_root
    tmp_root=$(mktemp -d)

    mount -t btrfs -o "subvol=@,compress=zstd,noatime,rw" "$_ROOT_DEVICE" "$tmp_root" || {
        log_warn "Could not temp-mount @ subvolume on ${tmp_root}"
        rmdir "$tmp_root" 2>/dev/null || true
        return 1
    }

    # Run callback — cleanup inline to avoid RETURN trap leaking into caller
    "$callback" "$tmp_root" "$@"
    local rc=$?

    umount "$tmp_root" 2>/dev/null || true
    rmdir "$tmp_root" 2>/dev/null || true
    return "$rc"
}

# --- Logging ----------------------------------------------------------------

log_info()  { printf '\033[0;34m[configure]\033[0m %s\n' "$*" >&2; }
log_ok()    { printf '\033[0;32m[configure]\033[0m %s\n' "$*" >&2; }
log_warn()  { printf '\033[0;33m[configure]\033[0m %s\n' "$*" >&2; }
log_error() { printf '\033[0;31m[configure]\033[0m %s\n' "$*" >&2; }

# Wrapper: run a command inside the chroot
in_chroot() {
    arch-chroot "$TARGET" "$@"
}

# --- Step 1: Locale ---------------------------------------------------------

configure_locale() {
    log_info "Configuring locale: ${LOCALE}"

    # Uncomment the selected locale in locale.gen
    sed -i "s/^#\(${LOCALE}\)/\1/" "${TARGET}/etc/locale.gen"

    in_chroot locale-gen

    echo "LANG=${LOCALE}" > "${TARGET}/etc/locale.conf"
    echo "KEYMAP=${KEYMAP}" > "${TARGET}/etc/vconsole.conf"

    log_ok "Locale configured."
}

# --- Step 2: Timezone -------------------------------------------------------

configure_timezone() {
    log_info "Setting timezone: ${TIMEZONE}"

    in_chroot ln -sf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
    in_chroot hwclock --systohc

    log_ok "Timezone set."
}

# --- Step 3: Hostname -------------------------------------------------------

configure_hostname() {
    log_info "Setting hostname: ${HOSTNAME}"

    echo "$HOSTNAME" > "${TARGET}/etc/hostname"

    cat > "${TARGET}/etc/hosts" << EOF
127.0.0.1   localhost
::1         localhost
127.0.1.1   ${HOSTNAME}.localdomain ${HOSTNAME}
EOF

    log_ok "Hostname configured."
}

# --- Step 4: mkinitcpio -----------------------------------------------------

configure_initramfs() {
    log_info "Generating initramfs..."

    cat > "${TARGET}/etc/mkinitcpio.conf" << 'EOF'
MODULES=(btrfs)
BINARIES=()
FILES=()
HOOKS=(base udev microcode modconf kms keyboard keymap consolefont block btrfs filesystems fsck)
EOF

    in_chroot mkinitcpio -P

    log_ok "Initramfs generated."
}

# --- Step 5: systemd-boot ---------------------------------------------------

configure_bootloader() {
    log_info "Installing systemd-boot..."

    in_chroot bootctl install --path=/boot --no-variables 2>/dev/null || {
        log_error "bootctl install failed"
        return 1
    }

    # Verify EFI binary and loader were written correctly.
    # bootctl status cannot access NVRAM from chroot, so we check files directly.
    if [[ ! -f "${TARGET}/boot/EFI/systemd/systemd-bootx64.efi" ]]; then
        log_error "bootctl install failed: EFI binary missing at boot/EFI/systemd/systemd-bootx64.efi"
        return 1
    fi
    if [[ ! -f "${TARGET}/boot/loader/loader.conf" ]]; then
        log_error "bootctl install failed: loader.conf missing at boot/loader/loader.conf"
        return 1
    fi
    log_ok "bootctl: EFI binary and loader.conf verified."

    # Register boot entry in UEFI NVRAM from the host side.
    # bootctl inside chroot cannot access real NVRAM, so we use
    # efibootmgr from the live ISO host targeting the installed ESP.
    local esp_part=""
    esp_part=$(lsblk -ln -o NAME,FSTYPE,MOUNTPOINT | grep "${TARGET}/boot" | grep vfat | awk '{print $1}' | head -1) || true
    if [[ -n "$esp_part" ]]; then
        local esp_disk="/dev/$(lsblk -dno PKNAME "/dev/${esp_part}" 2>/dev/null)" || true
        local esp_partnum=""
        esp_partnum=$(cat "/sys/block/${esp_disk#/dev/}/$(basename "/dev/${esp_part}")/partition" 2>/dev/null) || true
        if [[ -n "$esp_disk" && -n "$esp_partnum" ]]; then
            efibootmgr -c -d "$esp_disk" -p "$esp_partnum" \
                -L "ouroborOS" \
                -l "\\EFI\\systemd\\systemd-bootx64.efi" 2>/dev/null || true
            log_ok "UEFI boot entry registered via efibootmgr."
        fi
    fi

    local ucode_initrd_lines=""
    for ucode in intel-ucode.img amd-ucode.img; do
        if [[ -f "${TARGET}/boot/${ucode}" ]]; then
            ucode_initrd_lines+="initrd  /${ucode}
"
        fi
    done

    local root_dev="${ROOT_DEVICE}"
    if [[ -z "$root_dev" ]]; then
        local root_source
        root_source=$(findmnt -n -o SOURCE --target "${TARGET}" 2>/dev/null || true)
        root_dev="${root_source%%\[*}"
    fi
    if [[ -z "$root_dev" ]]; then
        log_error "Cannot determine root device for ${TARGET} (ROOT_DEVICE empty, findmnt failed)"
        return 1
    fi

    local root_uuid
    root_uuid=$(blkid -s UUID -o value "$root_dev" 2>/dev/null || true)
    if [[ -z "$root_uuid" ]]; then
        log_error "Cannot determine UUID for root device ${root_dev}"
        return 1
    fi

    local kernel_params="root=UUID=${root_uuid} rootflags=subvol=@ ro quiet loglevel=3 console=tty0 console=ttyS0,115200"

    if [[ "$ENABLE_LUKS" == "1" ]]; then
        local luks_uuid=""
        if [[ -f "${TARGET}/etc/crypttab" ]]; then
            luks_uuid=$(awk '{print $2}' "${TARGET}/etc/crypttab" | sed 's/UUID=//')
            kernel_params="rd.luks.uuid=${luks_uuid} ${kernel_params}"
        fi
    fi

    mkdir -p "${TARGET}/boot/loader/entries"

    cat > "${TARGET}/boot/loader/entries/ouroborOS.conf" << EOF
title   ouroborOS
linux   /vmlinuz-linux-zen
${ucode_initrd_lines}initrd  /initramfs-linux-zen.img
options ${kernel_params}
EOF

    cat > "${TARGET}/boot/loader/entries/ouroborOS-fallback.conf" << EOF
title   ouroborOS (fallback initramfs)
linux   /vmlinuz-linux-zen
${ucode_initrd_lines}initrd  /initramfs-linux-zen-fallback.img
options ${kernel_params}
EOF

    cat > "${TARGET}/boot/loader/loader.conf" << 'EOF'
default  ouroborOS.conf
timeout  3
console-mode auto
editor   no
EOF

    log_ok "Bootloader installed."
}

# --- Step 6: Network (systemd-networkd + iwd + resolved) --------------------

configure_network() {
    log_info "Configuring network..."

    mkdir -p "${TARGET}/etc/systemd/network"

    cat > "${TARGET}/etc/systemd/network/20-wired.network" << 'EOF'
[Match]
Name=en*
Name=eth*

[Network]
DHCP=yes
DNS=1.1.1.1
DNS=9.9.9.9

[DHCP]
RouteMetric=10
UseDNS=true
EOF

    cat > "${TARGET}/etc/systemd/network/25-wireless.network" << 'EOF'
[Match]
Name=wl*

[Network]
DHCP=yes
DNS=1.1.1.1
DNS=9.9.9.9
IgnoreCarrierLoss=3s

[DHCP]
RouteMetric=20
UseDNS=true
EOF

    # systemd-resolved: stub resolver symlink + DoT/DNSSEC config
    ln -sfn /run/systemd/resolve/stub-resolv.conf "${TARGET}/etc/resolv.conf"

    mkdir -p "${TARGET}/etc/systemd"
    cat > "${TARGET}/etc/systemd/resolved.conf" << 'EOF'
[Resolve]
DNS=1.1.1.1 9.9.9.9
FallbackDNS=8.8.8.8
DNSOverTLS=opportunistic
DNSSEC=allow-downgrade
EOF

    # Enable networking units
    in_chroot systemctl enable systemd-networkd.service
    # wait-online blocks network-online.target until DHCP assigns an IP.
    # Without this, network-online.target is reached instantly (no one satisfies it)
    # and sshd starts before the interface has an address.
    in_chroot systemctl enable systemd-networkd-wait-online.service
    in_chroot systemctl enable systemd-resolved.service
    in_chroot systemctl enable systemd-timesyncd.service

    if [[ "$ENABLE_IWD" == "1" ]]; then
        mkdir -p "${TARGET}/etc/iwd"
        cat > "${TARGET}/etc/iwd/main.conf" << 'EOF'
[General]
EnableNetworkConfiguration=false

[Network]
EnableIPv6=true
RoutePriorityOffset=300
EOF
        in_chroot systemctl enable iwd.service
    fi

    log_ok "Network configured."
}

# --- Step 7: zram swap ------------------------------------------------------

configure_zram() {
    log_info "Configuring zram swap..."

    mkdir -p "${TARGET}/etc/systemd"
    cat > "${TARGET}/etc/systemd/zram-generator.conf" << 'EOF'
# zram-generator.conf — ouroborOS
# Creates a single zram device sized at half the available RAM
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
EOF

    in_chroot systemctl enable systemd-zram-setup@zram0.service 2>/dev/null || true
    log_ok "zram configured."
}

# --- Step 8: User account ---------------------------------------------------

configure_users() {
    log_info "Creating user account: ${USERNAME}"

    # Create user
    in_chroot useradd \
        --create-home \
        --shell "$USER_SHELL" \
        --groups "$USER_GROUPS" \
        "$USERNAME"

    # Set hashed password directly in /etc/shadow
    in_chroot chpasswd --encrypted <<< "${USERNAME}:${USER_PASSWORD_HASH}"

    # Configure sudo: wheel group members can sudo
    cat > "${TARGET}/etc/sudoers.d/10-wheel" << 'EOF'
# ouroborOS: members of the 'wheel' group may use sudo
%wheel ALL=(ALL:ALL) ALL
EOF
    chmod 0440 "${TARGET}/etc/sudoers.d/10-wheel"

    # Lock root account (access via sudo only)
    in_chroot passwd --lock root

    log_ok "User '${USERNAME}' created."
}

# --- Step 9: Read-only root compatibility -----------------------------------

configure_immutable_root() {
    log_info "Configuring immutable root compatibility..."

    # tmpfiles.d: create /usr/local → /var/usrlocal symlink
    mkdir -p "${TARGET}/etc/tmpfiles.d"
    cat > "${TARGET}/etc/tmpfiles.d/ouroboros-ro-root.conf" << 'EOF'
# ouroborOS: redirect /usr/local writes to /var
L  /usr/local  -  -  -  -  /var/usrlocal
d  /var/usrlocal       0755  root root  -  -
d  /var/usrlocal/bin   0755  root root  -  -
d  /var/usrlocal/lib   0755  root root  -  -
d  /var/usrlocal/share 0755  root root  -  -
EOF

    # pacman hooks: snapshot + remount rw before upgrade, remount ro after
    # Two hooks are required because pacman writes to @(root RO) during upgrade.
    # Pre: create snapshot, then remount / as rw so pacman can write.
    # Post: remount / back to ro to restore the immutable guarantee.
    mkdir -p "${TARGET}/etc/pacman.d/hooks"

    cat > "${TARGET}/etc/pacman.d/hooks/00-pre-upgrade.hook" << 'EOF'
[Trigger]
Operation = Upgrade
Operation = Install
Operation = Remove
Type = Package
Target = *

[Action]
Description = Snapshot + remount rw before package changes...
When = PreTransaction
Exec = /usr/local/bin/ouroboros-pre-upgrade
EOF

    # Keep systemd-boot EFI binary in sync when systemd itself is upgraded.
    cat > "${TARGET}/etc/pacman.d/hooks/50-bootctl-update.hook" << 'EOF'
[Trigger]
Operation = Upgrade
Type = Package
Target = systemd

[Action]
Description = Updating systemd-boot after systemd upgrade...
When = PostTransaction
Exec = /usr/bin/bootctl update --graceful
EOF

    cat > "${TARGET}/etc/pacman.d/hooks/99-post-upgrade.hook" << 'EOF'
[Trigger]
Operation = Upgrade
Operation = Install
Operation = Remove
Type = Package
Target = *

[Action]
Description = Remount root read-only after package changes...
When = PostTransaction
Exec = /usr/local/bin/ouroboros-post-upgrade
EOF

    # Install hook scripts
    mkdir -p "${TARGET}/usr/local/bin"

    cat > "${TARGET}/usr/local/bin/ouroboros-pre-upgrade" << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
source /usr/local/lib/ouroboros/snapshot.sh
pre_upgrade_snapshot
mount -o remount,rw /
SCRIPT
    chmod 0755 "${TARGET}/usr/local/bin/ouroboros-pre-upgrade"

    cat > "${TARGET}/usr/local/bin/ouroboros-post-upgrade" << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
mount -o remount,ro /
SCRIPT
    chmod 0755 "${TARGET}/usr/local/bin/ouroboros-post-upgrade"

    # Install snapshot library to installed system
    mkdir -p "${TARGET}/usr/local/lib/ouroboros"
    cp "$(dirname "$0")/snapshot.sh" "${TARGET}/usr/local/lib/ouroboros/snapshot.sh"

    log_ok "Immutable root compatibility configured."
}

# --- Step 10: os-release ----------------------------------------------------

configure_os_release() {
    log_info "Writing os-release..."

    cat > "${TARGET}/etc/os-release" << 'EOF'
NAME="ouroborOS"
PRETTY_NAME="ouroborOS 0.1.0"
ID=ouroboros
ID_LIKE=arch
BUILD_ID=rolling
ANSI_COLOR="38;2;23;147;209"
HOME_URL="https://github.com/Arkhur-Vo/ouroborOS"
SUPPORT_URL="https://github.com/Arkhur-Vo/ouroborOS/issues"
BUG_REPORT_URL="https://github.com/Arkhur-Vo/ouroborOS/issues"
VERSION_ID="0.1.0"
EOF
    log_ok "os-release written."
}

# --- Main -------------------------------------------------------------------

main() {
    log_info "Starting post-install configuration for ${TARGET}"

    configure_locale
    configure_timezone
    configure_hostname
    configure_initramfs
    configure_bootloader
    configure_network
    configure_zram
    configure_users
    configure_immutable_root
    configure_os_release

    # --- Fixes that need to land on BOTH @etc (overlay) and @ (root subvolume) ---
    # systemd loads unit files from @ BEFORE @etc mounts over /etc.
    # journald starts before @var mounts over /var.
    # So certain files must exist directly on the @ subvolume.

    in_chroot systemctl enable getty@tty1.service
    in_chroot systemctl enable sshd.service

    # Drop-in: sshd must wait until DHCP assigns an IP before accepting connections.
    # Default sshd.service has After=network.target (interface up, no IP yet).
    # With this drop-in sshd waits for network-online.target, which is satisfied by
    # systemd-networkd-wait-online (enabled above) only after DHCP completes.
    # Wants= (not Requires=) so sshd still starts even if wait-online times out.
    mkdir -p "${TARGET}/etc/systemd/system/sshd.service.d"
    cat > "${TARGET}/etc/systemd/system/sshd.service.d/network-online.conf" << 'EOF'
[Unit]
After=network-online.target
Wants=network-online.target
EOF
    log_ok "sshd.service drop-in: waits for network-online.target."

    # Pre-generate SSH host keys during install so sshd can start immediately
    # on first boot without waiting for entropy. Without this, sshd resets
    # connections during key generation (kex_exchange_identification error).
    in_chroot ssh-keygen -A 2>/dev/null || true
    log_ok "SSH host keys pre-generated."

    # /var/log/journal — on @var (rw overlay) with correct ownership
    mkdir -p "${TARGET}/var/log/journal"
    chown root:systemd-journal "${TARGET}/var/log/journal"
    chmod 2755 "${TARGET}/var/log/journal"

    in_chroot systemd-machine-id-setup
    in_chroot systemctl mask systemd-firstboot.service

    # --- Write critical files to @ subvolume (pre-overlay) ---

    _write_journal_placeholder() {
        local mnt="$1"
        mkdir -p "${mnt}/var/log/journal"
        chown root:systemd-journal "${mnt}/var/log/journal"
        chmod 2755 "${mnt}/var/log/journal"
        log_ok "Journal placeholder written to @ subvolume."
    }
    write_to_root_subvolume _write_journal_placeholder || true

    _write_firstboot_mask() {
        local mnt="$1"
        mkdir -p "${mnt}/etc/systemd/system"
        ln -sf /dev/null "${mnt}/etc/systemd/system/systemd-firstboot.service"
        log_ok "firstboot mask written to @ subvolume."
    }
    write_to_root_subvolume _write_firstboot_mask || true

    _write_hostname_to_root() {
        local mnt="$1"
        mkdir -p "${mnt}/etc"
        echo "${HOSTNAME}" > "${mnt}/etc/hostname"
        log_ok "Hostname written to @ subvolume."
    }
    write_to_root_subvolume _write_hostname_to_root || true

    # Critical /etc files must exist on @ (root subvolume) because systemd reads
    # them before @etc is overlaid on /etc. If missing and /etc is already RO,
    # systemd cannot resolve groups/users → journal socket and other early units fail.
    # Files needed: machine-id, passwd, group, shadow, gshadow.
    _write_etc_to_root() {
        local mnt="$1"
        mkdir -p "${mnt}/etc"
        for f in machine-id passwd group shadow gshadow; do
            if [[ -f "${TARGET}/etc/${f}" ]]; then
                cp "${TARGET}/etc/${f}" "${mnt}/etc/${f}"
            fi
        done
        log_ok "Critical /etc files written to @ subvolume (machine-id, passwd, group, shadow, gshadow)."
    }
    write_to_root_subvolume _write_etc_to_root || true

    log_ok "All configuration steps complete."
}

main "$@"
