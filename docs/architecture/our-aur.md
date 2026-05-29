# our-aur — AUR Package Management via systemd-sysext

## Overview

`our-aur` is the AUR package manager for ouroborOS. It installs AUR packages as **systemd-sysext extensions** — read-only overlays mounted on `/usr` — preserving root immutability while making binaries available system-wide.

No AUR helper (paru, yay) is required. Packages are built directly with `makepkg` inside an ephemeral `systemd-nspawn` container.

---

## Architecture

```
our-aur -S <pkg>
    │
    ├── 1. Query AUR API (https://aur.archlinux.org/rpc/v5/info?arg[]=<pkg>)
    │       → verify pkg exists, get version
    │
    ├── 2. Create ephemeral build container
    │       systemd-nspawn -D /var/tmp/our-aur/containers/build-<PID>
    │       pacstrap: base base-devel git sudo (temp pacman.conf, no host HookDir)
    │       useradd aurbuild (unprivileged build user)
    │
    ├── 3. Build AUR package inside container
    │       git clone https://aur.archlinux.org/<pkg>.git
    │       makepkg --noconfirm --noprogressbar -si (as aurbuild)
    │
    ├── 4. Create sysext staging tree
    │       /var/tmp/our-aur/staging/our-aur-<pkg>/
    │           usr/         ← files from /usr/* in the container
    │           usr/lib/extension-release.d/
    │               extension-release.our-aur-<pkg>
    │                   ID=_any        ← wildcard: works on any host OS ID
    │
    ├── 5. Pack into extension directory
    │       /var/lib/extensions/our-aur-<pkg>/  (move from staging)
    │
    ├── 6. systemd-sysext merge
    │       → /usr is now an overlayfs: base /usr + extension /usr
    │       → new binaries immediately accessible via PATH
    │
    ├── 7. Save tracking metadata
    │       /var/lib/our-aur/packages/<pkg>.json
    │           { name, version, installed_at, sysext_path }
    │
    └── 8. Destroy ephemeral container
            rm -rf /var/tmp/our-aur/containers/build-<PID>
```

---

## Key Design Decisions

### Why sysext instead of native pacman?

| Approach | Root stays RO | Rollback | AUR support |
|----------|---------------|----------|-------------|
| pacman -S (our-pac) | ✅ via snapshot | ✅ btrfs | ❌ AUR only |
| native paru/yay | ❌ requires rw / | ❌ | ✅ |
| **our-aur (sysext)** | **✅ always** | **✅ remove extension** | **✅** |

Sysext extensions live entirely in `/var/lib/extensions/`, which is always writable (`@var` subvolume). Root (`@`) never changes.

### Why `ID=_any` in extension-release?

`systemd-sysext` validates that the extension's `ID` field matches the host's `/etc/os-release ID`. ouroborOS uses `ID=ouroboros`. Using `ID=_any` is the official systemd wildcard — it matches any host regardless of ID, making extensions portable.

**Never use** `ID=arch` or `SYSEXT_LEVEL=1` — these cause incompatibility rejections:
- `ID=arch` doesn't match `ID=ouroboros`
- `SYSEXT_LEVEL` must match the host's `/etc/os-release` (which ouroborOS doesn't set)

### Why drop paru/yay?

paru v2.1.0 changed its release format and introduced `libalpm.so.15` ABI requirements that conflict with the container's pacman version. Direct `git clone + makepkg -si` is simpler, has no external binary dependencies, and is fully auditable.

### Why a temp pacman.conf inside the container?

The host's `/etc/pacman.conf` contains `HookDir = /etc/pacman.d/hooks/`, which includes ouroborOS-specific hooks (e.g. `zzz-post-upgrade.hook` that tries to lock the root). When `pacstrap` uses this config inside the container, those hooks fire in an empty chroot and fail. The fix: a temp conf with only the default `HookDir = /usr/share/libalpm/hooks/`.

### Why `pacman --root="${container}" -Ql` returns full host paths?

`pacman --root=<dir>` returns absolute paths **prefixed with the root**, not container-relative paths. For example, if `container=/var/tmp/our-aur/containers/build-1234`, the output for a file `/usr/bin/hyprcaffeine` is:

```
/var/tmp/our-aur/containers/build-1234/usr/bin/hyprcaffeine
```

The sysext staging must strip the container prefix with `${full_path#${container}}` before checking for `/usr/*` and before copying to the staging tree.

---

## sysext and our-pac Coexistence

When a sysext extension is active, `/usr` is an **overlay mount** (read-only). Running `our-pac -S <pkg>` while an extension is active causes pacman to fail with:

```
error: Partition /usr is mounted read only
```

`our-pac` handles this automatically (since v0.5.7+):

1. Detects overlay via `findmnt -n -o FSTYPE /usr | grep overlay`
2. Runs `systemd-sysext unmerge` → exposes base `/usr`
3. Runs pacman
4. Locks root
5. Runs `systemd-sysext merge` → restores extensions

This is transparent to the user. The extension is re-applied after every `our-pac` operation.

---

## Commands

| Command | Action |
|---------|--------|
| `our-aur -S <pkg>` | Install AUR package as sysext |
| `our-aur -R <pkg>` | Remove sysext + tracking entry |
| `our-aur -Q` | List installed AUR packages |
| `our-aur -Si <pkg>` | Show AUR package info |
| `our-aur -Su` | Update all installed AUR packages |

---

## File Locations

| Path | Purpose |
|------|---------|
| `/usr/local/bin/our-aur` | Main script |
| `/var/lib/extensions/our-aur-<pkg>/` | Sysext extension directory |
| `/var/lib/our-aur/packages/<pkg>.json` | Tracking metadata |
| `/var/tmp/our-aur/containers/` | Ephemeral build containers (cleaned after build) |
| `/var/tmp/our-aur/staging/` | Staging tree before packing into extension |

---

## Constraints

- AUR packages with interactive `PKGBUILD` prompts will fail (non-interactive build)
- Packages that install to paths outside `/usr/` (e.g. `/etc/`) are not captured in the sysext and must be handled manually
- sysext extensions persist across reboots but are NOT included in Btrfs snapshots — they live in `@var`
- Multiple AUR packages can coexist as separate extensions; `systemd-sysext merge` overlays all of them
