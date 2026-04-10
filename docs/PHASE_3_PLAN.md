# Phase 3 Plan — System Management, Secure Boot & First-Boot Experience

**Version:** post-v0.2.0
**Date:** 2026-04-10
**Branch:** dev

> **v0.2.0 released 2026-04-10.** Phase 2 complete. This document defines Phase 3.

---

## Recomendaciones del Arquitecto

Antes del plan técnico, estas son las decisiones de diseño más importantes para Phase 3.

### R1 — Empezar por `our-snap` + `our-rollback`, no por Secure Boot

Secure Boot es visible y "cool", pero **el valor diferencial de ouroborOS es la recuperabilidad**. Si un usuario puede romper el sistema y restaurarlo en 10 segundos con un comando, eso es lo que lo va a fidelizar. `our-snap` y `our-rollback` son el corazón del sistema inmutable — sin ellos, los snapshots que ya se crean no sirven para nada en la práctica.

> **Orden recomendado:** 3.1 → 3.2 → 3.3 → resto. Secure Boot puede hacerse en paralelo al final.

### R2 — El selector de shell es más importante de lo que parece

Fish, Zsh y Bash tienen bases de usuarios muy distintas. Un desarrollador que usa fish en su máquina anterior y ve que ouroborOS solo le da bash probablemente busca otra distro. Es un detalle de UX con **alto impacto y costo muy bajo** — el campo `shell` ya existe en `UserConfig`, solo hay que exponerlo en la TUI y agregar los paquetes al ISO. Va en el estado `USER`, junto con username y password. Hacerlo bien incluye:
- Fish como opción (y **no** como default — es un shell no-POSIX y rompe scripts heredados)
- Bash como default explícito
- Zsh como opción intermedia
- `chsh` correcto en `configure.sh` para que el shell quede seteado en `/etc/passwd`

### R3 — `our-wifi` antes del first-boot, no después

Si el sistema instalado no tiene WiFi configurada, el usuario no puede actualizar ni instalar nada. Agregar el SSID/passphrase en el YAML del installer (que va a `/var/lib/iwd/SSID.psk`) es **una línea de configure.sh** — no debería bloquearse por el resto de la fase.

### R4 — Secure Boot: sbctl puro, sin shim, sin MOK

ouroborOS no usa shim. No hay dual-boot en el roadmap. La elección correcta es **sbctl nativo** con claves UEFI propias (PK/KEK/db). El tradeoff:
- ✅ Más seguro (sin intermediario)
- ✅ Más simple (un solo comando: `our-secureboot setup`)
- ⚠️ Requiere que el usuario entre al firmware a "borrar las claves" para entrar en Setup Mode
- ⚠️ Incompatible con sistemas que bootean Windows en la misma máquina

Para usuarios que necesiten dual-boot con Windows, documentar claramente que Secure Boot no es compatible con esa configuración en Phase 3.

### R5 — `homectl` en QEMU: resolver o descartar

El bug de `homectl create` en QEMU lleva dos fases sin resolverse. En Phase 3 hay que tomar una decisión: o se investiga con journalctl granular y se cierra, o se acepta que `homed_storage: classic` es el default de facto y se documenta honestamente. No vale la pena bloquear el resto de la fase por esto.

### R6 — No agregar AUR ni Flatpak todavía

Con `our-box` ya existe una forma de aislar software. Agregar AUR o Flatpak en Phase 3 va en contra de la filosofía del proyecto (minimal, systemd-native, sin capas adicionales). Si hay demanda real, que sea Phase 4 con una propuesta arquitectónica clara.

---

## Overview

Phase 3 foca en cuatro pilares:

1. **System Management** — `our-snap` (ciclo de vida de snapshots) y `our-rollback` (recuperación de un comando)
2. **Shell & User Experience** — Selector de shell (bash/zsh/fish) en el instalador
3. **First-Boot** — `our-wifi`, `ouroborOS-firstboot`, WiFi pre-configurado desde YAML
4. **Security Hardening** — Secure Boot via `sbctl` + `our-secureboot`, re-signing automático en updates

El objetivo: ouroborOS como **daily driver seguro, recuperable, y usable desde el primer arranque**.

---

## Estado del Proyecto al Inicio de Phase 3

### Completado (Phases 1-2)

| Feature | Status | Ubicación |
|---------|--------|-----------|
| ISO bootable (UEFI) | ✅ | `src/ouroborOS-profile/` |
| Installer FSM (11 estados) | ✅ | `src/installer/state_machine.py` |
| TUI interactive + unattended YAML | ✅ | `src/installer/tui.py`, `config.py` |
| Btrfs layout (5 subvols + `@snapshots/install`) | ✅ | `src/installer/ops/disk.sh` |
| systemd-boot + microcode auto-detect | ✅ | `src/installer/ops/configure.sh` |
| Desktop profiles (5 perfiles, 4 DMs) | ✅ | `src/installer/desktop_profiles.py` |
| `our-pac` (atomic update wrapper) | ✅ | `airootfs/usr/local/bin/our-pac` |
| `our-box` (17 comandos nspawn) | ✅ | `airootfs/usr/local/bin/our-box` |
| systemd-homed (subvolume default) | ✅ | `src/installer/ops/configure.sh` |
| `UserConfig.shell` (campo existente) | ✅ | `src/installer/config.py:47` |
| E2E QEMU: 11/11 estados, boot limpio | ✅ | `tests/scripts/e2e-desktop-profiles.sh` |
| 93% pytest coverage | ✅ | `src/installer/tests/` |

### Known Issues Heredados de Phase 2

| Issue | Workaround | Decisión Phase 3 |
|-------|-----------|-----------------|
| `homectl create --identity=JSON` falla en QEMU | Usar `homed_storage: classic` en E2E | Investigar con journalctl granular o documentar como limitación de QEMU |
| SSH en QEMU SLIRP tarda 60-90s | Poll nc antes de intentar SSH | Mantener workaround, no bloquea |

---

## Milestones de Phase 3

### 3.1 — `our-snap`: Gestión de Snapshots

**Objetivo:** CLI completa para gestionar snapshots Btrfs — crear, listar, eliminar, restaurar, y podar — con boot entries sincronizados automáticamente.

**Contexto técnico crítico:**
- Para hacer `btrfs property set ro false` en un snapshot, hay que montar **subvolid=5** (root del pool Btrfs) en un tmpdir. No se puede hacer sobre el mount point VFS actual (EROFS).
- systemd-boot no tiene soporte nativo de snapshots — las boot entries hay que generarlas manualmente en `/boot/loader/entries/`.
- El snapshot `@snapshots/install` (golden baseline) nunca debe ser purgado por `prune`.

**Comandos:**

```
our-snap list                         # Tabla: ID, nombre, fecha, tipo, tamaño
our-snap create [--name LABEL]        # Snapshot read-only manual de @
our-snap delete <name-or-id>          # Eliminar snapshot + boot entry + metadata
our-snap restore <name-or-id>         # → delega a our-rollback promote
our-snap prune [--keep N]             # Eliminar los más viejos (default: keep 5, nunca borra install)
our-snap boot-entries sync            # Regenerar /boot/loader/entries/ por snapshot existente
our-snap info <name-or-id>            # Metadata + diff de paquetes si existe
```

**Estructura de snapshot:**

```
/.snapshots/
├── install/                          # Golden baseline — NUNCA se toca
├── YYYY-MM-DD_pre-update/            # Creados por our-pac
├── YYYY-MM-DD_manual/                # Creados con our-snap create
└── .metadata/
    └── YYYY-MM-DD_pre-update.json    # { timestamp, packages, description, type }
```

**Boot entry por snapshot** (`/boot/loader/entries/ouroborOS-snapshot-YYYY-MM-DD.conf`):

```ini
title   ouroborOS (snapshot YYYY-MM-DD)
linux   /vmlinuz-linux-zen
initrd  /intel-ucode.img
initrd  /initramfs-linux-zen.img
options root=UUID=XXX rootflags=subvol=@snapshots/YYYY-MM-DD_pre-update,ro loglevel=4
```

**Poda automática (systemd timer semanal):**

```ini
# /etc/systemd/system/our-snap-prune.timer
[Timer]
OnCalendar=weekly
Persistent=true
```

**Milestones:**

- [ ] 3.1.1 `our-snap list` — parsea subvolumenes bajo `/.snapshots/`, muestra tabla
- [ ] 3.1.2 `our-snap create` — snapshot read-only + escribe `.metadata/NAME.json`
- [ ] 3.1.3 `our-snap delete` — elimina subvolume + boot entry + JSON
- [ ] 3.1.4 `our-snap prune` — ordena por fecha, elimina más viejos excepto `install`
- [ ] 3.1.5 `our-snap boot-entries sync` — genera entradas en `/boot/loader/entries/` por snapshot
- [ ] 3.1.6 `our-snap-prune.service` + `.timer` — unit systemd para poda semanal automática
- [ ] 3.1.7 Tests: shellcheck 0 warnings + pytest unitarios mockeados
- [ ] 3.1.8 Agregar `our-snap-prune.timer` al `ouroborOS-firstboot` (habilitar en primer arranque)

**Archivos:**

| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-snap` | Nuevo |
| `src/ouroborOS-profile/airootfs/etc/systemd/system/our-snap-prune.{service,timer}` | Nuevo |
| `tests/scripts/test-our-snap.sh` | Nuevo |

---

### 3.2 — `our-rollback`: Rollback de Un Comando

**Objetivo:** Volver al estado anterior con un solo comando. Sin conocer Btrfs internamente.

**Comandos:**

```
our-rollback list                     # Alias de our-snap list
our-rollback now [SNAPSHOT]           # One-shot reboot en el snapshot (bootctl set-oneshot)
our-rollback promote <SNAPSHOT>       # Swap permanente de @ por el snapshot
our-rollback status                   # ¿El root actual es @ o un snapshot?
```

**Mecánica de `our-rollback promote`** (rollback permanente):

```bash
TMPDIR=$(mktemp -d)
mount -o subvolid=5 /dev/disk/by-label/ouroborOS "$TMPDIR"

# Copia writable del snapshot
btrfs subvolume snapshot \
    "${TMPDIR}/@snapshots/${SNAPSHOT}" \
    "${TMPDIR}/@_new"

# Swap atómico
btrfs subvolume delete "${TMPDIR}/@"
mv "${TMPDIR}/@_new" "${TMPDIR}/@"

our-snap boot-entries sync
umount "$TMPDIR" && rmdir "$TMPDIR"
echo "Rollback listo. Reiniciá para aplicar."
```

> ⚠️ `our-rollback now` usa `bootctl set-oneshot` — falla en QEMU sin OVMF_VARS rw. En hardware real funciona. Los E2E tests deben usar `promote`.

**Milestones:**

- [ ] 3.2.1 `our-rollback list` — delega a `our-snap list`
- [ ] 3.2.2 `our-rollback now` — `bootctl set-oneshot <entry>` + `systemctl reboot`
- [ ] 3.2.3 `our-rollback promote` — swap atómico vía subvolid=5
- [ ] 3.2.4 `our-rollback status` — detecta si root es `@` o un snapshot
- [ ] 3.2.5 Tests shellcheck + unitarios

**Archivos:**

| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-rollback` | Nuevo |
| `tests/scripts/test-our-rollback.sh` | Nuevo |

---

### 3.3 — Shell Selector: bash / zsh / fish

**Objetivo:** El estado `USER` del instalador permite elegir el shell del usuario. El campo `UserConfig.shell` ya existe (`src/installer/config.py:47`) — solo hay que exponerlo en la TUI, agregarlo al YAML, instalar los paquetes necesarios, y hacer el `chsh` correcto en `configure.sh`.

**Shells soportados:**

| Shell | Paquete Arch | Path | Default |
|-------|-------------|------|---------|
| Bash | `bash` (ya en base) | `/bin/bash` | ✅ **Sí** |
| Zsh | `zsh` | `/bin/zsh` | No |
| Fish | `fish` | `/usr/bin/fish` | No |

**Por qué Bash es el default:** Fish es un shell no-POSIX — scripts heredados no funcionan sin modificación. Bash es el estándar de facto en ArchLinux y garantiza compatibilidad. Zsh y Fish son opciones para usuarios que los conocen.

**Cambios necesarios:**

**1. `packages.x86_64`** — agregar `zsh` y `fish` para que estén disponibles en el ISO live y puedan ser instalados en el target:

```
zsh
fish
```

> Nota: pacstrap ya incluye `bash` via `base`. `zsh` y `fish` se agregan a `extra_packages` en el installer si el usuario los elige, o directamente al pacstrap del perfil `base`.

**2. `src/installer/desktop_profiles.py`** — constantes de shells:

```python
VALID_SHELLS: dict[str, str] = {
    "bash": "/bin/bash",
    "zsh":  "/bin/zsh",
    "fish": "/usr/bin/fish",
}

SHELL_PACKAGES: dict[str, str] = {
    "zsh":  "zsh",
    "fish": "fish",
    # bash ya está en base
}
```

**3. `src/installer/tui.py`** — nueva función `show_shell_selection()`:

```python
def show_shell_selection(self) -> str:
    """Show shell selection menu. Returns shell path."""
    shells = [
        ("/bin/bash",        "Bash   — POSIX-compatible, universal default"),
        ("/bin/zsh",         "Zsh    — Bash-compatible with advanced completion"),
        ("/usr/bin/fish",    "Fish   — Modern, user-friendly, non-POSIX"),
    ]
    # Rich: radiolist / whiptail: --radiolist
    # Retorna el path del shell seleccionado. Default: /bin/bash
```

**4. `src/installer/state_machine.py`** — en `_handle_user()`, llamar `show_shell_selection()` y guardar en `config.user.shell`. Si el shell elegido tiene paquete asociado, agregarlo a `config.extra_packages`.

**5. `src/installer/ops/configure.sh`** — al crear el usuario, usar el shell correcto:

```bash
# Actual (solo useradd):
useradd -m -G "${USER_GROUPS}" -s "${USER_SHELL}" "${USERNAME}"

# Verificar que el shell existe en el sistema instalado antes de asignarlo:
if ! chroot /mnt grep -q "^${USER_SHELL}$" /etc/shells 2>/dev/null; then
    log_warn "Shell ${USER_SHELL} no registrado en /etc/shells — agregando"
    echo "${USER_SHELL}" >> /mnt/etc/shells
fi
```

**6. `templates/install-config.yaml`** — documentar el campo:

```yaml
user:
  username: "alice"
  password: "changeme"
  shell: "/bin/bash"    # /bin/bash (default) | /bin/zsh | /usr/bin/fish
```

**7. `docs/installer/configuration-format.md`** — actualizar validación:

```
- `user.shell` (si se provee): debe ser uno de `/bin/bash`, `/bin/zsh`, `/usr/bin/fish`
```

**Milestones:**

- [ ] 3.3.1 Agregar `zsh` y `fish` a `packages.x86_64` del ISO
- [ ] 3.3.2 `VALID_SHELLS` y `SHELL_PACKAGES` en `desktop_profiles.py`
- [ ] 3.3.3 `show_shell_selection()` en `tui.py` (Rich + whiptail fallback)
- [ ] 3.3.4 `_handle_user()` en `state_machine.py` — exponer shell selection, agregar paquete a `extra_packages` si es zsh/fish
- [ ] 3.3.5 `configure.sh` — verificar `/etc/shells` antes de `useradd -s`
- [ ] 3.3.6 Actualizar `config.py` — validar que `user.shell` sea uno de los válidos en `validate_config()`
- [ ] 3.3.7 Actualizar `templates/install-config.yaml` y `docs/installer/configuration-format.md`
- [ ] 3.3.8 Tests: `test_show_shell_selection()` en pytest + test de validación YAML con shell inválido

**Archivos a modificar:**

| Archivo | Cambio |
|---------|--------|
| `src/ouroborOS-profile/packages.x86_64` | Agregar `zsh`, `fish` |
| `src/installer/desktop_profiles.py` | `VALID_SHELLS`, `SHELL_PACKAGES` |
| `src/installer/tui.py` | `show_shell_selection()` |
| `src/installer/state_machine.py` | `_handle_user()` expone shell + agrega paquete |
| `src/installer/config.py` | Validar `user.shell` en `validate_config()` |
| `src/installer/ops/configure.sh` | `useradd -s` + verificar `/etc/shells` |
| `templates/install-config.yaml` | Documentar `shell:` |
| `docs/installer/configuration-format.md` | Agregar validación de `user.shell` |

---

### 3.4 — First-Boot Experience

#### 3.4.1 `our-wifi` — WiFi Setup Interactivo

**Comandos:**

```
our-wifi list                  # Scan + listar redes disponibles
our-wifi connect <SSID>        # Interactivo: pide passphrase
our-wifi connect <SSID> --password <PASS>   # No interactivo
our-wifi status                # Estado de conexión actual (iwctl station show)
our-wifi forget <SSID>         # Eliminar /var/lib/iwd/SSID.psk
our-wifi show-password <SSID>  # Mostrar passphrase guardada
```

**Pre-configuración WiFi desde YAML del installer:**

```yaml
network:
  wifi:
    ssid: "MiRed"
    passphrase: "mi-password"   # Escrito a /var/lib/iwd/ durante install, limpiado de InstallerConfig
```

`configure.sh` escribe `/var/lib/iwd/MiRed.psk` (chmod 600) y limpia `passphrase` de config en memoria.

#### 3.4.2 `ouroborOS-firstboot` — Servicio Oneshot

```bash
#!/usr/bin/env bash
# Corre UNA sola vez. Guard: /var/lib/ouroborOS/firstboot.done
set -euo pipefail

# 1. Mirrors — reflector server-side (rápido, sin benchmark local)
reflector --save /etc/pacman.d/mirrorlist --sort score --latest 20 --protocol https

# 2. machine-id único si quedó el default del ISO
[[ "$(cat /etc/machine-id)" == "b08dfa6083e7567a1921a715000001fb" ]] && \
    systemd-machine-id-setup --commit

# 3. Activar timer de poda de snapshots
systemctl enable --now our-snap-prune.timer 2>/dev/null || true

# 4. Marcar completado
mkdir -p /var/lib/ouroborOS
date -Iseconds > /var/lib/ouroborOS/firstboot.done
```

**Milestones:**

- [ ] 3.4.1 `our-wifi` CLI completo (list/connect/status/forget/show-password)
- [ ] 3.4.2 `network.wifi` en YAML schema — `ssid` + `passphrase`
- [ ] 3.4.3 `configure.sh` escribe `/var/lib/iwd/SSID.psk` + limpia passphrase de config
- [ ] 3.4.4 `ouroborOS-firstboot` script + `.service` con `ConditionPathExists=!/var/lib/ouroborOS/firstboot.done`
- [ ] 3.4.5 Reflector en firstboot (mirrors optimizados post-install)
- [ ] 3.4.6 Activar `our-snap-prune.timer` en firstboot
- [ ] 3.4.7 `machine-id` reset si es el default del ISO
- [ ] 3.4.8 Tests: shellcheck + test unitario con reflector mockeado

---

### 3.5 — Secure Boot: `sbctl` + `our-secureboot`

**Objetivo:** Secure Boot UEFI nativo vía `sbctl`. Sin shim, sin MOK. Workflow de un comando.

**Contexto técnico:**
- `sbctl` genera PK/KEK/db propios y los enrolla en EFI variables
- Firma el bootloader (`systemd-bootx64.efi`) y el kernel (`vmlinuz-linux-zen`)
- El paquete `sbctl` incluye un pacman hook que re-firma automáticamente en cada update
- **Requiere firmware en Setup Mode** (borrar claves Secure Boot en el UEFI)
- Claves en `/var/lib/sbctl/keys/`

**Comandos:**

```
our-secureboot setup           # create-keys + enroll-keys + sign-all
our-secureboot status          # sbctl status + archivos sin firmar
our-secureboot sign-all        # Re-firmar todos los archivos trackeados
our-secureboot rotate-keys     # Rotar claves (backup + nuevas + re-firma)
our-secureboot verify          # Verificar estado del firmware
```

**Integración con `our-pac`** — post-update, si SB está habilitado:

```bash
if command -v sbctl &>/dev/null && sbctl status 2>/dev/null | grep -q "Secure Boot: enabled"; then
    sbctl sign-all
fi
```

**YAML:**

```yaml
security:
  secure_boot: false              # true: habilitar Secure Boot via sbctl
  sbctl_include_ms_keys: false    # true: incluir claves Microsoft (compatibilidad hardware)
```

**Milestones:**

- [ ] 3.5.1 Agregar `sbctl` a `packages.x86_64`
- [ ] 3.5.2 `our-secureboot` CLI completo
- [ ] 3.5.3 `SecurityConfig` dataclass en `config.py`
- [ ] 3.5.4 Integración `sbctl sign-all` en `our-pac` post-update
- [ ] 3.5.5 Step opcional `SECURE_BOOT` en el FSM (post-CONFIGURE, pre-SNAPSHOT)
- [ ] 3.5.6 `show_secure_boot()` en `tui.py` — pantalla con instrucciones de Setup Mode
- [ ] 3.5.7 `docs/architecture/secure-boot.md`
- [ ] 3.5.8 Tests: shellcheck + integración mockeada

---

### 3.6 — Hardening de `our-pac` (Updates Atómicos)

**Flujo Phase 3:**

```
our-pac -Syu
  → verificar espacio ≥ 2GB en /.snapshots/
  → snapshot pre-update con metadata JSON
  → remount @ rw
  → pacman -Syu
  → remount @ ro
  → [si sbctl activo] sbctl sign-all
  → our-snap boot-entries sync
  → log estructurado a /var/log/our-pac/YYYY-MM-DD.json
  → our-snap prune si snapshots > 10
```

**Milestones:**

- [ ] 3.6.1 Verificación de espacio pre-update
- [ ] 3.6.2 Metadata JSON por snapshot
- [ ] 3.6.3 Integración `sbctl sign-all`
- [ ] 3.6.4 `our-snap boot-entries sync` post-update
- [ ] 3.6.5 Logging estructurado en `/var/log/our-pac/`
- [ ] 3.6.6 Poda automática si snapshots > 10

---

### 3.7 — `our-box` Mejoras: GUI/GPU Passthrough

**Nuevos flags en `our-box enter`:**

```bash
our-box enter <name> --wayland   # Bind-mount Wayland socket + vars
our-box enter <name> --gpu       # Bind-mount /dev/dri/
our-box enter <name> --audio     # Bind-mount PipeWire socket
our-box enter <name> --gui       # = --wayland + --gpu + --audio
```

**Implementación nspawn:**

```bash
--bind-ro=/run/user/${UID}/wayland-0
--bind=/dev/dri
--bind-ro=/run/user/${UID}/pipewire-0
--setenv=WAYLAND_DISPLAY=wayland-0
--setenv=XDG_RUNTIME_DIR=/run/user/${UID}
--property=DeviceAllow=char-drm rw
```

**Milestones:**

- [ ] 3.7.1 Flags `--wayland`, `--gpu`, `--audio`, `--gui` en `our-box enter`
- [ ] 3.7.2 `our-box create --gui` pre-configura el contenedor con capabilities gráficas
- [ ] 3.7.3 Documentación: sección "GUI containers" en `docs/our-box.md`
- [ ] 3.7.4 Tests: shellcheck

---

### 3.8 — Fix `homectl` en QEMU

**Plan:** Capturar `journalctl -u systemd-homed` durante el intento, identificar el error real, implementar fallback automático a `useradd` clásico sin romper la instalación.

**Fallback en `state_machine.py`:**

```python
try:
    _run_op("configure.sh", env={..., "USE_HOMED": "1"})
except InstallerError:
    log.warning("homectl failed, falling back to classic useradd")
    _run_op("configure.sh", env={..., "USE_HOMED": "0"})
```

**Milestones:**

- [ ] 3.8.1 Loguear journalctl de homed al install log durante install
- [ ] 3.8.2 Fallback automático a classic useradd si homectl falla
- [ ] 3.8.3 E2E test: verificar fallback en QEMU

---

### 3.9 — Multi-Language Installer (Stretch)

- [ ] Extraer strings del TUI a diccionario central
- [ ] `gettext` con `.po`/`.mo` para inglés y español
- [ ] Campo `locale.language` en YAML
- [ ] Pantalla de selección de idioma en estado INIT

> Puede postergarse a Phase 4 si los anteriores consumen más tiempo.

---

## Resumen de Milestones

| # | Feature | Prioridad | Complejidad | Depende de |
|---|---------|-----------|-------------|------------|
| 3.1 | `our-snap` | 🔴 Alta | Media | — |
| 3.2 | `our-rollback` | 🔴 Alta | Media | 3.1 |
| 3.3 | Shell selector (bash/zsh/fish) | 🔴 Alta | **Baja** | — |
| 3.4 | First-boot (`our-wifi` + firstboot) | 🟡 Media | Baja | — |
| 3.5 | Secure Boot (`sbctl` + `our-secureboot`) | 🟡 Media | Alta | — |
| 3.6 | `our-pac` hardening | 🟡 Media | Baja | 3.1 |
| 3.7 | `our-box` GUI/GPU | 🟢 Baja | Media | — |
| 3.8 | Fix `homectl` QEMU | 🟡 Media | Alta (investigación) | — |
| 3.9 | Multi-language | 🟢 Baja | Alta | — |

**Orden de implementación recomendado:**

```
3.3 (shell selector, bajo costo, alto impacto UX)
  → 3.1 (our-snap, corazón del sistema)
  → 3.2 (our-rollback, depende de 3.1)
  → 3.4 (first-boot, independiente, baja complejidad)
  → 3.6 (our-pac hardening, depende de 3.1)
  → 3.5 (secure boot, independiente, alta complejidad)
  → 3.7 + 3.8 (paralelo si hay tiempo)
  → 3.9 (stretch)
```

---

## Nuevos Archivos

```
src/ouroborOS-profile/airootfs/usr/local/bin/
├── our-snap               ← Nuevo (3.1)
├── our-rollback           ← Nuevo (3.2)
├── our-secureboot         ← Nuevo (3.5)
├── our-wifi               ← Nuevo (3.4)
└── ouroborOS-firstboot    ← Nuevo (3.4)

src/ouroborOS-profile/airootfs/etc/systemd/system/
├── our-snap-prune.service ← Nuevo (3.1)
├── our-snap-prune.timer   ← Nuevo (3.1)
└── ouroborOS-firstboot.service ← Nuevo (3.4)

docs/architecture/
└── secure-boot.md         ← Nuevo (3.5)

tests/scripts/
├── test-our-snap.sh       ← Nuevo (3.1)
└── test-our-rollback.sh   ← Nuevo (3.2)
```

## Archivos Modificados

```
src/ouroborOS-profile/packages.x86_64     ← zsh, fish, sbctl (3.3, 3.5)
src/installer/config.py                   ← validate shell, SecurityConfig, NetworkConfig.wifi
src/installer/desktop_profiles.py         ← VALID_SHELLS, SHELL_PACKAGES
src/installer/tui.py                      ← show_shell_selection(), show_secure_boot()
src/installer/state_machine.py            ← _handle_user() shell, SECURE_BOOT state
src/installer/ops/configure.sh            ← useradd -s, /etc/shells, wifi psk, sbctl
templates/install-config.yaml            ← shell, security, network.wifi
docs/installer/configuration-format.md   ← validación user.shell
```

## Schema YAML Phase 3

```yaml
user:
  username: "alice"
  password: "changeme"
  shell: "/bin/bash"              # NUEVO — /bin/bash | /bin/zsh | /usr/bin/fish

network:
  hostname: "ouroboros"
  enable_networkd: true
  enable_iwd: true
  enable_resolved: true
  wifi:                           # NUEVO — pre-configurar WiFi para primer boot
    ssid: ""
    passphrase: ""                # Escrita a /var/lib/iwd/, limpiada post-install

security:                         # NUEVO
  secure_boot: false
  sbctl_include_ms_keys: false

locale:
  language: "en"                  # NUEVO (stretch) — en | es
  locale: "en_US.UTF-8"
  keymap: "us"
  timezone: "America/New_York"
```

---

## Criterios de Aceptación de Phase 3

- [ ] Instalador muestra selector de shell (bash/zsh/fish) en estado USER
- [ ] El usuario instalado tiene el shell correcto en `/etc/passwd` y en `/etc/shells`
- [ ] `zsh` y `fish` están disponibles en el sistema instalado si fueron seleccionados
- [ ] `our-snap list` muestra todos los snapshots incluyendo `install`
- [ ] `our-snap create` crea un snapshot + boot entry + metadata JSON
- [ ] `our-snap prune --keep 3` elimina los más viejos, nunca toca `install`
- [ ] `our-rollback promote <snapshot>` reemplaza `@` correctamente — sistema bootea desde nuevo root
- [ ] `our-wifi connect <SSID>` conecta exitosamente con passphrase
- [ ] `ouroborOS-firstboot` corre una sola vez — actualiza mirrors, activa timer de poda
- [ ] `our-secureboot setup` firma kernel + bootloader en firmware en Setup Mode
- [ ] `our-pac -Syu` llama `sbctl sign-all` post-update si Secure Boot activo
- [ ] E2E QEMU: install con `shell: /bin/zsh` → usuario tiene zsh al boot
- [ ] Todos los scripts pasan shellcheck con 0 warnings
- [ ] pytest coverage ≥ 93%

---

## Out of Scope (Phase 4+)

- ARM / aarch64
- GUI installer
- AUR helper (`our-aur`)
- Flatpak / Snap
- Dual-boot con Secure Boot
- TPM2 + `systemd-cryptenroll` (LUKS sin passphrase)
- Live USB persistence
- Network namespaces / alternativas a nspawn
