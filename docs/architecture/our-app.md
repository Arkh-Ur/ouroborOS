# our-app — AppImage Manager

## Overview

`our-app` is the AppImage manager for ouroborOS. It wraps AppImage installation with a pacman-compatible interface (`-S`, `-R`, `-Q`, `-Qs`, `-Si`, `-Su`) and integrates each AppImage into the desktop menu **without writing to the immutable `/usr`**. Everything lives in `/var/lib/ouroboros/appimages/` on the `@var` subvolume.

---

## Design Principles

### Why AppImage needs no sysext

An AppImage is a single, self-contained executable: it bundles its own runtime and libraries. Unlike AUR packages (which install files into `/usr` and therefore need a `systemd-sysext` overlay via `our-aur`), an AppImage does not need to be merged into `/usr` at all. It runs from wherever it sits. So `our-app` simply stores the file in `@var` and makes it executable — no sysext, no overlay, no unlock/relock cycle.

### Why a thin pacman-style wrapper

- Consistent interface with `our-pac`, `our-aur`, and `our-flat`.
- Blocks `-Syu` (system update belongs to `sudo our-pac -Syu`).
- Tracks installed AppImages in the declarative manifest (`system.yaml:appimage_packages`), mirroring how `our-pac` tracks `user_packages` and `our-aur` tracks `aur_packages`.

### Why desktop integration via `XDG_DATA_DIRS`

`/usr/share/applications` (the standard system-wide `.desktop` location) is read-only on ouroborOS. Instead of touching `/usr`, `our-app` writes `.desktop` files and icons under `/var/lib/ouroboros/appimages/share/` and a login snippet (`/etc/profile.d/ouroboros-appimages.sh`, on the writable `@etc` subvolume) prepends that directory to `XDG_DATA_DIRS`. Launchers then discover AppImage entries with no change to the immutable root.

---

## Architecture

```
our-app -S <url|path> [name]
    │
    ├── 1. Resolve name (explicit arg, or derived/sanitized from filename)
    │
    ├── 2. Fetch → /var/lib/ouroboros/appimages/<name>/<name>.AppImage
    │       URL  → curl --fail --location
    │       path → cp; then chmod +x
    │
    ├── 3. Integrate desktop
    │       <appimage> --appimage-extract  (no FUSE needed)
    │       → parse .desktop, rewrite Exec= to stored AppImage path
    │       → copy icon (from Icon=, .DirIcon, or top-level image)
    │       → fall back to a minimal .desktop if extraction yields nothing
    │
    ├── 4. Link XDG
    │       share/applications/<name>.desktop  → symlink
    │       share/icons/<name>.<ext>           → symlink
    │       update-desktop-database (best-effort)
    │
    ├── 5. Persist metadata → <name>/.app.yaml (name, version, source, installed_at)
    │
    └── 6. Register → system.yaml:appimage_packages (add)
            No snapshot: writes are confined to @var.
```

---

## Why AppImage Does NOT Conflict with Immutability

Everything `our-app` writes lives on `@var` (`/var/lib/ouroboros/appimages/`) or `@etc` (`/etc/profile.d/`), both always mounted read-write. The immutable root (`@`) is never touched, and no `systemd-sysext` is involved.

| Location | Subvolume | Writability |
|----------|-----------|-------------|
| AppImage binary + metadata | `/var/lib/ouroboros/appimages/<name>/` | `@var` — always rw |
| `.desktop` / icon (XDG) | `/var/lib/ouroboros/appimages/share/` | `@var` — always rw |
| XDG login snippet | `/etc/profile.d/ouroboros-appimages.sh` | `@etc` — always rw |

---

## Snapshot / Rollback Behavior

Because AppImages live only in `@var`, they are **not** captured by root (`@`) snapshots — exactly like Flatpak apps. `our-app` therefore does **not** create a pre-write snapshot, and rolling back `@` via `our-rollback` does **not** remove installed AppImages. This is intentional and documented as expected behavior.

---

## Commands

| Command | Action |
|---------|--------|
| `our-app -S <url\|path> [name]` | Install an AppImage (download or copy local file) |
| `our-app -R <name>` | Remove an installed AppImage |
| `our-app -Q` | List installed AppImages |
| `our-app -Qs <query>` | Search installed AppImages |
| `our-app -Si <name>` | Show info for an installed AppImage |
| `our-app -Su` | Update all (re-download from each stored source URL) |

**Blocked:**
- `-Syu` — deliberately rejected. Use `sudo our-pac -Syu` for system upgrades.

**Notes:**
- `-Su` can only update AppImages whose `source` is an `http(s)://` URL; locally-installed ones are skipped (there is nothing to re-fetch).
- AppImages that are type-1 or ship no `.desktop` still install — `our-app` writes a minimal `.desktop` so they appear in the menu.

---

## Typical Flow

```bash
# Install from a URL (name derived from filename if omitted)
sudo our-app -S https://example.com/Foo-x86_64.AppImage foo

# Install from a local file
sudo our-app -S ./Bar.AppImage

# List, inspect, update, remove
our-app -Q
our-app -Si foo
sudo our-app -Su
sudo our-app -R foo
```

---

## File Locations

| Path | Purpose |
|------|---------|
| `/usr/local/bin/our-app` | Main script |
| `/var/lib/ouroboros/appimages/<name>/<name>.AppImage` | The executable |
| `/var/lib/ouroboros/appimages/<name>/.app.yaml` | Metadata (name, version, source, installed_at) |
| `/var/lib/ouroboros/appimages/<name>/icon.<ext>` | Extracted icon |
| `/var/lib/ouroboros/appimages/<name>/<name>.desktop` | Desktop entry (Exec rewritten) |
| `/var/lib/ouroboros/appimages/share/applications/` | XDG `.desktop` symlinks |
| `/var/lib/ouroboros/appimages/share/icons/` | XDG icon symlinks |
| `/etc/profile.d/ouroboros-appimages.sh` | Adds the share dir to `XDG_DATA_DIRS` |
| `/etc/ouroboros/system.yaml` (`appimage_packages`) | Declarative record of installed AppImages |

---

## Constraints

- All mutation commands (`-S`, `-R`, `-Su`) require root (auto re-exec via `sudo`).
- AppImage state is in `@var` — it persists across Btrfs snapshots/rollbacks.
- `our-rollback` of `@` does NOT undo AppImage installs (they live in `@var`).
- Desktop integration depends on `XDG_DATA_DIRS` being set by the login snippet — already-running sessions pick up new entries after a re-login.
- `-Su` requires a stored `http(s)` source URL; local-file installs cannot be auto-updated.
