# ISO Build Process

## Overview

ouroborOS ISOs are built using **archiso**, the official ArchLinux ISO build framework. The build process produces a bootable hybrid ISO (UEFI + BIOS fallback) containing the live environment and the ouroborOS installer.

---

## Requirements

### Host system
- ArchLinux (or ArchLinux-based distro)
- Packages: `archiso`, `mkinitcpio`, `dosfstools`, `e2fsprogs`, `squashfs-tools`, `libisoburn`

```bash
pacman -S archiso dosfstools e2fsprogs squashfs-tools libisoburn
```

### Permissions
- Build must run as **root** (archiso requirement)
- Recommended: use a dedicated build user with sudo rights, or a container

### Disk space
- Minimum 10 GB free in the working directory
- Output ISO: ~1.5–3 GB depending on included packages

---

## Profile Structure

```
ouroborOS-profile/
├── profiledef.sh              ← ISO metadata and build settings
├── pacman.conf                ← Package manager config for build
├── packages.x86_64            ← List of packages to install in live ISO
├── airootfs/                  ← Overlay onto live root filesystem
│   ├── etc/
│   │   ├── hostname           ← "ouroborOS-live"
│   │   ├── locale.conf
│   │   ├── vconsole.conf
│   │   ├── mkinitcpio.conf
│   │   ├── systemd/
│   │   │   └── system/
│   │   │       ├── ouroborOS-installer.service
│   │   │       └── getty@tty1.service.d/
│   │   │           └── autologin.conf
│   │   └── pacman.d/
│   │       └── mirrorlist
│   └── usr/
│       └── local/
│           └── bin/
│               └── ouroborOS-installer    ← Installer entrypoint
├── efiboot/                   ← UEFI boot files
│   └── loader/
│       ├── loader.conf
│       └── entries/
│           └── ouroborOS-live.conf
└── grub/                      ← BIOS fallback (GRUB)
    └── grub.cfg
```

---

## profiledef.sh

```bash
#!/usr/bin/env bash

iso_name="ouroborOS"
iso_label="OUROBOROS_$(date +%Y%m)"
iso_publisher="ouroborOS Project"
iso_application="ouroborOS Live/Install Medium"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito' 'uefi-ia32.systemd-boot.esp' 'uefi-x64.systemd-boot.esp')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/usr/local/bin/ouroborOS-installer"]="0:0:755"
)
```

---

## packages.x86_64 (core list)

```
# Base system
base
linux-zen
linux-zen-headers
linux-firmware
mkinitcpio

# Filesystem
btrfs-progs
dosfstools
e2fsprogs
exfatprogs

# Boot
efibootmgr

# Network
iwd
dhcpcd

# Installer dependencies
python
python-yaml
python-rich
dialog
parted
arch-install-scripts

# Utilities
neovim
git
curl
wget
rsync
sudo
man-db
terminus-font

# Accessibility
brltty
espeakup
```

---

## Build Steps

### 1. Prepare working directory
```bash
BUILDDIR=$(mktemp -d)
cp -r ouroborOS-profile/ "$BUILDDIR/profile"
```

### 2. Run mkarchiso
```bash
mkarchiso -v \
  -w "$BUILDDIR/work" \
  -o "$BUILDDIR/out" \
  "$BUILDDIR/profile"
```

This performs:
1. Installs all packages from `packages.x86_64` into a chroot
2. Applies `airootfs/` overlay
3. Runs `mkinitcpio` inside the chroot
4. Compresses filesystem to squashfs
5. Creates EFI images and BIOS boot sectors
6. Assembles final ISO with `xorriso`

### 3. Checksum generation
```bash
cd "$BUILDDIR/out"
sha256sum ouroborOS-*.iso > ouroborOS-*.iso.sha256
```

### 4. Optional: GPG signing
```bash
gpg --detach-sign ouroborOS-*.iso
```

---

## Using the Build Script

The `docs/scripts/build-iso.sh` script automates steps 1–3:

```bash
sudo bash docs/scripts/build-iso.sh
```

Output will be in `./out/`.

---

## Testing the ISO

### QEMU (recommended for quick tests)
```bash
qemu-system-x86_64 \
  -enable-kvm \
  -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso \
  -boot d
```

### QEMU with virtual disk (full install test)
```bash
qemu-img create -f qcow2 /tmp/test-disk.qcow2 30G

qemu-system-x86_64 \
  -enable-kvm \
  -m 4096 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso \
  -drive file=/tmp/test-disk.qcow2,format=qcow2 \
  -boot d
```

---

## CI/CD Notes

- Build should run in a clean container (Arch-based) to avoid host contamination
- Recommended: GitHub Actions with `archlinux:latest` container
- Build artifacts: ISO + SHA256 + (optionally) GPG signature
- Release tagging: `v{YEAR}.{MONTH}.{DAY}` (e.g., `v2025.03.01`)
