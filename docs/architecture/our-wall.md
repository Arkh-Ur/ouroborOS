# our-wall — Firewall Manager

## Overview

`our-wall` is the firewall management tool for ouroborOS. It wraps `firewalld`
with a concise, task-oriented interface: open and close ports, manage zones,
apply configuration presets, and query firewall state — all without needing to
remember `firewall-cmd` flags.

---

## Design Principles

### Why firewalld

ouroborOS is systemd-native. `firewalld` integrates with systemd, uses `nftables`
as its backend (no legacy iptables), and is the firewall of reference on modern
distributions (Fedora, RHEL, openSUSE, Arch). `ufw` and raw `iptables` do not fit
the project's systemd-first philosophy.

`firewalld` is always present on the installed system — it is included in
`packages.x86_64` and enabled in `configure.sh` PHASE 3, alongside other system
services like `iwd` and `systemd-resolved`.

### Why a wrapper

`firewall-cmd` is powerful but verbose. Every permanent change requires both
`--permanent` and a runtime flag (or `--reload`), and zone discovery involves
multiple invocations. `our-wall` collapses these patterns into single commands
and adds the `preset` shortcuts that cover the most common configurations for
desktop and server profiles.

### What our-wall does NOT do

- Does not uninstall `firewalld` — `disable` only stops and masks the service.
- Does not modify `system.yaml` — firewall state is runtime configuration, not
  declarative system state.
- Does not install packages — `firewalld` must already be present (installed by
  the ouroborOS installer).

---

## Architecture

```
our-wall <command> [args]
    │
    ├── status          systemctl is-active + firewall-cmd --list-*
    ├── enable          systemctl enable --now firewalld
    ├── disable         systemctl disable --now firewalld
    ├── reload          firewall-cmd --reload
    │
    ├── allow <target>  firewall-cmd --add-{port,service} --permanent + runtime
    ├── deny  <target>  firewall-cmd --remove-{port,service} --permanent + runtime
    ├── list            firewall-cmd --list-services + --list-ports
    │
    ├── zone show       firewall-cmd --get-active-zones
    ├── zone set <z>    firewall-cmd --change-interface --permanent + --reload
    │
    └── preset desktop  mdns + kde-connect + syncthing
        preset server   ssh + http + https
        preset reset    public zone, ssh only
```

### Target resolution

`allow` and `deny` detect whether the argument is a port (`/`-separated,
e.g. `8080/tcp`) or a service name (`ssh`, `http`). Port targets use
`--add-port` / `--remove-port`; service targets use `--add-service` /
`--remove-service`. Both operations are applied permanently **and** to the
running runtime in a single invocation pair, so changes take effect immediately
without a full `--reload`.

### Zone management

`zone set` detects the default interface via `ip route show default`, then moves
it to the requested zone permanently and reloads. If no default route exists
(e.g. WiFi not yet connected) the command aborts with an error rather than
silently misconfiguring.

---

## Presets

| Preset | Services opened | Typical use case |
|--------|----------------|-----------------|
| `desktop` | mdns, kde-connect, syncthing | Desktop workstation on a trusted LAN |
| `server` | ssh, http, https | Headless server or VM exposed to the network |
| `reset` | ssh only (all others removed) | Return to a known-safe baseline |

All presets operate on the `public` zone and call `--reload` once after all
changes to minimise transition time.

---

## Files

| Path | Purpose |
|------|---------|
| `/usr/local/bin/our-wall` | The binary (~195 lines, bash) |
| `src/ouroborOS-profile/profiledef.sh` | `["/usr/local/bin/our-wall"]="0:0:755"` |
| `src/ouroborOS-profile/packages.x86_64` | `firewalld` package |
| `src/installer/ops/configure.sh` | `systemctl enable firewalld.service` in PHASE 3 |

---

## Examples

```bash
# Check current state
our-wall status

# Open a dev server port, then close it when done
our-wall allow 3000/tcp
our-wall deny  3000/tcp

# Set up a typical desktop
our-wall preset desktop

# Move to the home zone for trusted LAN discovery
our-wall zone set home

# Hard reset to public + ssh only
our-wall preset reset
```
