# systemd-homed in ouroborOS — Decision & Limitations

**Status:** Partially supported — automatic fallback to classic user  
**Updated:** Phase 3 (2026-04)

---

## What We Tried

Phase 2 introduced `systemd-homed` as the default home directory backend, using the `subvolume` storage type to create per-user Btrfs subvolumes inside `/home` (the `@home` subvolume).

The intent: encrypted, portable, self-contained home directories managed by `systemd-homed`, giving each user their own Btrfs subvolume with native copy-on-write semantics.

---

## The Problem

`homectl create --storage=subvolume` fails when `/home` is already a Btrfs subvolume (`@home`).

**Root cause:** systemd-homed tries to create a new Btrfs subvolume *inside* an existing Btrfs subvolume at the same mount point. The kernel rejects creating nested subvolumes when the parent is mounted as a subvolume (not the top-level). This produces a generic "File exists" or "Operation not supported" error from the kernel.

**Upstream issues:**
- [systemd#15121](https://github.com/systemd/systemd/issues/15121) — homed subvolume create fails inside Btrfs subvolume
- [systemd#16829](https://github.com/systemd/systemd/issues/16829) — homed cannot create subvolume home inside existing Btrfs subvolume

**Reproducible in:**
- QEMU with virtio or e1000 block device
- Any Btrfs layout where `/home` is a named subvolume (not top-level)
- The ouroborOS layout: `@home` mounted at `/home` (standard configuration)

**Community consensus (Arch Wiki / Arch forums):** Use classic `useradd` with Btrfs. systemd-homed's Btrfs subvolume storage requires `/home` to be on the Btrfs top-level, which conflicts with the standard multi-subvolume layout.

---

## What Happens Today

### Installation (CONFIGURE state)

The installer creates the user with `useradd` unconditionally (in `configure.sh`). This is the stable, always-working path.

### First Boot (ouroboros-homed-migration.service)

If `homed_storage != "classic"`, the `ouroboros-homed-migration.service` runs and attempts to convert the classic user to a homed-managed identity.

**If `homectl create` succeeds:** User is migrated. Home directory is now managed by systemd-homed. PAM is patched for SSH compatibility.

**If `homectl create` fails (expected with `storage=subvolume` on `@home`):**
- Rollback runs automatically
- Home directory is restored from backup (no data loss)
- User remains as a classic `/etc/passwd` user
- System is fully functional — login works normally
- Detailed error message is logged to journal explaining the known issue

### Checking the Migration Status

```bash
journalctl -u ouroboros-homed-migration.service
```

If migration failed, you'll see:
```
User 'username' remains as a classic /etc/passwd user.
Home directory: /home/username (unchanged, no data loss).
Known issue: homectl create fails when /home is a Btrfs subvolume (@home).
```

---

## Recommended Configuration

For ouroborOS with the standard Btrfs layout, use:

```yaml
user:
  homed_storage: classic
```

This skips the migration service entirely and keeps the user as a classic `/etc/passwd` user with a standard home directory on `@home`.

**Functionally equivalent for most users:** Classic users on Btrfs still get copy-on-write semantics (Btrfs inherits from the `@home` subvolume), snapshots via `our-snapshot`, and all ouroborOS features.

---

## Alternative: `luks` or `directory` Storage

If you need systemd-homed management (portable home, per-user encryption), use:

```yaml
user:
  homed_storage: luks      # LUKS-encrypted image file in /home/.home/
  # or
  homed_storage: directory # Plain directory (no Btrfs subvolume creation)
```

The `luks` backend stores the home as a `.home` file under `/home/` (not a subvolume) and avoids the nested-subvolume issue. The `directory` backend creates a plain directory.

---

## Future Work

- Investigate mounting `@home` at top-level Btrfs before homed setup
- Evaluate systemd ≥ 256 for any fixes to nested subvolume creation
- Consider `luks` as the default for users who want homed encryption

---

## Files

| File | Purpose |
|------|---------|
| `src/ouroborOS-profile/airootfs/usr/local/lib/ouroboros/homed-migrate.sh` | Migration script (runs on first boot) |
| `src/ouroborOS-profile/airootfs/etc/systemd/system/ouroboros-homed-migration.service` | Systemd unit for migration |
| `src/installer/ops/configure.sh` — `configure_homed()` | Installs and enables the migration service |
| `src/installer/config.py` — `UserConfig.homed_storage` | Config field (`classic` skips migration) |
