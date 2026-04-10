# our-box — Container Management Guide

`our-box` is a systemd-nspawn wrapper that provides simple, Btrfs-aware container management on ouroborOS. It handles container lifecycle, snapshots, bind mounts, base images, monitoring, and diagnostics — all without the complexity of Docker or Podman.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Command Reference](#command-reference)
5. [Common Use Cases](#common-use-cases)
6. [Troubleshooting](#troubleshooting)
7. [systemd Integration](#systemd-integration)

---

## Overview

`our-box` wraps `systemd-nspawn` and `machinectl` to provide a streamlined container experience on ouroborOS. Key features:

- **Btrfs subvolumes** — containers are created as Btrfs subvolumes by default, enabling instant copy-on-write snapshots
- **Multiple distros** — create Arch Linux, Debian, or Ubuntu containers
- **Snapshot/restore** — atomic snapshots with automatic safety backups on restore
- **Bind mounts** — share host directories into containers via `.nspawn` configuration
- **Base image caching** — pre-bootstrap base images to speed up container creation
- **Monitoring** — real-time dashboard, health diagnostics, and performance stats
- **Automatic privilege escalation** — re-executes with `sudo` when needed

### Storage Layout

```
/var/lib/machines/              # MACHINES_ROOT — container home
├── mydev/                      # Container (Btrfs subvolume or directory)
│   ├── bin/                    #   Bootstrapped filesystem
│   ├── usr/
│   └── ...
├── mydb/                       # Another container
└── .snapshots/                 # SNAPSHOTS_ROOT — read-only snapshots
    ├── mydev/
    │   ├── v1.0/               #   Snapshot (read-only Btrfs subvolume)
    │   └── pre-restore-.../    #   Safety backup (auto-created on restore)
    └── mydb/
└── .images/                    # IMAGES_ROOT — cached base images
    ├── arch/
    │   └── .our-box-image      #   Metadata marker
    └── debian/
```

### Supported Distros

| Distro   | Bootstrap Tool | Notes                          |
|----------|---------------|--------------------------------|
| `arch`   | `pacstrap`    | Default. Requires `arch-install-scripts`. |
| `debian` | `debootstrap` | Requires `debootstrap` package. |
| `ubuntu` | `debootstrap` | Requires `debootstrap` package. |

---

## Prerequisites

| Requirement                    | Details                                                        |
|--------------------------------|----------------------------------------------------------------|
| ouroborOS installed            | `our-box` ships with the system at `/usr/local/bin/our-box`    |
| Btrfs filesystem               | Required for snapshots. Falls back to plain directories otherwise. |
| `systemd-machined`             | Enabled by default on ouroborOS. Run `diagnose` to verify.     |
| `arch-install-scripts`         | Required for Arch containers (`pacstrap`). Install via `our-pac`. |
| `debootstrap`                  | Required for Debian/Ubuntu containers. Install via `our-pac`.  |
| Root access                    | `our-box` auto-prompts with `sudo` when needed.                |

### Installing Bootstrap Tools

```bash
# For Arch containers
sudo our-pac -S arch-install-scripts

# For Debian/Ubuntu containers
sudo our-pac -S debootstrap
```

---

## Quick Start

```bash
# 1. Create a container
our-box create mydev arch

# 2. Start it
our-box start mydev

# 3. Enter it
our-box enter mydev

# 4. Do work inside the container
pacman -S neovim git

# 5. Snapshot before making changes
our-box snapshot create mydev v1.0

# 6. Check disk usage
our-box disk-usage

# 7. Clean up old snapshots
our-box cleanup

# 8. Remove when done
our-box remove mydev
```

---

## Command Reference

### Container Lifecycle

#### `our-box create <name> [distro]`

Bootstrap a new container. Creates a Btrfs subvolume (or plain directory fallback), bootstraps the distro filesystem, and sets a root password.

```bash
our-box create mydev              # Arch container (default)
our-box create webapp debian      # Debian container
our-box create testbox ubuntu     # Ubuntu container
```

**Container names** must match: `[a-zA-Z0-9._-]+`

**Bootstrap dependencies:**
- Arch: `pacstrap` (from `arch-install-scripts`)
- Debian/Ubuntu: `debootstrap`

On failure, partial artifacts are cleaned up automatically.

#### `our-box enter <name>`

Open an interactive shell inside a container. Uses `machinectl shell` if the container is registered; falls back to `systemd-nspawn -D` if not.

```bash
our-box enter mydev
```

#### `our-box start <name>`

Boot a container as a systemd machine via `machinectl start`. Waits up to 5 seconds for the container to reach "running" state.

```bash
our-box start mydev
```

#### `our-box stop <name>`

Stop a running container via `machinectl stop`. Waits up to 5 seconds for the container to stop. If stuck, suggests `machinectl terminate`.

```bash
our-box stop mydev
```

#### `our-box list` (alias: `ls`)

List all containers showing their registration state (machinectl), storage location, filesystem type, and running status.

```bash
our-box list
```

Output shows both machinectl-registered machines and on-disk containers at `/var/lib/machines/`.

#### `our-box remove <name>` (alias: `rm`)

Delete a container, its Btrfs subvolume, all associated snapshots, and any `.nspawn` configuration. If the container is running, it is stopped first.

```bash
our-box remove mydev
```

**This is destructive.** Snapshots are not preserved.

---

### Snapshot Management

Snapshots are **read-only Btrfs subvolumes**. They require the container to be on a Btrfs filesystem and stopped.

#### `our-box snapshot create <container> <name>`

Create a read-only snapshot of a container.

```bash
our-box snapshot create mydev v1.0
our-box snapshot create mydev before-upgrade
```

Snapshot names must match: `[a-zA-Z0-9._-]+`

#### `our-box snapshot list <container>`

List all snapshots for a container, showing name, read-only status, creation date, and size.

```bash
our-box snapshot list mydev
```

#### `our-box snapshot restore <container> <name>`

Restore a container from a snapshot. **Replaces the current container state entirely.**

A safety snapshot (`pre-restore-YYYYMMDDTHHMMSS`) is automatically created before the restore. If the restore fails, an attempt is made to recover from the safety snapshot.

```bash
our-box snapshot restore mydev v1.0
```

---

### Storage (Bind Mounts)

Bind mounts are persisted in systemd-nspawn `.nspawn` configuration files. They take effect when the container starts.

#### `our-box storage mount <container> <host-path> <container-path>`

Bind-mount a host directory into a container. The host path must exist. The container path must be absolute.

```bash
our-box storage mount mydev /home/user/projects /opt/projects
```

This creates or updates `/etc/systemd/nspawn/<container>.nspawn` with a `Bind=` directive. If the container is registered, restart it for the mount to take effect.

#### `our-box storage umount <container> <container-path>` (alias: `unmount`)

Remove a bind mount from a container's `.nspawn` configuration.

```bash
our-box storage umount mydev /opt/projects
```

If the `.nspawn` file becomes empty after removal, it is deleted entirely.

---

### Maintenance

#### `our-box cleanup [--threshold <percentage>]`

Prune old container snapshots. Default threshold is `80%`.

- Snapshots older than **30 days** are pruned.
- If disk usage is **>= 90%**, only the **3 most recent** snapshots per container are kept.
- `pre-restore-*` safety snapshots are always preserved.

```bash
our-box cleanup                  # Use default 80% threshold
our-box cleanup --threshold 70   # Prune if disk > 70%
```

#### `our-box disk-usage` (alias: `du`)

Show detailed disk usage: Btrfs filesystem stats, per-container size and state, snapshot sizes, and a threshold alert.

```bash
our-box disk-usage
```

---

### Image Management

Base images are cached, read-only Btrfs subvolumes stored under `/var/lib/machines/.images/`.

#### `our-box image pull <distro>`

Pre-bootstrap a base image. The image is marked read-only on Btrfs.

```bash
our-box image pull arch
our-box image pull debian
```

#### `our-box image list` (alias: `ls`)

List cached base images with distro, read-only status, creation date, and size.

```bash
our-box image list
```

#### `our-box image remove <distro>` (alias: `rm`)

Remove a cached base image. The directory must contain a `.our-box-image` metadata marker.

```bash
our-box image remove debian
```

---

### Monitoring and Diagnostics

#### `our-box monitor [--interval <seconds>] [filter]`

Real-time dashboard showing all containers. Refreshes every N seconds (default: 2).

Displays: system CPU cores, memory usage, running container count, storage usage, and per-container state/PID/IP.

```bash
our-box monitor                    # Default: refresh every 2 seconds
our-box monitor --interval 5       # Refresh every 5 seconds
our-box monitor mydev              # Show only containers matching "mydev"
```

Press **Ctrl+C** to stop.

#### `our-box diagnose`

Run health checks on the container subsystem:

1. **systemd-machined** — is it running?
2. **Container storage** — exists? Btrfs? Disk space healthy?
3. **Container integrity** — missing `/bin` or `/usr`? Orphaned containers?
4. **Host network** — systemd-networkd and DNS resolution working?
5. **Running containers** — PID alive? Memory usage?

```bash
our-box diagnose
```

Returns the number of issues found as the exit code.

#### `our-box stats [name]`

Show performance statistics for running containers (or a specific container):

- **CPU** — percentage (measured over 1 second via `/proc/[pid]/stat`)
- **Memory** — RSS, VIRT, Peak (from `/proc/[pid]/status`)
- **Threads** — thread count
- **Disk** — container directory size
- **Network** — open TCP connections

```bash
our-box stats              # All running containers
our-box stats mydev        # Specific container
```

#### `our-box logs <name> [-f|--follow] [-n|--lines <N>]`

Show journal logs for a container via `journalctl --machine`.

```bash
our-box logs mydev                # Last 100 lines (default)
our-box logs mydev -n 50          # Last 50 lines
our-box logs mydev -f             # Follow mode (like tail -f)
our-box logs mydev -f -n 200      # Follow, starting from last 200 lines
```

#### `our-box check`

Verify filesystem and configuration integrity:

1. **Storage filesystem** — Btrfs detected? Btrfs errors in `dmesg`? Subvolume validity?
2. **System services** — systemd-machined and systemd-networkd active?
3. **Required tools** — machinectl, systemd-nspawn, btrfs, journalctl available?
4. **Configuration consistency** — on-disk vs. registered container count? Ghost entries?
5. **Boot entries** — systemd-boot entries present? Snapshot entries counted?

```bash
our-box check
```

Returns the number of errors found as the exit code.

---

### Miscellaneous

#### `our-box help`

Display full usage information with all commands, aliases, and examples.

```bash
our-box help
```

### Exit Codes

| Code | Meaning                                    |
|------|--------------------------------------------|
| 0    | Success                                    |
| 1    | Error (invalid usage, operation failed)    |
| N    | Number of issues found (`diagnose`, `check`) |

---

## Common Use Cases

### Development Environment

Create an isolated Arch environment for building or testing:

```bash
# Create and enter
our-box create dev-env arch
our-box start dev-env
our-box enter dev-env

# Install build dependencies inside the container
pacman -S base-devel cmake git

# Snapshot before risky changes
our-box snapshot create dev-env before-refactor

# If something breaks, restore
our-box snapshot restore dev-env before-refactor
```

### Web Application Testing

Test a web app across multiple distros:

```bash
# Create containers for each distro
our-box create web-arch arch
our-box create web-debian debian
our-box create web-ubuntu ubuntu

# Share the project directory into each container
our-box storage mount web-arch /home/user/myproject /opt/myproject
our-box storage mount web-debian /home/user/myproject /opt/myproject
our-box storage mount web-ubuntu /home/user/myproject /opt/myproject

# Start and test
our-box start web-arch
our-box start web-debian
our-box start web-ubuntu

# Follow logs from all containers
our-box logs web-arch -f
our-box logs web-debian -f
```

### Database Sandbox

Run a database in an isolated container:

```bash
our-box create mydb arch
our-box enter mydb
# Inside: pacman -S postgresql && initdb && pg_ctl start
```

### Monitoring Multiple Containers

Watch all containers in real time:

```bash
# Real-time dashboard
our-box monitor

# Or check health
our-box diagnose

# Performance stats
our-box stats

# Individual container logs
our-box logs mydev -f
```

### Disk Space Management

Keep container storage under control:

```bash
# Check what's using space
our-box disk-usage

# Prune snapshots if disk is getting full
our-box cleanup --threshold 70

# Remove unused base images
our-box image remove debian
```

---

## Troubleshooting

### "container does not exist"

```bash
# Verify what's on disk
ls /var/lib/machines/

# Check registration with machinectl
machinectl list --all

# Run diagnostics
our-box diagnose
```

### Container won't start

```bash
# Check the systemd-machined journal
journalctl -u systemd-machined --since "5 min ago"

# Verify the container filesystem
our-box check

# Try entering directly (bypasses machinectl)
sudo systemd-nspawn -D /var/lib/machines/mydev
```

### Container is stuck in "running" but won't respond

```bash
# Force terminate
machinectl terminate mydev

# If that fails, kill the process directly
# Find the PID from 'machinectl list'
machinectl list --all --no-pager
# Then kill the init PID
```

### "Not on Btrfs — snapshots will not be available"

Snapshots require a Btrfs filesystem at `/var/lib/machines`. If you are running on a non-Btrfs filesystem (e.g., during testing), containers still work but snapshot commands will fail. This is expected behavior.

### "pacstrap not found"

```bash
sudo our-pac -S arch-install-scripts
```

### "debootstrap not found"

```bash
sudo our-pac -S debootstrap
```

### Bind mount not appearing inside container

Bind mounts are configured via `.nspawn` files and take effect on container start. If the container is already running:

```bash
our-box stop mydev
our-box start mydev
```

### "container appears corrupted (missing /bin and /usr)"

The container filesystem is incomplete. This usually means the bootstrap failed partway through. Remove and recreate:

```bash
our-box remove mydev
our-box create mydev arch
```

### High disk usage warning

```bash
# See what's consuming space
our-box disk-usage

# Clean old snapshots
our-box cleanup

# Remove unused images
our-box image list
our-box image remove <unused-distro>

# Remove unused containers
our-box list
our-box remove <unused-container>
```

---

## systemd Integration

### How our-box integrates with systemd

`our-box` delegates container lifecycle to systemd's native container management:

| our-box command   | systemd component         | What happens                                              |
|--------------------|--------------------------|-----------------------------------------------------------|
| `start`            | `machinectl start`       | Registers the container as a systemd machine unit          |
| `stop`             | `machinectl stop`        | Sends shutdown signal; waits for clean stop                |
| `enter`            | `machinectl shell`       | Opens a PTY shell inside the running machine              |
| `logs`             | `journalctl --machine`   | Reads the container's journal via `systemd-machined`       |
| `storage mount`    | `.nspawn` file           | Writes `[Files] Bind=` directives for `systemd-nspawn`     |
| `remove`           | `machinectl stop`        | Stops the machine before removing its storage              |

### systemd-machined

`systemd-machined` is the background service that manages containers. It must be running for `machinectl` commands to work:

```bash
# Check status
systemctl status systemd-machined

# Start if not running
sudo systemctl start systemd-machined
```

### .nspawn Configuration Files

When you use `our-box storage mount`, a configuration file is created or updated at:

```
/etc/systemd/nspawn/<container-name>.nspawn
```

Example file created by `our-box storage mount mydev /data /opt/data`:

```ini
[Exec]
PrivateUsers=no

[Files]
Bind=/data:/opt/data
```

These files are read by `systemd-nspawn` when starting a container. You can edit them manually for advanced configuration, but `our-box storage` commands handle the common cases.

### Running containers as systemd services

To start a container automatically at boot, create a systemd service:

```bash
sudo machinectl enable mydev
```

This creates a `systemd-nspawn@mydev.service` that starts on boot.

### Journal integration

Container logs are accessible through the host's journal:

```bash
# Via our-box
our-box logs mydev

# Direct journalctl (equivalent)
journalctl --machine=mydev --no-pager

# Follow container logs
journalctl --machine=mydev -f
```
