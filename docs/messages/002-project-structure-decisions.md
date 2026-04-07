# Project Structure Decisions — Session Log

**Date:** 2026-03-26
**Branch:** `dev`
**Session type:** Initial architecture and structure setup

---

## Decisions Made in This Session

### 1. Branch Strategy

| Branch | Purpose |
|--------|---------|
| `master` | Stable production releases |
| `dev` | Active development (current) |
| `feature/*` | Individual feature work, merged into dev |
| `claude/setup-project-dev-branch-laDS1` | Initial Claude Code setup branch |

**Rationale:** Classic GitFlow-inspired model. `master` is never touched directly. All development goes through `dev` first.

---

### 2. Immutability Strategy: Btrfs (not OSTree)

**Decision:** Use Btrfs subvolumes + read-only root mount.

**Alternatives evaluated:**
- **OSTree**: Rejected. Poor pacman/ArchLinux integration. Heavy dependency.
- **OverlayFS only**: Rejected for primary root. Good for live ISO, not for installed system.
- **ComposeFS**: Too new (kernel 6.6+), tooling immature. Revisit in v0.3.

**Btrfs layout decided:**
```
@          → /       (ro)
@var       → /var    (rw)
@etc       → /etc    (rw)
@home      → /home   (rw)
@snapshots → /.snapshots
```

---

### 3. Bootloader: systemd-boot (not GRUB)

**Decision:** systemd-boot exclusively. No GRUB support.

**Rationale:**
- GRUB adds 3x the configuration complexity
- systemd-boot is UEFI-native and minimal
- Integrates with `bootctl` and kernel install hooks automatically
- Snapshot entries are trivial `.conf` files

**Consequence:** BIOS systems are not supported in v0.1. This is acceptable given the target audience (modern hardware, UEFI).

---

### 4. Networking: systemd-networkd + iwd (not NetworkManager)

**Decision:** No NetworkManager. Use systemd-networkd for addressing, iwd for WiFi.

**Rationale:**
- NetworkManager is over-engineered for our use case
- systemd-networkd is declarative and integrates with the rest of the stack
- iwd is smaller and faster than wpa_supplicant

---

### 5. Installer Language: Bash + Python

**Decision:** Bash for low-level operations, Python for the installer logic and TUI.

**Rationale:**
- Bash is universal on ArchLinux live environments, no extra dependencies
- Python provides clean state machine implementation, YAML parsing, input validation
- Python **Rich** library handles TUI rendering (primary), with `whiptail` as fallback
- Avoids pulling in Rust/Go toolchain as a build dependency

---

### 6. docs/ Structure

```
docs/
├── architecture/    ← System design decisions
├── build/           ← ISO build process
├── installer/       ← Installer architecture
├── messages/        ← Project log and decisions (this folder)
└── build-and-flash.md ← Build, flash, and QEMU instructions
```

**Rationale:** Separates concerns. Architecture docs live with design decisions. Build docs live with build artifacts. Messages capture *why* decisions were made (ADR-style).

---

### 7. skills/ Structure

Six expert skill profiles defined for Claude Code:
1. `systemd-expert` — All systemd subsystems
2. `immutable-systems-expert` — Btrfs, overlayfs, atomic updates
3. `archiso-builder` — ISO build process
4. `installer-developer` — Installer state machine and UX
5. `filesystem-storage-expert` — Partitioning, LUKS, Btrfs
6. `bootloader-uefi-expert` — systemd-boot, UEFI, Secure Boot

**Rationale:** Each domain requires deep, specialized knowledge. Using skill files ensures Claude Code responses are grounded in the correct technical context for the subdomain.

---

### 8. CLAUDE.md

Created to give Claude Code persistent context about:
- Project type and goals
- Branch conventions
- Tech stack
- Which skills to use for which tasks
- Commit message conventions (Conventional Commits)

---

### 9. Implementation Plan Structure

Organized into 5 phases:
1. Build environment and archiso profile
2. Immutable filesystem design and Btrfs layout
3. Installer TUI and state machine
4. systemd full integration and configuration
5. Testing, CI/CD, and first release

Each phase has milestones, deliverables, and acceptance criteria.

---

## Open Questions (to be resolved)

| Question | Priority | Notes |
|----------|----------|-------|
| License selection | Medium | GPL-3.0 vs Apache-2.0 |
| Secure Boot support | Low | Phase 3+ |
| AUR helper inclusion | Low | yay vs paru, opt-in |
| GUI installer roadmap | Low | v0.3+ consideration |
| zram vs swap partition | Medium | Likely zram by default |
| Desktop environment default | Low | Out of scope v0.1 |
