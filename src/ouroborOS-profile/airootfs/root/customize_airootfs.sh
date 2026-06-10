#!/usr/bin/env bash
# customize_airootfs.sh — ouroborOS archiso airootfs post-install patch
# Run automatically by mkarchiso (deprecated but still supported) in chroot.
#
# Bug A fix (2026-06-10): patch mkinitcpio init_functions to silently skip
# fsck on empty device (the live ISO has no root= in cmdline, which would
# otherwise emit "ERROR: device '' not found. Skipping fsck.").
set -euo pipefail

INIT_FUNCS="/usr/lib/initcpio/init_functions"

if [[ ! -f "${INIT_FUNCS}" ]]; then
    echo "  ⚠ init_functions not found at ${INIT_FUNCS} — skipping fsck patch"
    exit 0
fi

if grep -qF "ouroborOS patch: skip empty device silently" "${INIT_FUNCS}"; then
    echo "  ✓ init_functions already patched (ouroborOS) — noop"
    exit 0
fi

if ! grep -qF "device '' not found. Skipping fsck." "${INIT_FUNCS}"; then
    echo "  ⚠ marker line not found in ${INIT_FUNCS} — mkinitcpio may have changed"
    exit 0
fi

# Replace the err() line with an early-return when $1 is empty
# This keeps fsck functional for real devices but hides the cosmetic warning
# on live ISO boots (where the kernel cmdline has no root=).
sed -i 's|^        err "device '"'"''"'"' not found\. Skipping fsck\."$|        [ -z "$1" ] && return 255 # ouroborOS patch: skip empty device silently|' "${INIT_FUNCS}"

echo "  ✓ Patched ${INIT_FUNCS} — fsck warning suppressed when device is empty"
