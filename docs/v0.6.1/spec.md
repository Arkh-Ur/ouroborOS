# Spec — our-dots & DOTS_PACK Installer State

**Version:** v0.6.1
**Status:** Approved
**Date:** 2026-06-07

---

## History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | Initial spec |

---

## 1. `our-dots` Command Interface

### 1.1 Pack Management

#### `our-dots list`

Prints the full catalog (built-in + external repos), one pack per line.

Output format:
```
NAME                  DE          COMPAT    CHANNEL    INSTALLED
noctalia              niri,hpr    low       stable     -
caelestia             hyprland    medium    stable     v20250612
ml4w                  hyprland    medium    0.2.3      -
ambxst                hyprland    medium    rolling    -
danklinux             niri,hpr    high      1.4        -
illogical-impulse     hyprland    critical  rolling    -
omarchy               hyprland    critical  rolling    -
```

- `INSTALLED` shows the version string if installed, `-` otherwise
- `⚠` prefix on compat column for `high` and `critical` entries

#### `our-dots -Si <pack>`

Detailed info for a pack. Example:

```
Pack         : noctalia
Name         : Noctalia v4
Description  : Quickshell-based desktop shell layer for Niri and Hyprland
               compositors. Modular design: bar, notifications, clipboard
               history, night light, calendar.

Creator      : noctalia-dev team
Homepage     : https://github.com/noctalia-dev/noctalia-shell
Docs         : https://docs.noctalia.dev/v4/getting-started/installation/
Target DE    : niri, hyprland
Immutability : low

Channels     :
  stable     noctalia-shell (AUR)
  git        noctalia-shell-git (AUR)  [bleeding edge]

Installed    : not installed
```

#### `our-dots -S <pack> [--git]`

Install a pack.

1. Read manifest for `<pack>` from built-in catalog or external repos
2. If `compatibility == critical`: show multi-step warning (see §1.1.1)
3. If `compatibility == high`: show single warning, prompt `[y/N]`
4. Show credits panel (always)
5. If pack has both `stable` and `git` variants and `--git` is not passed: prompt channel selection
6. Install dependencies via `our-pac -S <pkgs>` (pacman packages)
7. Install AUR packages via `our-aur -S <pkgs>`
8. Run `post_deploy` script if defined (as calling user, not root)
9. Update `system.yaml:dots_packs` — append `{id, channel, installed_at}`
10. Write log to `/var/log/our-dots/<pack>-<timestamp>.log`

**Exit codes:**
- `0` — success
- `1` — user cancelled
- `2` — pack not found
- `3` — dependency install failed
- `4` — post_deploy script failed

##### 1.1.1 CRITICAL Warning Flow

```
╔══════════════════════════════════════════════════════════════════════╗
║  ⚠  CRITICAL COMPATIBILITY WARNING — <pack name>                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  <compatibility_warning from manifest>                               ║
║                                                                      ║
║  Actions that will be taken on your system:                          ║
║    1. <action from manifest.critical_actions[0]>                     ║
║    2. <action from manifest.critical_actions[1]>                     ║
║    ...                                                               ║
║                                                                      ║
║  This cannot be undone automatically. See the documentation for      ║
║  manual rollback instructions.                                       ║
╚══════════════════════════════════════════════════════════════════════╝
Type 'yes' to proceed, anything else to cancel:
```

User must type the exact string `yes` (case-insensitive). Any other input exits with code 1.

#### `our-dots -R <pack>`

Remove a pack.

1. Check pack is in `system.yaml:dots_packs`; if not, error
2. Prompt `Remove <pack>? [y/N]`
3. Remove packages listed in `manifest.uninstall.aur` via `our-aur -R`
4. Remove packages listed in `manifest.uninstall.packages` via `our-pac -R`
5. Run `manifest.uninstall.post_remove` script if defined
6. Update `system.yaml:dots_packs` — remove entry

Does NOT remove config files from `~/.config` unless the manifest's `uninstall.remove_config: true`
(opt-in, off by default, since users may have customized the configs).

#### `our-dots -Q`

List installed packs from `system.yaml:dots_packs`.

```
noctalia     stable    installed 2026-06-07
```

#### `our-dots -Qs <pattern>`

Search catalog for packs whose id, name, or description match `<pattern>` (case-insensitive grep).

#### `our-dots -Su`

Update all installed packs.

For each pack in `system.yaml:dots_packs`:
1. Check if upstream has a newer version (AUR: compare pkgver; git: compare HEAD SHA)
2. If update available: install new version over existing (same flow as `-S`)
3. Report: `[updated]`, `[up to date]`, or `[failed]`

---

### 1.2 Repository Management

#### `our-dots repo-add <name> <url>`

Add an external manifest repository.

- `<url>` must be HTTPS
- Fetches `index.yaml` from the URL (or clones the git repo)
- Validates that `index.yaml` follows the manifest schema
- Appends to `/etc/ouroboros/dots-repos.yaml`
- Caches manifests to `/var/lib/ouroboros/dots/repos/<name>/`

#### `our-dots repo-remove <name>`

Remove an external repository.

- Removes entry from `/etc/ouroboros/dots-repos.yaml`
- Deletes cache at `/var/lib/ouroboros/dots/repos/<name>/`
- Does NOT uninstall packs that came from this repo

#### `our-dots repo-list`

```
NAME           URL                                    PACKS
built-in       (shipped with ISO)                     7
my-dots        https://github.com/user/dots-catalog   3
```

#### `our-dots repo-update`

Fetch latest manifests from all external repos. Does not install anything.

---

## 2. Pack Manifest Schema

File: `<id>.yaml` in `/usr/local/lib/ouroboros/dots/packs/` (built-in) or
`/var/lib/ouroboros/dots/repos/<repo-name>/` (external).

```yaml
# Required fields
id: string                    # unique identifier, lowercase, no spaces
name: string                  # display name
description: string           # multi-line description (shown in -Si and TUI)

credits:
  author: string              # creator name
  homepage: string            # project homepage URL
  docs: string                # installation docs URL (optional)
  license: string             # SPDX license identifier (optional)

compatibility:
  immutable: low|medium|high|critical
  profiles: list[string]      # desktop profiles this pack targets
  compatibility_note: string  # brief human-readable compat summary (optional)
  # Only for CRITICAL packs:
  compatibility_warning: string   # shown in warning banner
  critical_actions: list[string]  # list of actions that will be taken

variants:
  stable:                     # required; at minimum one of stable or git
    packages: list[string]    # pacman package names, via our-pac
    aur: list[string]         # AUR package names, via our-aur
    post_deploy: string|null  # shell script run as user after install
    version_hint: string      # display version (e.g. "0.2.3", "v1.4")
  git:                        # optional second channel
    packages: list[string]
    aur: list[string]
    post_deploy: string|null
    version_hint: string      # e.g. "git (bleeding edge)"

uninstall:
  packages: list[string]      # pacman packages to remove
  aur: list[string]           # AUR packages to remove
  post_remove: string|null    # shell script run after removal
  remove_config: false        # if true, also deletes ~/.config/<id> (opt-in)

# Reserved for future use
signature: string|null        # GPG signature of this manifest (not enforced in v0.6.1)
```

**Validation rules:**
- `id` must match the filename (without `.yaml`)
- `compatibility.immutable` must be one of the four enum values
- `variants` must have at least one of `stable` or `git`
- `credits.homepage` must be a valid HTTPS URL

---

## 3. Installer Integration

### 3.1 New FSM State: DOTS_PACK

**Position in FSM:** Between `DESKTOP` and `SECURE_BOOT`

**Trigger condition:**
- `config.desktop.profile != "minimal"` AND
- `config.desktop.profile` is not `None`

**Skip condition (no user prompt):**
- Profile is `minimal`
- `dots_pack` key is set in unattended config (auto-applied)

**State transition:**
```
DESKTOP → DOTS_PACK → SECURE_BOOT
              ↓
         (if profile == minimal)
              ↓
         SECURE_BOOT  (skipped)
```

### 3.2 DotsPackConfig Dataclass (config.py)

```python
@dataclass
class DotsPackConfig:
    pack: str | None = None      # pack id or None
    channel: str = "stable"      # "stable" | "git"
```

Nested inside `InstallerConfig`:
```python
@dataclass
class InstallerConfig:
    ...
    dots_pack: DotsPackConfig = field(default_factory=DotsPackConfig)
```

### 3.3 install-config.yaml Key

```yaml
dots_pack:
  pack: noctalia    # pack id, or omit/null for no pack
  channel: stable   # optional, default: stable
```

### 3.4 TUI Screen: show_dots_pack_selection()

**Rich backend — Step 1: Pack selection table**

```
╔══════════════════════════════════════════════════════════════════════╗
║  Dotfiles / Config Pack                                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  Choose an optional ricing pack for your <profile> environment.      ║
║  You can install or remove packs later with 'our-dots'.              ║
╠═══╦══════════════════════╦══════════╦════════════════════════════════╣
║ # ║ Pack                 ║ Channel  ║ Description                    ║
╠═══╬══════════════════════╬══════════╬════════════════════════════════╣
║ 0 ║ none (skip)          ║ —        ║ Keep the default empty profile ║
║ 1 ║ Noctalia v4          ║ stable   ║ Quickshell shell layer         ║
║ 2 ║ Caelestia Shell      ║ stable   ║ Waybar replacement, 9k stars   ║
║ 3 ║ ML4W Dotfiles        ║ 0.2.3    ║ Hyprland dotfiles framework    ║
║ 4 ║ Ambxst               ║ rolling  ║ Non-intrusive Quickshell shell ║
║ 5 ║ DankMaterialShell    ║ 1.4      ║ Material You for Niri/Hyprland ║
║ 6 ║ illogical-impulse    ║ rolling  ║ ⚠ CRITICAL — requires /etc    ║
║ 7 ║ Omarchy              ║ rolling  ║ ⚠ CRITICAL — full system take  ║
╚═══╩══════════════════════╩══════════╩════════════════════════════════╝
  Select [0-7, default 0]:
```

- List is filtered to only packs compatible with the chosen DE profile
- CRITICAL packs appear with `⚠` prefix and shorter description

**Step 2: Channel selection (only if pack has both stable and git)**

```
╔══════════════════════════════════════════════════════════════════════╗
║  <Pack Name> — Channel                                               ║
╠══════════════════════════════════════════════════════════════════════╣
║  1  stable   <stable install description>  — recommended             ║
║  2  git      <git install description>     — bleeding edge           ║
╚══════════════════════════════════════════════════════════════════════╝
  Select [1-2, default 1]:
```

**Step 3: Credits panel (always shown)**

```
╔══════════════════════════════════════════════════════════════════════╗
║  <Pack Name> — Info & Credits                                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  <description>                                                       ║
║                                                                      ║
║  Creator : <author>                                                  ║
║  Homepage: <homepage>                                                ║
║  Docs    : <docs>                                                    ║
║  Compat  : <immutable> — <compatibility_note>                        ║
║                                                                      ║
║  Will install: <packages + aur>                                      ║
╚══════════════════════════════════════════════════════════════════════╝
  Confirm? [y/N]:
```

**Return value:**
```python
{"pack": "noctalia", "channel": "stable"}   # or
{"pack": None}                               # if user chose 0 / none
```

### 3.5 ops/configure.sh Integration

New block in `configure.sh` after the existing `our-aur` block:

```bash
# ── Dotfiles pack ──────────────────────────────────────────────────────────
if [[ -n "${DOTS_PACK:-}" ]]; then
    log_info "Installing dotfiles pack: $DOTS_PACK (channel: ${DOTS_CHANNEL:-stable})"
    CHANNEL_FLAG=""
    [[ "${DOTS_CHANNEL:-stable}" == "git" ]] && CHANNEL_FLAG="--git"
    # Run as the primary user (first user in config)
    arch-chroot "${TARGET}" sudo -u "${PRIMARY_USER}" \
        our-dots -S "${DOTS_PACK}" ${CHANNEL_FLAG} --noconfirm 2>&1 \
        | tee -a "${LOG_FILE}" \
        || log_warn "Dotfiles pack install failed (non-fatal)"
fi
```

The `--noconfirm` flag suppresses interactive prompts in the installer context (unattended or post
user-confirmation in TUI).

---

## 4. Edge Cases

| Case | Behavior |
|------|---------|
| Pack already installed | `our-dots -S` reports "already installed" and exits 0 |
| Channel changed (stable → git) | Treat as reinstall: remove old, install new |
| Dependency of pack already installed by our-pac | our-pac deduplicates; no conflict |
| Pack not found in any repo | Exit 2 with "pack not found in catalog" message |
| External repo URL unreachable | `repo-update` reports error per repo; other repos still update |
| `our-aur` or `our-pac` fails mid-install | Partial install logged; user can re-run or `our-dots -R` |
| `minimal` profile selected, dots_pack set in YAML | Log warning, skip DOTS_PACK state |
| CRITICAL pack in unattended install | Pack is installed without interactive confirmation; a warning is logged |
