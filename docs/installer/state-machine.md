# Installer State Machine

## Overview

The ouroborOS installer is implemented as an explicit finite state machine (FSM). Every screen, action, and transition is defined as a state. This guarantees:
- No undefined behavior between steps
- Clean rollback to any previous state
- Testable logic independent of the UI layer
- Resumable installation (checkpoint files)

---

## States

```
PREFLIGHT → LOCALE → PARTITION → FORMAT → INSTALL → CONFIGURE → SNAPSHOT → FINISH
                                  │
                                  ▼
                            ERROR_RECOVERABLE
                                  │
                                  ▼
                            ERROR_FATAL
```

| State | ID | Description |
|-------|----|-------------|
| `PREFLIGHT` | 0 | System checks before anything starts |
| `LOCALE` | 1 | Language, keyboard, timezone selection |
| `PARTITION` | 2 | Disk selection and partition plan |
| `FORMAT` | 3 | Write partition table, create filesystems |
| `INSTALL` | 4 | pacstrap base packages |
| `CONFIGURE` | 5 | Bootloader, network, users, firstboot |
| `SNAPSHOT` | 6 | Create baseline Btrfs snapshot |
| `FINISH` | 7 | Unmount, display summary, reboot |
| `ERROR_RECOVERABLE` | 90 | Error that allows retry/rollback |
| `ERROR_FATAL` | 99 | Error that requires abort |

---

## Transitions

```python
TRANSITIONS = {
    "PREFLIGHT":  {"pass": "LOCALE",     "fail": "ERROR_FATAL"},
    "LOCALE":     {"next": "PARTITION",  "back": None},
    "PARTITION":  {"next": "FORMAT",     "back": "LOCALE",    "fail": "ERROR_RECOVERABLE"},
    "FORMAT":     {"next": "INSTALL",    "back": "PARTITION", "fail": "ERROR_RECOVERABLE"},
    "INSTALL":    {"next": "CONFIGURE",  "back": "FORMAT",    "fail": "ERROR_RECOVERABLE"},
    "CONFIGURE":  {"next": "SNAPSHOT",   "back": "INSTALL",   "fail": "ERROR_RECOVERABLE"},
    "SNAPSHOT":   {"next": "FINISH",     "fail": "ERROR_RECOVERABLE"},
    "FINISH":     {"reboot": None,       "stay": None},
    "ERROR_RECOVERABLE": {"retry": None, "back": None, "abort": "ERROR_FATAL"},
    "ERROR_FATAL": {"exit": None},
}
```

---

## Checkpoint System

Each completed state writes a checkpoint file:

```
/tmp/ouroborOS-checkpoint/
├── PREFLIGHT.done
├── LOCALE.done
├── PARTITION.done
├── FORMAT.done
├── INSTALL.done
├── CONFIGURE.done
└── SNAPSHOT.done
```

On crash/restart, the installer reads existing checkpoints and resumes from the last incomplete state. The user is prompted:

```
Installation checkpoint found: INSTALL complete.
Resume from CONFIGURE? [Y/n]
```

---

## Configuration State Object

The installer carries a single `Config` object through all states, progressively populated:

```python
@dataclass
class InstallerConfig:
    # LOCALE
    locale: str = "en_US.UTF-8"
    keymap: str = "us"
    timezone: str = "UTC"

    # PARTITION
    target_disk: str = ""
    partition_scheme: str = "auto"  # or "manual"
    use_luks: bool = False
    luks_passphrase: str = ""

    # derived from partitioning
    esp_device: str = ""
    root_device: str = ""
    root_uuid: str = ""
    esp_uuid: str = ""

    # CONFIGURE
    hostname: str = "ouroborOS"
    root_password_hash: str = ""
    username: str = ""
    user_password_hash: str = ""
    user_groups: list = field(default_factory=lambda: ["wheel", "audio", "video"])
    use_homed: bool = False

    # INSTALL
    packages_extra: list = field(default_factory=list)
    pacman_mirror: str = ""
```

---

## Python State Machine Implementation (skeleton)

```python
#!/usr/bin/env python3
"""ouroborOS Installer — State Machine Core"""

import sys
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum, auto

CHECKPOINT_DIR = Path("/tmp/ouroborOS-checkpoint")
CONFIG_FILE = Path("/tmp/ouroborOS-config.json")


class State(Enum):
    PREFLIGHT = "PREFLIGHT"
    LOCALE = "LOCALE"
    PARTITION = "PARTITION"
    FORMAT = "FORMAT"
    INSTALL = "INSTALL"
    CONFIGURE = "CONFIGURE"
    SNAPSHOT = "SNAPSHOT"
    FINISH = "FINISH"
    ERROR_RECOVERABLE = "ERROR_RECOVERABLE"
    ERROR_FATAL = "ERROR_FATAL"


class Installer:
    def __init__(self):
        self.state = State.PREFLIGHT
        self.config = InstallerConfig()
        self.error_message = ""
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def run(self):
        self.state = self._resume_from_checkpoint()
        while self.state not in (State.FINISH, State.ERROR_FATAL):
            handler = getattr(self, f"_handle_{self.state.value.lower()}")
            self.state = handler()
        getattr(self, f"_handle_{self.state.value.lower()}")()

    def _resume_from_checkpoint(self) -> State:
        states = list(State)
        for s in reversed(states[:-2]):  # skip error states
            if (CHECKPOINT_DIR / f"{s.value}.done").exists():
                idx = states.index(s)
                if idx + 1 < len(states) - 2:
                    return states[idx + 1]
        return State.PREFLIGHT

    def _checkpoint(self, state: State):
        (CHECKPOINT_DIR / f"{state.value}.done").touch()
        CONFIG_FILE.write_text(json.dumps(asdict(self.config), indent=2))

    def _handle_preflight(self) -> State:
        # Implement checks
        ...

    def _handle_locale(self) -> State:
        # Implement TUI locale selection
        ...

    # ... etc for each state
```

---

## TUI Layer

The state machine is **independent of the UI**. The TUI is a thin wrapper that:
1. Calls the state handler
2. Renders state-specific screens using `dialog` or `whiptail`
3. Passes user input back to the state handler

```
InstallerState.run()
    └── _handle_locale()
            └── tui.show_locale_menu()   ← whiptail/dialog call
                    └── returns user selection
            └── config.locale = selection
            └── return State.PARTITION
```

This separation allows:
- Unit testing state logic without UI
- Swapping TUI for a GUI in the future
- Unattended (headless) installation by bypassing TUI entirely
