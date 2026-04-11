# Phase 3 Plan — System Management, Secure Boot & First-Boot Experience

**Version:** post-v0.2.0
**Date:** 2026-04-10
**Branch:** dev

> **v0.2.0 released 2026-04-10.** Phase 2 complete. This document defines Phase 3.
> Plan revisado y aprobado después de investigación exhaustiva del código fuente + Arch Wiki.

---

## Convención de nombres `our-*` / `ouroboros-*`

| Prefijo | Audiencia | Ejecutables |
|---------|-----------|-------------|
| `our-*` | Usuario final (interactivo) | `our-pacman`, `our-snapshot`, `our-rollback`, `our-wifi`, `our-bluetooth`, `our-container` |
| `ouroboros-*` | Sistema (servicios, automatización) | `ouroboros-secureboot`, `ouroboros-firstboot` |

---

## Estado real al inicio de Phase 3

### Completado (Phases 1-2 + inicio de Phase 3)

| Feature | Status | Ubicación |
|---------|--------|-----------|
| ISO bootable (UEFI) | ✅ | `src/ouroborOS-profile/` |
| Installer FSM (11 estados) | ✅ | `src/installer/state_machine.py` |
| TUI interactive + unattended YAML | ✅ | `src/installer/tui.py`, `config.py` |
| Btrfs layout (5 subvols + `@snapshots/install`) | ✅ | `src/installer/ops/disk.sh` |
| systemd-boot + microcode auto-detect | ✅ | `src/installer/ops/configure.sh` |
| Desktop profiles (5 perfiles, 4 DMs) | ✅ | `src/installer/desktop_profiles.py` |
| `our-pacman` (atomic update wrapper) | ✅ | `airootfs/usr/local/bin/our-pacman` |
| `our-container` (17 comandos nspawn) | ✅ | `airootfs/usr/local/bin/our-container` |
| systemd-homed (subvolume default) | ✅ | `src/installer/ops/configure.sh` |
| Shell selector bash/zsh/fish | ✅ | `tui.py`, `desktop_profiles.py`, `configure.sh` |
| E2E QEMU: 11/11 estados, boot limpio | ✅ | `tests/scripts/` |
| 82 pytest tests | ✅ | `src/installer/tests/` |

### Funciones internas de snapshot (YA implementadas en snapshot.sh)

| Función | Propósito |
|---------|-----------|
| `pre_upgrade_snapshot()` | Llamada por `our-pacman` antes de cada update |
| `generate_snapshot_boot_entry()` | Escribe `.conf` en `/boot/loader/entries/` |
| `prune_snapshots()` | Limita snapshots a 5 / 30 días, nunca toca `install` |
| `create_install_snapshot()` | Baseline post-install |
| `list_snapshots()` | Lista subvolúmenes en `/.snapshots/` |

> **Nota:** `our-snapshot` es un wrapper CLI de usuario sobre estas funciones internas.
> El trabajo pesado ya existe — falta la UX de usuario.

### Known Issues heredados de Phase 2

| Issue | Workaround | Decisión Phase 3 |
|-------|-----------|-----------------|
| `homectl create` falla en QEMU/Btrfs | `homed_storage: classic` en E2E | Investigar + documentar + fallback automático |
| SSH en QEMU SLIRP tarda 60-90s | Poll nc antes de SSH | Mantener workaround |

---

## Milestone 3.0 — Limpieza de deuda Phase 2

Phase 2 prometió: "A compatibility symlink `ouroboros-upgrade → our-pacman` ships for one
release cycle, then gets removed in Phase 3."

- [x] Eliminar `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-upgrade` (symlink)

---

## Milestone 3.1 — `our-snapshot`: Gestión de Snapshots

**Objetivo:** CLI de usuario para gestionar snapshots Btrfs. Las funciones ya existen en
`snapshot.sh` — falta exponerlas con una interfaz clara.

**Comandos:**

```
our-snapshot list                       # Tabla: nombre, fecha, tipo, tamaño Btrfs
our-snapshot create [--name LABEL]      # Snapshot read-only de @ + boot entry + JSON
our-snapshot delete <name>              # Subvolume + boot entry + JSON
our-snapshot restore <name>             # Delega a our-rollback promote
our-snapshot prune [--keep N]           # Elimina más viejos (default 5), nunca toca install
our-snapshot boot-entries sync          # Regenera /boot/loader/entries/ por snapshot existente
our-snapshot info <name>                # Metadata JSON + btrfs subvolume show
```

**Gotcha crítico de boot entries:**

```ini
# ✅ CORRECTO — sin / inicial en subvol
options root=UUID=XXX rootflags=subvol=@snapshots/2026-04-10_manual ro loglevel=4

# ❌ INCORRECTO — kernel ignora el subvol
options root=UUID=XXX rootflags=subvol=/@snapshots/2026-04-10_manual ro loglevel=4
```

**Estructura:**

```
/.snapshots/
├── install/                            # Golden baseline — NUNCA purgado
├── 2026-04-10T143022/                  # Pre-update (creado por our-pacman)
├── 2026-04-10_manual/                  # Manual (creado con our-snapshot create)
└── .metadata/
    └── 2026-04-10T143022.json          # { timestamp, type, description, packages_count }
```

**Timer semanal:**

```ini
# our-snapshot-prune.timer
[Timer]
OnCalendar=weekly
Persistent=true
```

**Btrfs scrub:** Arch provee `btrfs-scrub@.timer` — `ouroboros-firstboot` lo habilita.

**Milestones:**
- [x] 3.1.1 `our-snapshot list`
- [x] 3.1.2 `our-snapshot create` — snapshot + `.metadata/NAME.json` + boot entry
- [x] 3.1.3 `our-snapshot delete` — subvolume + boot entry + JSON
- [x] 3.1.4 `our-snapshot prune --keep N` — purga más viejos, nunca `install`
- [x] 3.1.5 `our-snapshot boot-entries sync`
- [x] 3.1.6 `our-snapshot info`
- [x] 3.1.7 `our-snapshot-prune.{service,timer}` — poda semanal
- [x] 3.1.8 shellcheck 0 warnings

**Archivos:**
| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-snapshot` | Nuevo |
| `src/ouroborOS-profile/airootfs/etc/systemd/system/our-snapshot-prune.{service,timer}` | Nuevo |

---

## Milestone 3.2 — `our-rollback`: Rollback de Un Comando

**Comandos:**

```
our-rollback list               # Alias de our-snapshot list
our-rollback now [SNAPSHOT]     # bootctl set-oneshot + reboot (próximo boot solo)
our-rollback promote <SNAPSHOT> # Swap permanente y atómico de @ por el snapshot
our-rollback status             # ¿Root actual es @ o un snapshot?
```

**Mecánica de `promote`** (patrón validado en Phase 2 — subvolid=5):

```bash
TMPDIR=$(mktemp -d)
mount -o subvolid=5 /dev/disk/by-label/ouroborOS "$TMPDIR"

btrfs subvolume snapshot "${TMPDIR}/@snapshots/${SNAPSHOT}" "${TMPDIR}/@_new"
btrfs property set "${TMPDIR}/@_new" ro false

btrfs subvolume delete "${TMPDIR}/@"
btrfs subvolume snapshot "${TMPDIR}/@_new" "${TMPDIR}/@"
btrfs property set "${TMPDIR}/@" ro true
btrfs subvolume delete "${TMPDIR}/@_new"

our-snapshot boot-entries sync
umount "$TMPDIR" && rmdir "$TMPDIR"
```

> ⚠️ `our-rollback now` usa `bootctl set-oneshot`. En QEMU sin OVMF_VARS rw puede fallar.
> Tests E2E deben usar `promote`.

**`our-rollback status`:**

```bash
current=$(findmnt / -o OPTIONS -n | grep -oP 'subvol=\K[^,]+')
[[ "$current" == "@" ]] && echo "Root: @ (normal)" || echo "Root: $current (snapshot)"
```

**Milestones:**
- [x] 3.2.1 `our-rollback list`
- [x] 3.2.2 `our-rollback now`
- [x] 3.2.3 `our-rollback promote`
- [x] 3.2.4 `our-rollback status`
- [x] 3.2.5 shellcheck 0 warnings

**Archivos:**
| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-rollback` | Nuevo |

---

## Milestone 3.3 — Shell Selector ✅ COMPLETADO

bash / zsh / fish — ya en `dev`. No hay nada que hacer.

---

## Milestone 3.4 — First-Boot Experience

### 3.4.1 `our-wifi` — WiFi Setup Interactivo

```
our-wifi list                              # scan + lista redes (iwctl)
our-wifi connect <SSID>                    # interactivo: pide passphrase
our-wifi connect <SSID> --password <PASS>  # no interactivo
our-wifi status                            # iwctl station wlan0 show
our-wifi forget <SSID>                     # rm /var/lib/iwd/SSID.psk
our-wifi show-password <SSID>             # mostrar passphrase guardada
```

**Formato PSK de iwd** (Arch Wiki):

```ini
# /var/lib/iwd/SSID.psk  (chmod 600, directorio 700)
[Security]
Passphrase=mypassword
```

SSIDs con caracteres especiales → nombre hex: `=<hex_ssid>.psk`

**Pre-configuración desde YAML:**

```yaml
network:
  wifi:
    ssid: "MiRed"
    passphrase: "mi-password"   # escrito a /var/lib/iwd/, no persistido en checkpoint
```

**Milestones:**
- [x] 3.4.1 `our-wifi` CLI completo
- [x] 3.4.2 `NetworkConfig.wifi_ssid` + `wifi_passphrase` en `config.py` (transient)
- [x] 3.4.3 `configure.sh` escribe PSK (chmod 600, dir 700) + limpia env
- [x] 3.4.4 Validación: si `wifi.ssid` → `wifi.passphrase` requerido
- [ ] 3.4.5 `show_wifi_setup()` en `tui.py`
- [x] 3.4.6 `templates/install-config.yaml` — sección `network.wifi:`
- [ ] 3.4.7 `docs/installer/configuration-format.md` — campos WiFi

### 3.4.2 `ouroboros-firstboot` — Servicio Oneshot

```bash
#!/usr/bin/env bash
set -euo pipefail

[[ -f /var/lib/ouroborOS/firstboot.done ]] && exit 0

# 1. Mirrors optimizados (sin benchmark local)
reflector --save /etc/pacman.d/mirrorlist --sort score --latest 20 --protocol https

# 2. machine-id único si es el del ISO
if systemd-machine-id-setup --print 2>/dev/null | grep -q "^b08dfa6083e7567a1921a715000001fb$"; then
    systemd-machine-id-setup --commit
fi

# 3. Activar timers
systemctl enable --now our-snapshot-prune.timer 2>/dev/null || true
systemctl enable --now "btrfs-scrub@-.timer" 2>/dev/null || true

# 4. Guard
mkdir -p /var/lib/ouroborOS
date -Iseconds > /var/lib/ouroborOS/firstboot.done
```

```ini
[Unit]
Description=ouroborOS First Boot Setup
ConditionPathExists=!/var/lib/ouroborOS/firstboot.done
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/ouroboros-firstboot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

**Milestones:**
- [x] 3.4.8 `ouroboros-firstboot` script + `.service`
- [x] 3.4.9 `configure.sh` instala y habilita el servicio
- [x] 3.4.10 Copiar service a `@` (patrón `_write_systemd_enables_to_root`)
- [x] 3.4.11 shellcheck 0 warnings

**Archivos:**
| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-wifi` | Nuevo |
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-firstboot` | Nuevo |
| `src/ouroborOS-profile/airootfs/etc/systemd/system/ouroboros-firstboot.service` | Nuevo |
| `src/installer/config.py` | `NetworkConfig.wifi_ssid`, `wifi_passphrase` |
| `src/installer/tui.py` | `show_wifi_setup()` |
| `src/installer/ops/configure.sh` | WiFi PSK + firstboot enable |
| `templates/install-config.yaml` | `network.wifi:` |

---

## Milestone 3.5 — Secure Boot: `ouroboros-secureboot`

**Contexto técnico:**
- `sbctl` DB en `/var/lib/sbctl/` → en `@var` (writable) ✅
- `sbctl enroll-keys` requiere firmware en **Setup Mode**
- `sbctl enroll-keys -m` incluye claves Microsoft
- El paquete incluye pacman hook PostTransaction para re-firma automática
- Gotcha: `systemd-boot-update.service` actualiza bootloader en reboot, no en transacción

**Comandos:**

```
ouroboros-secureboot setup          # create-keys + enroll-keys + sign-all
ouroboros-secureboot status         # sbctl status + unsigned list
ouroboros-secureboot sign-all       # re-firma todos los trackeados
ouroboros-secureboot verify         # sbctl verify
ouroboros-secureboot rotate-keys    # backup + create-keys + sign-all
```

**Integración `our-pacman`:**

```bash
if command -v sbctl &>/dev/null && sbctl status 2>/dev/null | grep -q "Secure Boot.*enabled"; then
    sbctl sign-all || log_warn "sbctl sign-all failed"
fi
```

**Schema YAML:**

```yaml
security:
  secure_boot: false
  sbctl_include_ms_keys: false
```

**Milestones:**
- [x] 3.5.1 Agregar `sbctl` a `packages.x86_64`
- [x] 3.5.2 `ouroboros-secureboot` CLI completo
- [x] 3.5.3 `SecurityConfig` en `config.py` + validación
- [x] 3.5.4 `sbctl sign-all` en `our-pacman` post-update
- [ ] 3.5.5 State `SECURE_BOOT` opcional en FSM
- [ ] 3.5.6 `show_secure_boot_prompt()` en `tui.py`
- [x] 3.5.7 `docs/architecture/secure-boot.md`
- [x] 3.5.8 shellcheck 0 warnings

**Archivos:**
| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-secureboot` | Nuevo |
| `docs/architecture/secure-boot.md` | Nuevo |
| `src/ouroborOS-profile/packages.x86_64` | + `sbctl` |
| `src/installer/config.py` | `SecurityConfig` |
| `src/installer/tui.py` | `show_secure_boot_prompt()` |
| `src/installer/state_machine.py` | State `SECURE_BOOT` |
| `src/installer/ops/configure.sh` | sbctl step opcional |

---

## Milestone 3.6 — `our-pacman` Hardening

**Flujo Phase 3:**

```
our-pacman -Syu
  → verificar espacio ≥ 2GB en pool Btrfs
  → snapshot pre-update + metadata JSON
  → remount @ rw (subvolid=5)
  → pacman -Syu
  → remount @ ro
  → [si sbctl activo] sbctl sign-all
  → our-snapshot boot-entries sync
  → log JSON → /var/log/our-pacman/YYYY-MM-DD.json
  → our-snapshot prune si snapshots > 10
```

**Milestones:**
- [x] 3.6.1 Verificación espacio pre-update
- [x] 3.6.2 Metadata JSON por snapshot
- [x] 3.6.3 Integración sbctl sign-all
- [x] 3.6.4 our-snapshot boot-entries sync automático
- [x] 3.6.5 Logging JSON en `/var/log/our-pacman/`
- [x] 3.6.6 Auto-prune si snapshots > 10

---

## Milestone 3.7 — `our-container` Mejoras

### Networking Isolation (diferido de Phase 2)

```bash
our-container enter <name> --isolated   # --network-veth (red privada)
our-container create <name> --isolated  # pre-configura veth
```

### GUI/GPU Passthrough

```bash
our-container enter <name> --wayland   # bind-mount Wayland socket
our-container enter <name> --gpu       # bind-mount /dev/dri/
our-container enter <name> --audio     # bind-mount PipeWire socket
our-container enter <name> --gui       # = --wayland + --gpu + --audio
```

```bash
# Flags systemd-nspawn
--bind-ro=/run/user/${UID}/wayland-0
--bind=/dev/dri
--bind-ro=/run/user/${UID}/pipewire-0
--setenv=WAYLAND_DISPLAY=wayland-0
--property=DeviceAllow=char-drm rw
```

**Milestones:**
- [x] 3.7.1 `--isolated` en enter y create
- [x] 3.7.2 `--wayland`, `--gpu`, `--audio`, `--gui` en enter
- [x] 3.7.3 Docs: "Network Isolation" y "GUI containers"
- [x] 3.7.4 shellcheck 0 warnings

---

## Milestone 3.8 — `homectl`: Decisión Final

**Investigación 2024-2025:**
- Falla en QEMU porque `@home` es subvolumen Btrfs — systemd issues #15121, #16829
- Error: "File exists" al crear subvolume dentro de subvolume existente en `/home`
- Comunidad Arch recomienda useradd clásico con Btrfs

**Decisión:** Documentar como limitación conocida. Fallback automático a classic useradd.

**Milestones:**
- [x] 3.8.1 Capturar `journalctl -u systemd-homed` en E2E install log
- [x] 3.8.2 Fallback automático a classic useradd si homectl falla
- [x] 3.8.3 E2E test: verificar fallback
- [x] 3.8.4 `docs/architecture/systemd-homed.md` — decisión + razonamiento

---

## Milestone 3.9 — Cobertura de Tests

Brecha actual: 82 tests cubro infraestructura. Cero tests para handlers individuales.

**Milestones:**
- [x] 3.9.1 Tests `_handle_user()` y `_handle_desktop()`
- [x] 3.9.2 Tests env vars pasadas a configure.sh
- [x] 3.9.3 Tests validación WiFi (con y sin passphrase)
- [x] 3.9.4 Tests `SecurityConfig` en `validate_config()`
- [x] 3.9.5 Coverage ≥ 93%

---

## Milestone 3.10 — `our-bluetooth`: Bluetooth Interactivo

```
our-bluetooth list               # scan + lista dispositivos
our-bluetooth pair <MAC>         # emparejar (pide PIN si necesita)
our-bluetooth connect <MAC>      # conectar a dispositivo emparejado
our-bluetooth disconnect <MAC>   # desconectar
our-bluetooth forget <MAC>       # eliminar emparejamiento
our-bluetooth status             # estado del adaptador
our-bluetooth on / off           # habilitar / deshabilitar
```

Wrapper sobre `bluetoothctl`. `bluez` + `bluez-utils` como paquetes opcionales.

```yaml
network:
  bluetooth:
    enable: false    # true → habilita bluetooth.service post-install
```

**Milestones:**
- [x] 3.10.1 `our-bluetooth` CLI completo
- [x] 3.10.2 `NetworkConfig.bluetooth_enable` en `config.py`
- [x] 3.10.3 `configure.sh` habilita `bluetooth.service` si `BLUETOOTH_ENABLE=1`
- [x] 3.10.4 shellcheck 0 warnings

**Archivos:**
| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-bluetooth` | Nuevo |

---

## Milestone 3.11 — Multi-Language (Stretch)

Gettext, `.po`/`.mo`, campo `locale.language`, pantalla idioma en INIT.
> Puede postergarse a Phase 4.

---

## Tabla Resumen

| # | Feature | Ejecutable | Prioridad | Complejidad | Depende de |
|---|---------|-----------|-----------|-------------|------------|
| 3.0 | Eliminar `ouroboros-upgrade` symlink | — | 🔴 | Trivial | — |
| 3.1 | Gestión de snapshots | `our-snapshot` | 🔴 | Baja-Media | — |
| 3.2 | Rollback de un comando | `our-rollback` | 🔴 | Media | 3.1 |
| 3.3 | Shell selector | (TUI) | ✅ DONE | — | — |
| 3.4 | WiFi + first-boot | `our-wifi` + `ouroboros-firstboot` | 🟡 | Baja | — |
| 3.5 | Secure Boot | `ouroboros-secureboot` | 🟡 | Alta | — |
| 3.6 | Atomic updates hardening | `our-pacman` | 🟡 | Baja | 3.1 |
| 3.7 | Container networking + GUI | `our-container` | 🟢 | Media | — |
| 3.8 | homectl decisión + fallback | — | 🟡 | Media | — |
| 3.9 | Cobertura de tests | — | 🟡 | Media | Todos |
| 3.10 | Bluetooth | `our-bluetooth` | 🟡 | Baja | — |
| 3.11 | Multi-language | — | 🟢 | Alta | — |

**Orden de implementación:**

```
3.0 → 3.1 → 3.2 → 3.4 → 3.10 → 3.6 → 3.8 → 3.9 → 3.5 → 3.7 → 3.11
```

---

## Schema YAML Phase 3 Completo

```yaml
user:
  username: admin
  password: changeme
  shell: /bin/bash             # /bin/bash | /bin/zsh | /usr/bin/fish
  homed_storage: classic       # subvolume | luks | directory | classic
  groups: [wheel, audio, video, input]

network:
  hostname: ouroboros
  enable_networkd: true
  enable_iwd: true
  enable_resolved: true
  wifi:                        # NUEVO 3.4
    ssid: ""
    passphrase: ""             # no persistido en checkpoints
  bluetooth:                   # NUEVO 3.10
    enable: false

security:                      # NUEVO 3.5
  secure_boot: false
  sbctl_include_ms_keys: false

disk:
  device: /dev/vda
  use_luks: false
  btrfs_label: ouroborOS
  swap_type: zram

locale:
  locale: en_US.UTF-8
  keymap: us
  timezone: America/Santiago

desktop:
  profile: minimal
  dm: auto

extra_packages:
  - openssh

post_install_action: reboot
```

---

## Criterios de Aceptación Phase 3

- [x] Symlink `ouroboros-upgrade` eliminado del ISO
- [x] `our-snapshot list` muestra snapshots incluyendo `install`
- [x] `our-snapshot create` → snapshot + boot entry (sin `/` en subvol) + JSON
- [x] `our-snapshot prune --keep 3` — nunca toca `install`
- [x] `our-rollback promote <snap>` — sistema bootea desde nuevo root
- [x] `our-wifi connect <SSID>` conecta exitosamente
- [x] YAML con `network.wifi.ssid` → PSK en `/var/lib/iwd/` post-install
- [x] `ouroboros-firstboot` corre una sola vez — mirrors + timers activados
- [x] `ouroboros-secureboot setup` firma kernel + bootloader en Setup Mode
- [x] `our-pacman -Syu` llama sbctl sign-all si Secure Boot activo
- [x] `our-container enter <name> --isolated` usa `--network-veth`
- [x] `our-container enter <name> --gui` bind-mount wayland + DRI
- [x] homectl falla → fallback a classic useradd sin crash
- [ ] Todos los scripts: shellcheck 0 warnings
- [x] pytest coverage ≥ 93%

---

## Out of Scope (Phase 4+)

- TPM2 + `systemd-cryptenroll`
- ARM / aarch64
- GUI installer
- AUR helper
- Flatpak / Snap
- Dual-boot + Secure Boot
- Live USB persistence
- ZFS
