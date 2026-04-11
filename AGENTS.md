# BASE DE CONOCIMIENTO DEL PROYECTO

**Actualizado:** 2026-04-11
**Commit:** v0.3.0 (tag)
**Branch:** main

## REGLAS DE SALIDA (OBLIGATORIO)

1. **Idioma de salida:** Todas las respuestas, explicaciones, resúmenes y comunicaciones deben ser en **español**. El código, nombres de variables, mensajes de commit y documentación técnica del proyecto permanecen en inglés (son parte del código).
2. **Resumen final obligatorio:** Al terminar cada tarea o interacción, incluye **siempre** un resumen breve de lo último que realizaste, en este formato:

```
📋 **Resumen de lo realizado:**
- [acción concreta 1]
- [acción concreta 2]
- [estado final: completado / pendiente / error]
```

## RESUMEN GENERAL

ouroborOS es una distribución Linux inmutable basada en ArchLinux que usa systemd-boot, snapshots de Btrfs, y un instalador FSM en Python con operaciones en Bash. Rolling release, mínimo bloat, solo UEFI. Rich como backend TUI primario (whiptail como fallback). ISO live con SSH server habilitado.

**Repositorios:** `Arkh-Ur/ouroborOS-dev` (privado, dev) → `Arkh-Ur/ouroborOS` (público, releases). Tag push en dev dispara build + release en público.

**Releases:** v0.1.0 (2026-04-07), v0.2.0 (2026-04-10), v0.3.0 (2026-04-11).

**Estado actual:** Phase 3 completa — `our-snapshot`, `our-rollback`, `our-wifi`, `our-bluetooth`, `our-fido2`, `ouroboros-secureboot`, `ouroboros-firstboot`. Ver `docs/PHASE_3_PLAN.md`.

## ESTRUCTURA

```
ouroborOS/
├── src/
│   ├── installer/         # Python FSM installer + Bash ops (core app)
│   ├── scripts/           # Build, flash, dev-env shell scripts
│   └── ouroborOS-profile/ # archiso profile (airootfs, efiboot, packages)
├── templates/             # Default install config template for interactive mode
├── docs/                  # Architecture, build, installer, messages
│   └── architecture/      # overview, immutability, systemd, installer-phases,
│                          # secure-boot, systemd-homed, our-container
├── tests/                 # Docker-based test infra + shell scripts
├── agents/                # Agent role definitions (qa-tester, developer, etc.)
├── skills/                # Domain skill docs (systemd, archiso, filesystem, etc.)
├── .github/workflows/     # CI workflows (lint, test, build, opencode)
├── CLAUDE.md              # Canonical project constraints
├── IMPLEMENTATION_PLAN.md # Phased roadmap
└── README.md
```

## DÓNDE BUSCAR

| Tarea | Ubicación | Notas |
|-------|-----------|-------|
| Agregar estado/fase del instalador | `src/installer/state_machine.py` | FSM con checkpoints |
| Agregar pantalla TUI | `src/installer/tui.py` | Rich (primario) + whiptail (fallback) |
| Cambiar esquema de configuración | `src/installer/config.py` | Dataclasses + validación YAML |
| Agregar perfil de desktop | `src/installer/desktop_profiles.py` | PROFILE_PACKAGES, 5 perfiles |
| Agregar operación de disco/snapshot/config | `src/installer/ops/*.sh` | Librerías Bash invocadas via `_run_op()` |
| Agregar paquete al ISO | `src/ouroborOS-profile/packages.x86_64` | Justificar (bloat) |
| Cambiar entradas de boot | `src/ouroborOS-profile/efiboot/` | Archivos .conf de systemd-boot |
| Cambiar filesystem del ISO live | `src/ouroborOS-profile/airootfs/` | Copiado al ISO durante el build |
| Gestión de snapshots | `airootfs/usr/local/bin/our-snapshot` | list/create/delete/prune/info/boot-entries/scrub |
| Rollback de sistema | `airootfs/usr/local/bin/our-rollback` | now/promote/status/undo |
| WiFi interactivo | `airootfs/usr/local/bin/our-wifi` | list/connect/status/forget/show-password |
| Bluetooth | `airootfs/usr/local/bin/our-bluetooth` | list/pair/connect/disconnect/forget/status/on/off/le |
| FIDO2/WebAuthn/Passkey | `airootfs/usr/local/bin/our-fido2` | list/info/pin/cred/ble/qr-ready/reset |
| Secure Boot | `airootfs/usr/local/bin/ouroboros-secureboot` | setup/status/sign-all/verify/rotate-keys |
| First boot | `airootfs/usr/local/bin/ouroboros-firstboot` | mirrors/machine-id/timers (oneshot) |
| BlueZ config | `airootfs/etc/bluetooth/main.conf` | Experimental + LE tuning |
| Construir ISO | `src/scripts/build-iso.sh` | Wrapper de mkarchiso |
| Flashear USB | `src/scripts/flash-usb.sh` | Wrapper seguro de dd |
| Tests | `src/installer/tests/` | pytest, 323 tests, ≥93% coverage |
| Decisiones de arquitectura | `docs/architecture/` | overview, immutability, systemd, secure-boot, homed |

## MAPA DE CÓDIGO

| Símbolo | Tipo | Ubicación | Rol |
|---------|------|-----------|-----|
| `Installer` | clase | `src/installer/state_machine.py` | Orquestador FSM principal |
| `State` | enum | `src/installer/state_machine.py` | INIT→PREFLIGHT→LOCALE→USER→DESKTOP→**SECURE_BOOT**→PARTITION→FORMAT→INSTALL→CONFIGURE→SNAPSHOT→FINISH |
| `TUI` | clase | `src/installer/tui.py` | Wrapper de UI Rich (primario) + whiptail (fallback) |
| `InstallerConfig` | dataclass | `src/installer/config.py` | Modelo único de config (disco, locale, red, usuario, desktop, security) |
| `DesktopConfig` | dataclass | `src/installer/config.py` | Config de desktop profile y DM |
| `SecurityConfig` | dataclass | `src/installer/config.py` | `secure_boot`, `sbctl_include_ms_keys` |
| `NetworkConfig` | dataclass | `src/installer/config.py` | hostname, networkd, iwd, resolved, wifi, bluetooth |
| `PROFILE_PACKAGES` | dict | `src/installer/desktop_profiles.py` | Paquetes por perfil (minimal/hyprland/niri/gnome/kde) |
| `load_config` | func | `src/installer/config.py` | Cargador YAML→InstallerConfig |
| `load_config_from_url` | func | `src/installer/config.py` | Descarga config remota via URL (stdlib urllib) |
| `validate_config` | func | `src/installer/config.py` | Validación de esquema |
| `find_unattended_config` | func | `src/installer/config.py` | Descubre YAML en cmdline/USB/tmp |
| `main` | func | `src/installer/main.py` | Entry point CLI (--resume, --config, --validate-config) |
| `prepare_disk` | func | `src/installer/ops/disk.sh` | Particionado→formato→subvol→mount→fstab |
| configure steps | funcs | `src/installer/ops/configure.sh` | Chroot: locale, timezone, hostname, bootloader, network, users, immutable root, DM, homed, WiFi PSK, Bluetooth+FIDO2, firstboot |
| `our-pacman` | script | `airootfs/usr/local/bin/our-pacman` | Wrapper pacman: snapshot pre-update + remount rw + upgrade + remount ro + sbctl sign-all + boot-entries sync + prune |
| `our-snapshot` | script | `airootfs/usr/local/bin/our-snapshot` | CLI para snapshots Btrfs: list/create/delete/prune/info/boot-entries sync/scrub |
| `our-rollback` | script | `airootfs/usr/local/bin/our-rollback` | Rollback: now (bootctl set-oneshot), promote (swap atómico @), status, undo |
| `our-container` | script | `airootfs/usr/local/bin/our-container` | Wrapper systemd-nspawn: 17 comandos, --isolated (veth), --gui (wayland+GPU+audio) |
| `our-wifi` | script | `airootfs/usr/local/bin/our-wifi` | Wrapper iwctl: list/connect/status/forget/show-password |
| `our-bluetooth` | script | `airootfs/usr/local/bin/our-bluetooth` | Wrapper bluetoothctl + le subcommand (experimental, advmon) |
| `our-fido2` | script | `airootfs/usr/local/bin/our-fido2` | FIDO2/WebAuthn: USB + BLE GATT + Hybrid QR (CTAP2) |
| `ouroboros-secureboot` | script | `airootfs/usr/local/bin/ouroboros-secureboot` | sbctl wrapper: setup/status/sign-all/verify/rotate-keys |
| `ouroboros-firstboot` | script | `airootfs/usr/local/bin/ouroboros-firstboot` | Oneshot: mirrors + machine-id + timers. Guard: /var/lib/ouroborOS/firstboot.done |

## EJECUTABLES `our-*` Y `ouroboros-*`

| Ejecutable | Prefijo | Audiencia | Descripción |
|-----------|---------|-----------|-------------|
| `our-pacman` | `our-*` | Usuario | Atomic package manager wrapper |
| `our-snapshot` | `our-*` | Usuario | Btrfs snapshot manager |
| `our-rollback` | `our-*` | Usuario | System rollback en un comando |
| `our-container` | `our-*` | Usuario | systemd-nspawn container manager |
| `our-wifi` | `our-*` | Usuario | WiFi setup interactivo |
| `our-bluetooth` | `our-*` | Usuario | Bluetooth manager + BLE LE |
| `our-fido2` | `our-*` | Usuario | FIDO2/WebAuthn/Passkey manager |
| `ouroboros-secureboot` | `ouroboros-*` | Sistema | Secure Boot via sbctl |
| `ouroboros-firstboot` | `ouroboros-*` | Sistema | First boot oneshot service |

## CONVENCIONES

- **Python para lógica, Bash para operaciones.** Sin mezclar. `state_machine.py` orquesta; `ops/*.sh` ejecuta.
- **Conventional Commits:** `feat|fix|docs|build|installer|test|chore|refactor(scope): description`
- **Estrategia de branches:** `main` es la rama de trabajo. PR para mergear a `master` (releases).
- **Todos los shell scripts:** `set -euo pipefail` + pasar `shellcheck` (cero warnings).
- **Lint Python:** Ruff con E,W,F,I,UP,ANN001,ANN201,E722.
- **Cobertura mínima de tests:** ≥93% (323 tests, 14 skipped).
- **No GRUB, no NetworkManager, no /dev/sdX, no root rw en producción.** Ver ANTIPATRONES.

## ANTIPATRONES

| Prohibido | Motivo |
|-----------|--------|
| GRUB en código/configs | Solo systemd-boot; solo UEFI |
| NetworkManager | systemd-networkd + iwd |
| `/dev/sdX` en código runtime | Usar UUID en todo lugar |
| Root montado read-write en producción | Diseño inmutable; escrituras a /var, /etc, /tmp, /home |
| Commits directos a master | Estrategia: main→PR→master |
| Paquetes injustificados en el ISO | Mantener ISO liviano |
| Fallos de `shellcheck` | Todos los scripts deben pasar con cero warnings |
| `$AIROOTFS` en configure.sh | La variable no existe; usar rutas del live ISO directamente (ej. `/etc/bluetooth/main.conf`) |
| `/` al inicio de `rootflags=subvol=` | El kernel ignora el subvol si empieza con `/`; usar `subvol=@snapshots/...` |
| Contraseñas en texto plano en scripts/config | Hash via SHA-512 crypt; passphrase LUKS via stdin |
| `--fastest` en reflector | Usar `--sort score` (server-side, instantáneo) |

## SCHEMA YAML COMPLETO (v0.3.0)

```yaml
user:
  username: admin
  password: changeme           # Hasheado en load_config (SHA-512)
  shell: /bin/bash             # /bin/bash | /bin/zsh | /usr/bin/fish
  homed_storage: classic       # subvolume | luks | directory | classic
  groups: [wheel, audio, video, input]

network:
  hostname: ouroboros
  enable_networkd: true
  enable_iwd: true
  enable_resolved: true
  wifi:
    ssid: ""                   # Pre-configura iwd PSK en /var/lib/iwd/
    passphrase: ""             # Transitorio — no persistido en checkpoints
  bluetooth:
    enable: false              # Habilita bluetooth.service + instala libfido2

security:
  secure_boot: false           # true → sbctl setup durante install
  sbctl_include_ms_keys: false # true → sbctl enroll-keys -m

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
  profile: minimal             # minimal | hyprland | niri | gnome | kde
  dm: auto                     # auto | gdm | sddm | plm | none

extra_packages: []
post_install_action: reboot    # reboot | poweroff | none
```

## COMANDOS

```bash
# Setup (host Arch)
bash src/scripts/setup-dev-env.sh

# Construir ISO
sudo bash src/scripts/build-iso.sh --clean

# Flashear USB
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso

# Test en QEMU
qemu-system-x86_64 -enable-kvm -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso -boot d

# Tests unitarios
pytest src/installer/tests/ -v       # 323 tests, ≥93% coverage

# Suite CI completa (Docker)
docker-compose -f tests/docker-compose.yml run --rm full-suite
```

## NOTAS

- **FSM states (v0.3.0):** INIT → PREFLIGHT → LOCALE → USER → DESKTOP → SECURE_BOOT → PARTITION → FORMAT → INSTALL → CONFIGURE → SNAPSHOT → FINISH. SECURE_BOOT se omite si `security.secure_boot: false`.
- **Snapshots:** `/.snapshots/install/` es el baseline dorado (nunca purgado). Snapshots de pre-update: `YYYY-MM-DDTHHMMSS/`. Manuales: `YYYY-MM-DD_LABEL/`. Metadata JSON en `/.snapshots/.metadata/NAME.json`.
- **Boot entries:** `rootflags=subvol=@snapshots/...` — sin `/` inicial (requisito del kernel).
- **Secure Boot:** `sbctl` en `/var/lib/sbctl/` (subvolumen `@var`). Requiere firmware en Setup Mode. `our-pacman` corre `sbctl sign-all` post-update si Secure Boot está activo.
- **FIDO2/BLE:** BlueZ `--experimental` requerido para AdvertisingMonitor API (Chrome/Firefox CTAP2 hybrid QR). `our-fido2 qr-ready` verifica la stack completa. `71-fido2-ble.rules` maneja acceso a `/dev/hidraw*` para tokens BLE vía HOGP.
- **systemd-homed:** `homectl create` falla en QEMU (subvolumen Btrfs conflict). Fallback automático a classic `useradd`. Documentado en `docs/architecture/systemd-homed.md`.
- **WiFi PSK:** Escrito a `/var/lib/iwd/SSID.psk` (chmod 600, dir 700). SSIDs con caracteres especiales usan `=HEXSSID.psk`. La passphrase se limpia del env inmediatamente post-escritura.
- **ouroboros-firstboot:** Guard file `/var/lib/ouroborOS/firstboot.done`. Corre una sola vez. Activa `our-snapshot-prune.timer` y `btrfs-scrub@-.timer`.
- **Password plaintext lifecycle:** `UserConfig.password_plaintext` es transitorio. Se pasa a `configure.sh` como `USER_PASSWORD`, se limpia inmediatamente después. Nunca persistido en checkpoints.
- **E2E tests QEMU:** `setsid` para lanzar QEMU. `fuser -k 2222/tcp` antes de relanzar. Disco qcow2 en `/home/` (NO `/tmp/`). `-device e1000` (virtio-net cuelga). `-display none -vga virtio` (nunca `-nographic`).
- **Dual-repo:** `ouroborOS-dev` (privado) para desarrollo, `ouroborOS` (público) para releases. Tag push dispara build.yml.
