# TRD — ouroborOS Dotfiles/Config Packs

**Version:** v0.6.1
**Status:** Approved
**Date:** 2026-06-07

---

## History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | Initial draft |

---

## System Constraints

### 1. Immutable Root Filesystem

ouroborOS mounts `/` as read-only btrfs (`ro=true`). No file under `/usr`, `/etc`, or `/lib` can
be written at runtime. All package installation must go through `our-pac` (wraps pacman with
RO→RW→snapshot→RO lifecycle) or `our-aur` (same, for AUR packages). Direct `pacman -S` or
`makepkg --install` calls are invalid in this context.

**Implication for our-dots:**
- `our-dots` MUST NOT invoke `pacman` or `makepkg` directly
- All package-level operations route through `our-pac -S` and `our-aur -S`
- AUR build directories must land under `/tmp` or `/var` (writable), never `/usr`
- Config file deployment targets `~/.config` (user home, over `@home` subvolume) — no root access needed

### 2. CRITICAL Packs — Controlled /etc Modifications

Two packs require writing to `/etc/pacman.conf` (illogical-impulse) or making system-wide
configuration changes (Omarchy). These cannot be rejected outright — the user has opted in to the
installation — but must be handled with explicit confirmation and minimal blast radius.

**Approach:**
- CRITICAL packs display a multi-step warning flow before any changes are made
- Each destructive action (e.g. remounting RW, editing a file under `/etc`) requires explicit `yes`
- The full list of actions is presented BEFORE any action is taken
- After each action, the system verifies the change and logs it
- A rollback path is documented (but not automated) in the pack manifest

### 3. Manifest-Driven, Binary-Agnostic

The `our-dots` binary must not embed pack-specific logic. All pack metadata, install steps, and
compatibility data lives in YAML manifests under `/usr/local/lib/ouroboros/dots/packs/`. This
allows:
- Updating pack manifests without rebuilding the ISO (via `our-dots repo-update`)
- Adding new packs without modifying the tool itself
- Community-contributed packs via external repositories

### 4. External Repository System

Users can add third-party manifest repositories:
- Repos stored as git repositories or directories served over HTTPS
- Manifests cached in `/var/lib/ouroboros/dots/repos/<name>/` (writable)
- Repo index in `/etc/ouroboros/dots-repos.yaml` (requires root to write)
- `our-dots repo-update` fetches latest manifests; does not install anything automatically

### 5. system.yaml as Source of Truth

Installed packs are registered in `/etc/ouroboros/system.yaml` under a new `dots_packs` key,
consistent with `user_packages`, `aur_packages`, and `appimage_packages`. This ensures:
- The declarative system state is always accurate
- `our-dots -Q` reads from `system.yaml`, not from filesystem heuristics
- Future OTA or reinstall can replay the installed packs

---

## Architecture Decisions

### AD-1: Bash, not Python

**Decision:** `our-dots` is implemented in Bash, following `our-pac`, `our-aur`, `our-flat`,
`our-app`.

**Rationale:** All `our-*` tools are Bash for consistency and to avoid Python dependency during
early-boot or recovery scenarios. The installer (Python) calls `our-dots` as a subprocess; the
tool does not need to be a Python module.

**Trade-off:** Bash YAML parsing is fragile. For manifest reading, we use `python3 -c` one-liner
snippets (same technique as `our-pac`'s system.yaml updates) rather than pure bash sed/grep.

### AD-2: YAML manifests, not a central registry file

**Decision:** One YAML file per pack, not a single registry.

**Rationale:** Easier to add/remove individual packs, easier for external repos to contribute (one
file per pack, no merge conflicts on a central file), simpler to version in git.

### AD-3: our-pac / our-aur as install backends

**Decision:** `our-dots -S <pack>` never calls pacman directly; always routes through `our-pac`
and `our-aur`.

**Rationale:** These wrappers own the btrfs snapshot lifecycle. Bypassing them would install
packages outside the immutability boundary. `our-pac` also updates `system.yaml:user_packages`.

**Note:** `our-dots` registers the pack itself under `system.yaml:dots_packs`, separate from the
individual package entries that `our-pac`/`our-aur` add under their respective keys. This allows
`our-dots -R` to know which packages to remove even if they were installed via `our-aur`.

### AD-4: DOTS_PACK FSM state is optional

**Decision:** The `DOTS_PACK` installer state is skipped automatically when `profile == "minimal"`
or when `dots_pack` is not set in the config.

**Rationale:** Minimal installs have no compositor and no sensible target for a ricing pack. Forcing
a pack selection screen would confuse server or container use cases.

### AD-5: Post-deploy scripts run as the target user, not root

**Decision:** Any `post_deploy` script in a manifest runs as the installing user, not as root.

**Rationale:** Config files (`.config/`, `.local/`) are user-owned. Root-owned config files would
break most DE tooling. The pack manifests can declare `requires_root: true` if system-level files
must be touched (only CRITICAL packs use this).

---

## Security Considerations

- `our-dots repo-add` validates that the URL is HTTPS before fetching
- Manifest YAML is parsed with Python's `yaml.safe_load` (no arbitrary code execution)
- `post_deploy` scripts in manifests are executed directly — users should only add trusted repos
- Signing of external manifests is out of scope for v0.6.1 but the manifest schema includes a
  reserved `signature` field for future use
- Passwords and secrets are never stored in manifests

---

## Compatibility Matrix

| Pack | Immutable Concern | Install Backend | Writable /etc | system.yaml Key |
|------|------------------|-----------------|---------------|-----------------|
| noctalia | LOW | our-aur | No | dots_packs |
| caelestia | MEDIUM | our-aur | No | dots_packs |
| ml4w | MEDIUM | our-pac + git | No | dots_packs |
| ambxst | MEDIUM | our-pac + curl deploy | No | dots_packs |
| danklinux | HIGH | our-pac + our-aur | No | dots_packs |
| illogical-impulse | CRITICAL | our-pac + our-aur | Yes (/etc/pacman.conf) | dots_packs |
| omarchy | CRITICAL | our-pac + our-aur | Yes (multiple /etc files) | dots_packs |

---

## File Locations

| Path | Purpose |
|------|---------|
| `/usr/local/bin/our-dots` | The tool binary |
| `/usr/local/lib/ouroboros/dots/packs/*.yaml` | Built-in pack manifests |
| `/var/lib/ouroboros/dots/repos/` | External repo manifest cache |
| `/etc/ouroboros/dots-repos.yaml` | External repo index |
| `/etc/ouroboros/system.yaml` (key: `dots_packs`) | Installed packs registry |
| `/var/log/our-dots/` | Installation logs |
