# installer/

## OVERVIEW
Python FSM installer with Bash ops. Orchestrated by state_machine.py, UI via whiptail, config via YAML dataclasses.

## STRUCTURE
```
installer/
├── state_machine.py   # FSM orchestrator (Installer, State)
├── tui.py             # whiptail UI (TUI)
├── config.py          # Dataclasses + YAML (InstallerConfig)
├── main.py            # CLI entry
├── example-config.yaml
├── ops/               # Bash operations
│   ├── disk.sh        # partition, format, subvols, mount, fstab, LUKS
│   ├── snapshot.sh    # Btrfs snapshots, boot entries, prune
│   └── configure.sh   # chroot: locale, tz, hostname, bootloader, net, users, immutable root
└── tests/             # pytest unit tests
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add state/phase | `state_machine.py` | Update `State` enum + `_handler_map` |
| Add TUI screen | `tui.py` | whiptail wrapper, returns dict |
| Change config schema | `config.py` | Dataclasses + YAML validation |
| Disk/LUKS/Subvol op | `ops/disk.sh` | Bash lib, called via `_run_op()` |
| Snapshot/Boot entry | `ops/snapshot.sh` | Btrfs ops + systemd-boot entries |
| Chroot configuration | `ops/configure.sh` | Driven by env vars in chroot |
| CLI arguments | `main.py` | `--resume`, `--config`, `--target` |

## STATE MACHINE
- Flow: INIT → NETWORK_SETUP → PREFLIGHT → LOCALE → USER → DESKTOP → SECURE_BOOT → PARTITION → FORMAT → INSTALL → CONFIGURE → SNAPSHOT → FINISH.
- Error states: ERROR_RECOVERABLE, FATAL.
- Checkpoints: Persisted in `/tmp/ouroborOS-checkpoints/` per state.
- Resume: `--resume` flag loads last successful checkpoint.

## PYTHON↔BASH INTERFACE
- `_run_op()`: Python calls Bash via `subprocess`.
- `disk.sh` / `snapshot.sh`: Driven by CLI flags (`--action`, `--target`).
- `configure.sh`: Driven by environment variables passed to chroot.
- Return codes: 0 for success, non-zero triggers `InstallerError`.

## CONVENTIONS
- **Checkpoints**: JSON files in `/tmp/ouroborOS-checkpoints/`.
- **TUI**: Returns dicts, never mutates global state.
- **Config**: Dataclasses for Disk, Locale, Network, User.
- **Passwords**: Hashed via SHA-512 crypt before passing to ops.
- **Ops**: `set -euo pipefail` required in all scripts.

## ANTI-PATTERNS
- **No logic in Python ops**: Python orchestrates, Bash executes system changes.
- **No skipping checkpoints**: Every state transition must be recorded.
- **No hardcoded paths**: Use UUIDs or passed arguments, never `/dev/sdX`.
- **No global state in TUI**: Keep UI functions pure (input -> dict).
