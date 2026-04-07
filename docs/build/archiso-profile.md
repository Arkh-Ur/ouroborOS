# Archiso Profile Reference

## What is an archiso profile?

An archiso profile is a directory containing all configuration needed to build an ArchLinux-based live ISO. The `mkarchiso` tool reads the profile and produces the ISO image.

---

## Profile Directory Layout

```
ouroborOS-profile/
├── profiledef.sh
├── pacman.conf
├── packages.x86_64
├── airootfs/
│   ├── etc/
│   │   ├── hostname
│   │   ├── locale.conf
│   │   ├── vconsole.conf
│   │   ├── mkinitcpio.conf
│   │   ├── os-release
│   │   ├── issue
│   │   ├── motd
│   │   ├── pacman.d/
│   │   │   └── mirrorlist
│   │   ├── systemd/
│   │   │   ├── system/
│   │   │   │   ├── ouroborOS-installer.service
│   │   │   │   ├── choose-mirror.service    (optional)
│   │   │   │   └── getty@tty1.service.d/
│   │   │   │       └── autologin.conf
│   │   │   └── system-preset/
│   │   │       └── 50-ouroborOS.preset
│   │   └── ssh/
│   │       └── sshd_config.d/
│   │           └── 10-ouroborOS.conf  (optional remote install)
│   └── usr/
│       └── local/
│           └── bin/
│               ├── ouroborOS-installer
│               └── ouroborOS-installer-tui
├── efiboot/
│   └── loader/
│       ├── loader.conf
│       └── entries/
│           ├── 01-ouroborOS.conf
│           └── 02-ouroborOS-accessibility.conf
└── syslinux/
    ├── archiso_sys-linux.cfg
    └── archiso_head.cfg
```

---

## Key Files

### airootfs/etc/os-release
```ini
NAME="ouroborOS"
PRETTY_NAME="ouroborOS Live"
ID=ouroborOS
ID_LIKE=arch
ANSI_COLOR="38;2;23;147;209"
HOME_URL="https://github.com/Arkhur-Vo/ouroborOS"
BUILD_ID=rolling
```

### airootfs/etc/mkinitcpio.conf
```bash
MODULES=(btrfs)
BINARIES=()
FILES=()
HOOKS=(base udev autodetect modconf kms keyboard keymap consolefont block btrfs filesystems fsck)
COMPRESSION="zstd"
COMPRESSION_OPTIONS=(-3)
```

Key: `btrfs` in both `MODULES` and `HOOKS` ensures Btrfs root can be mounted from initramfs.

### airootfs/etc/systemd/system/50-ouroborOS.preset
```
enable ouroborOS-installer.service
enable systemd-networkd.service
enable systemd-resolved.service
enable iwd.service
enable systemd-timesyncd.service
```

### airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf
```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \\u' --noclear --autologin root %I $TERM
```

Automatically logs in as root on tty1 to launch the installer.

### airootfs/etc/motd
```
╔════════════════════════════════════════╗
║         Welcome to ouroborOS          ║
║   ArchLinux-based Immutable Distro    ║
╚════════════════════════════════════════╝

The installer will start automatically.
Type 'ouroborOS-installer' to restart it manually.
```

---

## EFI Boot Entry

### efiboot/loader/loader.conf
```ini
default  01-ouroborOS.conf
timeout  5
console-mode auto
editor   no
```

### efiboot/loader/entries/01-ouroborOS.conf
```ini
title   ouroborOS Live Installer
linux   /arch/boot/x86_64/vmlinuz-linux-zen
initrd  /arch/boot/x86_64/initramfs-linux-zen.img
options archisobasedir=arch archisolabel=OUROBOROS_YYYYMM quiet splash
```

### efiboot/loader/entries/02-ouroborOS-accessibility.conf
```ini
title   ouroborOS Live (Accessibility)
linux   /arch/boot/x86_64/vmlinuz-linux-zen
initrd  /arch/boot/x86_64/initramfs-linux-zen.img
options archisobasedir=arch archisolabel=OUROBOROS_YYYYMM accessibility=on
```

---

## Customizing the Live Environment

### Adding packages
Add package names to `packages.x86_64`, one per line. Comments start with `#`.

### Adding files to the ISO root
Place files under `airootfs/`. Example:
- `airootfs/root/.bashrc` → becomes `/root/.bashrc` in the live system
- `airootfs/usr/local/bin/mytool` → becomes `/usr/local/bin/mytool`

### Running scripts at boot in live environment
Use `airootfs/etc/systemd/system/` to define one-shot services.

### File permissions
Declare non-standard permissions in `profiledef.sh`:
```bash
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/usr/local/bin/ouroborOS-installer"]="0:0:755"
  ["/usr/local/bin/ouroborOS-installer-tui"]="0:0:755"
)
```

---

## Validation Checklist

Before running `mkarchiso`:

- [ ] `profiledef.sh` has correct `iso_label` (no spaces, uppercase)
- [ ] `packages.x86_64` includes `linux-zen` and `btrfs-progs`
- [ ] `mkinitcpio.conf` has `btrfs` in MODULES and HOOKS
- [ ] Installer scripts are executable and present in `airootfs/usr/local/bin/`
- [ ] Systemd preset enables installer service
- [ ] EFI entries reference the correct kernel and initrd paths
