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

ouroborOS has four package managers for different sources: **`our-pac`** (official repos via pacman), **`our-aur`** (AUR packages), **`our-flat`** (Flatpak apps), and **`our-app`** (AppImages). Because the root filesystem is read-only, you must use these wrappers — never call `pacman` directly.

### 8.1 Official packages — `our-pac`

`our-pac` wraps `pacman` with automatic snapshot creation and root unlock/relock:

```bash
# Search for a package
pacman -Ss neovim

# Install a package
sudo our-pac -S neovim tmux htop

# Update the entire system
sudo our-pac -Syu

# Remove a package
sudo our-pac -Rns packagename
```

Before every `our-pac` write operation, a timestamped Btrfs snapshot is created and a systemd-boot entry is added. If the upgrade breaks something, roll back (see section 9).

> If `systemd-sysext` extensions (AUR packages) are active when you run `our-pac`, they are automatically unmerged before pacman runs and re-merged afterward. This is transparent.

### 8.2 AUR packages — `our-aur`

`our-aur` installs AUR packages as read-only `systemd-sysext` extensions. No AUR helper (paru, yay) is required.

```bash
# Install an AUR package
sudo our-aur -S hyprcaffeine

# List installed AUR packages
our-aur -Q

# Remove an AUR package
sudo our-aur -R hyprcaffeine

# Update all AUR packages
sudo our-aur -Su
```

AUR packages are installed as sysext extensions in `/var/lib/extensions/our-aur-<pkg>/` and are immediately available after installation. They overlay `/usr` without touching the immutable root.

### 8.3 Flatpak apps — `our-flat`

Flatpak is not installed by default. Install it first, then enable Flathub:

```bash
# Install flatpak via our-pac
sudo our-pac -S flatpak

# Add Flathub remote (explicit opt-in required)
sudo our-flat remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# Install an app
sudo our-flat -S org.videolan.VLC

# List installed apps
our-flat -Q

# Update all apps
sudo our-flat -Su

# Remove an app
sudo our-flat -R org.videolan.VLC
```

Flatpak apps are installed system-wide in `/var/lib/flatpak/` and never touch the immutable root.

### 8.4 AppImages — `our-app`

`our-app` manages AppImages with the same pacman-style interface. An AppImage is a single self-contained executable, so — unlike AUR packages — it needs no `systemd-sysext` overlay. Everything lives in `/var/lib/ouroboros/appimages/` on the always-writable `@var` subvolume.

```bash
# Install from a URL (name derived from the filename if omitted)
sudo our-app -S https://example.com/Foo-x86_64.AppImage foo

# Install from a local file
sudo our-app -S ./Bar.AppImage

# List installed AppImages
our-app -Q

# Show info for one (version, source, install date)
our-app -Si foo

# Update all (re-downloads from each stored source URL)
sudo our-app -Su

# Remove an AppImage
sudo our-app -R foo
```

On install, `our-app` extracts the bundled `.desktop` entry and icon (`--appimage-extract`, no FUSE required), rewrites `Exec=` to the stored path, and links both into `/var/lib/ouroboros/appimages/share/`. A login snippet (`/etc/profile.d/ouroboros-appimages.sh`) adds that directory to `XDG_DATA_DIRS`, so launchers discover the entry without writing to the immutable `/usr`. New entries appear after a re-login.

> Because AppImages live only in `@var`, they are **not** captured by root snapshots — exactly like Flatpak apps. Rolling back `@` via `our-rollback` does **not** remove installed AppImages. Also, `-Su` can only update AppImages whose source was an `http(s)` URL; locally-installed files are skipped. See `docs/architecture/our-app.md` for the full design.

### 8.5 Containers — `our-container`

`our-container` manages containers across three engines:

| Engine | Kind | Use it for |
|--------|------|-----------|
| `nspawn` (default) | System container (`systemd-nspawn`) | OS-centric containers, Btrfs snapshots, a full booted Arch userland |
| `podman` | OCI, daemonless | App-centric containers from Docker Hub / OCI registries |
| `docker` | OCI, daemon | Same as podman, on a Docker daemon |

The default engine lives in `/etc/ouroboros/container.conf`; each container records its own engine in `/etc/ouroboros/containers.d/<name>.conf`, so every subcommand routes automatically.

```bash
# See available engines and the active default
our-container engine show

# Make podman the default engine (must be installed)
sudo our-container engine set podman

# Create a system container (nspawn — the default)
sudo our-container create devbox arch

# Create an OCI container from Docker Hub (per-create override)
sudo our-container create ub docker.io/library/ubuntu --engine podman

# Enter, list (across all engines), stop, remove
sudo our-container enter ub
our-container list
sudo our-container stop ub
sudo our-container remove ub
```

Repositories make images easy to discover and install. The registry lives at `/etc/ouroboros/container-repos.conf` and ships with the nspawn index plus `docker.io`.

```bash
# Register a registry (type autodetected, or pass it: index|direct|oci)
sudo our-container repo add ghcr ghcr.io oci
our-container repo list

# Search installable images across configured repos
our-container image available alpine

# Show details / the Docker Hub README for an image
our-container image info ubuntu
```

> **Windows ISOs are out of scope.** A container shares the host's Linux kernel, so Windows needs a virtual machine, not a container. OCI images (Docker Hub) are served through the `podman`/`docker` engines — they are not converted into `nspawn` rootfs tarballs. Only `nspawn` containers live on `@var`-backed Btrfs subvolumes and can be snapshotted independently; OCI containers are managed by their engine's own storage.

### 8.6 Dev environments and desktop apps — `our-box`

`our-box` is the user-space counterpart to `our-container`. It runs rootless containers via **podman** (no sudo required), mounts your home directory inside the box, and maps your host UID so files created inside are owned by you on the outside. Designed for development environments, throwaway shells, and GUI apps isolated from the host.

**Box types** are starting-point presets — every flag remains overridable regardless of type:

| Type | Default mounts/flags | Use it for |
|------|----------------------|-----------|
| `dev` | home + Wayland + audio | Development inside the box — coding, builds, AI/ML (add `--gpu` for CUDA) |
| `ephemeral` | none, `--rm` | Throwaway shells — gone when you exit |
| `app` | Wayland + GPU + audio | GUI apps shown on your desktop (Firefox, Spotify, etc.) |

```bash
# Create a dev box (home directory mounted automatically)
our-box create mydev docker.io/library/archlinux --type dev

# Enter it (auto-starts if stopped)
our-box enter mydev

# Create a CUDA dev box for AI/ML work
our-box create aidev nvidia/cuda:12.0-base --type dev --gpu

# Throwaway Alpine shell
our-box create scratch docker.io/library/alpine --type ephemeral

# GUI Firefox, isolated from the host
our-box create firefox docker.io/library/ubuntu --type app

# Export an app as a .desktop entry (shows in your launcher)
our-box export firefox firefox

# List all boxes (running + stopped)
our-box list

# Remove a box and its metadata
our-box remove mydev
```

**Lazy engine install** — if podman is not installed, `our-box` installs it automatically via `our-pac` on first use. Pass `--engine docker` to use Docker instead.

**Migrate from distrobox or toolbox** (if you used either before):

```bash
our-box migrate --from distrobox mybox
our-box migrate --from toolbox mybox
```

> `our-box` boxes live entirely in `$XDG_DATA_HOME/our-box/` and `$XDG_CONFIG_HOME/our-box/` — no system paths, no root. This is by design: `our-container` owns system containers (admin, `@var`-backed Btrfs, full systemd boot); `our-box` owns user containers (developer, XDG paths, rootless). See `docs/architecture/our-box.md` for the full design.

---

## 9. Roll back to a previous snapshot

### List snapshots

```bash
sudo our-snapshot list
```

Output:
```
    NAME                            TYPE        SIZE
    ----                            ----        ----
    install                         ro          1.2 GiB   ← installation baseline
    2026-03-26T143012               ro          840 MiB
  * 2026-03-27T091500               ro          220 MiB   ← currently running
```

### Boot once from a snapshot (safe — non-destructive)

```bash
sudo our-rollback try 2026-03-26T143012
# → reboot and the system boots from that snapshot once
# → next reboot returns to the default automatically
```

### Make a snapshot permanent (promote)

```bash
sudo our-rollback promote 2026-03-26T143012
# → replaces @ with the snapshot; original snapshot is preserved as a restore point
# → reboot required for the change to take effect
```

### From the boot menu

1. Restart the machine.
2. At the systemd-boot menu, press **↑/↓** to select a snapshot:
   ```
   ouroborOS snapshot (2026-03-26T143012)
   ```
3. Press **Enter** to boot into that snapshot.

### Undo the last promote

```bash
sudo our-rollback undo
```

---

## 10. System health and diagnostics

```bash
# Check system health (12 checks: root RO, failed units, disk space, etc.)
sudo ouroboros-health

# Run in doctor mode — detect and optionally fix issues
sudo ouroboros-health --doctor

# Output as YAML or JSON (for scripts)
sudo ouroboros-health --yaml
sudo ouroboros-health --json
```

### Check the system manifest

The declarative manifest is at `/etc/ouroboros/system.yaml`. It records the installed packages, users, and configuration at install time, and is updated when you install/remove packages via `our-pac`.

```bash
cat /etc/ouroboros/system.yaml
```

### Check for OTA updates

```bash
sudo ouroboros-rebase --dry-run
```

---

## 11. Multi-user management

Users are declared in the install config. After installation, manage them with standard tools:

```bash
# List users
cat /etc/passwd | grep -v nologin

# Add a user (write to / temporarily — use our-pac's approach)
# Use useradd directly — but first unlock root via our-pac or our-snapshot

# Check homed status
systemctl status systemd-homed
homectl list
```

For homed-managed users (`homed_storage: directory` or `luks`):
```bash
homectl inspect <username>
homectl passwd <username>
```

> **Note:** `homed_storage: subvolume` is known to fail when `/home` is a Btrfs subvolume (`@home`). Use `classic` or `directory` for reliable operation.

---

## 12. Bluetooth

Bluetooth is disabled by default. To enable it:

```bash
sudo our-pac -S bluez bluez-utils
sudo systemctl enable --now bluetooth.service
```

If `bluetooth: enable: true` was set in the install config, `bluetooth.service` is enabled automatically on first boot.

---

## 13. Useful commands reference

```bash
# Network status
networkctl status
resolvectl query archlinux.org

# Disk and Btrfs
lsblk -f
btrfs subvolume list /
btrfs filesystem show /

# Snapshots
sudo our-snapshot list
sudo our-snapshot create --name my-backup
sudo our-snapshot delete 2026-03-26T143012

# Rollback
sudo our-rollback list
sudo our-rollback try <snapshot>      # one-shot boot
sudo our-rollback promote <snapshot>  # permanent
sudo our-rollback undo                # revert promote

# AUR packages
sudo our-aur -S <pkg>
our-aur -Q
sudo our-aur -R <pkg>

# Flatpak
sudo our-flat remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo
sudo our-flat -S <app-id>
our-flat -Q

# AppImages
sudo our-app -S <url|path> [name]
our-app -Q
sudo our-app -R <name>

# Boot entries
bootctl status
ls /boot/loader/entries/

# Journal logs
journalctl -b                   # current boot
journalctl -b -1                # previous boot
journalctl -u systemd-networkd  # specific unit

# System manifest
cat /etc/ouroboros/system.yaml

# Health check
sudo ouroboros-health
```

---

## 14. Known limitations (v0.5.x)

| Limitation | Notes |
|-----------|-------|
| UEFI only | Legacy BIOS boot is not supported |
| No GUI installer | Rich TUI only; GUI planned for Phase 6 |
| homed subvolume backend | Fails when `/home` is `@home` subvolume — use `classic` or `directory` |
| No ARM support | x86_64 only; ARM planned for Phase 6 |
| AUR interactive PKGBUILDs | Packages with interactive prompts during build will fail |
| Flatpak not pre-installed | Must install via `our-pac -S flatpak` first |
| AppImage `-Su` needs a URL source | AppImages installed from a local file cannot be auto-updated (nothing to re-fetch) |
| AppImage entries need re-login | `XDG_DATA_DIRS` is set at login; already-running sessions pick up new entries after re-login |
| OTA image-based updates | casync-based OTA planned for Phase 6; current rebase is source-based |
