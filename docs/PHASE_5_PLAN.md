# Phase 5 Plan — Sistema Declarativo, Multi-Usuario y OTA

**Versión:** post-v0.4.12
**Fecha:** 2026-04-17
**Branch:** dev

> **v0.4.12 released 2026-04-17.** Phase 4 complete. This document defines Phase 5.

---

## Arquitectura central

Phase 5 gira alrededor de un **estado declarativo del sistema** (`system.yaml`) que actúa como
fuente de verdad. Todo lo demás — multi-usuario, OTA, rebase, reinstall, health — deriva de esto.

```
system.yaml  →  define QUÉ debe ser el sistema
OTA canal    →  entrega NUEVAS definiciones desde GitHub
rebase       →  aplica el manifiesto al sistema actual
.snapshot.yaml → registra el estado exacto en cada snapshot
reinstall    →  reconstruye @ desde manifiesto, preserva @home
health       →  verifica que el estado real = manifiesto
```

---

## Trazabilidad de milestones

| # | Feature | Estado | Tag |
|---|---------|--------|-----|
| 5.1 | `users: list[UserConfig]` — multi-usuario en installer | ✅ | v0.5.4 |
| 5.2 | homed directory (default multi-user) | ✅ | v0.5.4 |
| 5.3 | homed luks (encriptado per-user, opcional) | ✅ | v0.5.5 |
| 5.4 | TPM2 enroll para homed luks | ✅ | v0.5.5 |
| 5.5 | FIDO2 enroll para homed luks | ✅ | v0.5.5 |
| 5.6 | `our-pac` auto-rollback si update rompe boot | ✅ | v0.5.6 |
| 5.7 | `ouroboros-update` daemon (notifica updates) | ✅ | v0.5.2 |
| 5.8 | `our-snapshot diff A B` (btrfs-diff) | ✅ | v0.5.6 |
| 5.9 | `ouroboros-rebase` — rebasar baseline | ✅ | v0.5.1 |
| 5.10 | ISO signing GPG | ✅ | v0.5.7 |
| 5.11 | `our-bluetooth` hook en install | ✅ | v0.5.7 |
| 5.12 | `ouroboros-health` + `--doctor` | ✅ | v0.5.3 |
| 5.13 | Actualizar `user-guide.md` | ✅ | v0.5.8 |
| 5.14 | `docs/architecture/our-aur.md` + `our-flat.md` | ✅ | v0.5.8 |
| 5.15 | `docs/architecture/snapshot-system.md` | ✅ | v0.5.8 |
| 5.16 | `docs/PHASE_5_PLAN.md` | ✅ | v0.5.8 |
| 5.17 | GUI Installer | ❌ Phase 6+ | — |
| 5.18 | OTA casync image-based | ❌ Phase 6+ | — |
| 5.19 | ARM / aarch64 | ❌ Sin hardware | — |
| 5.20 | `systemd-repart` | ❌ Costo/beneficio bajo | — |
| — | `system.yaml` manifiesto declarativo | ✅ NUEVO | v0.5.0 |
| — | `.snapshot.yaml` en cada snapshot | ✅ NUEVO | v0.5.1 |
| — | `channels/stable.yaml` en repo + CI | ✅ NUEVO | v0.5.2 |
| — | `ouroboros-reinstall` | ✅ NUEVO | v0.5.3 |
| — | `ouroboros-health --json` | ✅ NUEVO | v0.5.3 |

---

## Regla de oro — Gate por tag

**No se avanza al siguiente milestone hasta que TODO esto esté verde:**

- [ ] `pytest` — 0 failures
- [ ] `ruff check --select "E,W,F,I,UP,ANN001,ANN201,E722" --line-length 120` — limpio
- [ ] `shellcheck` — 0 warnings en scripts modificados
- [ ] QEMU E2E local — install + boot + SSH verify + checks del milestone (`/qemu-e2e-test`)
- [ ] GitHub Actions dev: **Lint** ✓ + **Build ISO** ✓
- [ ] Release público: ISO + SHA256 ✓

---

## Tabla de versiones

| Tag | Milestone | Features principales | Depende de |
|-----|-----------|---------------------|------------|
| v0.5.0 | `system.yaml` | Manifiesto generado en install, our-pac actualiza user_packages | — |
| v0.5.1 | `.snapshot.yaml` + `ouroboros-rebase` | Estado en cada snapshot, rebase aplica manifiesto | v0.5.0 |
| v0.5.2 | Canal OTA + `ouroboros-update` | `channels/stable.yaml` en repo, timer diario | v0.5.1 |
| v0.5.3 | `ouroboros-reinstall` + `ouroboros-health` | Reinstall preserva @home, health --doctor --json | v0.5.0 |
| v0.5.4 | Multi-usuario `homed directory` | `users: list`, TUI multi-user, directory default | v0.5.0 |
| v0.5.5 | `homed luks` + TPM2/FIDO2 | Homes encriptados, enroll per-usuario | v0.5.4 |
| v0.5.6 | Auto-rollback + `our-snapshot diff` | Rollback en boot fallido, diff entre snapshots | v0.5.1 |
| v0.5.7 | GPG signing + bluetooth hook | ISO firmado en CI, bluetooth en install | — |
| v0.5.8 | Documentación | 6 nuevos docs de arquitectura, user-guide actualizado | todos |

---

## v0.5.0 — `system.yaml`: Manifiesto Declarativo

**Objetivo:** El installer genera `/etc/ouroboros/system.yaml` al finalizar.

### Schema

```yaml
version: 0.5.0
channel: stable
channel_url: https://raw.githubusercontent.com/Arkh-Ur/ouroborOS/main/channels/stable.yaml
installed: 2026-07-01T14:32:00Z
system:
  hostname: ouroboros
  locale: en_US.UTF-8
  timezone: America/Santiago
  desktop:
    profile: minimal
    dm: none
  shell: bash
base_packages:
  - base
  - linux-zen
  - linux-firmware
  - systemd
  - btrfs-progs
  # ... todos los paquetes de pacstrap
user_packages: []     # actualizado por our-pac -S/-R
aur_packages: []      # actualizado por our-aur
users:
  - username: admin
    real_name: ""
    groups: [wheel, audio, video, input]
    shell: bash
    homed_storage: classic
security:
  secure_boot: false
  tpm2_unlock: false
  fido2_pam: false
disk:
  device: /dev/vda
  use_luks: false
  btrfs_label: ouroborOS
  swap_type: zram
```

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `src/installer/config.py` | `InstallerConfig.to_system_yaml() -> dict` |
| `src/installer/state_machine.py` | En `_handle_finish()`: generar y copiar system.yaml al target |
| `src/installer/ops/configure.sh` | Instalar `/etc/ouroboros/system.yaml` en target |
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-pac` | Actualizar `user_packages` al instalar/remover |

### Criterios de aceptación

- [x] `/etc/ouroboros/system.yaml` existe post-install, parseable como YAML
- [x] `base_packages` contiene todos los paquetes pacstrapeados
- [x] `users:` lista el usuario creado con su configuración
- [x] `our-pac -S vim` → agrega `vim` a `user_packages`
- [x] `our-pac -R vim` → elimina `vim` de `user_packages`
- [x] Tests: `test_system_yaml.py`

---

## v0.5.1 — `.snapshot.yaml` + `ouroboros-rebase`

**Objetivo:** Cada snapshot captura el estado del sistema. `ouroboros-rebase` aplica manifiestos.

### `.snapshot.yaml`

```yaml
# /.snapshots/install/.snapshot.yaml
snapshot: install
created: 2026-07-01T14:32:00Z
type: install        # install | pre-update | manual | rebase | boot
system_version: 0.5.0
system_yaml_hash: sha256:abc123...
packages_count: 142
```

### `ouroboros-rebase`

```
ouroboros-rebase [--from-channel] [--dry-run]

1. Lee /etc/ouroboros/system.yaml
2. Si --from-channel: descarga canal remoto
3. Compara packages instalados vs manifiesto
4. --dry-run: muestra diff sin aplicar
5. Crea @snapshots/pre-rebase-T (type: pre-update)
6. Aplica: pacman -S/R según diferencias
7. Crea @snapshots/post-rebase-T (type: rebase)
```

### Archivos a crear/modificar

| Archivo | Cambio |
|---------|--------|
| `src/ouroborOS-profile/airootfs/usr/local/lib/ouroboros/snapshot.sh` | `create_snapshot()` genera `.snapshot.yaml` |
| `src/ouroborOS-profile/airootfs/usr/local/bin/our-snapshot` | `info <name>` muestra `.snapshot.yaml` |
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-rebase` | NUEVO |
| `src/installer/ops/configure.sh` | Instalar `ouroboros-rebase` |

---

## v0.5.2 — Canal OTA + `ouroboros-update` daemon

**Objetivo:** Verificación diaria de updates. Canal publicado en GitHub con cada release.

### Canal

```yaml
# channels/stable.yaml
version: 0.5.2
released: 2026-07-15T00:00:00Z
min_compatible_version: 0.5.0
changelog_url: https://github.com/Arkh-Ur/ouroborOS/releases/tag/v0.5.2
base_packages:
  linux-zen: "6.20.1.zen1-1"
  systemd: "257.4-1"
```

### Archivos a crear/modificar

| Archivo | Cambio |
|---------|--------|
| `channels/stable.yaml` | NUEVO — generado por CI con cada release tag |
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-update` | NUEVO |
| `src/ouroborOS-profile/airootfs/etc/systemd/system/ouroboros-update.{service,timer}` | NUEVO |
| `.github/workflows/build.yml` | Publicar `channels/stable.yaml` en release job |
| `src/installer/ops/configure.sh` | Habilitar `ouroboros-update.timer` |

---

## v0.5.3 — `ouroboros-reinstall` + `ouroboros-health`

### `ouroboros-reinstall` (desde live ISO)

```
ouroboros-reinstall [--keep-home] [--keep-config] [--from-snapshot NAME] --disk /dev/vda

1. Detecta instalación existente
2. Lee .snapshot.yaml del snapshot más reciente
3. Pregunta qué preservar: @home, @etc, @var
4. btrfs subvolume delete @ (solo @)
5. pacstrap con base_packages del snapshot.yaml
6. configure.sh con datos del system.yaml
7. @home intacto
```

### `ouroboros-health`

```
ouroboros-health [--doctor] [--json]

Checks: root RO, failed units, machine-id, system.yaml válido,
        Btrfs pool usage, snapshot count, boot entries huérfanas,
        SMART, Secure Boot, TPM2, updates disponibles (pacman+AUR+Flatpak+OTA)

--doctor: ofrece corregir cada problema detectado
--json:   output machine-readable
```

### Archivos a crear

| Archivo | Cambio |
|---------|--------|
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-health` | NUEVO |
| `src/ouroborOS-profile/airootfs/usr/local/bin/ouroboros-reinstall` | NUEVO (live ISO only) |

---

## v0.5.4 — Multi-usuario: `users: list[UserConfig]`

**Objetivo:** N usuarios en el installer. `homed_storage: directory` como nuevo default.

### Cambios principales

- `InstallerConfig.users: list[UserConfig]` (backwards compat: `user:` singular → lista de 1)
- `UserConfig.homed_storage` default cambia `classic` → `directory`
- `UserConfig.real_name: str = ""` — campo nuevo
- TUI: pantalla "Usuarios" con botón "Agregar usuario"
- `configure.sh`: loop sobre `USERS_JSON`, usa `homectl` o `useradd` según storage
- **QEMU E2E:** siempre `homed_storage: classic` (bug homectl+Btrfs en QEMU)

### E2E YAML: `tests/qemu/phase5-e2e.yaml`

```yaml
users:
  - username: admin
    password: changeme
    groups: [wheel, audio, video, input]
    shell: bash
    homed_storage: classic     # QEMU constraint
    real_name: "Administrator"
  - username: testuser
    password: testpass
    groups: [audio, video]
    shell: bash
    homed_storage: classic     # QEMU constraint
    real_name: "Test User"
```

---

## v0.5.5 — `homed luks` + TPM2/FIDO2 enroll

- `homed_storage: luks` → home encriptado como imagen LUKS
- Si `tpm2_enroll: true` + TPM2 disponible → `homectl update --tpm2-device=auto`
- Si `fido2_enroll: true` + FIDO2 disponible → `homectl update --fido2-device=auto`
- Fallback automático a `directory` si `luks` falla
- E2E QEMU: `classic` (bug conocido)

---

## v0.5.6 — Auto-rollback + `our-snapshot diff`

### Auto-rollback

```
our-pac -Syu
  → @snapshots/pre-update-T (.snapshot.yaml, type: pre-update)
  → escribe /var/lib/ouroborOS/pending-verification

ouroboros-verify-update.service (After=multi-user.target):
  → si pending-verification existe:
    → espera 60s
    → si 0 failed units: elimina flag (update OK)
    → si failed units: ouroboros-rollback → reboot
```

### `our-snapshot diff`

```bash
our-snapshot diff <SNAP_A> <SNAP_B>
# Usa btrfs send --no-data para listar archivos modificados
# Output: Added / Modified / Deleted por archivo
```

---

## v0.5.7 — GPG signing + `our-bluetooth` install hook

- `build-iso.sh`: firma ISO si `GPG_KEY_ID` en environment
- CI: secrets `GPG_KEY_ID` + `GPG_PRIVATE_KEY` → ISO firmado en releases
- `configure.sh`: `configure_bluetooth()` — habilita `bluetooth.service` si `BLUETOOTH_ENABLE=1`
- `our-bluetooth` CLI ya existe (Phase 3), solo falta el hook de configure

---

## v0.5.8 — Documentación

| Archivo | Acción |
|---------|--------|
| `docs/user-guide.md` | Actualizar — quitar limitaciones resueltas, agregar Phase 5 features |
| `docs/architecture/systemd-integration.md` | Actualizar estado (systemd-repart: still deferred) |
| `docs/architecture/our-aur.md` | NUEVO |
| `docs/architecture/snapshot-system.md` | NUEVO |
| `docs/architecture/declarative-system.md` | NUEVO |
| `docs/architecture/multi-user.md` | NUEVO |

---

## Out of Scope (Phase 6+)

| Feature | Razón |
|---------|-------|
| GUI Installer (Electron/Qt) | Largo plazo — TUI Rich es suficiente |
| OTA casync image-based | Requiere infraestructura de build de imágenes |
| ARM / aarch64 | Sin hardware para validar |
| systemd-repart | Costo/beneficio bajo — sgdisk funciona bien, Btrfs subvolumes no los maneja |

---

## Criterios de Aceptación Phase 5

- [ ] `system.yaml` generado en install, actualizado por our-pac
- [ ] `.snapshot.yaml` en cada snapshot con metadata completa
- [ ] `ouroboros-rebase --from-channel` aplica canal OTA
- [ ] `ouroboros-update.timer` detecta nuevas versiones diariamente
- [ ] `ouroboros-reinstall` reconstruye @ preservando @home
- [ ] `ouroboros-health --doctor` detecta y corrige problemas
- [ ] N usuarios configurables en install (homed directory/luks/classic)
- [ ] Auto-rollback funciona si update rompe boot
- [ ] `our-snapshot diff A B` lista cambios entre snapshots
- [ ] ISO firmado con GPG en releases
- [ ] bluetooth hook en install funciona
- [ ] Todos los docs actualizados
- [ ] 555+ tests pasando, ruff + shellcheck limpios
- [ ] Cada tag v0.5.X: QEMU E2E ✓ + CI dev ✓ + release público ✓
