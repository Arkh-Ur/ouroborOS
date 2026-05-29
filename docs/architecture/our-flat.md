# our-flat — Flatpak Wrapper

## Overview

`our-flat` is the Flatpak manager for ouroborOS. It wraps the `flatpak` CLI with a pacman-compatible interface and enforces ouroborOS policy: all apps are installed **system-wide** (`--system`) and Flathub must be added explicitly (opt-in by design).

---

## Design Principles

### Why system-wide installation only?

ouroborOS uses systemd-homed for user directories. Per-user Flatpak installations (`~/.local/share/flatpak`) are incompatible with homed's portable home directories, which may not be mounted at install time. System-wide installation in `/var/lib/flatpak/` ensures apps are available regardless of home directory state.

### Why no automatic Flathub?

Flathub is an opt-in remote — it is not added during installation. This keeps the system auditable: no external app repository is enabled unless the user explicitly adds it. This aligns with ouroborOS's "no defaults that require network trust" philosophy.

### Why a thin wrapper instead of native flatpak?

- Consistent interface with `our-pac` and `our-aur` (pacman-style flags: `-S`, `-R`, `-Q`, `-Su`)
- Enforces `--system` on all mutation commands (no accidental per-user installs)
- Guards against missing flatpak installation and missing remotes with actionable error messages
- Blocks `-Syu` (system update belongs to `our-pac -Syu`, not `our-flat`)

---

## Architecture

```
our-flat -S <app-id>
    │
    ├── 1. Guard: flatpak installed?
    │       command -v flatpak → or abort with install hint
    │
    ├── 2. Guard: any remotes configured?
    │       flatpak remotes --system → or abort with remote-add hint
    │
    ├── 3. Install system-wide
    │       flatpak install --system --noninteractive <app-id>
    │
    └── 4. Done — no snapshot, no lock/unlock needed
            (Flatpak lives in /var/lib/flatpak/, which is on @var — always writable)
```

---

## Why Flatpak Does NOT Conflict with Immutability

Flatpak apps install into `/var/lib/flatpak/`, which resides on the `@var` Btrfs subvolume. `@var` is always mounted read-write. The immutable root (`@`) is never touched.

| Location | Subvolume | Writability |
|----------|-----------|-------------|
| Flatpak runtimes | `/var/lib/flatpak/runtime/` | `@var` — always rw |
| Flatpak apps | `/var/lib/flatpak/app/` | `@var` — always rw |
| Flatpak system repo | `/var/lib/flatpak/repo/` | `@var` — always rw |
| User data | `~/.var/app/` | `@home` — always rw |

No `our-pac`-style unlock/lock cycle is needed. No `systemd-sysext` interaction.

---

## Interaction with systemd-sysext

`our-flat` itself has no sysext interaction. However, installing `flatpak` via `our-pac` while a sysext is active requires `our-pac`'s auto-unmerge/remerge cycle (since v0.5.7). Once `flatpak` is installed, `our-flat` operates independently of sysext state.

---

## Commands

| Command | Action |
|---------|--------|
| `our-flat -S <app-id>` | Install app system-wide |
| `our-flat -Ss <query>` | Search configured remotes |
| `our-flat -Si <app-id>` | Show app info |
| `our-flat -Su` | Update all installed apps |
| `our-flat -R <app-id>` | Uninstall app |
| `our-flat -Q` | List installed apps |
| `our-flat -Qs <query>` | Search installed apps |
| `our-flat remote-add <name> <url>` | Add a Flatpak remote |
| `our-flat remote-list` | List configured remotes |
| `our-flat remote-remove <name>` | Remove a remote |

**Blocked:**
- `-Syu` — deliberately rejected. Use `sudo our-pac -Syu` for system upgrades.

---

## Typical Setup Flow

```bash
# 1. Install flatpak via our-pac (required once)
sudo our-pac -S flatpak

# 2. Add Flathub remote (explicit opt-in)
sudo our-flat remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo

# 3. Install an app
sudo our-flat -S org.videolan.VLC

# 4. List installed apps
our-flat -Q

# 5. Update all apps
sudo our-flat -Su

# 6. Remove an app
sudo our-flat -R org.videolan.VLC
```

---

## File Locations

| Path | Purpose |
|------|---------|
| `/usr/local/bin/our-flat` | Main script |
| `/var/lib/flatpak/` | System-wide Flatpak installation root |
| `/var/lib/flatpak/repo/` | OSTree repo (Flatpak's internal format) |
| `/etc/flatpak/installations.d/` | System installation config |
| `~/.var/app/` | Per-user app data (in user home) |

---

## Constraints

- Flatpak must be installed via `our-pac -S flatpak` before `our-flat` works
- Flathub is not enabled by default — explicit `remote-add` required
- All installs are system-wide (`--system`) — per-user mode is unsupported
- Flatpak state is in `@var` — it persists across Btrfs snapshots/rollbacks
- Rolling back `@` via `our-rollback` does NOT undo Flatpak installs (they live in `@var`)
