# systemd Integration

ouroborOS is built entirely around the systemd ecosystem. This document describes each systemd component used, its role, and its configuration within the project.

---

## Bootloader: systemd-boot

**Package:** `systemd` (included)
**Role:** UEFI bootloader, replaces GRUB entirely.

### Configuration layout
```
/boot/
├── EFI/
│   └── systemd/
│       └── systemd-bootx64.efi
├── loader/
│   ├── loader.conf          ← global bootloader config
│   └── entries/
│       ├── ouroborOS.conf   ← default boot entry
│       └── ouroborOS-fallback.conf
└── vmlinuz-linux-zen
└── initramfs-linux-zen.img
```

### loader.conf
```ini
default  ouroborOS.conf
timeout  3
console-mode max
editor   no
```

### Boot entry (ouroborOS.conf)
```ini
title   ouroborOS
linux   /vmlinuz-linux-zen
initrd  /initramfs-linux-zen.img
options root=UUID=XXXX rootflags=subvol=@,ro quiet splash loglevel=3
```

**Installation:** `bootctl install` during installer post-config phase.
**Updates:** `bootctl update` via pacman hook.

---

## Network: systemd-networkd + iwd

**Role:** Replaces NetworkManager. Handles wired and wireless networking declaratively.

### Wired (DHCP)
```ini
# /etc/systemd/network/20-wired.network
[Match]
Name=en*

[Network]
DHCP=yes
DNS=1.1.1.1
DNSSec=yes
```

### Wireless (iwd backend)
```ini
# /etc/systemd/network/25-wireless.network
[Match]
Name=wl*

[Network]
DHCP=yes
IgnoreCarrierLoss=3s
```

**iwd** manages WiFi authentication; networkd manages addressing.

```ini
# /etc/iwd/main.conf
[General]
EnableNetworkConfiguration=false   # networkd handles this
```

**Units to enable:**
```
systemctl enable systemd-networkd.service
systemctl enable iwd.service
```

---

## DNS: systemd-resolved

**Role:** Local DNS stub resolver with DoT (DNS-over-TLS) support.

```ini
# /etc/systemd/resolved.conf
[Resolve]
DNS=1.1.1.1#cloudflare-dns.com 9.9.9.9#dns.quad9.net
FallbackDNS=8.8.8.8
DNSSEC=yes
DNSOverTLS=opportunistic
Cache=yes
```

```bash
# Symlink for compatibility
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
```

---

## Storage / Partitioning: systemd-repart

**Role:** Declarative partition creation during first boot or installation.
Used during the installer to define the target disk layout in code.

### Partition definitions
```ini
# /usr/lib/repart.d/10-esp.conf
[Partition]
Type=esp
Format=vfat
SizeMinBytes=512M
SizeMaxBytes=512M

# /usr/lib/repart.d/20-root.conf
[Partition]
Type=root
Format=btrfs
SizeMinBytes=10G
```

**Usage in installer:**
```bash
systemd-repart --dry-run=no --empty=force /dev/sda
```

---

## Home Directories: systemd-homed

**Role:** Portable, encrypted home directories per user.
Each user's home is a LUKS-encrypted image, unlockable via password or FIDO2 key.

```bash
# Create user with homed
homectl create alice --real-name="Alice" --storage=luks

# Inspect
homectl inspect alice
```

**Benefits for ouroborOS:**
- Home directory is portable (copy the image to another machine)
- Automatic encryption without separate LUKS setup
- Works with immutable root (home is always separate)

---

## First Boot Configuration: systemd-firstboot

**Role:** Prompt for locale, timezone, hostname, and root password on first real boot (or via installer).

```bash
systemd-firstboot \
  --locale=en_US.UTF-8 \
  --locale-messages=en_US.UTF-8 \
  --keymap=us \
  --timezone=UTC \
  --hostname=ouroborOS \
  --root-password-hashed="$6$..."
```

Used by the installer to pre-seed system configuration before handing off to user.

---

## Container / Chroot: systemd-nspawn

**Role:** Used during installation to chroot into the target system with full systemd support (instead of plain `arch-chroot`).

```bash
# Chroot into installed system
systemd-nspawn -D /mnt \
  --bind /etc/resolv.conf \
  /bin/bash
```

Benefits over plain chroot:
- Proper namespace isolation
- Mounts `/proc`, `/sys`, `/dev` correctly
- Can run systemd units inside the container

---

## Tmpfiles: systemd-tmpfiles

**Role:** Declarative creation of directories, symlinks, and files at boot. Used to handle read-only root compatibility.

```ini
# /usr/lib/tmpfiles.d/ouroborOS-compat.conf
# Create /usr/local from /var when root is read-only
L /usr/local - - - - /var/usrlocal
d /var/usrlocal 0755 root root -
```

---

## Unit Summary

| Unit | Enable at install | Purpose |
|------|------------------|---------|
| `systemd-networkd.service` | Yes | Network configuration |
| `systemd-resolved.service` | Yes | DNS resolution |
| `iwd.service` | Yes | WiFi management |
| `systemd-homed.service` | Yes | Encrypted home dirs |
| `systemd-timesyncd.service` | Yes | NTP time sync |
| `systemd-boot-update.service` | Yes | Auto-update bootloader |
| `fstrim.timer` | Yes | Weekly SSD TRIM |
| `systemd-oomd.service` | Yes | Out-of-memory daemon |

---

## Custom Installer Units (Live ISO)

During the live environment, these units manage the installer lifecycle:

```ini
# /etc/systemd/system/ouroborOS-installer.service
[Unit]
Description=ouroborOS Interactive Installer
After=network.target multi-user.target
ConditionPathExists=!/var/lib/ouroborOS-installed

[Service]
Type=oneshot
ExecStart=/usr/bin/ouroborOS-installer
StandardInput=tty
TTYPath=/dev/tty1
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```
