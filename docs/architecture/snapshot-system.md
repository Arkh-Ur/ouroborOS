# Snapshot System — Btrfs Snapshots + Rollback

## Overview

ouroborOS uses Btrfs snapshots for atomic rollback. Snapshots are taken automatically before every `our-pac` operation and can be used to boot into a previous state (`try`) or make a previous state permanent (`promote`).

The snapshot system consists of three layers:
- `snapshot.sh` — internal library (Bash functions for create/delete/metadata)
- `our-snapshot` — user-facing CLI wrapper
- `our-rollback` — atomic rollback with `try` and `promote` modes

---

## Btrfs Subvolume Layout

```
Btrfs pool (subvolid=5, top level)
├── @              ← running root (mounted at /)
├── @var           ← /var (always rw — pacman DB, Flatpak, sysext extensions)
├── @etc           ← /etc (always rw — system config, machine-id)
├── @home          ← /home (homed user directories)
└── @snapshots     ← /.snapshots (snapshot subvolumes)
    ├── install    ← post-install baseline (read-only)
    ├── 2025-06-01T120000  ← pre-update snapshot (read-only)
    └── 2025-06-15T093000
```

**Key constraint:** `@var` is NOT snapshotted along with `@`. Snapshots capture only the root filesystem state. Rolling back `@` does not revert pacman DB, Flatpak state, or sysext extensions.

---

## Snapshot Lifecycle

### 1. Installation snapshot (`install`)

Created by the installer at the end of the `SNAPSHOT` state, immediately after `pacstrap` + `configure.sh` complete. Read-only. Never deleted by auto-prune.

### 2. Pre-update snapshots

Created automatically by `our-pac` before every `pacman` operation:

```bash
our-pac -S firefox
# → snapshot 2025-06-15T093000 created (read-only, locked)
# → pacman -S firefox
# → snapshot listed in systemd-boot entries
```

Naming: ISO-8601 timestamp (`YYYY-MM-DDTHHMMSS`).

### 3. Safety snapshots (pre-promote)

Created automatically by `our-rollback promote` before replacing `@`. Named `pre-promote-YYYY-MM-DDTHHMMSS`. Allows undoing a promote if the new root is broken.

---

## Rollback Modes

### `try` — boot once from a snapshot

Non-destructive. Uses `bootctl set-oneshot` to boot into the snapshot on the next boot only. If boot fails, the system returns to the previous default automatically.

```bash
sudo our-rollback try 2025-06-01T120000
# → systemd-boot boots from /.snapshots/2025-06-01T120000 once
# → Next reboot: default entry restored automatically
```

### `promote` — make a snapshot permanent

Atomically replaces `@` with a copy of the snapshot. The original snapshot is preserved as a restore point. Steps:

```
1. Create safety snapshot: pre-promote-TIMESTAMP (read-only)
2. Mount subvolid=5 (top-level Btrfs mount)
3. Copy snapshot → @_new (btrfs subvolume snapshot)
4. Rename @ → @.del
5. Rename @_new → @
6. Run package consistency repair (pacman -Qk + reinstall broken packages)
7. Update systemd-boot default entry
8. Reboot required
```

**Why rename instead of delete?**

`btrfs subvolume delete @` while `@` is the running root invalidates the kernel's dcache for `/usr/bin/*` and related paths. Any command executed after the delete may fail with "No such file or directory" even though the filesystem is not actually corrupt. The rename-then-rename pattern (`@` → `@.del`, `@_new` → `@`) is atomic and safe.

**Why `@.del` is not deleted:**

`our-rollback promote` intentionally does not delete `@.del` after the rename succeeds. Deleting it mid-session is equally dangerous. `@.del` is cleaned up on the next `promote` or via manual `btrfs subvolume delete`.

### `undo` — revert the last promote

Restores `@.old` as `@` if it exists. Same rename-then-rename pattern.

```bash
sudo our-rollback undo
```

---

## Boot Integration

Each snapshot gets a systemd-boot entry in `/boot/loader/entries/`:

```ini
# /boot/loader/entries/ouroborOS-snap-2025-06-01T120000.conf
title   ouroborOS (snapshot: 2025-06-01T120000)
linux   /vmlinuz-linux-zen
initrd  /intel-ucode.img
initrd  /initramfs-linux-zen.img
options root=UUID=<uuid> rootflags=subvol=@snapshots/2025-06-01T120000 ro quiet
```

These entries are synced by `our-pac` and `our-snapshot sync-boot-entries` after every operation.

---

## Snapshot Metadata

Each snapshot stores a `.snapshot.yaml` file:

```yaml
snapshot: "2025-06-01T120000"
type: pre-update       # install | pre-update | manual | rebase
timestamp: "2025-06-01T12:00:00Z"
kernel: "6.9.3-zen1-1-zen"
system_yaml_hash: "sha256:..."
package_count: 847
```

Written while root is still writable (before `lock_root`), inside the snapshot subvolume.

---

## Auto-Prune

`our-pac` automatically prunes snapshots when count exceeds 10:

```bash
our-snapshot prune --keep 5 --days 30
```

The `install` snapshot is never pruned (it has no timestamp name and is excluded by the prune policy).

---

## Commands

| Command | Action |
|---------|--------|
| `our-snapshot list` | List all snapshots |
| `our-snapshot create [NAME]` | Create a manual snapshot |
| `our-snapshot delete <NAME>` | Delete a snapshot |
| `our-snapshot info <NAME>` | Show snapshot metadata |
| `our-snapshot prune [--keep N] [--days D]` | Prune old snapshots |
| `our-snapshot sync-boot-entries` | Rebuild systemd-boot entries for all snapshots |
| `our-rollback list` | Alias for our-snapshot list |
| `our-rollback try <NAME>` | One-shot boot from snapshot |
| `our-rollback promote <NAME> [--force]` | Replace @ with snapshot |
| `our-rollback undo` | Restore @.old as @ |
| `our-rollback status` | Show current root subvolume |

---

## File Locations

| Path | Purpose |
|------|---------|
| `/usr/local/lib/ouroboros/snapshot.sh` | Internal Bash library |
| `/usr/local/bin/our-snapshot` | User-facing snapshot CLI |
| `/usr/local/bin/our-rollback` | Rollback CLI |
| `/.snapshots/` | Snapshot subvolumes (`@snapshots`) |
| `/.snapshots/install` | Post-install baseline (read-only) |
| `/.snapshots/<name>/.snapshot.yaml` | Snapshot metadata |
| `/boot/loader/entries/ouroborOS-snap-*.conf` | systemd-boot entries for snapshots |

---

## Constraints

- Snapshots capture `@` only — not `@var`, `@etc`, or `@home`
- Rolling back does not undo pacman DB changes, Flatpak installs, or sysext extensions
- Package consistency repair runs automatically after `promote` (reinstalls packages missing from new `@`)
- `install` snapshot is never auto-pruned
- `@.del` left on disk after promote — safe to delete manually after verifying the new root boots
