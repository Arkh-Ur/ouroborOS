# Changelog

All notable changes to ouroborOS are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [0.2.0] — 2026-04-10

### Added

- **Desktop profiles** — Five selectable profiles at install time: `minimal` (TTY only), `hyprland`, `niri`, `gnome`, `kde`. Each profile ships the right package set and display manager by default.
- **Decoupled display manager selection** — DM can be overridden independently of the desktop profile (`none`, `gdm`, `sddm`, `plm`).
- **`our-pacman`** — Atomic package manager wrapper: takes a read-only snapshot of `@` before each `pacman -Syu`, then remounts `rw`, runs the upgrade, and remounts `ro`. Replaces the previous `ouroboros-upgrade` script.
- **`our-container`** — Full `systemd-nspawn` container manager with 17 commands: lifecycle (`create`, `enter`, `start`, `stop`, `remove`), snapshots, storage management, image management, and monitoring/diagnostics.
- **systemd-homed** — Per-user home encryption enabled by default (`subvolume` backend). First-boot migration service handles the transition non-interactively.
- **FSM reorder** — `USER` and `DESKTOP` states now run before `PARTITION`. All user input is collected before any disk is touched. Installer can be cancelled at any point before the partition confirmation with zero disk impact.
- **Remote config URL in INIT** — Unattended config can be fetched from a URL (e.g., a GitHub raw URL) at boot, in addition to the existing local file detection.
- **`our-container` autostart** — Containers can be configured to start automatically at boot via a systemd service.
- **E2E desktop profile tests** — Automated QEMU test suite validating all five profiles end-to-end.
- **`hyprpolkitagent`** — Polkit agent for Hyprland profile (replaces `polkit-gnome`).

### Changed

- **Mirror selection** — `reflector` now uses `--sort score` (server-side ranking) instead of `--fastest` (local benchmark). Eliminates multi-minute mirror benchmarking during install.
- **Pacman hook order** — Post-upgrade hook renamed to `zzz-post-upgrade.hook` to ensure correct ASCII sort order after all pacman operations complete.
- **`our-pacman` hook** — Moved from pre-transaction (ineffective) to a wrapper approach (modelled after openSUSE MicroOS). The wrapper owns the full upgrade cycle.
- **Btrfs root ro enforcement** — Changed from `btrfs property set / ro true` to `btrfs property set <subvol-path> ro true` via a subvolid=5 mount. Direct property set on a VFS ro mount (EROFS) is rejected by the kernel.
- **`graphical.target.wants`** — Now mirrored to the `@` subvolume during install so the display manager actually starts at boot.

### Fixed

- Circular deadlock in `our-pacman` when remounting immutable root.
- `homed` PAM configuration on Arch (uses `/etc/pam.d/sshd` directly, not `system-auth`).
- SSH `UseDNS=no` to avoid reverse DNS timeout on first connect.
- `network-online.target` blocking boot in QEMU SLIRP (added `--any --timeout=30` to `networkd-wait-online`).
- `zram-generator.conf`, `.network` files, and `resolved.conf` not mirrored to `@` subvolume — caused missing network and swap at boot.
- Journal socket `FAILED` at boot — masked `/var/log/journal` on `@` to prevent socket conflict.
- E2E test artifacts accidentally included in airootfs (inflated ISO size).
- ShellCheck violations across all test scripts (SC2054, SC2329, SC2086).
- Ruff violations: `collections.abc.Generator` (UP035), import ordering (I001), trailing whitespace (W293).

### Known Issues

- `homectl create --identity=JSON` fails in QEMU with a generic error. Workaround: use `homed_storage: classic` in E2E configs. Root cause under investigation (likely a D-Bus race or subvolume conflict in the QEMU environment).
- `bootctl set-oneshot` requires writable EFI variables. Fails in QEMU without a writable `OVMF_VARS.fd`. Works correctly on real hardware.

---

## [0.1.0] — 2026-04-07

Initial release.

### Added

- **Bootable live ISO** — UEFI-only, built with `archiso`. Base: ArchLinux, kernel `linux-zen`, compressor `zstd -19`.
- **Btrfs immutable layout** — Five subvolumes: `@` (root, mounted `ro`), `@var`, `@etc`, `@home`, `@snapshots`. fstab generated with UUIDs only.
- **Interactive TUI installer** — 11-state FSM (`INIT → PREFLIGHT → LOCALE → USER → DESKTOP → PARTITION → FORMAT → INSTALL → CONFIGURE → SNAPSHOT → FINISH`). Primary backend: `python-rich`. Fallback: `whiptail`.
- **Unattended install** — YAML config auto-detected from kernel cmdline, `/tmp/`, `/run/`, or USB drive. Flag `--validate-config` for pre-flight validation.
- **Checkpoint / resume** — Each destructive state writes a `.done` file. `--resume` flag picks up from the last completed state.
- **systemd-boot** — UEFI bootloader with boot entries for main system and install snapshot. `editor=no` enforced.
- **Microcode auto-detection** — Installer detects CPU vendor from `/proc/cpuinfo` and installs `intel-ucode` or `amd-ucode` automatically.
- **Baseline snapshot** — Read-only Btrfs snapshot `@snapshots/install` created immediately after installation. Matching boot entry added to `/boot/loader/entries/`.
- **systemd-networkd + iwd** — No NetworkManager. DNS via `systemd-resolved` with DNS-over-TLS (`opportunistic`), DNSSEC enabled, upstream: Cloudflare + Quad9.
- **zram swap** — `zram-generator` configured for `ram/2` with `zstd` compression. No swap partition.
- **SSH host keys** — Pre-generated during install so the installed system has SSH available immediately on first boot.
- **`ouroboros-upgrade` wrapper** — Atomic upgrade script: snapshot → remount rw → pacman → remount ro (predecessor to `our-pacman`).
- **CI/CD pipeline** — GitHub Actions: lint (shellcheck + ruff), build ISO on tag, publish release to public repo `Arkh-Ur/ouroborOS`.
- **93% pytest coverage** — Full test suite for installer state machine, config validation, TUI, and disk operations.
- **Developer tooling** — `src/scripts/setup-dev-env.sh`, `src/scripts/build-iso.sh`, `src/scripts/flash-usb.sh`.

### Architecture

| Layer | Technology |
|-------|-----------|
| Base OS | ArchLinux (rolling) |
| Kernel | linux-zen |
| Bootloader | systemd-boot (UEFI only) |
| Filesystem | Btrfs, root `ro` |
| Network | systemd-networkd + iwd |
| DNS | systemd-resolved (DoT) |
| Swap | zram-generator |
| Installer | Python 3 + Bash ops |
| ISO builder | archiso (mkarchiso) |

### Known Limitations (at release)

- UEFI only — no BIOS/legacy support by design.
- No GUI installer — TUI (`rich` / `whiptail`) and unattended YAML only.
- No Secure Boot — deferred to Phase 3.
- English only — multi-language installer deferred to Phase 3.
- No AUR helper — use `makepkg` manually.

[0.2.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.2.0
[0.1.0]: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.1.0
