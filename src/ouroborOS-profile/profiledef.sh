#!/usr/bin/env bash
# shellcheck disable=SC2034
set -euo pipefail
# profiledef.sh — ouroborOS archiso profile definition

iso_name="ouroborOS"
iso_label="OUROBOROS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="ouroborOS <https://github.com/Arkh-Ur/ouroborOS>"
iso_application="ouroborOS ArchLinux-based immutable Linux distribution"
iso_version="0.6.1"
install_dir="arch"
buildmodes=('iso')
bootmodes=('uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="erofs"
airootfs_image_tool_options=('-zlzma' '-E' 'ztailpacking')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/ouroboros/shell.bashrc"]="0:0:644"
  ["/usr/local/bin/ouroborOS-installer"]="0:0:755"
  ["/usr/local/bin/sshd-hostkeys"]="0:0:755"
  ["/usr/local/bin/our-app"]="0:0:755"
  ["/usr/local/bin/our-dots"]="0:0:755"
  ["/usr/local/bin/our-aur"]="0:0:755"
  ["/usr/local/bin/our-bluetooth"]="0:0:755"
  ["/usr/local/bin/our-box"]="0:0:755"
  ["/usr/local/bin/our-container"]="0:0:755"
  ["/usr/local/bin/our-container-autostart"]="0:0:755"
  ["/usr/local/bin/our-fido2"]="0:0:755"
  ["/usr/local/bin/our-flat"]="0:0:755"
  ["/usr/local/bin/our-pac"]="0:0:755"
  ["/usr/local/bin/our-rollback"]="0:0:755"
  ["/usr/local/bin/our-wall"]="0:0:755"
  ["/usr/local/bin/ouroboros-install"]="0:0:755"
  ["/usr/local/bin/our-snapshot"]="0:0:755"
  ["/usr/local/bin/our-wifi"]="0:0:755"
  ["/usr/local/bin/ouroboros-firstboot"]="0:0:755"
  ["/usr/local/bin/ouroboros-rebase"]="0:0:755"
  ["/usr/local/bin/ouroboros-secureboot"]="0:0:755"
  ["/usr/local/bin/ouroboros-snapshot-on-boot"]="0:0:755"
  ["/usr/local/bin/ouroboros-update"]="0:0:755"
  ["/usr/local/bin/ouroboros-health"]="0:0:755"
  ["/usr/local/bin/ouroboros-reinstall"]="0:0:755"
)


# ── customize_airootfs() — patch mkinitcpio init_functions (Bug A fix) ──
# Bug: Live ISO boot emits "ERROR: device '' not found. Skipping fsck."
# because the live ISO has no root= in its kernel cmdline, so fsck_root()
# calls fsck_device "" with an empty string. The err() call writes the
# warning to console (visible during boot). We patch fsck_device() to
# silently skip when $1 is empty.
customize_airootfs() {
    local init_funcs="${1}/usr/lib/initcpio/init_functions"
    if [[ -f "${init_funcs}" ]]; then
        # Replace the err() line with an early return when $1 is empty.
        # This keeps the fsck step functional for real devices but hides
        # the cosmetic warning on live ISO boots.
        if grep -qF "device '' not found. Skipping fsck." "${init_funcs}"; then
            sed -i 's|^        err "device '"'"''"'"' not found\. Skipping fsck\."$|        [ -z "$1" ] && return 255 # ouroborOS patch: skip empty device silently|' "${init_funcs}"
            echo "  ✓ Patched init_functions: skip empty fsck device (ouroborOS)"
        fi
    fi
}
