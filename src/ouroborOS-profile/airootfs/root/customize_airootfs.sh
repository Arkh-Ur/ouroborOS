#!/usr/bin/env bash
# customize_airootfs.sh — ouroborOS archiso airootfs post-install patch
# Run automatically by mkarchiso (deprecated but still supported) in chroot.
#
# Bug A (fsck warning): the live ISO kernel cmdline now includes fsck.mode=skip
# (see efiboot/loader/entries/01-ouroborOS.conf), which prevents the fsck step
# from running in the initramfs. Without fsck.root=, fsck_device() is never
# called with an empty device and the "device '' not found" warning is
# never emitted. This file is kept as a hook-point for future airootfs
# post-install patches.
set -euo pipefail

echo "  OK: ouroborOS customize_airootfs.sh — noop (patches moved to kernel cmdline)"
