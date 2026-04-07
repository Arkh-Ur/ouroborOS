# ouroborOS-profile/

## OVERVIEW
archiso profile defining the live ISO layout: airootfs filesystem, EFI boot entries, package selection.

## STRUCTURE
```
ouroborOS-profile/
├── airootfs/          # Live ISO filesystem root (copied at build)
│   ├── etc/           # System configs (networkd, iwd, systemd)
│   └── usr/local/bin/ # Installer launcher script
├── efiboot/           # systemd-boot EFI entries
│   └── loader/        # Bootloader and entry configs
├── packages.x86_64    # ISO package list (keep lean)
├── pacman.conf        # Build-time package manager config
└── profiledef.sh      # archiso metadata and permissions
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add ISO package | `packages.x86_64` | Justify additions; minimize bloat |
| Change boot entry | `efiboot/loader/entries/` | systemd-boot .conf files only |
| Edit live config | `airootfs/etc/` | Networkd, iwd, motd, os-release |
| Installer launch | `airootfs/usr/local/bin/` | `ouroborOS-installer` wrapper |
| Build metadata | `profiledef.sh` | ISO name, label, file permissions |
| Network config | `airootfs/etc/systemd/network/` | Wired/wireless networkd configs |
| Auto-start | `airootfs/etc/systemd/system/` | Installer service and autologin |

## CONVENTIONS
- **airootfs mirrors live root.** Files here are copied directly to the ISO.
- **systemd-boot only.** `efiboot/` contains `.conf` entries for UEFI boot.
- **Lean packages.** `packages.x86_64` must stay minimal. No GUI tools.
- **Network stack.** Use `systemd-networkd` + `iwd`. No NetworkManager.
- **Launcher script.** `ouroborOS-installer` validates root/python/module before FSM.
- **Profile metadata.** `profiledef.sh` defines ISO name, label, and file permissions.
- **Shellcheck.** `profiledef.sh` uses `# shellcheck disable=SC2034` for metadata.

## ANTI-PATTERNS
- **No GRUB.** Use systemd-boot `.conf` files, never `.cfg`.
- **No NetworkManager.** Forbidden in ISO; use native systemd tools.
- **No hardcoded mirrors.** `pacman.conf` must use generic mirrorlist.
- **No unjustified bloat.** Every package in `packages.x86_64` needs a role.
- **No root rw.** ISO is immutable; writes go to tmpfs/cow.
- **No hardcoded archisolabel.** Must match `iso_label` in `profiledef.sh` (dynamic).
- **No .cfg files.** Boot entries must be `.conf` for systemd-boot.
