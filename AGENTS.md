# BASE DE CONOCIMIENTO DEL PROYECTO

**Generado:** 2026-04-08
**Commit:** a5c318d (uncommitted changes)
**Branch:** dev

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

**Release v0.1.0:** Publicado el 2026-04-07 con ISO (1.3GB) + SHA256SUMS. Fases 1-5 completadas.

**Estado actual:** Phase 2 completa — namespace `our-*` (`our-pac`, `our-box`), desktop profiles, systemd-homed default-on. Ver `docs/PHASE_2_PLAN.md`. Phase 3 pendiente.

## ESTRUCTURA

```
ouroborOS/
├── src/
│   ├── installer/         # Python FSM installer + Bash ops (core app)
│   ├── scripts/           # Build, flash, dev-env shell scripts
│   └── ouroborOS-profile/ # archiso profile (airootfs, efiboot, packages)
├── templates/             # Default install config template for interactive mode
├── docs/                  # Architecture, build, installer, messages
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
| Agregar estado/fase del instalador | `src/installer/state_machine.py` | FSM con checkpoints, ver installer/AGENTS.md |
| Agregar pantalla TUI | `src/installer/tui.py` | Wrapper de UI Rich (primario) + whiptail (fallback) |
| Cambiar esquema de configuración | `src/installer/config.py` | Dataclasses + validación YAML |
| Agregar perfil de desktop | `src/installer/desktop_profiles.py` | PROFILE_PACKAGES, PROFILE_DM, 5 perfiles |
| Cambiar DM seleccionable | `src/installer/desktop_profiles.py` | VALID_DMS, _DM_PACKAGE, _DM_SERVICE, dm_package(), dm_service(), resolve_dm() |
| Agregar operación de disco/snapshot/config | `src/installer/ops/*.sh` | Librerías Bash invocadas via `_run_op()` |
| Agregar paquete al ISO | `src/ouroborOS-profile/packages.x86_64` | Debe justificarse (preocupación de bloat) |
| Cambiar entradas de boot | `src/ouroborOS-profile/efiboot/` | Archivos .conf de systemd-boot |
| Cambiar filesystem del ISO live | `src/ouroborOS-profile/airootfs/` | Copiado al ISO durante el build |
| Construir ISO | `src/scripts/build-iso.sh` | Wrapper de mkarchiso |
| Flashear USB | `src/scripts/flash-usb.sh` | Wrapper seguro de dd |
| Entorno de desarrollo | `src/scripts/setup-dev-env.sh` | Instala deps de build en host Arch |
| Agregar check de CI | `.github/workflows/` | lint.yml, test.yml, build.yml, opencode.yml |
| Agregar test | `src/installer/tests/` o `tests/scripts/` | pytest o scripts shell |
| Decisiones de arquitectura | `docs/architecture/` | overview, immutability, systemd, installer-phases |
| Config default interactiva | `templates/install-config.yaml` | Template YAML con contraseña plaintext, auto-hasseada |
| Plan Phase 2 | `docs/PHASE_2_PLAN.md` | our-pac, our-box, desktop profiles, homed |
| Documentación our-box | `docs/our-box.md` | Guía de usuario completa (651 líneas) |
| Tests E2E our-box | `tests/scripts/e2e-our-box.sh` | 15 fases, 1382 líneas, QEMU+SSH |
| Tests unitarios our-box | `tests/our_box/` | pytest unit tests |
| Tests integración our-box | `src/installer/tests/test_our_box_integration.py` | pytest integration tests |
| CI build + release | `.github/workflows/build.yml` | Tag push → ISO build → release en repo público |

## MAPA DE CÓDIGO

| Símbolo | Tipo | Ubicación | Rol |
|---------|------|-----------|-----|
| `Installer` | clase | `src/installer/state_machine.py` | Orquestador FSM principal |
| `State` | enum | `src/installer/state_machine.py` | INIT→PREFLIGHT→LOCALE→USER→DESKTOP→PARTITION→FORMAT→INSTALL→CONFIGURE→SNAPSHOT→FINISH |
| `TUI` | clase | `src/installer/tui.py` | Wrapper de UI Rich (primario) + whiptail (fallback) |
| `InstallerConfig` | dataclass | `src/installer/config.py` | Modelo único de config (disco, locale, red, usuario, desktop) |
| `DesktopConfig` | dataclass | `src/installer/config.py` | Config de desktop profile y homed storage |
| `PROFILE_PACKAGES` | dict | `src/installer/desktop_profiles.py` | Paquetes por perfil (minimal/hyprland/niri/gnome/kde) |
| `PROFILE_DM` | dict | `src/installer/desktop_profiles.py` | Display manager por perfil (gdm, sddm, o ninguno) |
| `VALID_DMS` | frozenset | `src/installer/desktop_profiles.py` | DMs permitidos: gdm, sddm, plm, none |
| `load_config` | func | `src/installer/config.py` | Cargador YAML→InstallerConfig |
| `load_config_from_url` | func | `src/installer/config.py` | Descarga config remota via URL (stdlib urllib) |
| `validate_config` | func | `src/installer/config.py` | Validación de esquema (ruta disco, timezone, hostname, username) |
| `find_unattended_config` | func | `src/installer/config.py` | Descubre YAML en cmdline/USB/tmp |
| `show_remote_config_prompt` | method | `src/installer/tui.py` | Prompt para URL de config remota (Rich + whiptail) |
| `templates/install-config.yaml` | file | `templates/install-config.yaml` | Config default YAML con contraseña plaintext |
| `main` | func | `src/installer/main.py` | Entry point CLI (--resume, --config, --validate-config) |
| `prepare_disk` | func | `src/installer/ops/disk.sh` | Particionado→formato→subvol→mount→fstab completo |
| `create_install_snapshot` | func | `src/installer/ops/snapshot.sh` | Snapshot baseline de Btrfs |
| configure steps | funcs | `src/installer/ops/configure.sh` | Chroot: locale, timezone, hostname, bootloader, network, users, immutable root, DM enable, homed |
| `our-pac` | script | `src/ouroborOS-profile/airootfs/usr/local/bin/our-pac` | Wrapper de pacman con snapshot + remount rw (antes `ouroboros-upgrade`, symlink de compat) |
| `our-box` | script | `src/ouroborOS-profile/airootfs/usr/local/bin/our-box` | Wrapper systemd-nspawn: create/enter/start/stop/list/remove, snapshot, storage mount, image pull, monitor, diagnose, stats, logs, check (17 comandos, 1786 líneas) |

## CONVENCIONES

- **Python para lógica, Bash para operaciones.** Sin mezclar. `state_machine.py` orquesta; `ops/*.sh` ejecuta. Rich como backend TUI primario, whiptail como fallback.
- **Conventional Commits:** `feat|fix|docs|build|installer|test|chore|refactor)(scope): description`
- **Estrategia de branches:** `dev` o `feature/*` solamente. PR para mergear. Nunca push directo a `master`.
- **Todos los shell scripts:** `set -euo pipefail` + pasar `shellcheck -S style` (cero warnings).
- **Lint Python:** Ruff con E,W,F,I,UP,ANN001,ANN201,E722.
- **Cobertura mínima de tests:** 93% (forzado por `tests/scripts/run-pytest.sh`, mínimo 70%).
- **No GRUB, no NetworkManager, no /dev/sdX, no root rw en producción.** Ver ANTIPATRONES.

## ANTIPATRONES

| Prohibido | Motivo |
|-----------|--------|
| GRUB en código/configs | Solo systemd-boot; solo UEFI |
| NetworkManager | systemd-networkd + iwd |
| `/dev/sdX` en código runtime | Usar UUID en todo lugar |
| Root montado read-write en producción | Diseño inmutable; escrituras a /var, /etc, /tmp, /home |
| Commits directos a master | Estrategia: dev→PR→master |
| Paquetes injustificados en el ISO | Mantener ISO liviano |
| Fallos de `shellcheck` | Todos los scripts deben pasar con cero warnings |
| TODO en código enviado | Trackear apropiadamente o implementar |
| PARTUUID en fstab para root | Usar UUID= para el subvolumen root |
| archisolabel hardcodeado en boot entries | Usar template `%ARCHISO_UUID%` + `archisosearchuuid=` (archiso v87+) |
| Contraseñas en texto plano en scripts/config | Hash via SHA-512 crypt; passphrase LUKS via stdin |
| Lógica Python en ops Bash o viceversa | Separación estricta de responsabilidades |
| URLs de mirrors hardcodeadas en pacman.conf | Parametrizar o configurar |
| Rich unavailable en el ISO live sin instalarlo | Instalar python-rich en packages.x86_64 del perfil archiso |

## ESTILOS ÚNICOS

- **FSM con checkpoints:** Estado del instalador persistido por fase en `/tmp/ouroborOS-checkpoints/`; soporta reanudación tras interrupciones.
- **Límite Python↔Bash:** `state_machine._run_op()` invoca `ops/*.sh` con flags `--action` y `--target`; `configure.sh` es impulsado por variables de entorno.
- **Layout del perfil archiso:** `airootfs/` refleja el filesystem del ISO live; `efiboot/` contiene las entradas de systemd-boot; `profiledef.sh` define los metadatos de build.
- **Infra de tests basada en Docker:** Todos los tests de CI corren en un contenedor Arch Linux construido desde `tests/Dockerfile`.
- **TUI Rich como backend primario:** Rich como backend primario con whiptail como fallback; barra de progreso inline + progreso global de instalación.
- **Templates de configuración:** `templates/install-config.yaml` sirve como default interactivo; el instalador lo copia/modifica.

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
pytest src/installer/tests/ -v

# Suite CI completa (Docker)
docker-compose -f tests/docker-compose.yml run --rm full-suite

# Suites de test individuales
docker-compose -f tests/docker-compose.yml run --rm shellcheck-suite
docker-compose -f tests/docker-compose.yml run --rm pytest-suite
docker-compose -f tests/docker-compose.yml run --rm smoke-test

# Lint
tests/scripts/lint-python.sh
tests/scripts/test-shellcheck.sh
```

## NOTAS

- No hay `pyproject.toml`, `pytest.ini`, `conftest.py`, ni `Makefile` — la config de tests está en `tests/scripts/`.
- `out/` contiene artefactos de build (ISO), gitignored.
- `IMPLEMENTATION_PLAN.md` trackea progreso de fases; actualmente en Phase 3 completa.
- TUI usa Rich como backend primario; whiptail como fallback si Rich no está disponible.
- `templates/install-config.yaml` es la config default para instalación interactiva.
- El ISO live tiene SSH server habilitado con generación de host keys al boot.
- `skills/` y `agents/` son bases de conocimiento no-código para Claude Code; no se ejecutan.
- `skills/qemu-e2e-test.md` — plan completo de test E2E: build ISO → install en QEMU (desatendido) → verificar sistema instalado via SSH + serial log.
- Dual-repo: `ouroborOS-dev` (privado) para desarrollo, `ouroborOS` (público) para releases. Tag push en dev dispara build.yml que construye ISO y publica release en el repo público.
- `our-pac` reemplaza a `ouroboros-upgrade` (symlink de compatibilidad por un release cycle). `our-box` es el wrapper de systemd-nspawn con 17 comandos (create/enter/start/stop/list/remove, snapshot create/list/restore, storage mount/umount, cleanup, disk-usage, image pull/list/remove, monitor, diagnose, stats, logs, check). Documentación en `docs/our-box.md`. Tests E2E en `tests/scripts/e2e-our-box.sh` (15 fases, 1382 líneas). Tests unitarios en `tests/our_box/`. Tests de integración en `src/installer/tests/test_our_box_integration.py`.
- `desktop_profiles.py` define 5 perfiles: minimal, hyprland, niri, gnome, kde. GNOME usa gdm, KDE usa plm (plasma-login-manager), hyprland/niri usan sddm, minimal arranca desde TTY. DM desacoplado del perfil con 4 opciones (gdm, sddm, plm, none) y selector visual ↑↓.
- La FSM ahora tiene estados USER y DESKTOP antes de PARTITION — todas las decisiones humanas se toman antes de cualquier operación destructiva.
- pacman PreTransaction hooks NO funcionan para remount rw (pacman verifica escritura antes de ejecutar hooks). Por eso existe el wrapper `our-pac`.
- **homed-migrate.sh** es no-interactivo: usa JSON identity file (`--identity=`) para `homectl create` y D-Bus `ActivateHome` para activate. El password plaintext se pasa via `HOMED_PASSWORD` env var, se guarda en `/etc/ouroboros/homed-migration.conf` (chmod 600), y se elimina post-migration.
- **Remote config URL:** Si no hay config local, el INIT state pregunta si el usuario quiere proveer una URL (ej: GitHub raw) para descargar un config remoto. Usa `urllib.request` (stdlib). Si falla, cae a modo interactivo.
- **Reflector mirrors:** Usa `--sort score` (server-side, instantáneo) en vez de `--fastest` (benchmark local, lento). Fallback worldwide si regional falla.
- **E2E tests QEMU:** Siempre usar `setsid` para lanzar QEMU (sobrevive tool timeouts). Siempre `fuser -k 2222/tcp` antes de relanzar. Disco qcow2 en `/home/` (NO `/tmp/`, es tmpfs). `ps aux | grep qemu` para encontrar el PID real (`$!` da el PID incorrecto con setsid).
- **E2E known issue:** `homectl create --identity=JSON` falla en QEMU con error genérico (en investigación). SSH en sistema instalado solo escucha en AF_UNIX socket por default (necesita investigación de networkd DHCP en SLIRP).
- **Password plaintext lifecycle:** `UserConfig.password_plaintext` es transitorio — se llena en load_config o TUI, se pasa a configure.sh como `USER_PASSWORD`, y se limpia en state_machine.py inmediatamente después de que configure.sh termina. Nunca se persiste en checkpoints.
