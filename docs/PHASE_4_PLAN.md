# Phase 4 Plan — AUR, TPM2, Flatpak & Extended Package Management

**Version:** v0.4.12
**Date:** 2026-04-16 (updated)
**Branch:** main

> **Phase 4 COMPLETA.** Todos los milestones implementados.
> v0.4.12 = bugfix release + ARM eliminado + i18n es_CL.

---

## Convención de nombres (herencia de Phase 3)

| Prefijo | Audiencia | Ejecutables |
|---------|-----------|-------------|
| `our-*` | Usuario final (interactivo) | `our-pac`, `our-aur`, `our-snapshot`, `our-rollback`, `our-wifi`, `our-bluetooth`, `our-container`, `our-fido2`, `our-flat` |
| `ouroboros-*` | Sistema (servicios, automatización) | `ouroboros-secureboot`, `ouroboros-firstboot` |

---

## Tabla Resumen

| # | Feature | Ejecutable/Clave | Versión | Complejidad | Estado |
|---|---------|-----------------|---------|-------------|--------|
| 4.0 | `our-aur` AUR helper containerizado | `our-aur` | v0.4.0 | Alta | ✅ |
| 4.1 | Lazy AUR install via firstboot queue | pipeline | v0.4.0 | Media | ✅ |
| 4.2 | TPM2 + `systemd-cryptenroll` | `ouroboros-secureboot` | v0.4.8 | Alta | ✅ |
| 4.3 | Multi-Language TUI (en_US, es_CL, de_DE) | TUI + i18n | v0.4.9 | Media | ✅ |
| 4.4 | Flatpak | `our-flat` | v0.4.0 | Baja | ✅ |
| 4.5 | Live USB Persistence | — | — | — | ❌ N/A |
| 4.6 | Dual-Boot + Secure Boot | installer | v0.4.10 | Alta | ✅ |
| 4.7 | ARM / aarch64 | — | — | — | ❌ REMOVED |
| 4.A | ISO & CI Hardening | `packages.x86_64`, CI | v0.4.5 | Baja | ✅ |
| 4.B | Desktop Profile Completion | `desktop_profiles.py` | v0.4.5 | Baja | ✅ |

**Orden de implementación:**
```
[✅ 4.0] → [✅ 4.1] → [✅ 4.4] → [✅ 4.A] → [✅ 4.B] → [✅ 4.2] → [✅ 4.3] → [✅ 4.6]
```

---

## Milestones Detallados

### Milestone 4.0 — `our-aur` (AUR helper containerizado) ✅

**Completado:** 2026-04-11 — commit `71bda2d`

AUR helper que corre `paru` dentro de un contenedor efímero (`systemd-nspawn`) y
convierte el resultado en una extensión `systemd-sysext`. Nunca toca el root del host
durante el build.

**Decisiones de diseño clave:**

| Decisión | Elección | Motivo |
|----------|----------|--------|
| Backend de build | `paru` (via paru-bin de GitHub releases) | Resuelve deps AUR→AUR; sin bootstrap circular |
| Instalación final | `systemd-sysext` directorio | Sin remount de `/`; squashfs como optimización futura |
| Formato sysext | Directorio en `/var/lib/extensions/our-aur-<pkg>/` | `squashfs-tools` no está en el ISO |
| JSON parsing | `python3 -c` con `sys.argv[1]` | `jq` no disponible en ISO; evita SC2259 |
| AUR API | `curl` → AUR RPC v6 | `curl` ya en packages.x86_64 |
| Contenedor build | Efímero en `/var/tmp/our-aur/containers/` | No contamina `/var/lib/machines/` |
| Usuario build | `aurbuild` (UID 1000) creado en el contenedor | `makepkg` rechaza root |
| Limpieza | `trap _cleanup EXIT` | Garantía incluso en error |

**Interface (flags paru-compatibles):**

```
our-aur -S  <pkg>    instalar desde AUR → sysext directory → sysext refresh
our-aur -Ss <query>  buscar en AUR (AUR RPC v6)
our-aur -Si <pkg>    info del paquete AUR
our-aur -Su          upgrade paquetes AUR instalados (rebuild sysext)
our-aur -R  <pkg>    remover sysext directory + refresh
our-aur -Q           listar paquetes AUR instalados
our-aur -Qs <query>  buscar en instalados
our-aur --clean      limpiar contenedores huérfanos + cache
```

**Criterios de aceptación:**
- [x] `our-aur -Ss hyprlock` devuelve resultados sin root
- [x] `our-aur -Si quickshell` muestra versión + descripción
- [x] `our-aur -S <pkg>` construye en contenedor efímero y crea sysext directory
- [x] `our-aur -Q` lista paquetes instalados desde JSON tracking
- [x] `our-aur -R <pkg>` remueve sysext + tracking JSON
- [x] `our-aur -Su` reconstruye todos los sysexts tracked
- [x] shellcheck 0 warnings
- [x] Contenedor destruido al terminar (incluso en error)

---

### Milestone 4.1 — Lazy AUR Install Queue (firstboot pipeline) ✅

**Completado:** 2026-04-11 — commit `17f618f`

Los perfiles de escritorio con paquetes AUR (e.g. hyprland) no bloquean el installer.
Los paquetes se encolan en `firstboot-aur-packages.txt` y se instalan en el primer boot
via `ouroboros-firstboot` + `our-aur`.

**Paquetes AUR por perfil:**

| Perfil | AUR packages |
|--------|-------------|
| `minimal` | — |
| `hyprland` | `quickshell` |
| `niri` | — (niri está en `[extra]`) |
| `gnome` | — |
| `kde` | — |
| `cosmic` | — (cosmic está en `[extra]`) |

**Criterios de aceptación:**
- [x] Perfil `hyprland` → `DESKTOP_AUR_PACKAGES="quickshell"` en env
- [x] `configure.sh` escribe `/var/lib/ouroborOS/firstboot-aur-packages.txt`
- [x] `ouroboros-firstboot` habilita `systemd-sysext.service`
- [x] `ouroboros-firstboot` corre `our-aur -S` por cada paquete en el queue
- [x] `ouroboros-firstboot` borra el queue file al terminar

---

### Milestone 4.2 — TPM2 + `systemd-cryptenroll` ✅

**Completado:** v0.4.8

Integración de TPM2 para desbloqueo automático de LUKS sin passphrase en boot.
PCR 7 (Secure Boot state) + PCR 14 (systemd-boot measured boot entries).

**Implementación:**
- `SecurityConfig.tpm2_unlock` en `config.py` — validación: requiere `disk.use_luks: true`
- `configure_tpm2()` en `configure.sh` — `systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7+14`
- `ouroboros-secureboot tpm2-enroll` y `tpm2-status` subcomandos
- `show_tpm2_prompt()` en `tui.py` — detecta `/sys/class/tpm/tpm0`, warning si ausente
- `tpm2-tools` en `packages.x86_64`
- YAML key: `security.tpm2_unlock: true`
- Fallback graceful a passphrase si TPM2 no disponible

**Criterios de aceptación:**
- [x] `security.tpm2_unlock: true` con `disk.use_luks: false` → ConfigValidationError
- [x] TUI muestra prompt TPM2 con detección de hardware
- [x] `configure_tpm2()` enrola LUKS slot con PCR 7+14
- [x] Fallback a passphrase si systemd-cryptenroll falla
- [x] Tests en `test_config.py`, `test_state_machine.py`

---

### Milestone 4.3 — Multi-Language TUI ✅

**Completado:** v0.4.9 (actualizado a es_CL en v0.4.12)

Soporte i18n en el installer via gettext. Archivos `.po`/`.mo`.
Campo `locale.language` en YAML. Pantalla de selección de idioma en estado INIT.

**Idiomas:** en_US (base), es_CL (Chile), de_DE (Deutschland)

**Implementación:**
- `i18n.py` — `init_i18n()` + `_()` wrapper con NullTranslations fallback
- `.po` files en `src/installer/locale/{en_US,es_CL,de_DE}/LC_MESSAGES/installer.po`
- `.mo` compilados al vuelo en `build-iso.sh` via `msgfmt`
- `show_language_selection()` en `tui.py`
- `_STEP_LABELS` usa `_()` en el punto de uso (NO en definición)
- `SUPPORTED_LANGUAGES` en `i18n.py` + `_LANGUAGE_OPTIONS` en `tui.py`

**Criterios de aceptación:**
- [x] Selección de idioma en INIT state antes de cualquier string
- [x] `_()` wrap en todos los strings user-facing del TUI
- [x] `.po` files con ~80+ strings traducidos por idioma
- [x] Fallback silencioso a inglés si `.mo` no encontrado
- [x] `test_i18n.py` con 12 tests

---

### Milestone 4.4 — Flatpak ✅

**Completado:** v0.4.0

Integración de Flatpak como fuente complementaria para apps de escritorio.
Sin Flathub por defecto — el usuario lo habilita explícitamente.

**Interface:**
```
our-flat install <app>    instalar app (Flathub)
our-flat remove <app>     remover app
our-flat update           actualizar todas las apps
our-flat search <query>   buscar en remotos
our-flat list             listar apps instaladas
our-flat info <app>       info de app
our-flat remote           gestionar remotos (add, remove, list)
```

---

### Milestone 4.5 — Live USB Persistence ❌ N/A

> Eliminado — ouroborOS es un ISO live con formato erofs (`airootfs_image_type="erofs"`).
> La persistencia no aplica: el ISO es de instalación, no de uso persistente.
> El sistema instalado usa Btrfs con snapshots para gestión de estado.

---

### Milestone 4.6 — Dual-Boot + Secure Boot ✅

**Completado:** v0.4.10

Instalación junto a Windows con Secure Boot activo.
Detección de Windows Boot Manager via EFI path.

**Implementación:**
- `configure_dual_boot()` en `configure.sh` — detecta `EFI/Microsoft/Boot/bootmgfw.efi`
- Genera `windows.conf` en systemd-boot entries
- Ajusta `loader.conf` timeout a 5s cuando dual-boot está activo
- `SecurityConfig.dual_boot` en `config.py`
- `show_dual_boot_prompt()` en `tui.py` (rich + whiptail)
- `_detect_existing_os()` en `state_machine.py` — escanea ESP para OS conocidos
- `sbctl enroll-keys --microsoft` cuando `sbctl_include_ms_keys: true` + dual-boot
- Integración con Secure Boot: MS OEM keys incluidas automáticamente en modo dual-boot

**Criterios de aceptación:**
- [x] Windows Boot Manager detectado en ESP
- [x] `windows.conf` generado en `/boot/loader/entries/`
- [x] Timeout ajustado a 5s en `loader.conf`
- [x] `sbctl enroll-keys --microsoft` cuando dual-boot + secure boot
- [x] Tests en `test_config.py`, `test_state_machine.py`, `test_tui.py`

---

### Milestone 4.7 — ARM / aarch64 ❌ REMOVED

> Removed in v0.4.12 — no ARM hardware for validation.

---

### Milestone 4.A — ISO & CI Hardening ✅

**Completado:** v0.4.5

**ISO (`packages.x86_64`):**
- `cryptsetup` agregado — fix bug crítico LUKS
- `linux-zen-headers` eliminado (-30 MB)
- `flatpak` eliminado — on-demand via `our-flat` (-15 MB)
- `pciutils`, `usbutils`, `diffutils` agregados
- ISO image format: **erofs** (`airootfs_image_type="erofs"` con lzma + ztailpacking)

**CI (`.github/workflows/build.yml`):**
- `actions/checkout` v5
- Verificación post-patch de mkarchiso con `::error::`
- Regex awk endurecido

**Rollback (`our-rollback`):**
- `promote`: boot entry huérfana eliminada tras swap atómico
- `promote`: `bootctl set-default ouroborOS.conf` explícito

---

### Milestone 4.B — Desktop Profile Completion ✅

**Completado:** v0.4.5

**Hyprland:** grim + slurp, dunst, thunar, hyprlock, hypridle, hyprpaper, hyprsunset
**Niri:** waybar, mako, swaylock, swaybg, swayidle
**KDE:** curated set (dolphin, konsole, kate, gwenview, ark, ffmpegthumbs) sin kde-applications-meta
**COSMIC:** perfil completo (15 paquetes), greetd + cosmic-greeter
**GPU detection:** auto/mesa/amdgpu/nvidia/nvidia-open/none via `lspci`

---

## Criterios de Aceptación Phase 4

- [x] `our-aur -S quickshell` instala sin tocar el root del host
- [x] Perfil hyprland encola AUR packages para firstboot
- [x] `ouroboros-firstboot` instala AUR queue via `our-aur` al primer boot
- [x] `cryptsetup` disponible en el live ISO (fix bug LUKS)
- [x] Perfiles Hyprland y Niri con screenshots, notificaciones, lock screen y file manager
- [x] KDE sin `kde-applications-meta` (curated set ~400 MB vs ~1.5 GB)
- [x] `our-rollback promote` limpia boot entry huérfana y resetea default boot
- [x] CI: awk patch de mkarchiso verificado y endurecido
- [x] TPM2 unlock — `systemd-cryptenroll --tpm2-pcrs=7+14` con fallback a passphrase
- [x] Multi-language TUI operativa en en_US, es_CL, de_DE
- [x] Dual-boot con Windows detectado y entrada en systemd-boot
- [x] ISO image format: erofs (lzma + ztailpacking)
- [x] COSMIC desktop profile completo con greetd
- [x] GPU detection automática via lspci
- [x] 555 tests pytest pasando sin regresiones
- [x] shellcheck 0 warnings en scripts principales
- [x] ruff check limpio

---

## Out of Scope (Phase 5+)

- GUI installer (Electron o Qt)
- ZFS como alternativa a Btrfs
- Soporte de múltiples usuarios con homed
- Snapper integration
- OTA updates via casync o ostree
- ARM / aarch64 (eliminado en v0.4.12)
