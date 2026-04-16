# Changelog

All notable changes to ouroborOS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.8] - 2026-04-16

### Added

- TPM2 auto-unlock for LUKS (`disk.tpm2_unlock: true` in YAML). Binds the LUKS
  slot to TPM2 PCR 7+14 (Secure Boot state + measured boot) using
  `systemd-cryptenroll`. The disk unlocks automatically at boot if the boot chain
  is unmodified. Falls back to passphrase if TPM2 is absent or measurements change.
- Installer TUI: TPM2 prompt shown after LUKS passphrase input. Detects
  `/sys/class/tpm/tpm0` and warns if no TPM2 is present.
- `ouroboros-secureboot tpm2-enroll [DEVICE]` — enroll LUKS partition with TPM2
  post-install. Auto-detects device from `/etc/crypttab` if not specified.
- `ouroboros-secureboot tpm2-status` — show TPM2 presence, PCR 7+14 values,
  and current LUKS slot enrollment.
- `tpm2-tools` added to `packages.x86_64` (live ISO).
- `SecurityConfig.tpm2_unlock` field in `config.py` with YAML validation
  (requires `disk.use_luks: true`).

## [0.4.7] - 2026-04-16

### Added

- Desktop profiles: COSMIC Desktop profile — fully in `[extra]`, no AUR required.
  Includes `cosmic-session`, `cosmic-comp`, `cosmic-terminal`, `cosmic-files`,
  `cosmic-launcher`, `cosmic-settings`, `cosmic-applets`, `cosmic-notifications`,
  `cosmic-bg`, `cosmic-idle`, `cosmic-panel`, `cosmic-osd`, `cosmic-app-library`,
  `xdg-desktop-portal-cosmic`.
- Desktop profiles: `greetd` display manager option — used by COSMIC profile with
  `cosmic-greeter`. `configure.sh` writes `/etc/greetd/config.toml` and creates
  the `greeter` system user automatically.
- Desktop profiles: KDE flavor selector — `kde_flavor` field in YAML and TUI.
  Options: `plasma-meta` (recommended, ~1 GB), `plasma` (full, ~1.5 GB),
  `plasma-desktop` (minimal, ~400 MB). Dynamically injected as first package
  in `packages_for()`.
- Desktop profiles: GPU driver detection and selection — `gpu_driver` field in YAML
  and TUI. `_detect_gpu()` probes `lspci` and suggests the appropriate driver.
  `configure.sh` installs: `nvidia` (proprietary), `nvidia-open`, `mesa`/`amdgpu`,
  or `vulkan-intel` for auto-detected Intel. `none` skips install.
- `config.py`: `DesktopConfig.kde_flavor` and `DesktopConfig.gpu_driver` fields
  with YAML loading and validation.

### Changed

- Desktop profiles: Hyprland profile migrated to the Hypr ecosystem.
  `wofi` replaced by `hyprlauncher` (Hypr ecosystem launcher, in `[extra]`).
  `hyprlock`, `hypridle` moved from AUR to regular packages (now in `[extra]`).
  Added `hyprpaper`, `hyprsunset`, `hyprland-qt-support`.
  `hyprshot` removed from AUR defaults — `grim`+`slurp` already provide screenshot
  capability; `quickshell` remains as the only AUR package for this profile.
- `desktop_profiles.py`: `packages_for()` accepts optional `kde_flavor` parameter.
  `VALID_DMS` and DM tables updated to include `greetd`.

### Fixed

- CI: dry-run test was failing after erofs migration: `mksquashfs` mock replaced
  with `mkfs.erofs` mock to match the updated preflight check in `build-iso.sh`.

## [0.4.6] - 2026-04-15

### Added

- Boot entries: `architecture x64` field added to `01-ouroborOS.conf` and
  `02-ouroborOS-accessibility.conf` (systemd-boot spec compliance).

### Changed

- ISO: airootfs compression migrated from `squashfs` (zstd-15) to `erofs`
  (lzma + ztailpacking). Faster kernel mount at boot; `erofs-utils` already
  present in CI build environment.
- `build-iso.sh`: `mksquashfs` preflight check replaced with `mkfs.erofs`;
  `--version` flag now also injects version into `os-release` (VERSION_ID,
  PRETTY_NAME) and boot entry titles in addition to `profiledef.sh`.
- `profiledef.sh`: `iso_publisher` URL corrected to `Arkh-Ur` (was `Arkhur-Vo`).

### Fixed

- Installer: keyboard layout selected in the locale screen was never applied to
  the live environment. `loadkeys` is now called immediately after the user
  selects a keymap, so the layout takes effect for the rest of the installation.

## [0.4.5] - 2026-04-15

### Added

- Desktop profiles: `grim` + `slurp` added to Hyprland (screenshot backend required by `hyprshot` AUR).
- Desktop profiles: `dunst` added to Hyprland (notification daemon).
- Desktop profiles: `thunar` added to Hyprland (lightweight file manager, avoids KDE dep chain).
- Desktop profiles: `waybar` + `mako` + `swaylock` + `swaybg` + `swayidle` added to Niri
  (status bar, notifications, lock screen, wallpaper, idle daemon — all previously missing).
- ISO: `cryptsetup` added to `packages.x86_64` — required by `disk.sh` `encrypt_partition()`;
  any installation with `use_luks: true` previously failed with `command not found`.
- ISO: `pciutils` + `usbutils` + `diffutils` added for hardware diagnostics in the live environment.
- CI: Explicit verification step after `mkarchiso` awk patch — fails immediately with a clear
  `::error::` message if the patch did not apply, instead of failing silently deep in the build.

### Changed

- Desktop profiles: KDE profile replaces `kde-applications-meta` (~300 packages, ~1.5 GB of
  games, education and office suites) with a curated set: `dolphin konsole kate gwenview ark
  ffmpegthumbs`. Reduces KDE install size from ~1.5 GB to ~400 MB.
- CI: `actions/checkout` upgraded from `v4` to `v5` (Node.js 20 deprecates on 2026-06-02).
- CI: `mkarchiso` awk patch hardened to use `[[:space:]]+` instead of hardcoded 4-space
  indent, and adds a function-end guard (`}`) to prevent false matches in other functions.

### Fixed

- `our-rollback promote`: orphaned boot entry `ouroboros-snapshot-<name>.conf` was left on
  the ESP after the atomic swap, pointing to `@snapshots/<name>` which no longer exists.
  The entry is now removed and `bootctl set-default ouroborOS.conf` is called explicitly
  to reset the default boot target to `@`.
- ISO: `linux-zen-headers` removed from the live ISO — only needed for DKMS on the installed
  system; already installed via `pacstrap` (-30 MB).
- ISO: `flatpak` removed from the live ISO — installed on-demand post-install via `our-flat` (-15 MB).
- `os-release`: `VERSION_ID` and `PRETTY_NAME` were frozen at `0.1.0` since initial release.
  Updated to `0.4.5`. Also corrects `HOME_URL` to `Arkh-Ur` (was `Arkhur-Vo`).

## [0.4.4] - 2026-04-15

### Fixed

- CI: `mkarchiso` patch pipeline failing due to non-zero `du` exit code in
  `_make_efibootimg()`. Added `|| true` to prevent pipefail from aborting the build.
- CI: `python3` not available in the Arch Linux base container image.
  Replaced Python-based mkarchiso patch with `awk`.
- CI: `mkarchiso` losing execute permission after `awk` patch (temp file via redirect
  drops original permissions). Fixed by adding `chmod +x` after `mv`.
- CI: `head -1` interpreted as an invalid flag by `sh` (dash) in the runner.
  Changed to POSIX-compliant `head -n 1` throughout the workflow.

## [0.4.3] - 2026-04-13

### Fixed

- Display manager (SDDM/GDM/PLM) not starting automatically after install.
  The system booted to `multi-user.target` (Arch default) even when a DM was
  enabled. Added `systemctl set-default graphical.target` in `configure.sh`.
- `our-aur` and `our-flat` not executable on the live ISO (644 permissions).
  Fixed to 755.
- WiFi credentials from the live ISO not passed to the installed system.
  `show_wifi_connect()` now returns `{ssid, passphrase}` so `configure.sh`
  can write the iwd PSK file on the target.
- Ruff lint violations (F841 unused variables, E501 line too long) in test files.

## [0.4.2] - 2026-04-13

### Added

- WiFi TUI with signal bars, real dBm values, quality labels (Excellent/Fair/Weak),
  pagination (10 networks/page), re-scan, and manual SSID entry for hidden networks.
  Both Rich and Whiptail backends updated.
- `iw` package added to the ISO for WiFi interface detection (`iw dev`).

### Fixed

- WiFi interface never detected. `_find_wifi_interface()` checked for
  `type station` but `iw` reports `type managed`. Also added `rfkill unblock`
  and a retry loop for slow driver init.
- `iwd.service` not enabled in the live ISO, making WiFi non-functional on boot.
  Added `After=iwd.service` to the installer service.
- Boot menu showing `ouroborOS 0.1.0` instead of the current version.

## [0.4.1] - 2026-04-13

### Fixed

- GitHub Actions CI/CD pipeline:
  - `PUBLIC_REPO_TOKEN` checked at runtime instead of in YAML `if` conditions.
  - Release job skipped on public repo where the token is absent.
  - Release notes passed via environment variable to prevent backtick injection.
  - Existing release deleted before recreating on hotfix re-runs.
  - `--force` added to tag push in build workflow.
- Ruff lint violations (I001, ANN001, E501) caught by CI.

## [0.4.0] - 2026-04-12

### Added

- `our-aur` — Containerized AUR helper using systemd-sysext. Isolates AUR
  builds in ephemeral nspawn containers. Supports lazy install queue.
- `our-flat` — Flatpak wrapper with pacman-style interface
  (install/remove/update/search/list/info/remote).
- Lazy AUR queue — First boot mechanism: packages queued during install are
  installed by `ouroboros-firstboot` using `our-aur`.
- `/var/lib/extensions` — systemd-sysext directory for containerized AUR builds.

### Changed

- `our-pacman` renamed to `our-pac` for consistency with `our-*` naming.

### Fixed

- AUR RPC URL pointing to non-existent v6 — aligned to v5.
- Appstream cache not updated after Flatpak remote-add.
- AUR queue file not cleaned up on failure.
- our-aur not included in installer tools copy.
- Regex pipe escaping in E2E phase 4 tests.

## [0.3.0] - 2026-04-11

### Added

- `our-snapshot` — CLI for Btrfs snapshot management:
  list/create/delete/prune/info/boot-entries sync/scrub.
- `our-rollback` — One-command rollback:
  now/promote/status/undo.
- Shell selector — `bash`, `zsh`, `fish` selectable at install time.
- `our-wifi` — Interactive WiFi manager wrapping `iwctl`.
- `ouroboros-firstboot` — Oneshot service: mirrors, machine-id, timers.
- `our-snapshot-prune.timer` — Weekly automatic snapshot prune.
- `ouroboros-secureboot` — Secure Boot management via `sbctl`.
- `SECURE_BOOT` FSM state — New installer state for Setup Mode guidance.
- `our-container --isolated` — Private container networking with NAT.
- `our-container --gui` — Wayland/GPU/audio passthrough for graphical containers.
- `our-bluetooth` — Bluetooth manager with BLE LE support.
- `our-fido2` — FIDO2/WebAuthn CLI: token management, BLE, PAM, SSH, LUKS2.
- `security.fido2_pam` YAML field for PAM integration.
- BlueZ experimental mode for CTAP2 hybrid QR passkey flow.
- BLE LE tuning (`AdvMonAllowlistScanDuration`, `ExchangeMTU`).
- FIDO2 BLE udev rules for HID-over-GATT access.
- `our-pac` hardening: free space check, JSON logging, auto-prune.
- systemd-homed fallback to classic `useradd` on failure.
- Test coverage >= 93%.

### Changed

- `ouroboros-upgrade` removed — use `our-pac` directly.
- `our-container` internal references cleaned up from `our-box`.
- Snapshot metadata JSON with timestamp, type, description, packages_count.
- Boot entries regenerated for all snapshots with correct `rootflags`.

### Fixed

- `homectl create` crash in QEMU — automatic fallback to classic user creation.
- `our-container` help text still referencing `our-box`.
- `rootflags` in boot entries incorrectly prefixed with `/`.
- WiFi PSK files not written with correct permissions.

## [0.2.0] - 2026-04-10

### Added

- Desktop profiles — Five selectable: minimal, hyprland, niri, gnome, kde.
- Decoupled display manager selection (none, gdm, sddm, plm).
- `our-pac` — Atomic package manager wrapper with snapshot-based upgrades.
- `our-container` — Full systemd-nspawn container manager (17 commands).
- systemd-homed — Per-user home encryption (subvolume backend).
- FSM reorder — User input collected before any disk changes.
- Remote config URL in INIT state.
- `our-container` autostart via systemd service.
- E2E desktop profile tests in QEMU.
- `hyprpolkitagent` for Hyprland profile.

### Changed

- Mirror selection uses `reflector --sort score` instead of `--fastest`.
- Pacman hook renamed to `zzz-post-upgrade.hook`.
- `our-pac` changed to wrapper approach (like openSUSE MicroOS).
- Btrfs root ro enforcement via subvolid=5 mount.
- `graphical.target.wants` mirrored to `@` subvolume during install.

### Fixed

- Circular deadlock in `our-pac` when remounting immutable root.
- `homed` PAM configuration on Arch.
- SSH `UseDNS=no` to avoid reverse DNS timeout.
- `network-online.target` blocking boot in QEMU SLIRP.
- Config files not mirrored to `@` subvolume.
- Journal socket `FAILED` at boot.
- E2E test artifacts in airootfs.
- ShellCheck and Ruff violations.

## [0.1.0] - 2026-04-07

### Added

- Bootable live ISO — UEFI-only, ArchLinux, kernel linux-zen, zstd -19.
- Btrfs immutable layout — Five subvolumes: @, @var, @etc, @home, @snapshots.
- Interactive TUI installer — 11-state FSM with Rich/whiptail backends.
- Unattended install via YAML config.
- Checkpoint / resume support.
- systemd-boot with editor=no.
- Microcode auto-detection (Intel/AMD).
- Baseline Btrfs snapshot with boot entry.
- systemd-networkd + iwd (no NetworkManager).
- zram swap (ram/2, zstd).
- SSH host keys pre-generated during install.
- `ouroboros-upgrade` atomic upgrade script.
- CI/CD pipeline (GitHub Actions: lint, build, release).
- 93% pytest coverage.
- Developer tooling scripts.

[0.4.8]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.8
[0.4.7]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.7
[0.4.6]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.6
[0.4.5]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.5
[0.4.4]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.4
[0.4.3]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.3
[0.4.2]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.2
[0.4.1]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.1
[0.4.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.0
[0.3.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.3.0
[0.2.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.2.0
[0.1.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.1.0
