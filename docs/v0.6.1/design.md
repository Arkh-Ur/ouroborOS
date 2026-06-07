# Technical Design — v0.6.1 Dotfiles/Config Packs

**Version:** v0.6.1
**Status:** Approved
**Date:** 2026-06-07

---

## History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | Initial design |

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface                              │
│                                                                     │
│   our-dots CLI          installer TUI (DOTS_PACK state)             │
│   (post-install)        (during install)                            │
└────────────┬────────────────────────┬───────────────────────────────┘
             │                        │
             ▼                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        our-dots core (Bash)                         │
│                                                                     │
│  manifest_load()   catalog_list()   pack_install()  pack_remove()   │
│  repo_add()        repo_update()    sysyaml_update()                │
└────────────┬──────────────┬─────────────────────┬───────────────────┘
             │              │                     │
             ▼              ▼                     ▼
    ┌─────────────┐  ┌────────────┐      ┌──────────────────┐
    │ our-pac -S  │  │ our-aur -S │      │ /etc/ouroboros/  │
    │ (pacman RW  │  │ (AUR build │      │ system.yaml      │
    │  wrapper)   │  │  wrapper)  │      │ dots-repos.yaml  │
    └─────────────┘  └────────────┘      └──────────────────┘
             │              │
             ▼              ▼
    ┌─────────────────────────┐
    │ btrfs: RO → snapshot    │
    │        → install        │
    │        → new snapshot   │
    │        → RO             │
    └─────────────────────────┘

Manifest sources:
┌──────────────────────────────────────┐
│  /usr/local/lib/ouroboros/dots/      │
│  packs/*.yaml  (built-in, 7 packs)   │
├──────────────────────────────────────┤
│  /var/lib/ouroboros/dots/repos/      │
│  <name>/*.yaml  (external repos)     │
└──────────────────────────────────────┘
```

---

## Design Decisions

### D1: Why YAML manifests outside the binary?

**Alternative considered:** Embed pack metadata as Bash associative arrays inside `our-dots`.

**Decision:** External YAML files.

**Reasoning:**
- External manifests can be updated via `repo-update` without an ISO rebuild
- One file per pack → clean git history, no merge conflicts when adding packs
- External repos can distribute manifests in the same format without modifying the tool
- Schema validation can be done with `python3 -c 'import yaml; yaml.safe_load(...)'`

**Trade-off:** Bash has no native YAML parser. We use embedded `python3 -c` one-liners (same
technique as `our-pac`'s `system.yaml` updates). This adds a Python dependency, but Python is
always present on ouroborOS (`python` is in `packages.x86_64`).

---

### D2: Why route through our-pac/our-aur instead of pacman directly?

**Alternative considered:** Call `pacman -S` directly inside a `mount -o remount,rw /` wrapper.

**Decision:** Always use `our-pac -S` and `our-aur -S`.

**Reasoning:**
- `our-pac` owns the btrfs snapshot lifecycle (pre-install snapshot → install → post-install
  snapshot). Bypassing it would install packages between snapshots, corrupting the rollback chain.
- `our-pac` handles the `PermitRootLogin` / sudoers / PAM edge cases in the live system
- Consistency: all package operations in ouroborOS go through the `our-*` family
- `our-pac -R` knows how to clean up; `pacman -R` without the wrapper might leave ghost entries
  in `system.yaml`

**Trade-off:** `our-dots` cannot install packages in a single atomic btrfs transaction across
the pack's dependencies. Each `our-pac -S` call creates its own snapshot. This means a partial
install (e.g. pacman packages succeed, AUR fails) leaves the system in a mixed state. Documented
in edge cases: user can `our-dots -R` to clean up.

---

### D3: Why is DOTS_PACK an optional FSM state?

**Alternative considered:** Always show the dots pack screen, even for minimal.

**Decision:** Skip DOTS_PACK when `profile == "minimal"`.

**Reasoning:**
- Minimal has no compositor. There is no sensible target for a ricing pack.
- A dots pack selection screen with zero options would confuse server/container installers.
- Showing a screen and then immediately saying "no packs available for this profile" is bad UX.

**How to apply:** `state_machine.py` checks `config.desktop.profile == "minimal"` in the
`_next_state()` transition from `DESKTOP` and jumps to `SECURE_BOOT` directly.

---

### D4: Why do post_deploy scripts run as the target user?

**Alternative considered:** Run post_deploy as root, then chown the files.

**Decision:** `post_deploy` runs as the installing user.

**Reasoning:**
- Dotfiles tools (all 7 packs) are designed to deploy to `~/.config`, `~/.local/share`.
  Root-owned files in these directories break application access.
- XDG directories (`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`) resolve to the user's home.
  Running as root gives `/root/.config`, not `/home/user/.config`.
- If a pack genuinely needs root (CRITICAL only), it declares `requires_root: true` in the
  manifest and handles elevated operations explicitly through documented steps.

---

### D5: CRITICAL packs — install or block?

**Alternative considered:** Block CRITICAL packs entirely (catalog-only, no auto-install).

**Decision:** Install with multi-step explicit confirmation.

**Reasoning:** The user explicitly opted in by selecting the pack. Blocking the install after
showing the pack in the catalog would be misleading. The right answer is to make the risks
transparent and let the user decide — consistent with the ouroborOS philosophy of giving the
user power with clear information.

**How CRITICAL is handled:**
1. Show the full list of system changes BEFORE doing anything
2. Require typing the exact string `yes`
3. Confirm each destructive action individually (e.g. "Proceed with /etc/pacman.conf edit? [y/N]")
4. After each step, verify the change succeeded before continuing
5. On any failure, stop and report current state (partial install, not rolled back)

---

### D6: External repository format — git repo or directory?

**Alternative considered:** Support only git repos as external sources.

**Decision:** Support both git repos (detected by `.git` in the URL or trailing `.git`) and
plain HTTPS directories (index.yaml + individual pack files).

**Reasoning:**
- Git repos give atomic versioning and easy `repo-update` via `git pull`
- Plain HTTPS is simpler for distribution via static file hosting or GitHub raw
- Both formats use the same manifest schema; only the fetch mechanism differs

**Implementation:**
- URL ending in `.git` or containing `/tree/` → git clone to cache dir
- Otherwise → `curl` the individual manifest files referenced in `index.yaml`

---

### D7: Version detection for -Su

**Challenge:** Packs have heterogeneous versioning:
- AUR-based: compare current vs available `pkgver` from AUR RPC
- Git-based (post_deploy scripts): compare installed commit SHA vs upstream HEAD
- Rolling/curl (Ambxst, Danklinux): no reliable version — compare SHA of downloaded content

**Decision:**
- AUR packages: query `https://aur.archlinux.org/rpc/?v=5&type=info&arg=<pkgname>` and compare `Version`
- Git repos: use `git ls-remote` to check HEAD without a full clone
- Rolling/unknown: always report "update check not available" and offer reinstall

**Stored in system.yaml:**
```yaml
dots_packs:
  - id: noctalia
    channel: stable
    installed_version: "4-1"   # AUR pkgver-pkgrel
    installed_at: "2026-06-07"
```

---

## dots_profiles.py Module Design

New Python module at `src/installer/dots_profiles.py` — the installer-side catalog reader.

```python
@dataclass
class DotsPack:
    id: str
    name: str
    description: str
    author: str
    homepage: str
    compatibility: str          # "low" | "medium" | "high" | "critical"
    profiles: list[str]         # compatible DE profiles
    has_stable: bool
    has_git: bool
    stable_version_hint: str    # display string like "v4", "0.2.3"

def load_catalog(manifest_dir: str = MANIFEST_DIR) -> list[DotsPack]:
    """Load all pack manifests from the given directory."""

def packs_for_profile(profile: str) -> list[DotsPack]:
    """Return packs compatible with the given desktop profile."""
```

The manifest directory path in the installer context points to the ISO's manifest directory,
which is mounted at runtime.

---

## system.yaml Schema Extension

```yaml
# Existing keys (unchanged)
user_packages: [...]
aur_packages: [...]
appimage_packages: [...]

# New key
dots_packs:
  - id: noctalia
    channel: stable
    installed_version: "4-1"
    installed_at: "2026-06-07"
```

The `update_dots_packs()` function in `our-dots` uses the same embedded `python3 -c` pattern
as `our-pac`'s `update_system_yaml_packages()`:

```bash
python3 - <<'EOF'
import yaml, sys, os
path = "/etc/ouroboros/system.yaml"
with open(path) as f:
    doc = yaml.safe_load(f) or {}
packs = doc.setdefault("dots_packs", [])
# add/remove logic here
tmp = path + ".tmp"
with open(tmp, "w") as f:
    yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
os.replace(tmp, path)
EOF
```
