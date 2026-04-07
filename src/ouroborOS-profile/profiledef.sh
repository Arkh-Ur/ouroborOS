#!/usr/bin/env bash
# shellcheck disable=SC2034
set -euo pipefail
# profiledef.sh — ouroborOS archiso profile definition

iso_name="ouroborOS"
iso_label="OUROBOROS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="ouroborOS <https://github.com/Arkhur-Vo/ouroborOS>"
iso_application="ouroborOS ArchLinux-based immutable Linux distribution"
iso_version="0.1.0"
install_dir="arch"
buildmodes=('iso')
bootmodes=('uefi.systemd-boot')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '15')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/usr/local/bin/ouroborOS-installer"]="0:0:755"
  ["/usr/local/bin/sshd-hostkeys"]="0:0:755"
)
