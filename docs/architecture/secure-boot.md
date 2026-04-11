# Secure Boot in ouroborOS

ouroborOS implements UEFI Secure Boot using [`sbctl`](https://github.com/Foxboron/sbctl) —
a stateless key management tool that creates a custom Platform Key (PK), Key Exchange Key
(KEK), and Signature Database (db) without shims or MOK.

---

## Architecture Overview

```
UEFI Firmware (Setup Mode)
    │
    ▼
sbctl create-keys          → /var/lib/sbctl/keys/{PK,KEK,db}/
    │
    ▼
sbctl enroll-keys [-m]     → Enrolls keys into firmware
    │  (-m includes Microsoft 3rd-party keys for hardware compatibility)
    ▼
sbctl sign -s <EFI>        → Signs and tracks files
    │
    ▼
Secure Boot: ON            → Only signed binaries boot
```

### Key Storage

sbctl stores keys in `/var/lib/sbctl/keys/`. This directory lives on the `@var` Btrfs
subvolume (read-write, survives snapshots). Keys survive system updates and rollbacks.

---

## Installation Flow

### Prerequisites

The firmware must be in **Setup Mode** before `sbctl enroll-keys` runs. Setup Mode means
the firmware's Secure Boot database has been cleared — the firmware will accept a new PK.

The installer guides the user through this in the `SECURE_BOOT` FSM state (between `DESKTOP`
and `PARTITION`). See `src/installer/state_machine.py` and `src/installer/tui.py`.

### During Install (configure.sh)

When `security.secure_boot: true` in the install config YAML, `configure.sh` runs inside
the chroot:

```bash
# 1. Create custom keys (PK/KEK/db)
sbctl create-keys

# 2. Enroll into firmware — -m adds Microsoft 3rd-party keys
#    (required for hardware with Microsoft-signed option ROMs: NVMe, GPU, etc.)
sbctl enroll-keys -m     # or sbctl enroll-keys without -m

# 3. Sign bootloader and kernel
sbctl sign -s /boot/EFI/systemd/systemd-bootx64.efi
sbctl sign -s /boot/EFI/BOOT/BOOTX64.EFI
sbctl sign -s /boot/vmlinuz-linux-zen

# 4. Verify nothing is unsigned
sbctl verify
```

sbctl ships a pacman PostTransaction hook that re-signs all tracked files after every
package update, so kernel and bootloader updates are handled automatically.

---

## Post-Install Management

Use `ouroboros-secureboot` for all Secure Boot management:

```
ouroboros-secureboot setup          # Initial setup (needs firmware in Setup Mode)
ouroboros-secureboot status         # Show status + list any unsigned files
ouroboros-secureboot sign-all       # Re-sign all tracked files manually
ouroboros-secureboot verify         # Verify all tracked files are signed
ouroboros-secureboot rotate-keys    # Generate new keys and re-sign everything
```

---

## Integration with our-pacman

`our-pacman` calls `sbctl sign-all` after every successful update if Secure Boot is active:

```bash
# In our-pacman (post-update hook):
if command -v sbctl &>/dev/null && sbctl status 2>/dev/null | grep -q "Secure Boot.*enabled"; then
    sbctl sign-all || log_warn "sbctl sign-all failed — check unsigned binaries with: ouroboros-secureboot status"
fi
```

The pacman PostTransaction hook from the `sbctl` package also runs, providing a second
signing pass for files that pacman tracks directly.

---

## YAML Configuration

```yaml
security:
  secure_boot: false               # true → run sbctl setup during install
  sbctl_include_ms_keys: false     # true → sbctl enroll-keys -m (adds Microsoft keys)
```

`sbctl_include_ms_keys: true` is recommended for systems with:
- NVIDIA GPUs (signed firmware)
- NVMe drives with Microsoft-signed option ROMs
- Any hardware that requires Microsoft 3rd-party signing

---

## Known Limitations

### QEMU / Virtual Machines

Secure Boot cannot be enrolled in QEMU using the default `OVMF_CODE.fd` + `OVMF_VARS.fd`
setup because:

1. `OVMF_VARS.fd` is typically read-only in test setups
2. QEMU's OVMF does not expose a real Secure Boot database to `sbctl enroll-keys`

For VM testing, use a pre-enrolled OVMF image or test on real hardware.

### Microsoft Key Inclusion

`sbctl enroll-keys` without `-m` creates a minimal key set that excludes Microsoft's
3rd-party signing keys. This blocks firmware components (option ROMs, PCI firmware) that
are signed only by Microsoft. If hardware refuses to boot after enrollment:

```bash
ouroboros-secureboot rotate-keys    # Generates new keys
sbctl enroll-keys -m                # Re-enroll including Microsoft keys
```

### systemd-boot Updates

`systemd-boot-update.service` may update the bootloader EFI binary after first boot. The
sbctl pacman hook signs the binary during the pacman transaction, but if the service
copies a new unsigned binary post-boot, `our-pacman` will catch it on the next update.
Run `ouroboros-secureboot sign-all` manually if booting fails after a bootloader update.

---

## References

- [sbctl GitHub](https://github.com/Foxboron/sbctl)
- [Arch Wiki: Unified Extensible Firmware Interface/Secure Boot](https://wiki.archlinux.org/title/Unified_Extensible_Firmware_Interface/Secure_Boot)
- `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-secureboot`
- `src/installer/config.py` — `SecurityConfig` dataclass
- `src/installer/state_machine.py` — `SECURE_BOOT` state and `_handle_secure_boot()`
