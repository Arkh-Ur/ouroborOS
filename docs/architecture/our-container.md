# our-container — Architecture

`our-container` is a single-file Bash wrapper around `systemd-nspawn` and `machinectl` that provides Btrfs-aware container management on ouroborOS. It is the primary tool for running development environments, services, and multi-distro workloads inside the host system.

---

## 1. Architectural Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        ouroborOS Host                          │
│                                                                 │
│  ┌──────────┐     ┌──────────────┐     ┌────────────────────┐  │
│  │  User     │────>│   our-container    │────>│  systemd-nspawn    │  │
│  │  (sudo)   │     │  (wrapper)   │     │  (container engine)│  │
│  └──────────┘     └──────┬───────┘     └────────┬───────────┘  │
│                          │                      │               │
│              ┌───────────┼──────────┐           │               │
│              ▼           ▼          ▼           ▼               │
│       ┌────────────┐ ┌────────┐ ┌────────┐ ┌─────────────┐   │
│       │ machinectl │ │ btrfs  │ │ journal│ │ .nspawn     │   │
│       │ (lifecycle)│ │(snaps) │ │ (logs) │ │ (config)    │   │
│       └────────────┘ └────────┘ └────────┘ └─────────────┘   │
│                            │                                   │
│  ┌─────────────────────────▼────────────────────────────────┐  │
│  │               /var/lib/machines/  (Btrfs)                │  │
│  │  ┌───────┐  ┌───────┐  ┌───────────┐  ┌──────────┐     │  │
│  │  │ ctr-1 │  │ ctr-2 │  │.snapshots │  │.images   │     │  │
│  │  │(subvol)│  │(subvol)│  │(ro snaps) │  │(base imgs)│    │  │
│  │  └───────┘  └───────┘  └───────────┘  └──────────┘     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow: Container Lifecycle

```
  our-container create mydev arch
         │
         ▼
  ┌──────────────┐     ┌───────────────┐     ┌────────────────┐
  │  Validate    │────>│  Create       │────>│  Bootstrap     │
  │  name + root │     │  Btrfs subvol │     │  (pacstrap /   │
  │  access      │     │  or mkdir     │     │   debootstrap) │
  └──────────────┘     └───────────────┘     └───────┬────────┘
                                                      │
                                                      ▼
                                               ┌──────────────┐
                                               │  Set root    │
                                               │  password    │
                                               │  via nspawn  │
                                               └──────────────┘

  our-container start mydev
         │
         ▼
  ┌──────────────┐     ┌───────────────┐     ┌────────────────┐
  │  Check state │────>│  machinectl   │────>│  Poll state    │
  │  (not        │     │  start        │     │  (5 retries,   │
  │   running)   │     │               │     │   1s interval) │
  └──────────────┘     └───────────────┘     └────────────────┘

  our-container enter mydev
         │
         ▼
  ┌──────────────┐     ┌──────────────┐     ┌───────────────┐
  │  Check state │────>│  machinectl  │──X──>│  systemd-     │
  │              │     │  shell       │ fail │  nspawn -D    │
  └──────────────┘     └──────────────┘     │  (fallback)   │
                                            └───────────────┘
```

### Data Flow: Snapshot & Restore

```
  our-container snapshot create mydev v1.0
         │
         ▼
  ┌──────────────┐     ┌──────────────┐     ┌────────────────────┐
  │  Verify Btrfs│────>│  btrfs       │────>│  Read-only snapshot│
  │  subvolume   │     │  subvolume   │     │  at .snapshots/    │
  │              │     │  snapshot -r │     │  mydev/v1.0/      │
  └──────────────┘     └──────────────┘     └────────────────────┘

  our-container snapshot restore mydev v1.0
         │
         ▼
  ┌──────────────────┐     ┌──────────────┐     ┌───────────────┐
  │  Safety snapshot │────>│  btrfs       │────>│  btrfs         │
  │  (pre-restore-   │     │  subvolume   │     │  subvolume     │
  │   timestamp)     │     │  delete      │     │  snapshot      │
  └──────────────────┘     └──────────────┘     │  (restore)     │
                                                 └───────┬───────┘
                                                         │
                                              ┌──────────▼────────┐
                                              │  On failure:      │
                                              │  restore from     │
                                              │  safety snapshot  │
                                              └───────────────────┘
```

---

## 2. Script Design

### File Location

```
src/ouroborOS-profile/airootfs/usr/local/bin/our-container   # Source (ships in ISO)
/usr/local/bin/our-container                                   # Installed on target
```

1786 lines of Bash. Single file, no external dependencies beyond systemd and Btrfs tools.

### Internal Structure

```
our-container
│
├── Constants & Configuration                    [lines 1-26]
│   ├── MACHINES_ROOT="/var/lib/machines"
│   ├── SNAPSHOTS_ROOT="/var/lib/machines/.snapshots"
│   ├── IMAGES_ROOT="/var/lib/machines/.images"
│   └── PROGRAM_NAME="our-container"
│
├── Logging Helpers                              [lines 28-38]
│   ├── _log(level, ...)       → stderr with timestamp
│   ├── log_info / log_warn / log_error
│   └── die(msg)               → log_error + exit 1
│
├── Pre-condition Checks                           [lines 40-98]
│   ├── require_root(args)    → re-exec with sudo if $EUID != 0
│   ├── _container_exists(name)
│   ├── _container_state(name)              → queries machinectl
│   ├── _require_container_exists(name, action)
│   ├── _require_container_not_running(name, action)
│   ├── _is_btrfs(path)                    → findmnt check
│   ├── _is_btrfs_subvolume(path)          → btrfs subvolume show
│   └── _nspawn_file(name)                 → /etc/systemd/nspawn/<name>.nspawn
│
├── Container Lifecycle Commands               [lines 100-366]
│   ├── cmd_create      → validate → subvol → bootstrap → passwd
│   ├── cmd_enter       → machinectl shell (fallback: nspawn -D)
│   ├── cmd_start       → machinectl start → poll state
│   ├── cmd_stop        → machinectl stop → poll state
│   ├── cmd_list        → machinectl list + disk scan
│   └── cmd_remove      → stop → remove snapshots → remove .nspawn → delete subvol
│
├── Snapshot Management                          [lines 368-515]
│   ├── cmd_snapshot_create   → btrfs subvolume snapshot -r (read-only)
│   ├── cmd_snapshot_list     → creation time + size via qgroup
│   └── cmd_snapshot_restore  → safety snap → delete → restore → rollback on fail
│
├── Storage Management                           [lines 517-638]
│   ├── cmd_storage_mount    → create/update .nspawn [Files] Bind= entry
│   └── cmd_storage_umount   → grep -v the Bind line, clean up empty .nspawn
│
├── Cleanup & Disk Usage                        [lines 640-879]
│   ├── cmd_cleanup     → prune snapshots >30 days OR when disk >=90%
│   └── cmd_disk_usage  → df + btrfs qgroup per container + threshold alert
│
├── Image Management                            [lines 881-1037]
│   ├── cmd_image_pull    → bootstrap read-only base image with metadata marker
│   ├── cmd_image_list    → show distro + created date + size + ro status
│   └── cmd_image_remove  → set rw → btrfs subvolume delete
│
├── Monitoring & Diagnostics                    [lines 1039-1625]
│   ├── cmd_monitor   → real-time dashboard (clear + machinectl list loop)
│   ├── cmd_diagnose  → 5 health checks (machined, storage, integrity, net, PID)
│   ├── cmd_stats     → CPU delta (2 samples), RSS/VIRT/Peak, threads, TCP conns
│   ├── cmd_logs      → journalctl --machine=$name [--follow] [--lines N]
│   └── cmd_check     → Btrfs errors, services, tools, registration consistency
│
└── Command Dispatcher                           [lines 1627-1786]
    ├── usage()        → full help text (HELP heredoc)
    └── case "${1:-}"  → routes to cmd_* functions
        ├── Top-level: create, enter, start, stop, list, remove, cleanup, ...
        ├── Sub-groups: snapshot {create,list,restore}
        │               storage {mount,umount}
        │               image {pull,list,remove}
        └── Aliases: ls→list, rm→remove, du→disk-usage, unmount→umount
```

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Single file, zero deps** | No external scripts, no libraries. Just Bash + systemd tools. |
| **Fail loudly** | `set -euo pipefail` + `die()` on every validation failure. |
| **Auto-escalate** | `require_root()` re-execs with `sudo` transparently. |
| **Btrfs-first, directory-fallback** | Tries `btrfs subvolume create`, falls back to `mkdir -p`. |
| **Idempotent where possible** | `start` on running container = no-op. `stop` on stopped = no-op. |
| **Destructive operations ask** | `snapshot restore` creates safety backup first. `remove` stops if running. |

---

## 3. systemd Integration

### Relationship to systemd Components

```
┌─────────────────────────────────────────────────┐
│                  systemd (PID 1)                │
│                                                  │
│  ┌─────────────────────┐  ┌──────────────────┐  │
│  │ systemd-machined    │  │ systemd-nspawn   │  │
│  │ (dbus API for       │  │ (container       │  │
│  │  machine mgmt)      │──│  execution)      │  │
│  └────────┬────────────┘  └──────────────────┘  │
│           │                                      │
│  ┌────────▼────────────┐                        │
│  │ machinectl          │  CLI frontend          │
│  │ (list/start/stop/   │  our-container delegates     │
│  │  shell/terminate)   │  lifecycle to this     │
│  └─────────────────────┘                        │
│                                                  │
│  ┌─────────────────────┐  ┌──────────────────┐  │
│  │ journalctl          │  │ systemd-resolved │  │
│  │ (--machine=<name>)  │  │ (container DNS)  │  │
│  └─────────────────────┘  └──────────────────┘  │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │ .nspawn files                           │    │
│  │ /etc/systemd/nspawn/<name>.nspawn       │    │
│  │ (bind mounts, user ns, resolv conf)     │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### How our-container Uses Each Component

| systemd Tool | our-container Usage |
|---|---|
| **machinectl list** | `cmd_list`, `cmd_monitor`, `cmd_stats` — enumerate containers and state |
| **machinectl start** | `cmd_start` — boot container as systemd machine |
| **machinectl stop** | `cmd_stop` — graceful shutdown via systemd inside container |
| **machinectl shell** | `cmd_enter` — open interactive shell (preferred method) |
| **machinectl show** | `_container_state()` — parse `State=` property |
| **machinectl terminate** | Suggested in error messages for stuck containers |
| **systemd-nspawn -D** | `cmd_create` (passwd), `cmd_enter` (fallback) — direct access |
| **journalctl --machine** | `cmd_logs` — container journal output with `--follow` and `--lines` |
| **.nspawn files** | `cmd_storage_mount/umount` — configure bind mounts declaratively |

### .nspawn File Format

Generated by `cmd_storage_mount`. Location: `/etc/systemd/nspawn/<container>.nspawn`.

```ini
[Exec]
PrivateUsers=no

[Files]
Bind=/host/path:/container/path
```

Files are read by `systemd-nspawn` on container start. Changes to `.nspawn` files require a container restart to take effect — `our-container` warns the user about this.

---

## 4. Storage Management

### Directory Layout

```
/var/lib/machines/                          # MACHINES_ROOT
├── webserver/                              # Container (Btrfs subvolume)
│   ├── bin/ usr/ var/ etc/ ...             #   Full bootstrapped filesystem
│   └── ...
├── dev-env/                                # Another container
│   └── ...
├── .snapshots/                             # SNAPSHOTS_ROOT (hidden)
│   ├── webserver/
│   │   ├── v1.0/                           #   Read-only Btrfs snapshot
│   │   ├── v1.1/
│   │   └── pre-restore-20260407T143000/    #   Auto-created safety backup
│   └── dev-env/
│       └── baseline/
└── .images/                                # IMAGES_ROOT (hidden)
    ├── arch/                               #   Cached Arch base image (ro)
    │   └── .our-container-image                  #     Metadata marker
    ├── debian/
    │   └── .our-container-image
    └── ubuntu/
        └── .our-container-image
```

### Btrfs Subvolume Strategy

```
  btrfs subvolume create /var/lib/machines/webserver
         │
         ▼
  ┌─────────────────────────┐
  │  webserver/              │  ← Read-write Btrfs subvolume
  │  (live container root)   │     Container boots from here
  └──────────┬──────────────┘
             │
             │  btrfs subvolume snapshot -r
             │
             ▼
  ┌─────────────────────────┐
  │  .snapshots/webserver/  │
  │  ├── v1.0/              │  ← Read-only COW snapshot
  │  │   (shared blocks     │     Space-efficient: only
  │  │    with parent)      │     changed blocks are new
  │  └── v1.1/              │
  └─────────────────────────┘
```

**Key properties:**
- Containers are Btrfs subvolumes → **instant, copy-on-write snapshots**.
- Snapshots are created read-only (`-r` flag) → **immutable by default**.
- Base images are set read-only via `btrfs property set -ts ro true`.
- On non-Btrfs filesystems, our-container falls back to plain directories (snapshots unavailable).

### Snapshot Restore Safety

```
  1. Create safety snapshot "pre-restore-<timestamp>"
  2. Delete current container subvolume
  3. Restore from target snapshot
  4. If step 3 fails → restore from safety snapshot
```

This ensures the container can always be recovered even if the restore operation is interrupted.

### Cleanup Strategy

The `cmd_cleanup` command applies two pruning rules:

| Condition | Action |
|-----------|--------|
| Snapshot is **older than 30 days** | Prune (unless `pre-restore-*`) |
| Disk usage **>= 90%** and container has **> 3 snapshots** | Keep only 3 most recent |

Safety snapshots (`pre-restore-*`) are **never** automatically pruned.

---

## 5. Security Model

### Privilege Escalation

```
  our-container create mydev
         │
         ▼
  ┌──────────────────────┐
  │ require_root()       │
  │                      │
  │ if $EUID != 0:       │
  │   exec sudo          │
  │   /usr/local/bin/    │
  │   our-container "$@"       │
  └──────────────────────┘
```

Every command that modifies state calls `require_root()`. The function re-execs the entire script with `sudo` — this preserves the original argument vector.

### Input Validation

| Input | Validation | Regex |
|-------|-----------|-------|
| Container name | Alphanumeric + `.`, `-`, `_` | `^[a-zA-Z0-9._-]+$` |
| Snapshot name | Same as container name | `^[a-zA-Z0-9._-]+$` |
| Container path (storage) | Must be absolute | Starts with `/` |
| Host path (storage) | Must exist on host | `[[ -e "$host_path" ]]` + `realpath` |
| Distro | Allowlist only | `arch`, `debian`, `ubuntu` |
| Cleanup threshold | Integer 1-99 | `^[0-9]+$` + range check |
| Monitor interval | Positive integer | `^[0-9]+$` + `>= 1` |

### Container Isolation

`our-container` delegates isolation to `systemd-nspawn`, which provides:

| Isolation Feature | systemd-nspawn Default |
|-------------------|----------------------|
| PID namespace | Yes (separate PID tree) |
| Mount namespace | Yes (separate filesystem view) |
| Network namespace | Optional (host networking by default) |
| User namespace | Off by default (`PrivateUsers=no` in .nspawn) |
| seccomp | Applied by default |
| cgroups | Managed by systemd-machined |
| CAP drop | All capabilities dropped except essential |

### State Guards

Every destructive operation checks container state first:

```
  _require_container_not_running()  → called before: create, remove, snapshot create/restore
  _require_container_exists()       → called before: enter, start, stop, remove, snapshot
```

`cmd_remove` auto-stops running containers before deletion. `cmd_stop` suggests `machinectl terminate` if the graceful stop fails.

---

## 6. Installation Flow

### Build-Time (archiso → ISO)

```
  src/ouroborOS-profile/airootfs/
  └── usr/local/bin/our-container          ← Full 1786-line script
         │
         │  archiso build (mkarchiso)
         ▼
  out/ouroborOS-*.iso               ← Ships at /usr/local/bin/our-container in live env
```

The script lives in `airootfs/usr/local/bin/` which mirrors the live ISO filesystem. During `mkarchiso`, the entire `airootfs/` tree is copied into the ISO. No separate installation step is needed.

### Install-Time (configure.sh → target)

```
  Live ISO
  /usr/local/bin/our-container (full version)
         │
         │  configure.sh: _install_our_tools()
         ▼
  ┌────────────────────────────────────────┐
  │  if [[ -f /usr/local/bin/our-container ]];   │
  │    cp → $TARGET/usr/local/bin/our-container   │
  │    chmod 0755                           │
  │  else                                   │
  │    Install minimal stub                 │
  │    (echoes error, points to our-pacman)    │
  │  fi                                     │
  └────────────────────────────────────────┘
         │
         ▼
  Installed System
  /usr/local/bin/our-container (full version)
```

**Key detail:** The installer copies the script from the **live ISO's** `/usr/local/bin/our-container` (which is the full version from the archiso profile). If the ISO copy is missing, a minimal stub is installed that tells the user to reinstall via `our-pacman`.

### Runtime Dependencies

| Dependency | Required For | Installed By |
|-----------|-------------|-------------|
| `systemd-nspawn` | All container operations | `systemd` (base) |
| `machinectl` | Lifecycle + state queries | `systemd` (base) |
| `btrfs` progs | Snapshots, subvolumes, qgroup | `btrfs-progs` (base) |
| `pacstrap` | Arch container bootstrap | `arch-install-scripts` |
| `debootstrap` | Debian/Ubuntu bootstrap | User installs via `our-pacman` |
| `journalctl` | Container log viewing | `systemd` (base) |
| `findmnt` | Btrfs detection | `util-linux` (base) |

---

## 7. Testing Strategy

### Three-Layer Test Pyramid

```
              ╱╲
             ╱  ╲         E2E Tests
            ╱ QEMU╲       15 phases, QEMU + SSH
           ╱________╲     Full container lifecycle
          ╱          ╲
         ╱ Integration╲   Integration Tests
        ╱  (pytest +   ╲   Real our-container script + mock
       ╱   subprocess)  ╲  tools (machinectl, btrfs)
      ╱________________╲
     ╱                  ╲
    ╱   Unit Tests       ╲   Unit Tests (pytest)
   ╱  (mock everything)  ╲  Full mock of all external tools
  ╱________________________╲  Individual command validation
```

### Unit Tests

**Location:** `tests/our_container/test_our_container.py`, `tests/our_container/conftest.py`

- Mock all external tools (`machinectl`, `btrfs`, `pacstrap`, `debootstrap`) via PATH override
- Test individual commands in isolation: create, list, snapshot, storage, image, etc.
- Validate output parsing, error conditions, and argument validation
- Conftest creates a complete mock environment with fake `MACHINES_ROOT`

```python
# Pattern: mock environment via PATH override
@pytest.fixture
def mock_env(tmp_path):
    # Create mock binaries in tmp_path/bin/
    # Set PATH to prefer mocks
    # Set MACHINES_ROOT to tmp_path
    yield {"MACHINES_ROOT": str(tmp_path), "PATH": f"{tmp_path}/bin:{os.environ['PATH']}"}
```

### Integration Tests

**Location:** `src/installer/tests/test_our_container_integration.py`, `src/installer/tests/conftest.py`

- Uses the **real** `our-container` script (subprocess execution)
- Mocks only external tools that need kernel access (`machinectl`, `btrfs`)
- Tests full command flows: create → start → enter → stop → remove
- Validates .nspawn file generation, snapshot directory structure, cleanup behavior
- Conftest provides `our_container_run()` helper for subprocess execution with env overrides

### E2E Tests

**Location:** `tests/scripts/e2e-our-container.sh` (1382 lines, 15 phases)

Full end-to-end lifecycle inside a QEMU virtual machine with an installed ouroborOS:

| Phase | What It Tests |
|-------|--------------|
| 0 | Prerequisites (KVM, OVMF, SSH) |
| 1 | Build ISO |
| 2 | Unattended install in QEMU |
| 3 | Boot installed system |
| 4 | Verify our-container installation on target |
| 5 | Container lifecycle (create/list/start/stop/remove) |
| 6 | Error handling (invalid names, missing containers, etc.) |
| 7 | Snapshot management (create/list/restore/verify data persistence) |
| 8 | Storage management (mount/umount bind mounts) |
| 9 | Image management (pull/list/remove) |
| 10 | Monitoring & diagnostics (diagnose/check/disk-usage/stats) |
| 11 | Cleanup command |
| 12 | Logs command |
| 13 | Persistence verification (reboot + verify containers survive) |
| 14 | System integrity (host health after all operations) |

All communication happens via **SSH** (`sshpass` + `ssh`) into the QEMU VM. Serial console output is captured for debugging.

### CI Coverage

| Test Type | Runs In | CI Workflow |
|-----------|---------|-------------|
| Unit tests | Docker (Arch container) | `test.yml` → `pytest-suite` |
| Integration tests | Docker (Arch container) | `test.yml` → `pytest-suite` |
| E2E tests | Requires KVM (not in CI) | Manual / local only |
| Shell validation | Docker | `lint.yml` → `shellcheck -S style` |

---

## 8. Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| **Btrfs required for snapshots** | `snapshot create/list/restore` fail on non-Btrfs | Containers still work as plain directories without snapshots |
| **debootstrap optional** | Debian/Ubuntu containers unavailable if not installed | `sudo our-pacman -S debootstrap` |
| **arch-install-scripts optional** | Arch containers unavailable if not installed | `sudo our-pacman -S arch-install-scripts` |
| **No container networking isolation** | Containers share host network by default | Configure via `.nspawn` files manually |
| **No resource limits** | No CPU/memory/disk limits on containers | Not implemented; could use systemd resource controls |
| **No container registry** | Images are local-only, no push/pull from remote | Manual file transfer or rebuild |
| **No automatic image updates** | Base images are static after `image pull` | Remove and re-pull to update |
| **Single-host only** | No cluster or multi-node support | By design — use for local development |
| **Root required** | All operations need root (auto-escalated via sudo) | Necessary for container management |
| **No container autostart** | Containers don't start on boot | Create systemd unit manually |
| **E2E tests require KVM** | Cannot run in CI containers | Run locally with QEMU |

---

## Related Documents

- [Architecture Overview](./overview.md) — System design and layer diagram
- [systemd Integration](./systemd-integration.md) — systemd ecosystem in ouroborOS
- [Immutability Strategy](./immutability-strategy.md) — Btrfs layout and host snapshots
- [our-container User Guide](../our-container.md) — Command reference and usage examples
