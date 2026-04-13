# Changelog

All notable changes to ouroborOS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.4.3]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.3
[0.4.2]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.2
[0.4.1]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.1
[0.4.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.4.0
[0.3.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.3.0
[0.2.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.2.0
[0.1.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.1.0
