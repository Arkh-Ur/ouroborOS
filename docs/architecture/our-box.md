# our-box — Architecture

## Overview

`our-box` is the user-space container tool for ouroborOS. It manages rootless
containers via **podman** (default) or **docker**, with no root requirement. It
is the user-facing counterpart to `our-container`, which manages system containers
as root.

### Separation of concerns

| Dimension | `our-container` | `our-box` |
|-----------|-----------------|-----------|
| Privilege | root required | no root (rootless podman) |
| Backend | nspawn (default) + OCI | OCI only (podman/docker) |
| Storage | `/var/lib/machines/`, `/etc/ouroboros/` | `$XDG_DATA_HOME/our-box/`, `$XDG_CONFIG_HOME/our-box/` |
| Home mount | no | yes (`--userns=keep-id` + `-v $HOME:$HOME`) |
| Use cases | system VMs, full-boot OS containers, admin tools | dev envs, throwaway shells, GUI desktop apps |
| system.yaml key | — | `box_packages: []` |

---

## Box types

Types are **presets** — they set flag defaults, they do not restrict what flags
can be used. Any flag works with any type.

| Type | `--home` | `--wayland` | `--audio` | `--gpu` | Persistence |
|------|:--------:|:-----------:|:---------:|:-------:|:-----------:|
| `dev` | ✅ | ✅ | ✅ | ❌ | ✅ |
| `ephemeral` | ❌ | ❌ | ❌ | ❌ | ❌ (`--rm`) |
| `app` | ❌ | ✅ | ✅ | ✅ | ✅ |

GPU is off by default for `dev` because most development (web, backend, systems)
does not need it. Enable explicitly when it does:

```bash
# AI/ML development with CUDA
our-box create aidev nvidia/cuda:12.0-base --type dev --gpu

# PyTorch workload
our-box create pytorch pytorch/pytorch --type dev --gpu
```

---

## Paths

```
$XDG_CONFIG_HOME/our-box/
├── box.conf                # global engine default (ENGINE=podman)
├── repos.conf              # registered OCI/image repos
└── boxes.d/
    └── <name>.conf         # per-box metadata (IMAGE=, TYPE=, ENGINE=, ...)

$XDG_DATA_HOME/our-box/
└── <name>/                 # reserved for future persistent volumes
```

Metadata format is `KEY=VALUE` (sourced by bash), parallel to
`/etc/ouroboros/containers.d/` in `our-container`.

---

## GUI passthrough

Each display/audio flag maps to specific bind mounts and environment variables:

| Flag | Bind mount | Environment |
|------|-----------|-------------|
| `--home` | `-v $HOME:$HOME` + `--workdir $HOME` | — |
| `--wayland` | `-v $XDG_RUNTIME_DIR/wayland-0:...:ro` | `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR` |
| `--x11` | `-v /tmp/.X11-unix:/tmp/.X11-unix:ro` | `DISPLAY` |
| `--gpu` | `--device /dev/dri` | — |
| `--audio` | `-v $XDG_RUNTIME_DIR/pipewire-0:...:ro` (PipeWire) or pulse fallback | `PIPEWIRE_RUNTIME_DIR` |

`--userns=keep-id` is always added so the UID/GID inside the container matches
the host user, preventing permission mismatches on bind-mounted files.

---

## Lazy engine install

`our-box` does not require podman or docker to be pre-installed. On the first
command that needs an engine, `_engine_ensure <engine>` checks availability and
calls `our-pac -S <engine>` if missing. This keeps the base ISO slim while
ensuring the tool is always self-sufficient.

---

## system.yaml integration

`box_packages` in `/etc/ouroboros/system.yaml` tracks the names of boxes managed
by `our-box`. The key is initialized to `[]` by the installer and updated
atomically (Python `os.replace`) after each `create` (add) or `remove` (remove)
call. `-Su` does not modify this key.

---

## Distrobox / toolbox migration

`our-box migrate --from distrobox|toolbox <name>` reads the existing container's
metadata and creates a matching `our-box` metadata entry. It does **not** copy
container filesystem state — the container itself is managed by its original
engine and must be recreated via `our-box create` if full migration is desired.
This is intentional: distrobox and toolbox are supported only as a migration
path, not as engines.

---

## Relation to our-container

`our-container` and `our-box` share some design patterns (engine resolution,
repo management, metadata format) but are independent binaries with independent
storage paths. There is no shared state between them. A future refactor could
extract shared logic into a library, but the current approach keeps each tool
self-contained and independently auditable.
