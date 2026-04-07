# BASE DE CONOCIMIENTO DEL PROYECTO

**Generado:** 2026-04-04
**Commit:** de2950d
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
├── .github/workflows/     # CI workflows (lint, test, code-review, opencode)
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
| Agregar operación de disco/snapshot/config | `src/installer/ops/*.sh` | Librerías Bash invocadas via `_run_op()` |
| Agregar paquete al ISO | `src/ouroborOS-profile/packages.x86_64` | Debe justificarse (preocupación de bloat) |
| Cambiar entradas de boot | `src/ouroborOS-profile/efiboot/` | Archivos .conf de systemd-boot |
| Cambiar filesystem del ISO live | `src/ouroborOS-profile/airootfs/` | Copiado al ISO durante el build |
| Construir ISO | `src/scripts/build-iso.sh` | Wrapper de mkarchiso |
| Flashear USB | `src/scripts/flash-usb.sh` | Wrapper seguro de dd |
| Entorno de desarrollo | `src/scripts/setup-dev-env.sh` | Instala deps de build en host Arch |
| Agregar check de CI | `.github/workflows/` | lint.yml, test.yml, code-review.yml, opencode.yml |
| Agregar test | `src/installer/tests/` o `tests/scripts/` | pytest o scripts shell |
| Decisiones de arquitectura | `docs/architecture/` | overview, immutability, systemd, installer-phases |
| Config default interactiva | `templates/install-config.yaml` | Template YAML con contraseña plaintext, auto-hasseada |
| CI workflows | `.github/workflows/` | 4 workflows: lint, test, code-review, opencode |

## MAPA DE CÓDIGO

| Símbolo | Tipo | Ubicación | Rol |
|---------|------|-----------|-----|
| `Installer` | clase | `src/installer/state_machine.py` | Orquestador FSM principal |
| `State` | enum | `src/installer/state_machine.py` | INIT→PREFLIGHT→LOCALE→PARTITION→FORMAT→INSTALL→CONFIGURE→SNAPSHOT→FINISH |
| `TUI` | clase | `src/installer/tui.py` | Wrapper de UI Rich (primario) + whiptail (fallback) |
| `InstallerConfig` | dataclass | `src/installer/config.py` | Modelo único de config (disco, locale, red, usuario) |
| `load_config` | func | `src/installer/config.py` | Cargador YAML→InstallerConfig |
| `validate_config` | func | `src/installer/config.py` | Validación de esquema (ruta disco, timezone, hostname, username) |
| `find_unattended_config` | func | `src/installer/config.py` | Descubre YAML en cmdline/USB/tmp |
| `templates/install-config.yaml` | file | `templates/install-config.yaml` | Config default YAML con contraseña plaintext |
| `main` | func | `src/installer/main.py` | Entry point CLI (--resume, --config, --validate-config) |
| `prepare_disk` | func | `src/installer/ops/disk.sh` | Particionado→formato→subvol→mount→fstab completo |
| `create_install_snapshot` | func | `src/installer/ops/snapshot.sh` | Snapshot baseline de Btrfs |
| configure steps | funcs | `src/installer/ops/configure.sh` | Chroot: locale, timezone, hostname, bootloader, network, users, immutable root |

## CONVENCIONES

- **Python para lógica, Bash para operaciones.** Sin mezclar. `state_machine.py` orquesta; `ops/*.sh` ejecuta. Rich como backend TUI primario, whiptail como fallback.
- **Conventional Commits:** `feat|fix|docs|build|installer|test|chore|refactor)(scope): description`
- **Estrategia de branches:** `dev` o `feature/*` solamente. PR para mergear. Nunca push directo a `master`.
- **Todos los shell scripts:** `set -euo pipefail` + pasar `shellcheck -S style` (cero warnings).
- **Lint Python:** Ruff con E,W,F,I,UP,ANN001,ANN201,E722.
- **Cobertura mínima de tests:** 70% (forzado por `tests/scripts/run-pytest.sh`).
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
