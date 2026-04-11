# our-container — Container Management Guide

`our-container` is a systemd-nspawn wrapper that provides simple, Btrfs-aware container management on ouroborOS. It handles container lifecycle, snapshots, bind mounts, base images, monitoring, and diagnostics — all without the complexity of Docker or Podman.

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

`our-container` wraps `systemd-nspawn` and `machinectl` to provide a streamlined container experience on ouroborOS. Key features:

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
    │   └── .our-container-image      #   Metadata marker
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
| ouroborOS installed            | `our-container` ships with the system at `/usr/local/bin/our-container`    |
| Btrfs filesystem               | Required for snapshots. Falls back to plain directories otherwise. |
| `systemd-machined`             | Enabled by default on ouroborOS. Run `diagnose` to verify.     |
| `arch-install-scripts`         | Required for Arch containers (`pacstrap`). Install via `our-pacman`. |
| `debootstrap`                  | Required for Debian/Ubuntu containers. Install via `our-pacman`.  |
| Root access                    | `our-container` auto-prompts with `sudo` when needed.                |

### Installing Bootstrap Tools

```bash
# For Arch containers
sudo our-pacman -S arch-install-scripts

# For Debian/Ubuntu containers
sudo our-pacman -S debootstrap
```

---

## Quick Start

```bash
# 1. Create a container
our-container create mydev arch

# 2. Start it
our-container start mydev

# 3. Enter it
our-container enter mydev

# 4. Do work inside the container
pacman -S neovim git

# 5. Snapshot before making changes
our-container snapshot create mydev v1.0

# 6. Check disk usage
our-container disk-usage

# 7. Clean up old snapshots
our-container cleanup

# 8. Remove when done
our-container remove mydev
```

---

## Command Reference

### Container Lifecycle

#### `our-container create <name> [distro]`

Bootstrap a new container. Creates a Btrfs subvolume (or plain directory fallback), bootstraps the distro filesystem, and sets a root password.

```bash
our-container create mydev              # Arch container (default)
our-container create webapp debian      # Debian container
our-container create testbox ubuntu     # Ubuntu container
```

**Container names** must match: `[a-zA-Z0-9._-]+`

**Bootstrap dependencies:**
- Arch: `pacstrap` (from `arch-install-scripts`)
- Debian/Ubuntu: `debootstrap`

On failure, partial artifacts are cleaned up automatically.

#### `our-container enter <name>`

Open an interactive shell inside a container. Uses `machinectl shell` if the container is registered; falls back to `systemd-nspawn -D` if not.

```bash
our-container enter mydev
```

#### `our-container start <name>`

Boot a container as a systemd machine via `machinectl start`. Waits up to 5 seconds for the container to reach "running" state.

```bash
our-container start mydev
```

#### `our-container stop <name>`

Stop a running container via `machinectl stop`. Waits up to 5 seconds for the container to stop. If stuck, suggests `machinectl terminate`.

```bash
our-container stop mydev
```

#### `our-container list` (alias: `ls`)

List all containers showing their registration state (machinectl), storage location, filesystem type, and running status.

```bash
our-container list
```

Output shows both machinectl-registered machines and on-disk containers at `/var/lib/machines/`.

#### `our-container remove <name>` (alias: `rm`)

Delete a container, its Btrfs subvolume, all associated snapshots, and any `.nspawn` configuration. If the container is running, it is stopped first.

```bash
our-container remove mydev
```

**This is destructive.** Snapshots are not preserved.

---

### Snapshot Management

Snapshots are **read-only Btrfs subvolumes**. They require the container to be on a Btrfs filesystem and stopped.

#### `our-container snapshot create <container> <name>`

Create a read-only snapshot of a container.

```bash
our-container snapshot create mydev v1.0
our-container snapshot create mydev before-upgrade
```

Snapshot names must match: `[a-zA-Z0-9._-]+`

#### `our-container snapshot list <container>`

List all snapshots for a container, showing name, read-only status, creation date, and size.

```bash
our-container snapshot list mydev
```

#### `our-container snapshot restore <container> <name>`

Restore a container from a snapshot. **Replaces the current container state entirely.**

A safety snapshot (`pre-restore-YYYYMMDDTHHMMSS`) is automatically created before the restore. If the restore fails, an attempt is made to recover from the safety snapshot.

```bash
our-container snapshot restore mydev v1.0
```

---

### Storage (Bind Mounts)

Bind mounts are persisted in systemd-nspawn `.nspawn` configuration files. They take effect when the container starts.

#### `our-container storage mount <container> <host-path> <container-path>`

Bind-mount a host directory into a container. The host path must exist. The container path must be absolute.

```bash
our-container storage mount mydev /home/user/projects /opt/projects
```

This creates or updates `/etc/systemd/nspawn/<container>.nspawn` with a `Bind=` directive. If the container is registered, restart it for the mount to take effect.

#### `our-container storage umount <container> <container-path>` (alias: `unmount`)

Remove a bind mount from a container's `.nspawn` configuration.

```bash
our-container storage umount mydev /opt/projects
```

If the `.nspawn` file becomes empty after removal, it is deleted entirely.

---

### Maintenance

#### `our-container cleanup [--threshold <percentage>]`

Prune old container snapshots. Default threshold is `80%`.

- Snapshots older than **30 days** are pruned.
- If disk usage is **>= 90%**, only the **3 most recent** snapshots per container are kept.
- `pre-restore-*` safety snapshots are always preserved.

```bash
our-container cleanup                  # Use default 80% threshold
our-container cleanup --threshold 70   # Prune if disk > 70%
```

#### `our-container disk-usage` (alias: `du`)

Show detailed disk usage: Btrfs filesystem stats, per-container size and state, snapshot sizes, and a threshold alert.

```bash
our-container disk-usage
```

---

### Image Management

Base images are cached, read-only Btrfs subvolumes stored under `/var/lib/machines/.images/`.

#### `our-container image pull <distro>`

Pre-bootstrap a base image. The image is marked read-only on Btrfs.

```bash
our-container image pull arch
our-container image pull debian
```

#### `our-container image list` (alias: `ls`)

List cached base images with distro, read-only status, creation date, and size.

```bash
our-container image list
```

#### `our-container image remove <distro>` (alias: `rm`)

Remove a cached base image. The directory must contain a `.our-container-image` metadata marker.

```bash
our-container image remove debian
```

---

### Monitoring and Diagnostics

#### `our-container monitor [--interval <seconds>] [filter]`

Real-time dashboard showing all containers. Refreshes every N seconds (default: 2).

Displays: system CPU cores, memory usage, running container count, storage usage, and per-container state/PID/IP.

```bash
our-container monitor                    # Default: refresh every 2 seconds
our-container monitor --interval 5       # Refresh every 5 seconds
our-container monitor mydev              # Show only containers matching "mydev"
```

Press **Ctrl+C** to stop.

#### `our-container diagnose`

Run health checks on the container subsystem:

1. **systemd-machined** — is it running?
2. **Container storage** — exists? Btrfs? Disk space healthy?
3. **Container integrity** — missing `/bin` or `/usr`? Orphaned containers?
4. **Host network** — systemd-networkd and DNS resolution working?
5. **Running containers** — PID alive? Memory usage?

```bash
our-container diagnose
```

Returns the number of issues found as the exit code.

#### `our-container stats [name]`

Show performance statistics for running containers (or a specific container):

- **CPU** — percentage (measured over 1 second via `/proc/[pid]/stat`)
- **Memory** — RSS, VIRT, Peak (from `/proc/[pid]/status`)
- **Threads** — thread count
- **Disk** — container directory size
- **Network** — open TCP connections

```bash
our-container stats              # All running containers
our-container stats mydev        # Specific container
```

#### `our-container logs <name> [-f|--follow] [-n|--lines <N>]`

Show journal logs for a container via `journalctl --machine`.

```bash
our-container logs mydev                # Last 100 lines (default)
our-container logs mydev -n 50          # Last 50 lines
our-container logs mydev -f             # Follow mode (like tail -f)
our-container logs mydev -f -n 200      # Follow, starting from last 200 lines
```

#### `our-container check`

Verify filesystem and configuration integrity:

1. **Storage filesystem** — Btrfs detected? Btrfs errors in `dmesg`? Subvolume validity?
2. **System services** — systemd-machined and systemd-networkd active?
3. **Required tools** — machinectl, systemd-nspawn, btrfs, journalctl available?
4. **Configuration consistency** — on-disk vs. registered container count? Ghost entries?
5. **Boot entries** — systemd-boot entries present? Snapshot entries counted?

```bash
our-container check
```

Returns the number of errors found as the exit code.

---

### Miscellaneous

#### `our-container help`

Display full usage information with all commands, aliases, and examples.

```bash
our-container help
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
our-container create dev-env arch
our-container start dev-env
our-container enter dev-env

# Install build dependencies inside the container
pacman -S base-devel cmake git

# Snapshot before risky changes
our-container snapshot create dev-env before-refactor

# If something breaks, restore
our-container snapshot restore dev-env before-refactor
```

### Web Application Testing

Test a web app across multiple distros:

```bash
# Create containers for each distro
our-container create web-arch arch
our-container create web-debian debian
our-container create web-ubuntu ubuntu

# Share the project directory into each container
our-container storage mount web-arch /home/user/myproject /opt/myproject
our-container storage mount web-debian /home/user/myproject /opt/myproject
our-container storage mount web-ubuntu /home/user/myproject /opt/myproject

# Start and test
our-container start web-arch
our-container start web-debian
our-container start web-ubuntu

# Follow logs from all containers
our-container logs web-arch -f
our-container logs web-debian -f
```

### Database Sandbox

Run a database in an isolated container:

```bash
our-container create mydb arch
our-container enter mydb
# Inside: pacman -S postgresql && initdb && pg_ctl start
```

### Monitoring Multiple Containers

Watch all containers in real time:

```bash
# Real-time dashboard
our-container monitor

# Or check health
our-container diagnose

# Performance stats
our-container stats

# Individual container logs
our-container logs mydev -f
```

### Disk Space Management

Keep container storage under control:

```bash
# Check what's using space
our-container disk-usage

# Prune snapshots if disk is getting full
our-container cleanup --threshold 70

# Remove unused base images
our-container image remove debian
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
our-container diagnose
```

### Container won't start

```bash
# Check the systemd-machined journal
journalctl -u systemd-machined --since "5 min ago"

# Verify the container filesystem
our-container check

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
sudo our-pacman -S arch-install-scripts
```

### "debootstrap not found"

```bash
sudo our-pacman -S debootstrap
```

### Bind mount not appearing inside container

Bind mounts are configured via `.nspawn` files and take effect on container start. If the container is already running:

```bash
our-container stop mydev
our-container start mydev
```

### "container appears corrupted (missing /bin and /usr)"

The container filesystem is incomplete. This usually means the bootstrap failed partway through. Remove and recreate:

```bash
our-container remove mydev
our-container create mydev arch
```

### High disk usage warning

```bash
# See what's consuming space
our-container disk-usage

# Clean old snapshots
our-container cleanup

# Remove unused images
our-container image list
our-container image remove <unused-distro>

# Remove unused containers
our-container list
our-container remove <unused-container>
```

---

## systemd Integration

### How our-container integrates with systemd

`our-container` delegates container lifecycle to systemd's native container management:

| our-container command   | systemd component         | What happens                                              |
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

When you use `our-container storage mount`, a configuration file is created or updated at:

```
/etc/systemd/nspawn/<container-name>.nspawn
```

Example file created by `our-container storage mount mydev /data /opt/data`:

```ini
[Exec]
PrivateUsers=no

[Files]
Bind=/data:/opt/data
```

These files are read by `systemd-nspawn` when starting a container. You can edit them manually for advanced configuration, but `our-container storage` commands handle the common cases.

### Running containers as systemd services

To start a container automatically at boot, create a systemd service:

```bash
sudo machinectl enable mydev
```

This creates a `systemd-nspawn@mydev.service` that starts on boot.

### Journal integration

Container logs are accessible through the host's journal:

```bash
# Via our-container
our-container logs mydev

# Direct journalctl (equivalent)
journalctl --machine=mydev --no-pager

# Follow container logs
journalctl --machine=mydev -f
```
