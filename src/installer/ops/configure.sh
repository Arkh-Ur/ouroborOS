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
#   USER_PASSWORD         — Plaintext password for systemd-homed migration
#   USER_GROUPS           — comma-separated groups (e.g. wheel,audio,video)
#   USER_SHELL            — e.g. /bin/bash
#   ENABLE_IWD            — "1" to enable iwd, "0" to skip
#   ENABLE_LUKS           — "1" if LUKS was used (add rd.luks.uuid to boot entry)

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
: "${HOMED_STORAGE:='subvolume'}"
: "${ROOT_DEVICE:=''}"
: "${WIFI_SSID:=''}"
: "${WIFI_PASSPHRASE:=''}"
: "${BLUETOOTH_ENABLE:='0'}"
: "${FIDO2_PAM:='0'}"
: "${DESKTOP_AUR_PACKAGES:=''}"
: "${DESKTOP_KDE_FLAVOR:='plasma-meta'}"
: "${GPU_DRIVER:='auto'}"
: "${ENABLE_TPM2:='0'}"
: "${LUKS_PARTITION:=''}"
: "${ENABLE_DUAL_BOOT:='0'}"
: "${SECURE_BOOT:='0'}"
: "${SBCTL_INCLUDE_MS_KEYS:='0'}"

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

    local tmp_root tmp_top _was_ro=0
    tmp_root=$(mktemp -d)
    tmp_top=$(mktemp -d)

    # The pacman PostTransaction hook (99-post-upgrade) runs inside the chroot
    # during GPU/package installs and sets btrfs property ro=true on @.
    # Even with the rw mount option, Btrfs enforces the subvolume ro property
    # at the VFS level — writes fail with EROFS. We must temporarily clear it.
    # Use subvolid=5 (top-level) to manipulate the property on the @ subvolume.
    if mount -t btrfs -o "subvolid=5,compress=zstd,noatime,rw" "$_ROOT_DEVICE" "$tmp_top" 2>/dev/null; then
        if btrfs property get "${tmp_top}/@" ro 2>/dev/null | grep -q "ro=true"; then
            _was_ro=1
            btrfs property set "${tmp_top}/@" ro false 2>/dev/null || true
        fi
        umount "$tmp_top" 2>/dev/null || true
    fi
    rmdir "$tmp_top" 2>/dev/null || true

    # Mount the @ subvolume directly (subvol=/@), not the top-level (subvolid=5).
    # This ensures callbacks write to @/etc/ (correct), not top-level/etc/.
    mount -t btrfs -o "subvol=/@,compress=zstd,noatime,rw" "$_ROOT_DEVICE" "$tmp_root" || {
        log_warn "Could not temp-mount @ subvolume on ${tmp_root}"
        rmdir "$tmp_root" 2>/dev/null || true
        return 1
    }

    # Run callback — cleanup inline to avoid RETURN trap leaking into caller
    "$callback" "$tmp_root" "$@"
    local rc=$?

    umount "$tmp_root" 2>/dev/null || true
    rmdir "$tmp_root" 2>/dev/null || true

    # Restore ro=true if @ was read-only before (pacman hook had already set it)
    if (( _was_ro )); then
        tmp_top=$(mktemp -d)
        if mount -t btrfs -o "subvolid=5,compress=zstd,noatime,rw" "$_ROOT_DEVICE" "$tmp_top" 2>/dev/null; then
            btrfs property set "${tmp_top}/@" ro true 2>/dev/null || true
            umount "$tmp_top" 2>/dev/null || true
        fi
        rmdir "$tmp_top" 2>/dev/null || true
    fi

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

    # Verify both initramfs images exist on the ESP (${TARGET}/boot).
    # The fallback image may fail silently if the ESP is too small (512 MiB
    # can be tight with linux-firmware embedded).  Log clearly so we can
    # diagnose missing-file issues at boot time.
    local -A _expected_images=(
        ["main"]="${TARGET}/boot/initramfs-linux-zen.img"
        ["fallback"]="${TARGET}/boot/initramfs-linux-zen-fallback.img"
    )
    for _name in main fallback; do
        if [[ -f "${_expected_images[$_name]}" ]]; then
            local _size
            _size=$(du -sh "${_expected_images[$_name]}" | cut -f1)
            log_ok "initramfs (${_name}): ${_expected_images[$_name]} (${_size})"
        else
            log_warn "initramfs (${_name}) MISSING: ${_expected_images[$_name]}"
            log_warn "If this is the fallback, the boot entry will fail. Consider increasing ESP size."
        fi
    done
    unset _expected_images _name _size

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
        local esp_disk
        esp_disk="/dev/$(lsblk -dno PKNAME "/dev/${esp_part}" 2>/dev/null)" || true
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

    local kernel_params="root=UUID=${root_uuid} rootflags=subvol=@ ro loglevel=4 console=tty0 console=ttyS0,115200"

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

    if [[ -f "${TARGET}/boot/initramfs-linux-zen-fallback.img" ]]; then
        cat > "${TARGET}/boot/loader/entries/ouroborOS-fallback.conf" << EOF
title   ouroborOS (fallback initramfs)
linux   /vmlinuz-linux-zen
${ucode_initrd_lines}initrd  /initramfs-linux-zen-fallback.img
options ${kernel_params}
EOF
    else
        log_warn "Skipping fallback boot entry — initramfs-linux-zen-fallback.img not found on ESP."
    fi

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
IPv6AcceptRA=no
# wait-online is satisfied as soon as IPv4 DHCP completes.
# Without this, it also waits for IPv6 RA which QEMU SLIRP never sends.
RequiredFamilyForOnline=ipv4

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
    log_ok "systemd-networkd-wait-online enabled."
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

        # Pre-configure WiFi if SSID + passphrase were provided (unattended installs).
        # Format: /var/lib/iwd/<SSID>.psk (chmod 600, dir chmod 700).
        # SSIDs with special characters (spaces, =, etc.) use hex-encoded filenames.
        if [[ -n "${WIFI_SSID:-}" && -n "${WIFI_PASSPHRASE:-}" ]]; then
            local iwd_dir="${TARGET}/var/lib/iwd"
            mkdir -p "$iwd_dir"
            chmod 700 "$iwd_dir"

            # Determine PSK filename.
            # SSID must be hex-encoded if it contains: =, space, or non-ASCII chars.
            local psk_file
            if [[ "$WIFI_SSID" =~ [^[:print:]] || "$WIFI_SSID" =~ [=\ ] ]]; then
                # Hex-encode: iwd format is =<hex_of_ssid>.psk
                local ssid_hex
                ssid_hex=$(printf '%s' "$WIFI_SSID" | od -An -tx1 | tr -d ' \n')
                psk_file="${iwd_dir}/=${ssid_hex}.psk"
            else
                psk_file="${iwd_dir}/${WIFI_SSID}.psk"
            fi

            cat > "$psk_file" << EOF
[Security]
Passphrase=${WIFI_PASSPHRASE}
EOF
            chmod 600 "$psk_file"
            log_ok "WiFi pre-configured for SSID '${WIFI_SSID}' (PSK written, passphrase NOT logged)."

            # Security: clear passphrase from env immediately after writing
            WIFI_PASSPHRASE=""
        fi
    fi

    # Bluetooth: enable bluetooth.service + configure experimental LE for FIDO2.
    # bluez must be installed (not in the default package set — user must add it
    # via extra_packages or our-pac post-install).
    if [[ "${BLUETOOTH_ENABLE:-0}" == "1" ]]; then
        if in_chroot pacman -Qi bluez &>/dev/null 2>&1; then
            in_chroot systemctl enable bluetooth.service
            log_ok "bluetooth.service enabled."

            # Install libfido2 for FIDO2/WebAuthn/passkey support (USB + BLE).
            # libfido2 provides:
            #   - fido2-token, fido2-cred, fido2-assert CLI tools
            #   - /usr/lib/udev/rules.d/70-u2f.rules (USB FIDO2 HID access rules)
            # Required for our-fido2 and for browser WebAuthn with physical keys.
            if in_chroot pacman -Qi libfido2 &>/dev/null 2>&1; then
                log_ok "libfido2 already installed."
            else
                log_info "Installing libfido2 for FIDO2/WebAuthn support..."
                if in_chroot pacman -S --noconfirm libfido2 2>/dev/null; then
                    log_ok "libfido2 installed."
                else
                    log_warn "Could not install libfido2 — FIDO2 management tools unavailable."
                    log_warn "Install after first boot: sudo our-pac -S libfido2"
                fi
            fi

            # Configure BlueZ experimental LE mode.
            # Required for CTAP2 hybrid transport (QR code passkey flow) and for
            # the BLE AdvertisingMonitor API used by Chrome/Firefox on Linux.
            local bt_drop_in_dir="${TARGET}/etc/systemd/system/bluetooth.service.d"
            local bt_drop_in="${bt_drop_in_dir}/experimental.conf"
            if [[ ! -f "$bt_drop_in" ]]; then
                mkdir -p "$bt_drop_in_dir"
                cat > "$bt_drop_in" << 'BT_DROPIN'
# Installed by ouroborOS configure.sh (BLUETOOTH_ENABLE=1)
# Enables BlueZ experimental D-Bus APIs required for:
#   - CTAP2 hybrid transport (QR code passkey flow) via AdvertisingMonitor API
#   - BLE FIDO2 GATT profile improvements
[Service]
ExecStart=
ExecStart=/usr/lib/bluetooth/bluetoothd --experimental
BT_DROPIN
                log_ok "BlueZ experimental mode drop-in written."
            fi

            # Install BlueZ main.conf (experimental LE tuning for FIDO2).
            # The source is the live ISO's own /etc/bluetooth/main.conf,
            # which was placed there by the ouroborOS airootfs profile.
            local bt_conf_dir="${TARGET}/etc/bluetooth"
            if [[ ! -f "${bt_conf_dir}/main.conf" ]]; then
                mkdir -p "$bt_conf_dir"
                if [[ -f /etc/bluetooth/main.conf ]]; then
                    cp /etc/bluetooth/main.conf "${bt_conf_dir}/main.conf"
                    log_ok "/etc/bluetooth/main.conf installed (experimental LE + GATT tuning)."
                else
                    # Fallback: write a minimal config inline
                    cat > "${bt_conf_dir}/main.conf" << 'BT_CONF'
[General]
Experimental = true
KernelExperimental = true
FastConnectable = true

[Policy]
AutoEnable = true

[LE]
MinConnectionInterval = 6
MaxConnectionInterval = 9
ConnectionLatency = 0
ConnectionSupervisionTimeout = 100
AdvMonAllowlistScanDuration = 300
AdvMonNoFilterScanDuration = 10
EnableAdvMonInterleaveScan = 1

[GATT]
Cache = yes
KeySize = 0
ExchangeMTU = 517
Channels = 3
BT_CONF
                    log_ok "/etc/bluetooth/main.conf written (inline fallback)."
                fi
            fi

            # Install BLE FIDO2 udev rules (supplement libfido2 USB rules with BLE HID-over-GATT).
            # Source: live ISO's /etc/udev/rules.d/71-fido2-ble.rules (from airootfs).
            local udev_rules_dir="${TARGET}/etc/udev/rules.d"
            local ble_udev="${udev_rules_dir}/71-fido2-ble.rules"
            if [[ ! -f "$ble_udev" ]]; then
                mkdir -p "$udev_rules_dir"
                if [[ -f /etc/udev/rules.d/71-fido2-ble.rules ]]; then
                    cp /etc/udev/rules.d/71-fido2-ble.rules "$ble_udev"
                    log_ok "BLE FIDO2 udev rules installed (71-fido2-ble.rules)."
                else
                    log_warn "71-fido2-ble.rules not found in live ISO — skipping."
                    log_warn "Install after first boot from: our-fido2 qr-ready"
                fi
            fi

        else
            log_warn "BLUETOOTH_ENABLE=1 but bluez is not installed — skipping."
            log_warn "Install after first boot with: sudo our-pac -S bluez bluez-utils libfido2"
        fi
    fi

    log_ok "Network configured."
}

# --- Step 6b: TPM2 auto-unlock (systemd-cryptenroll) -------------------------

configure_tpm2() {
    # Bind LUKS slot to TPM2 PCR 7+14.
    # PCR 7  = Secure Boot state (firmware + signing authority).
    # PCR 14 = systemd-boot measured boot entries.
    # Falls back to passphrase if TPM2 absent or measurements change.
    #
    # Requires: ENABLE_LUKS=1, LUKS_PARTITION set to raw device (e.g. /dev/vda2).

    [[ "${ENABLE_TPM2:-0}" == "1" ]] || return 0

    if [[ -z "${LUKS_PARTITION:-}" ]]; then
        log_warn "TPM2 unlock requested but LUKS_PARTITION is unset — skipping."
        return 0
    fi

    log_info "Enrolling LUKS partition ${LUKS_PARTITION} with TPM2 (PCR 7+14)..."

    if ! arch-chroot "${TARGET}" \
        systemd-cryptenroll \
            --tpm2-device=auto \
            --tpm2-pcrs=7+14 \
            "${LUKS_PARTITION}" 2>/dev/null; then
        log_warn "systemd-cryptenroll failed — TPM2 may not be available in this environment."
        log_warn "You can enroll manually after reboot:"
        log_warn "  sudo ouroboros-secureboot tpm2-enroll"
        return 0
    fi

    log_ok "TPM2 slot enrolled on ${LUKS_PARTITION} (PCR 7+14)."
    log_ok "The disk will unlock automatically at boot if the boot chain is unmodified."
}

# --- Step 6c: FIDO2 PAM integration ----------------------------------------

configure_fido2_pam() {
    # Install pam-u2f and pre-configure PAM for FIDO2 sudo + login.
    # The user must still register their token post-install:
    #   our-fido2 pam register --system
    #   our-fido2 pam enable sudo login
    #
    # This step only installs pam-u2f and creates the empty authfile so that
    # the PAM module doesn't error if the file is missing.

    [[ "${FIDO2_PAM:-0}" == "1" ]] || return 0

    log_info "Configuring FIDO2 PAM integration (pam-u2f)..."

    # Install pam-u2f (Yubico's PAM module, available in Arch official repos)
    if in_chroot pacman -Qi pam-u2f &>/dev/null 2>&1; then
        log_ok "pam-u2f already installed."
    else
        log_info "Installing pam-u2f..."
        if in_chroot pacman -S --noconfirm pam-u2f 2>/dev/null; then
            log_ok "pam-u2f installed."
        else
            log_warn "Could not install pam-u2f — FIDO2 PAM integration skipped."
            log_warn "Install after first boot: sudo our-pac -S pam-u2f"
            return 0
        fi
    fi

    # Create empty system authfile so pam_u2f doesn't fail before registration
    local authfile="${TARGET}/etc/u2f_mappings"
    if [[ ! -f "$authfile" ]]; then
        touch "$authfile"
        chmod 600 "$authfile"
        log_ok "Created empty FIDO2 authfile: /etc/u2f_mappings"
    fi

    # Note: we do NOT configure /etc/pam.d/* here — that would lock the user
    # out before they register a token. The user runs:
    #   our-fido2 pam register --system
    #   our-fido2 pam enable sudo login
    # after first boot once their token is present.

    log_info "FIDO2 PAM ready. Register your token after first boot:"
    log_info "  sudo our-fido2 pam register --system"
    log_info "  sudo our-fido2 pam enable sudo login"
    log_ok "FIDO2 PAM integration configured."
}

# --- Step 6d: Dual-boot — add Windows boot entry if detected -----------------

configure_dual_boot() {
    [[ "${ENABLE_DUAL_BOOT:-0}" == "1" ]] || return 0

    log_info "Dual-boot: scanning ESP for existing OS boot entries..."

    local esp_loader_dir="${TARGET}/boot/loader/entries"

    # Detect Windows Boot Manager
    local win_efi="${TARGET}/boot/EFI/Microsoft/Boot/bootmgfw.efi"
    if [[ -f "${win_efi}" ]]; then
        log_info "Dual-boot: Windows Boot Manager detected — generating windows.conf"
        mkdir -p "${esp_loader_dir}"
        cat > "${esp_loader_dir}/windows.conf" <<'WINDOWS_EOF'
title   Windows Boot Manager
efi     /EFI/Microsoft/Boot/bootmgfw.efi
WINDOWS_EOF
        log_ok "Dual-boot: windows.conf written to ${esp_loader_dir}."
    else
        log_info "Dual-boot: no Windows Boot Manager found — skipping windows.conf."
    fi

    # Ensure systemd-boot shows the menu long enough to make a selection
    local loader_conf="${TARGET}/boot/loader/loader.conf"
    if [[ -f "${loader_conf}" ]]; then
        # Set timeout to 5s if it's currently 0 or missing
        if grep -q "^timeout" "${loader_conf}"; then
            local current_timeout
            current_timeout=$(grep "^timeout" "${loader_conf}" | awk '{print $2}')
            if [[ "${current_timeout}" == "0" ]]; then
                sed -i 's/^timeout.*/timeout 5/' "${loader_conf}"
                log_ok "Dual-boot: loader.conf timeout updated to 5s."
            fi
        else
            echo "timeout 5" >> "${loader_conf}"
            log_ok "Dual-boot: loader.conf timeout set to 5s."
        fi
    fi

    log_ok "Dual-boot configuration complete."
}

# --- Step 6e: Secure Boot — sbctl key creation and enrollment ----------------

configure_secure_boot() {
    [[ "${SECURE_BOOT:-0}" == "1" ]] || return 0

    log_info "Secure Boot: creating and enrolling keys with sbctl..."

    # sbctl must be installed (added to pacstrap packages by the installer)
    if ! arch-chroot "${TARGET}" command -v sbctl &>/dev/null; then
        log_warn "sbctl not found in chroot — skipping Secure Boot key enrollment."
        log_warn "Install sbctl and run 'sudo ouroboros-secureboot setup' after reboot."
        return 0
    fi

    # Create Secure Boot keys (Platform Key, Key Exchange Key, Signature DB)
    if ! arch-chroot "${TARGET}" sbctl create-keys; then
        log_warn "sbctl create-keys failed — Secure Boot keys not created."
        return 0
    fi
    log_ok "Secure Boot: custom keys created."

    # Enroll keys — include Microsoft OEM keys when dual-boot or MS keys requested
    if [[ "${SBCTL_INCLUDE_MS_KEYS:-0}" == "1" ]]; then
        if arch-chroot "${TARGET}" sbctl enroll-keys --microsoft; then
            log_ok "Secure Boot: keys enrolled (including Microsoft OEM keys)."
        else
            log_warn "sbctl enroll-keys --microsoft failed — Secure Boot not fully configured."
            log_warn "Run 'sudo ouroboros-secureboot setup' after reboot."
        fi
    else
        if arch-chroot "${TARGET}" sbctl enroll-keys; then
            log_ok "Secure Boot: custom-only keys enrolled."
        else
            log_warn "sbctl enroll-keys failed — Secure Boot not fully configured."
            log_warn "Run 'sudo ouroboros-secureboot setup' after reboot."
        fi
    fi

    # Sign the kernel and bootloader binaries
    local esp_boot="${TARGET}/boot"
    local signed=0
    while IFS= read -r -d '' bin; do
        if arch-chroot "${TARGET}" sbctl sign "${bin#"${TARGET}"}"; then
            (( signed++ )) || true
        fi
    done < <(find "${esp_boot}" -name "*.efi" -print0 2>/dev/null)

    if [[ "${signed}" -gt 0 ]]; then
        log_ok "Secure Boot: ${signed} EFI binary(ies) signed."
    else
        log_warn "Secure Boot: no EFI binaries found to sign — check ESP layout."
    fi
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

    # Ensure the chosen shell is registered in /etc/shells inside the target.
    # Some shells (e.g. fish) may not add themselves during pacstrap.
    if ! grep -qx "$USER_SHELL" "${TARGET}/etc/shells" 2>/dev/null; then
        echo "$USER_SHELL" >> "${TARGET}/etc/shells"
        log_info "Registered shell in /etc/shells: ${USER_SHELL}"
    fi

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

    # pacman hooks: only PostTransaction hooks here.
    # PreTransaction remount is NOT done via hook — pacman checks filesystem
    # writability BEFORE running any hook, making PreTransaction remount useless.
    # Instead, our-pac (wrapper) handles unlock + remount + snapshot before
    # invoking the real pacman binary.
    mkdir -p "${TARGET}/etc/pacman.d/hooks"

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

    # Hook named zzz- to guarantee it runs LAST.
    # CRITICAL: pacman hooks are sorted alphabetically and numbers sort BEFORE letters
    # in ASCII ('9'=57 < 'd'=100 < 'z'=122). A hook named 99-* always runs before
    # dconf-update, fontconfig, glib-compile-schemas, gtk-update-icon-cache, and
    # update-desktop-database — all of which write to /usr/share/* on the root @
    # subvolume. If we lock root before those hooks, they fail with EROFS.
    # zzz- ensures we always run after every other hook.
    cat > "${TARGET}/etc/pacman.d/hooks/zzz-post-upgrade.hook" << 'EOF'
[Trigger]
Operation = Upgrade
Operation = Install
Operation = Remove
Type = Package
Target = *

[Action]
Description = Restore root immutability after package changes...
When = PostTransaction
Exec = /usr/local/bin/our-post-upgrade
EOF

    # Install wrapper and helper scripts
    mkdir -p "${TARGET}/usr/local/bin"

    # our-pac — the ONLY safe way to install/upgrade packages on ouroborOS.
    #
    # pacman checks filesystem writability before PreTransaction hooks run, so a hook
    # cannot unlock root in time. This wrapper:
    #   1. Unlocks root via btrfs property set ro=false (Btrfs-level immutability)
    #   2. Remounts / rw at the VFS layer so pacman can write
    #   3. Creates a timestamped Btrfs snapshot (pre-upgrade baseline)
    #   4. Invokes real pacman with all arguments forwarded
    #   5. The 99-post-upgrade hook restores ro via btrfs property set ro=true
    #
    # NOTE: mount-option ro alone is NOT sufficient for Btrfs immutability — when
    # @var/@etc/@home are mounted rw from the same device, the superblock is rw,
    # overriding the ro flag on @. btrfs property set ro=true is the real enforcement.
    #
    # Usage: sudo our-pac -Syu
    #        sudo our-pac -S <pkg>
    #        sudo our-pac -R <pkg>
    cat > "${TARGET}/usr/local/bin/our-pac" << 'SCRIPT'
#!/usr/bin/env bash
# our-pac — the ONLY safe way to install/upgrade packages on ouroborOS.
#
# On the installed system:
#   1. Mounts the Btrfs top-level (subvolid=5) to unlock @ without hitting
#      the VFS ro restriction (circular deadlock prevention).
#   2. Remounts / read-write at the VFS layer.
#   3. Creates a timestamped Btrfs snapshot (pre-upgrade baseline).
#   4. Runs pacman (NOT exec — we need control back after pacman exits).
#   5. Locks root again via lock_root() AFTER pacman and ALL its hooks finish.
#
# Why NOT use exec:
#   pacman hooks are sorted alphabetically. Hooks from packages like gtk4,
#   dconf, glib write to /usr/share/* AFTER our zzz-post-upgrade.hook would
#   run (if the hook existed alone). By doing the lock here — after pacman
#   returns — we guarantee ALL hooks completed on a writable root.
#
# On the live ISO:
#   Simply forwards to pacman (root already writable, no snapshots needed).
set -euo pipefail

readonly PROGRAM_NAME="our-pac"
_msg()    { echo "[${PROGRAM_NAME}] $*"; }
_err()    { _msg "ERROR: $*" >&2; }

if [[ $EUID -ne 0 ]]; then
    exec sudo "/usr/local/bin/${PROGRAM_NAME}" "$@"
fi

is_immutable_root() {
    btrfs property get / ro 2>/dev/null | grep -q 'ro=true'
}

# Unlock root via top-level Btrfs mount (avoids circular deadlock).
# btrfs property set / ro false fails when VFS mount is ro — metadata
# writes are blocked. Mounting subvolid=5 to a temp dir bypasses this.
unlock_root() {
    local root_dev tmp
    root_dev=$(findmnt -n -o SOURCE / | sed 's/\[.*//')
    tmp=$(mktemp -d)

    if ! mount -t btrfs -o subvolid=5 "$root_dev" "$tmp" 2>/dev/null; then
        rmdir "$tmp"; _err "Could not mount Btrfs top-level from ${root_dev}"; exit 1
    fi
    if ! btrfs property set "${tmp}/@" ro false 2>/dev/null; then
        umount "$tmp"; rmdir "$tmp"; _err "Could not clear Btrfs ro on @"; exit 1
    fi
    umount "$tmp"; rmdir "$tmp"
    mount -o remount,rw /
    _msg "Root unlocked (Btrfs ro=false) and remounted read-write"
}

# Lock root after pacman + all its hooks have finished.
# Same top-level mount approach to avoid issues with busy mounts.
lock_root() {
    local root_dev tmp
    root_dev=$(findmnt -n -o SOURCE / | sed 's/\[.*//')
    tmp=$(mktemp -d)

    if mount -t btrfs -o subvolid=5 "$root_dev" "$tmp" 2>/dev/null; then
        btrfs property set "${tmp}/@" ro true 2>/dev/null && \
            _msg "Root locked (Btrfs ro=true)"
        umount "$tmp"; rmdir "$tmp"
    else
        rmdir "$tmp"
        _msg "Could not mount top-level — root may remain writable"
    fi
    mount -o remount,ro / 2>/dev/null || \
        _msg "Root busy — Btrfs property protects immutability regardless"
}

if is_immutable_root; then
    _msg "Preparing package operation on immutable root..."

    snapshot_lib="/usr/local/lib/ouroboros/snapshot.sh"
    if [[ -r "$snapshot_lib" ]]; then
        source "$snapshot_lib"
        unlock_root
        pre_upgrade_snapshot
    else
        _msg "Snapshot library not found — unlocking root (direct)"
        unlock_root
    fi

    _msg "Running pacman $*"
    /usr/bin/pacman "$@"
    pacman_exit=$?

    lock_root
    exit "$pacman_exit"
else
    _msg "Running pacman $* (writable root — live ISO or unlocked)"
    exec /usr/bin/pacman "$@"
fi
SCRIPT
    chmod 0755 "${TARGET}/usr/local/bin/our-pac"
    log_ok "our-pac installed."

    # our-container — full-featured systemd-nspawn container wrapper for ouroborOS.
    # Copy from the live ISO (which ships the complete version with snapshots,
    # storage management, image management, monitoring, diagnostics, and stats).
    # Falls back to a minimal inline version if the ISO copy is missing.
    local OUR_CONTAINER_SRC="/usr/local/bin/our-container"
    if [[ -f "${OUR_CONTAINER_SRC}" && -r "${OUR_CONTAINER_SRC}" ]]; then
        cp "${OUR_CONTAINER_SRC}" "${TARGET}/usr/local/bin/our-container"
        chmod 0755 "${TARGET}/usr/local/bin/our-container"
        log_ok "our-container installed (copied full version from live ISO)."
    else
        log_warn "our-container not found on live ISO at ${OUR_CONTAINER_SRC} — installing minimal stub"
        cat > "${TARGET}/usr/local/bin/our-container" << 'STUB'
#!/usr/bin/env bash
# our-container — minimal stub (full version was not available on the ISO at install time)
set -euo pipefail
die() { echo "our-container: $*" >&2; exit 1; }
echo "our-container: full version not installed. Reinstall with: sudo our-pac -S ouroboros-scripts" >&2
exit 1
STUB
        chmod 0755 "${TARGET}/usr/local/bin/our-container"
    fi

    # Phase 3 user-facing tools — copy from live ISO to installed system.
    # These tools live in airootfs/usr/local/bin/ on the ISO and must be
    # explicitly copied; pacstrap does not pick them up from the live environment.
    local _p3_tools=(
        our-snapshot
        our-rollback
        our-wifi
        our-bluetooth
        our-fido2
        our-flat
        our-aur
        ouroboros-secureboot
    )
    for _tool in "${_p3_tools[@]}"; do
        local _src="/usr/local/bin/${_tool}"
        if [[ -f "${_src}" && -r "${_src}" ]]; then
            cp "${_src}" "${TARGET}/usr/local/bin/${_tool}"
            chmod 0755 "${TARGET}/usr/local/bin/${_tool}"
            log_ok "${_tool} installed."
        else
            log_warn "${_tool} not found on live ISO at ${_src} — skipping."
        fi
    done
    unset _p3_tools _tool _src

    # Phase 3 Bluetooth/FIDO2 config files — copy from live ISO.
    # /etc/bluetooth/main.conf: BLE LE tuning (MTU, AdvMon scan duration).
    # experimental.conf drop-in: enables bluetoothd --experimental (CTAP2 hybrid QR).
    # 71-fido2-ble.rules: udev rules for HID-over-GATT BLE FIDO2 tokens.
    local _bt_main_src="/etc/bluetooth/main.conf"
    if [[ -f "${_bt_main_src}" ]]; then
        mkdir -p "${TARGET}/etc/bluetooth"
        cp "${_bt_main_src}" "${TARGET}/etc/bluetooth/main.conf"
        log_ok "Bluetooth main.conf installed (BLE LE tuning)."
    fi
    local _bt_exp_src="/etc/systemd/system/bluetooth.service.d/experimental.conf"
    if [[ -f "${_bt_exp_src}" ]]; then
        mkdir -p "${TARGET}/etc/systemd/system/bluetooth.service.d"
        cp "${_bt_exp_src}" "${TARGET}/etc/systemd/system/bluetooth.service.d/experimental.conf"
        log_ok "BlueZ experimental mode drop-in installed."
    fi
    local _fido2_udev_src="/etc/udev/rules.d/71-fido2-ble.rules"
    if [[ -f "${_fido2_udev_src}" ]]; then
        mkdir -p "${TARGET}/etc/udev/rules.d"
        cp "${_fido2_udev_src}" "${TARGET}/etc/udev/rules.d/71-fido2-ble.rules"
        log_ok "FIDO2 BLE udev rules installed."
    fi

    # our-container-autostart — oneshot service that starts containers listed in
    # /etc/our-container/autostart.conf at boot.  The wrapper script reads the conf
    # and calls `our-container start <name>` for each entry.
    local AUTOSTART_SRC="/usr/local/bin/our-container-autostart"
    if [[ -f "${AUTOSTART_SRC}" && -r "${AUTOSTART_SRC}" ]]; then
        cp "${AUTOSTART_SRC}" "${TARGET}/usr/local/bin/our-container-autostart"
        chmod 0755 "${TARGET}/usr/local/bin/our-container-autostart"
    fi

    # Install the systemd unit file for autostart
    local AUTOSTART_UNIT_SRC="/etc/systemd/system/our-container-autostart.service"
    if [[ -f "${AUTOSTART_UNIT_SRC}" && -r "${AUTOSTART_UNIT_SRC}" ]]; then
        mkdir -p "${TARGET}/etc/systemd/system"
        cp "${AUTOSTART_UNIT_SRC}" "${TARGET}/etc/systemd/system/our-container-autostart.service"
        log_ok "our-container-autostart.service installed."
    fi

    cat > "${TARGET}/usr/local/bin/our-post-upgrade" << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
# our-post-upgrade — restore root immutability after a package transaction.
#
# Called by the 99-post-upgrade pacman hook (PostTransaction).
#
# Strategy (belt-and-suspenders):
#   1. btrfs property set ro=true: enforces immutability at the Btrfs subvolume
#      level. This is the primary mechanism — it works even when other subvolumes
#      from the same device are mounted rw (the mount-option ro alone is
#      overridden by Btrfs superblock sharing).
#   2. mount -o remount,ro: secondary VFS-layer enforcement. May fail if there
#      are active SSH sessions or open file handles — that is expected and safe
#      because btrfs property ro=true already protects the subvolume.
if btrfs property set / ro true 2>/dev/null; then
    echo "[our-post-upgrade] Root subvolume set read-only (Btrfs property)"
else
    echo "[our-post-upgrade] WARNING: Could not set Btrfs ro property — root may not be immutable"
fi
# Best-effort VFS-layer remount (non-fatal)
mount -o remount,ro / 2>/dev/null && echo "[our-post-upgrade] Root remounted ro (VFS)" || \
    echo "[our-post-upgrade] Root busy — Btrfs property protects immutability regardless"
SCRIPT
    chmod 0755 "${TARGET}/usr/local/bin/our-post-upgrade"

    # Install snapshot library to installed system
    mkdir -p "${TARGET}/usr/local/lib/ouroboros"
    cp "$(dirname "$0")/snapshot.sh" "${TARGET}/usr/local/lib/ouroboros/snapshot.sh"

    log_ok "Immutable root compatibility configured."
}

# --- Step 10: os-release ----------------------------------------------------

configure_os_release() {
    log_info "Writing os-release..."

    local version="${ISO_VERSION:-rolling}"

    cat > "${TARGET}/etc/os-release" << EOF
NAME="ouroborOS"
PRETTY_NAME="ouroborOS ${version}"
ID=ouroboros
ID_LIKE=arch
BUILD_ID=rolling
ANSI_COLOR="38;2;23;147;209"
HOME_URL="https://github.com/Arkhur-Vo/ouroborOS"
SUPPORT_URL="https://github.com/Arkhur-Vo/ouroborOS/issues"
BUG_REPORT_URL="https://github.com/Arkhur-Vo/ouroborOS/issues"
VERSION_ID="${version}"
EOF
    log_ok "os-release written (version: ${version})."
}

# --- Step 11: systemd-homed migration setup ---------------------------------

configure_homed() {
    log_info "Configuring systemd-homed (storage: ${HOMED_STORAGE})"

    case "$HOMED_STORAGE" in
        subvolume|directory|luks) ;;
        classic)
            log_info "homed_storage=classic — skipping migration setup."
            return 0
            ;;
        *)
            log_error "Unknown homed_storage: ${HOMED_STORAGE}"
            return 1
            ;;
    esac

    in_chroot systemctl enable systemd-homed.service

    local homed_migrate_src=""
    homed_migrate_src="/usr/local/lib/ouroboros/homed-migrate.sh"
    if [[ -f "$homed_migrate_src" && -r "$homed_migrate_src" ]]; then
        mkdir -p "${TARGET}/usr/local/lib/ouroboros"
        cp "$homed_migrate_src" "${TARGET}/usr/local/lib/ouroboros/homed-migrate.sh"
        chmod 0755 "${TARGET}/usr/local/lib/ouroboros/homed-migrate.sh"
        log_ok "homed-migrate.sh installed."
    else
        log_warn "homed-migrate.sh not found on live ISO — migration will not work."
    fi

    mkdir -p "${TARGET}/etc/systemd/system"
    local service_src="/etc/systemd/system/ouroboros-homed-migration.service"
    if [[ -f "$service_src" && -r "$service_src" ]]; then
        cp "$service_src" "${TARGET}/etc/systemd/system/ouroboros-homed-migration.service"
        log_ok "ouroboros-homed-migration.service installed."
    else
        log_warn "Migration service unit not found on live ISO."
    fi

    mkdir -p "${TARGET}/etc/ouroboros"
    cat > "${TARGET}/etc/ouroboros/homed-migration.conf" << EOF
HOMED_USERNAME=${USERNAME}
HOMED_STORAGE=${HOMED_STORAGE}
HOMED_PASSWORD=${USER_PASSWORD}
EOF
    chmod 600 "${TARGET}/etc/ouroboros/homed-migration.conf"

    # The migration service runs only when this file exists; the script
    # removes it after success to prevent re-execution on subsequent boots.
    touch "${TARGET}/etc/ouroboros/homed-migration-pending"

    in_chroot systemctl enable ouroboros-homed-migration.service

    log_ok "systemd-homed migration configured (runs on first boot)."
}

# --- Main -------------------------------------------------------------------

main() {
    log_info "Starting post-install configuration for ${TARGET}"

    configure_locale
    configure_timezone
    configure_hostname
    configure_initramfs
    configure_bootloader
    configure_tpm2
    configure_dual_boot
    configure_secure_boot
    configure_network
    configure_fido2_pam
    configure_zram
    configure_users
    configure_immutable_root
    configure_os_release
    configure_homed

    # --- Fixes that need to land on BOTH @etc (overlay) and @ (root subvolume) ---
    # systemd loads unit files from @ BEFORE @etc mounts over /etc.
    # journald starts before @var mounts over /var.
    # So certain files must exist directly on the @ subvolume.

    in_chroot systemctl enable getty@tty1.service
    in_chroot systemctl enable sshd.service
    log_ok "sshd enabled (uses default After=network.target)."

    # Display manager — enabled only for desktop profiles that ship one.
    # greetd (COSMIC) requires extra setup: cosmic-greeter config + greeter user.
    if [[ -n "${DESKTOP_DM:-}" ]]; then
        if [[ "${DESKTOP_DM}" == "greetd" ]]; then
            arch-chroot "${TARGET}" pacman -S --noconfirm cosmic-greeter
            mkdir -p "${TARGET}/etc/greetd"
            cat > "${TARGET}/etc/greetd/config.toml" <<'GREETD_EOF'
[terminal]
vt = 1

[default_session]
command = "cosmic-greeter"
user = "greeter"
GREETD_EOF
            arch-chroot "${TARGET}" useradd --system --no-create-home \
                --shell /sbin/nologin greeter 2>/dev/null || true
            log_ok "greetd configured with cosmic-greeter."
        fi
        in_chroot systemctl enable "${DESKTOP_DM}.service"
        in_chroot systemctl daemon-reload
        in_chroot systemctl set-default graphical.target
        log_ok "Display manager enabled: ${DESKTOP_DM}."
    else
        log_info "No display manager enabled (profile: ${DESKTOP_PROFILE:-minimal})."
    fi

    # GPU driver installation
    case "${GPU_DRIVER:-auto}" in
        nvidia)
            arch-chroot "${TARGET}" pacman -S --noconfirm nvidia nvidia-utils
            log_ok "GPU: NVIDIA proprietary driver installed."
            ;;
        nvidia-open)
            arch-chroot "${TARGET}" pacman -S --noconfirm nvidia-open nvidia-utils
            log_ok "GPU: NVIDIA open kernel module installed."
            ;;
        amdgpu|mesa)
            arch-chroot "${TARGET}" pacman -S --noconfirm mesa vulkan-radeon xf86-video-amdgpu
            log_ok "GPU: Mesa + AMD open source driver installed."
            ;;
        auto)
            # auto: detect via lspci and install the best driver
            if lspci 2>/dev/null | grep -qi "nvidia"; then
                arch-chroot "${TARGET}" pacman -S --noconfirm nvidia nvidia-utils
                log_ok "GPU: auto-detected NVIDIA — proprietary driver installed."
            elif lspci 2>/dev/null | grep -qiE "amd|radeon"; then
                arch-chroot "${TARGET}" pacman -S --noconfirm mesa vulkan-radeon xf86-video-amdgpu
                log_ok "GPU: auto-detected AMD — mesa + vulkan-radeon installed."
            elif lspci 2>/dev/null | grep -qi "intel"; then
                arch-chroot "${TARGET}" pacman -S --noconfirm mesa vulkan-intel
                log_ok "GPU: auto-detected Intel — mesa + vulkan-intel installed."
            else
                log_info "GPU: auto-detect found no known GPU — skipping driver install."
            fi
            ;;
        none)
            log_info "GPU: driver install skipped (none selected)."
            ;;
    esac

    # our-container autostart — copy default config and enable service if containers are listed.
    # The autostart.conf shipped in the ISO is empty (comments only); users add container
    # names post-install.  During unattended installs the config can be pre-populated.
    local AUTOSTART_CONF_SRC="/etc/our-container/autostart.conf"
    mkdir -p "${TARGET}/etc/our-container"
    if [[ -f "${AUTOSTART_CONF_SRC}" && -r "${AUTOSTART_CONF_SRC}" ]]; then
        cp "${AUTOSTART_CONF_SRC}" "${TARGET}/etc/our-container/autostart.conf"
    fi

    # Enable the service only if autostart.conf has at least one real entry
    if grep -qE '^[[:space:]]*[^#[:space:]]' "${TARGET}/etc/our-container/autostart.conf" 2>/dev/null; then
        in_chroot systemctl enable our-container-autostart.service
        log_ok "our-container-autostart.service enabled (containers found in autostart.conf)."
    else
        log_info "our-container-autostart.service not enabled (no containers in autostart.conf)."
    fi

    # our-snapshot-prune.timer — daily automatic snapshot rotation.
    # Keeps at most 5 snapshots, removes snapshots older than 30 days.
    # The timer is installed from the ISO; enable it unconditionally.
    local PRUNE_UNIT_SRC="/etc/systemd/system/our-snapshot-prune.service"
    local PRUNE_TIMER_SRC="/etc/systemd/system/our-snapshot-prune.timer"
    if [[ -f "${PRUNE_UNIT_SRC}" && -f "${PRUNE_TIMER_SRC}" ]]; then
        mkdir -p "${TARGET}/etc/systemd/system"
        cp "${PRUNE_UNIT_SRC}" "${TARGET}/etc/systemd/system/our-snapshot-prune.service"
        cp "${PRUNE_TIMER_SRC}" "${TARGET}/etc/systemd/system/our-snapshot-prune.timer"
        in_chroot systemctl enable our-snapshot-prune.timer
        log_ok "our-snapshot-prune.timer enabled (daily snapshot rotation)."
    else
        log_warn "our-snapshot-prune units not found on live ISO — skipping."
    fi

    # ouroboros-snapshot-on-boot — early-boot service that auto-creates and promotes
    # a new snapshot when the system boots from @snapshots/X instead of @.
    # This preserves all existing snapshots as restore points.
    local SNAP_ON_BOOT_SRC="/usr/local/bin/ouroboros-snapshot-on-boot"
    local SNAP_ON_BOOT_UNIT_SRC="/etc/systemd/system/ouroboros-snapshot-on-boot.service"
    if [[ -f "${SNAP_ON_BOOT_SRC}" && -f "${SNAP_ON_BOOT_UNIT_SRC}" ]]; then
        # @ may be ro=true at this point (set by zzz-post-upgrade pacman hook during
        # configure_gpu). Temporarily clear ro before copying directly to TARGET.
        local _snap_ro
        _snap_ro=$(btrfs property get "${TARGET}" ro 2>/dev/null | grep -oP '(?<=ro=)\w+' || echo "false")
        [[ "$_snap_ro" == "true" ]] && btrfs property set "${TARGET}" ro false 2>/dev/null || true

        cp "${SNAP_ON_BOOT_SRC}" "${TARGET}/usr/local/bin/ouroboros-snapshot-on-boot"
        chmod 0755 "${TARGET}/usr/local/bin/ouroboros-snapshot-on-boot"
        mkdir -p "${TARGET}/etc/systemd/system"
        cp "${SNAP_ON_BOOT_UNIT_SRC}" "${TARGET}/etc/systemd/system/ouroboros-snapshot-on-boot.service"

        [[ "$_snap_ro" == "true" ]] && btrfs property set "${TARGET}" ro true 2>/dev/null || true

        in_chroot systemctl enable ouroboros-snapshot-on-boot.service
        log_ok "ouroboros-snapshot-on-boot.service installed and enabled."
    else
        log_warn "ouroboros-snapshot-on-boot not found on live ISO — skipping."
    fi

    # ouroboros-firstboot — one-shot service that runs on the first real boot.
    # Handles: reflector mirror update, machine-id check, enable btrfs-scrub timer,
    #          systemd-sysext merge, and lazy AUR package install via our-aur.
    local FIRSTBOOT_SRC="/usr/local/bin/ouroboros-firstboot"
    local FIRSTBOOT_UNIT_SRC="/etc/systemd/system/ouroboros-firstboot.service"
    if [[ -f "${FIRSTBOOT_SRC}" && -f "${FIRSTBOOT_UNIT_SRC}" ]]; then
        # Write to @ subvolume (pre-overlay) — /usr is read-only after overlay
        _write_firstboot_to_root() {
            local mnt="$1"
            mkdir -p "${mnt}/usr/local/bin"
            cp "${FIRSTBOOT_SRC}" "${mnt}/usr/local/bin/ouroboros-firstboot"
            chmod 0755 "${mnt}/usr/local/bin/ouroboros-firstboot"
            log_ok "ouroboros-firstboot binary written to @ subvolume."
        }
        write_to_root_subvolume _write_firstboot_to_root

        # Unit file goes to @etc (will be overlaid on /etc/systemd/system)
        mkdir -p "${TARGET}/etc/systemd/system"
        cp "${FIRSTBOOT_UNIT_SRC}" "${TARGET}/etc/systemd/system/ouroboros-firstboot.service"
        in_chroot systemctl enable ouroboros-firstboot.service
        log_ok "ouroboros-firstboot.service installed and enabled."

        # Write AUR package list for lazy firstboot install
        if [[ -n "${DESKTOP_AUR_PACKAGES:-}" ]]; then
            mkdir -p "${TARGET}/var/lib/ouroborOS"
            echo "${DESKTOP_AUR_PACKAGES}" > "${TARGET}/var/lib/ouroborOS/firstboot-aur-packages.txt"
            log_ok "AUR packages queued for firstboot install: ${DESKTOP_AUR_PACKAGES}"
        fi
    else
        log_warn "ouroboros-firstboot not found on live ISO — skipping."
    fi

    # /var/lib/extensions — required by systemd-sysext and our-aur.
    # systemd-sysext expects this directory to exist at merge time.
    mkdir -p "${TARGET}/var/lib/extensions"
    chmod 0755 "${TARGET}/var/lib/extensions"
    log_ok "/var/lib/extensions created (systemd-sysext / our-aur)."

    # sshd_config: disable reverse DNS lookup.
    # Without UseDNS=no, sshd does a PTR lookup for each connecting client.
    # In QEMU SLIRP, the client appears as 10.0.2.2 which has no PTR record.
    # This causes a 30s+ hang at banner exchange even though sshd is running.
    # Append directly to sshd_config — Arch openssh does not read sshd_config.d/
    # by default (no Include directive in the default config).
    echo "UseDNS no" >> "${TARGET}/etc/ssh/sshd_config"
    log_ok "sshd_config: UseDNS no (appended to sshd_config)."

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
        for f in machine-id passwd group shadow gshadow crypttab; do
            if [[ -f "${TARGET}/etc/${f}" ]]; then
                cp "${TARGET}/etc/${f}" "${mnt}/etc/${f}"
            fi
        done
        log_ok "Critical /etc files written to @ subvolume (machine-id, passwd, group, shadow, gshadow, crypttab)."
    }
    write_to_root_subvolume _write_etc_to_root || true

    # systemd reads /etc/systemd/system/ from @ BEFORE fstab mounts /etc from @etc.
    # Any symlink created by `systemctl enable` lives in @etc and is invisible to
    # systemd at early boot.  We must mirror those symlinks onto @ so that networkd,
    # resolved, sshd, timesyncd and their wait-online deps are actually scheduled.
    #
    # CRITICAL: systemd-networkd and systemd-resolved also start BEFORE /etc is
    # mounted (network-pre.target happens in sysinit, before local-fs.target).
    # Their config files (.network, resolved.conf) live on @etc and are invisible
    # at that point.  We must copy them to @ so they are picked up on first read.
    _write_systemd_enables_to_root() {
        local mnt="$1"
        local src="${TARGET}/etc/systemd/system"
        local dst="${mnt}/etc/systemd/system"
        mkdir -p "${dst}"

        # Directories whose contents must exist on @ for early-boot scheduling.
        # Includes .target.wants (enable symlinks) AND service drop-ins that
        # must take effect before @etc is mounted over /etc.
        for dir in \
            multi-user.target.wants \
            network-online.target.wants \
            sysinit.target.wants \
            sockets.target.wants \
            getty.target.wants \
            graphical.target.wants; do
            if [[ -d "${src}/${dir}" ]]; then
                mkdir -p "${dst}/${dir}"
                cp -a "${src}/${dir}/." "${dst}/${dir}/"
            fi
        done

        log_ok "systemd enable symlinks mirrored to @ subvolume."

        # Mirror .network files: networkd starts BEFORE /etc is mounted and reads
        # /etc/systemd/network/ from @ directly.  Without this, no interface is
        # configured and DHCP never runs.
        if [[ -d "${TARGET}/etc/systemd/network" ]]; then
            mkdir -p "${mnt}/etc/systemd/network"
            cp -a "${TARGET}/etc/systemd/network/." "${mnt}/etc/systemd/network/"
            log_ok ".network files mirrored to @ subvolume."
        fi

        # Mirror resolved.conf: systemd-resolved also starts before /etc mounts.
        # Without this, DoT/DNS config is ignored on first boot.
        if [[ -f "${TARGET}/etc/systemd/resolved.conf" ]]; then
            mkdir -p "${mnt}/etc/systemd"
            cp "${TARGET}/etc/systemd/resolved.conf" "${mnt}/etc/systemd/resolved.conf"
            log_ok "resolved.conf mirrored to @ subvolume."
        fi

        # Mirror zram-generator.conf: systemd generators run before /etc mounts.
        # Without this, zram-generator doesn't see the config and zram swap is
        # never created.
        if [[ -f "${TARGET}/etc/systemd/zram-generator.conf" ]]; then
            mkdir -p "${mnt}/etc/systemd"
            cp "${TARGET}/etc/systemd/zram-generator.conf" "${mnt}/etc/systemd/zram-generator.conf"
            log_ok "zram-generator.conf mirrored to @ subvolume."
        fi

        # Mirror ouroboros-firstboot service: must be visible at first boot
        # before @etc is mounted, so the unit is found when multi-user.target.wants
        # symlink is evaluated.
        if [[ -f "${TARGET}/etc/systemd/system/ouroboros-firstboot.service" ]]; then
            mkdir -p "${mnt}/etc/systemd/system"
            cp "${TARGET}/etc/systemd/system/ouroboros-firstboot.service" \
                "${mnt}/etc/systemd/system/ouroboros-firstboot.service"
        fi

        # Mirror display-manager.service alias: graphical.target wants
        # display-manager.service, but the Alias= symlink created by
        # `systemctl enable sddm` lives in @etc and is invisible to systemd
        # at early boot.  Without this, SDDM/GDM never starts on the installed
        # system because systemd cannot resolve the alias.
        if [[ -L "${src}/display-manager.service" ]]; then
            cp -a "${src}/display-manager.service" "${dst}/display-manager.service"
            log_ok "display-manager.service alias mirrored to @ subvolume."
        fi

        # Mirror homed migration service + config: systemd-homed starts before
        # @etc is mounted. Without this, the migration unit is invisible at
        # first boot and the user is never migrated.
        if [[ -f "${TARGET}/etc/systemd/system/ouroboros-homed-migration.service" ]]; then
            mkdir -p "${mnt}/etc/systemd/system"
            cp "${TARGET}/etc/systemd/system/ouroboros-homed-migration.service" \
                "${mnt}/etc/systemd/system/ouroboros-homed-migration.service"
        fi
        if [[ -f "${TARGET}/etc/ouroboros/homed-migration.conf" ]]; then
            mkdir -p "${mnt}/etc/ouroboros"
            cp "${TARGET}/etc/ouroboros/homed-migration.conf" \
                "${mnt}/etc/ouroboros/homed-migration.conf"
        fi
        if [[ -f "${TARGET}/etc/ouroboros/homed-migration-pending" ]]; then
            mkdir -p "${mnt}/etc/ouroboros"
            cp "${TARGET}/etc/ouroboros/homed-migration-pending" \
                "${mnt}/etc/ouroboros/homed-migration-pending"
        fi
    }
    write_to_root_subvolume _write_systemd_enables_to_root || true

    # Install system.yaml if the Python installer already wrote it to TARGET.
    # _write_system_yaml() in state_machine.py writes it during FINISH state;
    # this step ensures /etc/ouroboros/ has the correct permissions.
    if [[ -f "${TARGET}/etc/ouroboros/system.yaml" ]]; then
        chmod 644 "${TARGET}/etc/ouroboros/system.yaml"
        log_ok "system.yaml present at ${TARGET}/etc/ouroboros/system.yaml (chmod 644)."
    else
        log_warn "system.yaml not found at ${TARGET}/etc/ouroboros/system.yaml — will be written by installer at FINISH state."
    fi

    # Seal @ as immutable — this is the critical step that activates the
    # our-pac flow on first boot. Without this, our-pac detects a writable
    # root and falls back to plain pacman (no snapshot, no lock cycle).
    # Must run LAST — after all writes to TARGET are complete.
    local _top_mount
    _top_mount=$(mktemp -d)
    if mount -o subvolid=5 "${DEVICE}" "${_top_mount}" 2>/dev/null; then
        if btrfs property set "${_top_mount}/@" ro true 2>/dev/null; then
            log_ok "Root subvolume @ sealed as immutable (ro=true)."
        else
            log_warn "Could not seal @ as immutable — our-pac will run in unlocked mode on first boot."
        fi
        umount "${_top_mount}" 2>/dev/null || true
    else
        log_warn "Could not mount Btrfs top-level to seal @."
    fi
    rmdir "${_top_mount}" 2>/dev/null || true

    log_ok "All configuration steps complete."
}

main "$@"
