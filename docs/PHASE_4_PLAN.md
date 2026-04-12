# Phase 4 Plan — AUR, TPM2, Flatpak & Extended Package Management

**Version:** post-v0.3.0
**Date:** 2026-04-11
**Branch:** main

> **v0.3.0 released.** Phase 3 complete. Este documento define Phase 4.
> Arranca desde el backlog "Out of Scope (Phase 4+)" de PHASE_3_PLAN.md
> más lo resuelto en la sesión de kickoff del 2026-04-11.

---

## Convención de nombres (herencia de Phase 3)

| Prefijo | Audiencia | Ejecutables |
|---------|-----------|-------------|
| `our-*` | Usuario final (interactivo) | `our-pac`, `our-aur`, `our-snapshot`, `our-rollback`, `our-wifi`, `our-bluetooth`, `our-container`, `our-fido2` |
| `ouroboros-*` | Sistema (servicios, automatización) | `ouroboros-secureboot`, `ouroboros-firstboot` |

---

## Estado al inicio de Phase 4

### Completado en Phases 1–3

Todo lo listado en PHASE_3_PLAN.md como completado, más:

| Feature | Commit |
|---------|--------|
| `our-pac` (renombrado de `our-pacman`) | `c1b1dad` |
| ISO version 0.3.0 | `00d1209` |

---

## Actividades Phase 4

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

**Archivos:**

| Archivo | Tipo |
|---------|------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-aur` | Nuevo |
| `src/ouroborOS-profile/profiledef.sh` | Modificado — permiso `0:0:755` para `our-aur` |

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
| `hyprland` | `quickshell`, `hyprlock`, `hypridle`, `hyprshot` |
| `niri` | — (niri está en `[extra]`) |
| `gnome` | — |
| `kde` | — |

**Archivos:**

| Archivo | Cambio |
|---------|--------|
| `src/installer/desktop_profiles.py` | `PROFILE_AUR_PACKAGES` dict + `aur_packages_for()` |
| `src/installer/config.py` | `DesktopConfig.aur_packages` field, populado en loader |
| `src/installer/state_machine.py` | `DESKTOP_AUR_PACKAGES` env var pasada a `configure.sh` |
| `src/installer/ops/configure.sh` | Escribe `firstboot-aur-packages.txt` si hay AUR packages |
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-firstboot` | Habilita `systemd-sysext` + instala AUR queue |

**Criterios de aceptación:**
- [x] Perfil `hyprland` → `DESKTOP_AUR_PACKAGES="quickshell hyprlock hypridle hyprshot"` en env
- [x] `configure.sh` escribe `/var/lib/ouroborOS/firstboot-aur-packages.txt`
- [x] `ouroboros-firstboot` habilita `systemd-sysext.service`
- [x] `ouroboros-firstboot` corre `our-aur -S` por cada paquete en el queue
- [x] `ouroboros-firstboot` borra el queue file al terminar
- [x] 347 tests pytest pasan sin regresiones

---

### Milestone 4.2 — TPM2 + `systemd-cryptenroll` ⬜

Integración de TPM2 para desbloqueo automático de LUKS sin passphrase en boot.
Permite que sistemas con LUKS arranquen sin intervención del usuario cuando el
estado del sistema es el esperado (PCR measurements).

**Alcance:**
- `systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7+14` post-install
- Integración con `ouroboros-secureboot` (PCR 7 = Secure Boot state)
- TUI: opción "TPM2 auto-unlock" en pantalla LUKS del installer
- Fallback a passphrase si TPM2 no disponible o measurements cambian
- YAML key: `disk.tpm2_unlock: true`

**Dependencias:** LUKS activo (`disk.use_luks: true`), Secure Boot opcional (mejora PCR binding)

**Complejidad:** Alta — PCR policy binding, sealed secrets, manejo de re-enroll tras updates de kernel

---

### Milestone 4.3 — Multi-Language TUI ⬜

Soporte i18n en el installer (postergado de Milestone 3.11).
Gettext + archivos `.po`/`.mo`. Campo `locale.language` en YAML.
Pantalla de selección de idioma en estado INIT.

**Idiomas iniciales:** en_US (base), es_AR, de_DE

**Complejidad:** Media — gettext en Python es directo; la complejidad está en traducir strings de TUI Rich

---

### Milestone 4.4 — Flatpak ⬜

Integración de Flatpak como fuente complementaria para apps de escritorio.
Sin Flathub por defecto — el usuario lo habilita explícitamente.

**Alcance:**
- `our-flatpak` wrapper: `our-flatpak -S <app>`, `-R`, `-Q`, `-Su`
- `flatpak` en packages.x86_64
- Remoto Flathub opt-in vía `our-flatpak remote-add flathub`
- No integración con sysext (Flatpak gestiona su propio sandbox en `/var/lib/flatpak`)
- YAML key: `desktop.flatpak: true`

**Complejidad:** Baja — Flatpak ya resuelve sandboxing; el wrapper es thin

---

### Milestone 4.5 — Live USB Persistence ⬜

Permitir que el ISO live mantenga estado entre reboots en el mismo USB.
Usando una partición Btrfs adicional en el dispositivo USB.

**Alcance:**
- Script `our-persist setup` — crea partición Btrfs en el USB live
- Mount en `/persistence` al boot (via cmdline `ouroborOS.persist=auto`)
- `/home`, `/etc`, `/var/lib` redirigidos via bind mounts
- Compatible con immutable root (no rompe el modelo actual)

**Complejidad:** Alta — requiere cambios en initramfs hooks y systemd-repart

---

### Milestone 4.6 — Dual-Boot + Secure Boot ⬜

Instalación junto a Windows u otra distro Linux con Secure Boot activo.
Requiere enrolamiento de Microsoft OEM keys (`sbctl enroll-keys -m`).

**Alcance:**
- Installer: detectar instalaciones existentes en disco (os-prober)
- `systemd-boot` con múltiples entradas (Windows via EFI chainload)
- `sbctl enroll-keys -m` cuando `sbctl_include_ms_keys: true`
- Documentación: proceso de enrolamiento + recuperación

**Ya implementado:** `SecurityConfig.sbctl_include_ms_keys` en config.py y `ouroboros-secureboot`

**Complejidad:** Alta — interacción con firmware OEM, edge cases de UEFI variables

---

### Milestone 4.7 — ARM / aarch64 ⬜

Soporte de arquitectura aarch64 para Raspberry Pi 5 y hardware ARM similar.
Requiere perfil archiso separado + ajustes en bootloader (UEFI via EDKII).

**Complejidad:** Muy Alta — requiere hardware real para validar; out of scope hasta tener base x86_64 estable

---

## Tabla Resumen

| # | Feature | Ejecutable/Clave | Prioridad | Complejidad | Estado |
|---|---------|-----------------|-----------|-------------|--------|
| 4.0 | `our-aur` AUR helper containerizado | `our-aur` | 🔴 | Alta | ✅ |
| 4.1 | Lazy AUR install via firstboot queue | pipeline | 🔴 | Media | ✅ |
| 4.2 | TPM2 + `systemd-cryptenroll` | `ouroboros-secureboot` | 🟡 | Alta | ⬜ |
| 4.3 | Multi-Language TUI | TUI | 🟢 | Media | ⬜ |
| 4.4 | Flatpak | `our-flatpak` | 🟡 | Baja | ⬜ |
| 4.5 | Live USB Persistence | `our-persist` | 🟢 | Alta | ⬜ |
| 4.6 | Dual-Boot + Secure Boot | installer | 🟡 | Alta | ⬜ |
| 4.7 | ARM / aarch64 | archiso | 🟢 | Muy Alta | ⬜ |

**Orden de implementación sugerido:**
```
4.2 → 4.4 → 4.3 → 4.6 → 4.5 → 4.7
```
> 4.2 y 4.4 son independientes y pueden ir en paralelo.

---

## Criterios de Aceptación Phase 4

- [x] `our-aur -S quickshell` instala sin tocar el root del host
- [x] Perfil hyprland encola AUR packages para firstboot
- [x] `ouroboros-firstboot` instala AUR queue via `our-aur` al primer boot
- [ ] Todos los scripts: shellcheck 0 warnings (pendiente: `our-snapshot`, `configure.sh`)
- [ ] pytest coverage ≥ 93% (actualmente: 347 tests pasan)
- [ ] TPM2 unlock funciona en QEMU con OVMF + swtpm
- [ ] Flatpak instala apps de Flathub en perfil gnome/kde

---

## Out of Scope (Phase 5+)

- GUI installer (Electron o Qt)
- ZFS como alternativa a Btrfs
- Soporte de múltiples usuarios con homed
- Snapper integration
- OTA updates via casync o ostree
