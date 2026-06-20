# Implementation Plan — v0.6.1 Dotfiles/Config Packs

**Version:** v0.6.1
**Status:** In Progress
**Date:** 2026-06-07
**Branch:** dev

---

## History

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-06-07 | Initial plan |

---

## Milestones

### M1 — Core tool + manifests (no installer integration)

**Goal:** `our-dots` is functional as a standalone post-install tool.

| Task | File | Notes |
|------|------|-------|
| Create manifest directory | `src/ouroborOS-profile/airootfs/usr/local/lib/ouroboros/dots/packs/` | 7 YAML files |
| Write 7 pack manifests | `*.yaml` (one per pack) | See spec §2 |
| Write `our-dots` bash tool | `src/ouroborOS-profile/airootfs/usr/local/bin/our-dots` | list, -Si, -S, -R, -Q, -Qs |
| Register in shellcheck test | `tests/scripts/test-shellcheck.sh` | Add our-dots to the list |
| Register in profiledef.sh | `src/ouroborOS-profile/profiledef.sh` | 0:0:755 |

**Verification:** `shellcheck -S style our-dots` clean; `our-dots list` shows 7 packs; `our-dots -Si noctalia` shows credits.

---

### M2 — Confirmation flows + -Su + system.yaml

**Goal:** CRITICAL warning flow, system.yaml integration, update command.

| Task | File | Notes |
|------|------|-------|
| HIGH warning flow | `our-dots` | Single prompt before install |
| CRITICAL multi-step flow | `our-dots` | See spec §1.1.1 |
| `--noconfirm` flag | `our-dots` | Suppresses all interactive prompts (for installer use) |
| system.yaml wiring | `our-dots` | Read/write `dots_packs` key via python3 one-liner |
| `-Su` update command | `our-dots` | Check AUR pkgver or git HEAD |
| Write log to `/var/log/our-dots/` | `our-dots` | Timestamped per install |

**Verification:** Install/remove noctalia; check `system.yaml:dots_packs` updated. Run CRITICAL flow for illogical-impulse (dry run with mock our-aur).

---

### M3 — External repository system

**Goal:** Users can add, update, and remove external manifest repos.

| Task | File | Notes |
|------|------|-------|
| `repo-add` command | `our-dots` | HTTPS validation, fetch index.yaml, cache |
| `repo-remove` command | `our-dots` | Remove from dots-repos.yaml + cache |
| `repo-list` command | `our-dots` | Built-in + external |
| `repo-update` command | `our-dots` | Fetch latest manifests from all external repos |
| `dots-repos.yaml` schema | `/etc/ouroboros/dots-repos.yaml` | Created on first `repo-add` |
| `/var/lib/ouroboros/dots/` directory | `configure.sh` or service | Ensure exists at boot |

**Verification:** `repo-add` with a local test server or GitHub raw URL; `repo-update` downloads manifests; `list` shows packs from external repo.

---

### M4 — Installer integration

**Goal:** `dots_pack` selectable during installation.

| Task | File | Notes |
|------|------|-------|
| `DotsPackConfig` dataclass | `src/installer/config.py` | With YAML loading + validation |
| `DOTS_PACK` FSM state | `src/installer/state_machine.py` | Between DESKTOP and SECURE_BOOT |
| `show_dots_pack_selection()` | `src/installer/tui.py` | 3-step flow: list → channel → confirm |
| `dots_profiles.py` module | `src/installer/dots_profiles.py` | Pack catalog reader for installer |
| `configure.sh` block | `src/installer/ops/configure.sh` | DOTS_PACK + DOTS_CHANNEL env vars |
| YAML template | `templates/install-config.yaml` | `dots_pack: { pack: null, channel: stable }` |
| FSM tests | `src/installer/tests/test_state_machine.py` | DOTS_PACK skip when minimal |
| Config tests | `src/installer/tests/test_config.py` | DotsPackConfig load + validation |

**Verification:** Unattended install with `dots_pack: {pack: noctalia, channel: stable}` → noctalia present in installed system. TUI flow tested manually.

---

### M5 — E2E tests + documentation

**Goal:** CI coverage and docs complete.

| Task | File | Notes |
|------|------|-------|
| `our-dots` E2E section | `tests/scripts/e2e-our-tools.sh` | Section 9: our-dots lifecycle |
| docs/v0.6.1/ complete | All 5 documents | PRD, TRD, spec, plan, design |
| `PHASE_6_PLAN.md` update | `docs/PHASE_6_PLAN.md` | Add v0.6.1 section |
| Bump version | `src/ouroborOS-profile/profiledef.sh` | `iso_version="0.6.1"` |

---

## Commit Plan

```
feat(our-dots): add our-dots tool with 7 built-in pack manifests
feat(our-dots): add CRITICAL/HIGH confirmation flows and system.yaml wiring
feat(our-dots): add repo management (repo-add/remove/list/update)
feat(installer): add DOTS_PACK state and show_dots_pack_selection()
feat(installer): wire dots_pack to configure.sh
test(e2e): add our-dots lifecycle to e2e-our-tools.sh
docs: add v0.6.1 documentation
build(profile): bump version to 0.6.1
```

---

## Dependencies

None. All features are self-contained. `our-pac` and `our-aur` are already present in the ISO
and are used as install backends (no modifications needed).

---

## Phase 6 Context

After v0.6.1 ships, Phase 6 begins:
- **GUI Installer** — GTK4/libadwaita-based graphical installer
- **OTA casync** — image-based OTA updates via casync

The `our-dots` feature deliberately avoids touching Phase 6 infrastructure to keep v0.6.1
scope-contained and shippable independently.
