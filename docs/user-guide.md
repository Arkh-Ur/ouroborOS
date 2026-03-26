# ouroborOS — User Guide

This guide covers everything from booting the live USB to using the installed system.

---

## 1. Booting from the USB

1. Plug the ouroborOS USB into the target machine.
2. Power on (or restart) the machine.
3. Enter the UEFI boot menu — commonly **F12**, **F2**, **Del**, or **Esc** at power-on (varies by manufacturer).
4. Select the USB drive from the boot menu.
5. You will see the **systemd-boot** menu with a 3-second countdown:

```
ouroborOS 0.1.0
ouroborOS 0.1.0 (accessibility)
```

Press **Enter** or wait for the default entry to boot.

> **Note:** ouroborOS requires UEFI. Legacy BIOS boot is not supported.

---

## 2. Live environment overview

After booting, you are logged in automatically as **root** on tty1.
The MOTD shows:

```
  ouroborOS — Immutable ArchLinux — systemd-native

  Run 'ouroborOS-installer' to install to disk.
  Type 'systemctl status' to check service health.
```

**Switch between virtual terminals:**

```bash
# tty2, tty3, etc.
Ctrl+Alt+F2
Ctrl+Alt+F1   # back to tty1
```

---

## 3. Connect to the internet

### Ethernet (automatic)

Ethernet is configured automatically via `systemd-networkd`. Verify:

```bash
networkctl status
```

Expected output includes `State: routable` for your ethernet interface.

### WiFi with `iwctl`

```bash
# Launch the iwd interactive prompt
iwctl

# List wireless devices
device list

# Scan for networks on wlan0 (replace wlan0 with your interface name)
station wlan0 scan

# List available networks
station wlan0 get-networks

# Connect to a network (you will be prompted for the password)
station wlan0 connect "MyNetworkSSID"

# Exit iwctl
quit
```

Wait a few seconds, then verify the connection:

```bash
ping -c 3 archlinux.org
```

Expected output:

```
PING archlinux.org (95.217.163.246): 56 data bytes
64 bytes from 95.217.163.246: icmp_seq=0 ttl=51 time=22.4 ms
...
3 packets transmitted, 3 received, 0% packet loss
```

---

## 4. Interactive installation

Run the installer:

```bash
ouroborOS-installer
```

The TUI will guide you through:

| Step | What you configure |
|------|--------------------|
| Locale | Language, keyboard layout, timezone |
| Disk | Which disk to install to, optional LUKS encryption |
| User | Username and password |
| Confirm | Review and confirm before any disk writes |
| Install | Progress display while pacstrap runs |
| Configure | Bootloader, network, system settings |
| Finish | Summary and reboot prompt |

> **LUKS encryption:** If you enable it, you will be prompted for a passphrase at every boot.
> Use a strong passphrase and do not forget it — there is no recovery without it.

To resume an interrupted installation:

```bash
ouroborOS-installer --resume
```

Installation log:

```bash
tail -f /tmp/ouroborOS-install.log
```

---

## 5. Unattended installation

For automated deployments, create a config file and pass it to the installer.

### Minimal config (copy-paste ready)

```yaml
# /tmp/ouroborOS-config.yaml
disk:
  device: /dev/sda          # Replace with your target disk
  use_luks: false
  swap_type: zram

locale:
  locale: en_US.UTF-8
  keymap: us
  timezone: UTC             # Example: America/New_York, Europe/Madrid

network:
  hostname: myhost

user:
  username: alice
  # Generate hash: python3 -c "import crypt; print(crypt.crypt('yourpass', crypt.mksalt(crypt.METHOD_SHA512)))"
  password_hash: "$6$rounds=656000$YOURSALT$YOURHASH"
  groups: [wheel, audio, video, input]
  shell: /bin/bash
```

Save it to `/tmp/ouroborOS-config.yaml` and run:

```bash
ouroborOS-installer --config /tmp/ouroborOS-config.yaml
```

Or validate the config without installing:

```bash
ouroborOS-installer --validate-config /tmp/ouroborOS-config.yaml
```

### Config placed on USB auto-detection

The installer automatically looks for a config file at:

1. Kernel cmdline: `ouroborOS.config=/path/to/config.yaml`
2. `/tmp/ouroborOS-config.yaml`
3. `/run/ouroborOS-config.yaml`
4. Any `ouroborOS-config.yaml` on a mounted USB drive

---

## 6. First boot into the installed system

After installation, remove the USB and reboot:

```bash
reboot
```

The systemd-boot menu will show:

```
ouroborOS
ouroborOS (fallback initramfs)
ouroborOS snapshot (install)   ← baseline snapshot from installation
```

Log in with the username and password you set during installation.

### Verify core services are running

```bash
systemctl status systemd-networkd
systemctl status systemd-resolved
systemctl status systemd-timesyncd
```

All three should show `active (running)`.

```bash
# Check no units failed
systemctl --failed
```

Expected: `0 loaded units listed.`

---

## 7. Connect to WiFi after installation

WiFi works the same way as in the live environment:

```bash
iwctl
station wlan0 scan
station wlan0 get-networks
station wlan0 connect "MyNetworkSSID"
quit
```

The connection persists across reboots — `iwd` saves known networks to `/var/lib/iwd/`.

---

## 8. Install software

ouroborOS uses `pacman` for package management. The root filesystem is read-only, but `pacman` handles this transparently.

```bash
# Search for a package
pacman -Ss neovim

# Install a package
sudo pacman -S neovim tmux htop

# Update the entire system
sudo pacman -Syu

# Remove a package
sudo pacman -Rns packagename
```

> Every `sudo pacman -S/R/U` automatically creates a Btrfs snapshot before applying changes.
> If an update breaks something, you can roll back (see next section).

---

## 9. Roll back to a previous snapshot

### From the running system

List available snapshots:

```bash
ls /.snapshots/
```

```
install          ← baseline from installation
2026-03-26T143012
2026-03-27T091500
```

To boot into a snapshot, reboot and select it from the systemd-boot menu.

### From the boot menu

1. Restart the machine.
2. At the systemd-boot menu, press **↑/↓** to select:
   ```
   ouroborOS snapshot (2026-03-26T143012)
   ```
3. Press **Enter** to boot into that snapshot.

The snapshot is mounted read-only. From there you can:
- Investigate what went wrong
- Promote the snapshot to the active root (advanced — see architecture docs)

---

## 10. Useful commands reference

```bash
# Network status
networkctl status
resolvectl query archlinux.org

# Disk and Btrfs
lsblk -f
btrfs subvolume list /
btrfs filesystem show /

# Snapshots
ls /.snapshots/
btrfs subvolume list /.snapshots

# Boot entries
bootctl status
ls /boot/loader/entries/

# Journal logs
journalctl -b                   # current boot
journalctl -b -1                # previous boot
journalctl -u systemd-networkd  # specific unit

# Installer log (after installation)
cat /tmp/ouroborOS-install.log
```

---

## 11. Known limitations (v0.1)

| Limitation | Notes |
|-----------|-------|
| UEFI only | Legacy BIOS boot is not supported |
| English only | Installer UI is English only |
| No GUI | Terminal/TUI installer only |
| No AUR | No AUR helper included; use `makepkg` manually |
| No Secure Boot | TPM2/MOK not configured in v0.1 |
| No ARM support | x86_64 only |
