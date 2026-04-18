#!/usr/bin/env bash
# shellcheck disable=SC2034
set -euo pipefail
# profiledef.sh — ouroborOS archiso profile definition

iso_name="ouroborOS"
iso_label="OUROBOROS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="ouroborOS <https://github.com/Arkh-Ur/ouroborOS>"
iso_application="ouroborOS ArchLinux-based immutable Linux distribution"
iso_version="0.5.0"
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
  ["/usr/local/bin/ouroborOS-installer"]="0:0:755"
  ["/usr/local/bin/sshd-hostkeys"]="0:0:755"
  ["/usr/local/bin/our-aur"]="0:0:755"
  ["/usr/local/bin/our-bluetooth"]="0:0:755"
  ["/usr/local/bin/our-container"]="0:0:755"
  ["/usr/local/bin/our-container-autostart"]="0:0:755"
  ["/usr/local/bin/our-fido2"]="0:0:755"
  ["/usr/local/bin/our-flat"]="0:0:755"
  ["/usr/local/bin/our-pac"]="0:0:755"
  ["/usr/local/bin/our-rollback"]="0:0:755"
  ["/usr/local/bin/our-snapshot"]="0:0:755"
  ["/usr/local/bin/our-wifi"]="0:0:755"
  ["/usr/local/bin/ouroboros-firstboot"]="0:0:755"
  ["/usr/local/bin/ouroboros-secureboot"]="0:0:755"
  ["/usr/local/bin/ouroboros-snapshot-on-boot"]="0:0:755"
)
