# Multi-User Support

## Overview

ouroborOS supports multiple user accounts declared in the install config. Each user is created during the `CONFIGURE` install state and can optionally be migrated to systemd-homed on first boot.

See `docs/architecture/systemd-homed.md` for the detailed homed migration flow and known limitations.

---

## User Declaration

Users are declared in `install-config.yaml` as a list:

```yaml
users:
  - username: admin
    password: changeme
    real_name: "Administrator"
    groups: [wheel, audio, video, input]
    shell: /bin/bash
    homed_storage: subvolume   # subvolume | luks | directory | classic
    tpm2_enroll: false
    fido2_enroll: false

  - username: alice
    password: alice123
    groups: [audio, video, input]
    shell: /usr/bin/fish
    homed_storage: classic
```

**Shells:** `bash` (default), `zsh`, `fish`. Shells other than bash are installed automatically if selected.

---

## homed_storage Backends

| Backend | Description | Status |
|---------|-------------|--------|
| `subvolume` | Btrfs subvolume per user (homed-managed) | Known issue: fails when `/home` is `@home` subvolume |
| `luks` | LUKS-encrypted home image | Requires LUKS support; tested |
| `directory` | Plain directory (homed-managed) | Functional |
| `classic` | Standard `/etc/passwd` + `/home/<user>` | Recommended for stability |

See `docs/architecture/systemd-homed.md` for the `subvolume` limitation details.

---

## Installation Flow

### CONFIGURE state (in `configure.sh`)

For each user declared in `USERS_JSON`:

```
1. Register shell in /etc/shells (if not standard)
2. useradd --create-home --shell <shell> --groups <groups> <username>
3. chpasswd --encrypted <<< "<username>:<password_hash>"
4. Write /etc/ouroboros/homed-migration.conf (chmod 600)
   → Contains plaintext password for first-boot homed migration
5. Enable ouroboros-homed-migration.service (runs once on first boot)
```

The primary user (`users[0]`) also:
- Gets `sudo` access via `/etc/sudoers.d/<username>` (wheel group)
- Has their shell set as the system default login shell

### Password Plaintext Lifecycle

`UserConfig.password_plaintext` is a transient field:
- Filled from YAML config or TUI input
- Passed to `configure.sh` as `USER_PASSWORD` environment variable
- Written to `/etc/ouroboros/homed-migration.conf` (chmod 600) for first-boot homed
- **Cleared in `state_machine.py` immediately after `configure.sh` finishes**
- `homed-migrate.sh` removes `HOMED_PASSWORD` from the conf file after successful migration
- Never persisted in install checkpoints

---

## First Boot — homed Migration

`ouroboros-homed-migration.service` runs once on first boot (via `ConditionPathExists=!/var/lib/ouroboros/homed-migrated`).

For each user with `homed_storage != "classic"`:

```
1. Read password from /etc/ouroboros/homed-migration.conf
2. homectl create <username> --storage=<backend> --uid=<uid> ...
3. If success: migrate home dir, patch PAM, set migrated flag
4. If failure: rollback, user stays as classic /etc/passwd user
   (no data loss — home dir preserved)
5. Remove plaintext password from homed-migration.conf
```

TPM2/FIDO2 enrollment (`tpm2_enroll`, `fido2_enroll`) is attempted after successful migration. Silently skipped if hardware is absent.

---

## Groups

Default groups for the primary user: `wheel audio video input`

| Group | Purpose |
|-------|---------|
| `wheel` | sudo access |
| `audio` | PipeWire / ALSA audio |
| `video` | GPU access |
| `input` | Input device access (libinput) |

Additional groups can be specified per-user in the config.

---

## system.yaml Representation

Each user is persisted in `/etc/ouroboros/system.yaml`:

```yaml
users:
  - username: admin
    real_name: "Administrator"
    groups: [wheel, audio, video, input]
    shell: /bin/bash
    homed_storage: subvolume
  - username: alice
    real_name: ""
    groups: [audio, video, input]
    shell: /usr/bin/fish
    homed_storage: classic
```

Note: passwords are never stored in `system.yaml`.

---

## File Locations

| Path | Purpose |
|------|---------|
| `templates/install-config.yaml` | `users:` section template with all options |
| `src/installer/config.py` | `UserConfig` dataclass + YAML validation |
| `src/installer/ops/configure.sh` | `useradd` + `chpasswd` + migration conf write |
| `/etc/ouroboros/homed-migration.conf` | First-boot homed migration config (chmod 600, cleared after use) |
| `/var/lib/ouroboros/homed-migrated` | Sentinel: migration already ran (prevents re-run) |
| `src/ouroborOS-profile/airootfs/usr/local/lib/ouroboros/homed-migrate.sh` | First-boot migration script |

---

## Constraints

- The first user in `users:` is the primary admin user (gets sudo via `wheel`)
- Shells not in `/etc/shells` are registered automatically
- homed `subvolume` storage fails on the standard `@home` layout — use `classic` for stability
- TPM2/FIDO2 enrollment requires a successful homed migration first
- The plaintext password field is transient and is never written to install checkpoints
