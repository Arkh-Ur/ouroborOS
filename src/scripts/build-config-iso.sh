#!/usr/bin/env bash
# build-config-iso.sh — Create a config ISO for unattended ouroborOS installs.
#
# Usage:
#   bash src/scripts/build-config-iso.sh --config path/to/unattended.yaml \
#                                         [--output unattended.iso]
#
# The resulting ISO has LABEL=OUROBOROS_CFG and contains unattended.yaml
# at its root. The installer detects it automatically and runs silently.
#
# QEMU usage:
#   qemu-system-x86_64 -cdrom ouroborOS.iso \
#     -drive file=unattended.iso,if=ide,media=cdrom,index=1 ...
set -euo pipefail

CONFIG=""
OUTPUT="unattended.iso"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config) CONFIG="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) echo "Usage: $0 --config <yaml> [--output <iso>]" >&2; exit 1 ;;
    esac
done

[[ -z "$CONFIG" ]] && { echo "ERROR: --config required" >&2; exit 1; }
[[ -f "$CONFIG" ]] || { echo "ERROR: config file not found: $CONFIG" >&2; exit 1; }

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cp "$CONFIG" "$TMPDIR/unattended.yaml"

if command -v xorriso &>/dev/null; then
    xorriso -as mkisofs -V "OUROBOROS_CFG" -r -J -o "$OUTPUT" "$TMPDIR"
elif command -v genisoimage &>/dev/null; then
    genisoimage -V "OUROBOROS_CFG" -r -J -o "$OUTPUT" "$TMPDIR"
elif command -v mkisofs &>/dev/null; then
    mkisofs -V "OUROBOROS_CFG" -r -J -o "$OUTPUT" "$TMPDIR"
else
    echo "ERROR: xorriso, genisoimage, or mkisofs required" >&2
    exit 1
fi

echo "Config ISO created: $OUTPUT"
echo "  Label:  OUROBOROS_CFG"
echo "  Config: unattended.yaml"
echo ""
echo "QEMU: -drive file=${OUTPUT},if=ide,media=cdrom,index=1"
