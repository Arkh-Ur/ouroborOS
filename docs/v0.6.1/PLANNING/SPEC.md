# SPEC — ouroborOS v0.6.1: Gestor de Dotfiles `our-dots`

**Versión:** 1.1  
**Fecha:** 2026-06-07  
**Autor:** ouroborOS dev team  
**Estado:** Borrador  
**Referencias:** PRD v1.1 (2026-06-07) · TRD v1.2 (2026-06-07)

> **Changelog v1.1:** C-01 `set -o pipefail` en header (§5.0). C-02 illogical-impulse/ambxst son git-only (§4.5, §4.1). C-03 handler FSM incluye auto-corrección de canal (§6.1). I-01 `cmd_search` expandido (§5.5). I-02 `repo_dir` en ruta persistente (§5.6). I-03 `sysyaml_append_repo` contrato upsert (§5.7). I-05 licencia noctalia `null` (§4.1). I-06 validación `post_remove` como path (§9.1). M-01 log en `-R` (§5.4). M-03 `--noconfirm` en `-R` (§3.2, §5.4). M-04 clarificación argumento `-S` (§3.2). M-05 plan migración `dots_profiles.py` (§11.4).

> **Nota de autoridad:** El schema de manifests YAML documentado en la §4 de esta especificación es el schema canónico de `our-dots`. En caso de discrepancia con el PRD §6.8, prevalece el TRD §2.3 (y por extensión, esta sección). Las demás secciones son consistentes con PRD v1.1 y TRD v1.2.

---

## Tabla de Contenidos

1. [Alcance](#1-alcance)
2. [Contexto y Arquitectura](#2-contexto-y-arquitectura)
3. [Interfaces CLI](#3-interfaces-cli)
4. [Formato de Datos](#4-formato-de-datos)
5. [Algoritmos por Subcomando](#5-algoritmos-por-subcomando)
6. [Máquinas de Estado](#6-máquinas-de-estado)
7. [Contratos: Pre/Post Condiciones](#7-contratos-prepost-condiciones)
8. [Manejo de Errores](#8-manejo-de-errores)
9. [Validaciones](#9-validaciones)
10. [Diagramas de Secuencia](#10-diagramas-de-secuencia)
11. [Configuración y Variables de Entorno](#11-configuración-y-variables-de-entorno)
12. [Logging](#12-logging)
13. [Seguridad](#13-seguridad)
14. [Glosario](#14-glosario)
15. [Referencias Cruzadas](#15-referencias-cruzadas)

---

## 1. Alcance

Esta especificación define el comportamiento observable de `our-dots` — el gestor de packs de dotfiles y configuración de escritorio de ouroborOS v0.6.1. Cubre:

- La interfaz CLI completa: todos los subcomandos, flags, argumentos, y comportamiento en stdin/stdout/stderr.
- Los formatos de datos canónicos: manifests YAML de packs, schema de `system.yaml` (clave `dots_packs`), `dots-repos.yaml`, e `index.yaml` de repositorios HTTP.
- Los algoritmos de cada operación, expresados como pseudocódigo Bash (CLI) y Python (instalador).
- Las máquinas de estado del instalador (`DOTS_PACK`) y de instalación de un pack.
- Los contratos de pre/post condiciones e invariants para cada operación.
- El manejo de errores: exit codes, mensajes, y comportamiento de recovery.
- Las reglas de validación de schema y detección de conflictos.
- Las restricciones de seguridad y el mecanismo de cleanup para packs CRITICAL.

Esta especificación **no** define:
- La interfaz gráfica (GUI) para gestión de packs (fuera de scope de v0.6.1).
- El rollback automático de packs (se delega a `our-rollback` + snapshots Btrfs).
- La firma criptográfica de manifests (campo `signature: null` reservado para versión futura).
- Packs para perfiles GNOME, KDE o Cosmic (solo Hyprland y Niri en v0.6.1).

---

## 2. Contexto y Arquitectura

### 2.1 Componentes del Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Usuario / Instalador TUI                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │ CLI: our-dots -S / -R / -Q / repo-add…
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                   our-dots (Bash CLI)                               │
│  /usr/local/bin/our-dots                                            │
│                                                                     │
│  cmd_list · cmd_info · cmd_install · cmd_remove · cmd_query        │
│  cmd_search · cmd_upgrade · cmd_repo_{add,remove,list,update}      │
│                                                                     │
│  Helpers: yaml_get · yaml_list · sysyaml_add/remove/is_installed   │
│           find_manifest · compat_badge · log_info/warn/error · die │
└──────┬──────────────┬───────────────────┬───────────────────┬──────┘
       │              │                   │                   │
       ▼              ▼                   ▼                   ▼
 ┌──────────┐  ┌─────────────┐   ┌─────────────────┐  ┌──────────────┐
 │ MANIFEST │  │  REPOS_DIR  │   │   system.yaml   │  │  our-pac /   │
 │   _DIR   │  │  (externos) │   │ /etc/ouroboros/ │  │  our-aur     │
 │ (builtin)│  │/var/lib/…   │   │ (fuente verdad) │  │  (paquetes)  │
 └──────────┘  └─────────────┘   └─────────────────┘  └──────────────┘
       │
       ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │         dots_profiles.py (módulo Python del instalador)           │
 │         /usr/local/lib/ouroboros/installer/                       │
 │                                                                   │
 │  DotsPack dataclass · load_catalog() · packs_for_profile()       │
 └──────────────────────────────────────────────────────────────────┘
       │
       ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │     InstallerFSM (state_machine.py) — Estado DOTS_PACK           │
 │     Posición: DESKTOP → DOTS_PACK → SECURE_BOOT                  │
 └──────────────────────────────────────────────────────────────────┘
```

### 2.2 Rutas de Instalación

| Componente | Ruta | Tipo |
|------------|------|------|
| `our-dots` binary | `/usr/local/bin/our-dots` | Bash 5+, executable |
| Manifests built-in | `/usr/local/lib/ouroboros/dots/packs/` | Read-only (ISO) |
| Repositorios externos | `/var/lib/ouroboros/dots/repos/` | Mutable |
| Índice de repos | `/etc/ouroboros/dots-repos.yaml` | YAML mutable |
| Estado instalado | `/etc/ouroboros/system.yaml` (clave `dots_packs`) | YAML mutable |
| Logs | `/var/log/our-dots/` | Mutable |
| `dots_profiles.py` | `src/installer/dots_profiles.py` | Python 3.11+ |

---

## 3. Interfaces CLI

### 3.1 Sinopsis

```
our-dots [OPCIÓN]
our-dots list [--git]
our-dots -Si <id>
our-dots -S <id> [--git] [--noconfirm]
our-dots -R <id> [--force]
our-dots -Q
our-dots -Qs [<patrón>]
our-dots -Su
our-dots repo-add <nombre> <url>
our-dots repo-remove <nombre>
our-dots repo-list
our-dots repo-update
our-dots --version
our-dots --help | help
```

### 3.2 Subcomandos de Gestión de Packs

#### `list`

Lista todos los packs disponibles en el catálogo (built-in + repositorios externos).

```
our-dots list
```

**Salida (stdout):** Tabla con columnas:

```
NAME             COMPAT    PROFILES         CHANNELS    STATUS
[EXTERN] <name>  critical  hyprland         git         installed (v4, stable)
<name>           low       hyprland, niri   stable/git  —
```

- Columna `NAME`: packs externos prefijados con `[EXTERN]`.
- Columna `COMPAT`: `low` | `medium` | `high` | `critical`.
- Columna `PROFILES`: lista separada por comas.
- Columna `CHANNELS`: `stable` | `git` | `stable/git`.
- Columna `STATUS`: versión instalada o `—` si no instalado.
- Sin manifests → tabla vacía con encabezado.
- `MANIFEST_DIR` inexistente → tabla vacía, sin error.

**Exit codes:** 0 en todos los casos (incluso sin packs).

---

#### `-Si <id>`

Muestra información detallada de un pack.

```
our-dots -Si <id>
```

**Salida (stdout):** Panel formateado con:

```
Pack: <name> [EXTERN]            (prefijo si es externo)
Author: <credits.author>
Homepage: <credits.homepage>
Docs: <credits.docs>             (si definido)
Repo: <credits.repo>             (si definido)
License: <credits.license>       (si definido)
Compatibility: <level>
Profiles: <lista>
Note: <compatibility.note>       (si definido)

Channels:
  stable — <version_hint>        (si variants.stable definido)
  git    — <version_hint>        (si variants.git definido)

Status: installed (channel: <ch>, version: <v>, date: <d>)
    OR: not installed

Origin: builtin | external (<repo-name>)
```

**Exit codes:**
- 0: pack encontrado y mostrado.
- 1: pack no encontrado (`die "Pack not found: <id>"`).

---

#### `-S <id>`

Instala un pack.

```
our-dots -S <id> [--git] [--noconfirm]
```

**Argumento:** `<id>` es el identificador del pack en kebab-case (e.g., `noctalia`, `ml4w`). **No** acepta el nombre de display (e.g., "Noctalia v4"). Usar `our-dots list` o `-Qs` para descubrir IDs. [M-04]

**Flags:**
- `--git`: fuerza canal git sin menú de selección. Error si el pack no define `variants.git`.
- `--noconfirm`: omite prompts interactivos. **Ignorado para packs CRITICAL** (produce error).

**Salida (stdout/stderr):** Progreso de instalación, log path, resultado.

**Requiere:** `sudo` (root). Verifica con `[[ $EUID -eq 0 ]]`.

**Exit codes:** Ver §8.

---

#### `-R <id>`

Desinstala un pack.

```
our-dots -R <id> [--force] [--noconfirm]
```

**Flags:**
- `--force`: permite ejecutar `-R` aunque el pack no esté en `system.yaml`. Útil para limpiar paquetes huérfanos tras un `post_deploy` fallido. Sin `--force`, requiere que el pack esté registrado.
- `--noconfirm`: omite el prompt `[y/N]` de confirmación. [M-03]

**Log:** Genera log en `/var/log/our-dots/<id>-remove-<timestamp>.log`. El path se informa al usuario antes de comenzar. [M-01]

**Argumento:** `<id>` es el identificador del pack (kebab-case). No acepta nombre de display. [M-04]

**Requiere:** `sudo` (root).

---

#### `-Q`

Lista los packs instalados.

```
our-dots -Q
```

**Salida (stdout):** Tabla con columnas `ID`, `CHANNEL`, `INSTALLED_AT`.

```
ID          CHANNEL    INSTALLED_AT
noctalia    stable     2026-06-07
ml4w        stable     2026-06-05
```

- Sin packs instalados: `(no packs installed)`.
- `system.yaml` inexistente: `(no packs installed)`, sin error.

**Exit codes:** 0 en todos los casos.

---

#### `-Qs [<patrón>]`

Busca packs por patrón (case-insensitive sobre ID, nombre y descripción).

```
our-dots -Qs [<patrón>]
```

- Sin `<patrón>`: muestra catálogo completo (equivalente a `list`).
- Sin coincidencias: resultado vacío, sin error.

**Exit codes:** 0 en todos los casos.

---

#### `-Su`

Actualiza los packs instalados.

```
our-dots -Su
```

**Requiere:** `sudo` (root).

**Comportamiento:** Ver algoritmo en §5.6.

---

### 3.3 Subcomandos de Gestión de Repositorios

#### `repo-add <nombre> <url>`

Agrega un repositorio externo de manifests.

```
sudo our-dots repo-add <nombre> <url>
```

- `<nombre>`: identificador único del repositorio (sin espacios).
- `<url>`: URL HTTPS del repositorio. HTTP simple es rechazado.

**Tipos soportados:**
- Git (URL termina en `.git` o `git ls-remote` responde): `git clone --depth=1`.
- HTTP: descarga `index.yaml` desde `<url>/index.yaml` y luego cada `<id>.yaml`.

**Requiere:** `sudo` (root).

---

#### `repo-remove <nombre>`

Elimina un repositorio externo.

```
sudo our-dots repo-remove <nombre>
```

**Requiere:** `sudo` (root).

---

#### `repo-list`

Lista todos los repositorios configurados.

```
our-dots repo-list
```

**Salida (stdout):**

```
NAME       URL                                          TYPE  PACKS
(builtin)  /usr/local/lib/ouroboros/dots/packs/        —     7
mi-repo    https://github.com/user/dots-manifests.git  git   3
```

**Exit codes:** 0 en todos los casos.

---

#### `repo-update`

Actualiza manifests de repositorios externos.

```
sudo our-dots repo-update
```

**Requiere:** `sudo` (root).

---

### 3.4 Opciones Globales

| Flag | Descripción |
|------|-------------|
| `--version` | Imprime `our-dots <VERSION>` y sale con código 0. |
| `--help` / `help` | Imprime ayuda completa de todos los subcomandos y sale con código 0. Subcomando desconocido: imprime ayuda y sale con código 1. |

### 3.5 Streams

| Stream | Contenido |
|--------|-----------|
| **stdout** | Progreso normal, tablas, paneles informativos, resultado de operaciones. |
| **stderr** | Warnings (`log_warn`), errores (`log_error`, `die`). |
| **stdin** | Prompts de confirmación interactivos. No usados con `--noconfirm`. |

---

## 4. Formato de Datos

> **Referencia autoritativa:** Este schema supersede PRD §6.8. Fuente: TRD v1.2 §2.3.

### 4.1 Schema de Manifest YAML (`<id>.yaml`)

Cada pack del catálogo (built-in o externo) se describe en un archivo `<id>.yaml`.

#### Tabla de campos

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `id` | string | **Sí** | Identificador único. Kebab-case, minúsculas. Debe ser único en el catálogo. |
| `name` | string | **Sí** | Nombre de display del pack. |
| `description` | string (multiline) | **Sí** | Descripción completa del pack. |
| `credits.author` | string | **Sí** | Nombre del autor u organización. |
| `credits.homepage` | url (HTTPS) | **Sí** | URL del proyecto. |
| `credits.docs` | url | No | URL de documentación oficial. |
| `credits.repo` | url | No | URL del repositorio de código fuente. |
| `credits.license` | string | No | Identificador SPDX (e.g., `MIT`, `GPL-2.0`). |
| `compatibility.immutable` | enum | **Sí** | `low` \| `medium` \| `high` \| `critical`. |
| `compatibility.profiles` | list[string] | **Sí** | Perfiles desktop compatibles. Valores: `hyprland`, `niri`. Lista no vacía. |
| `compatibility.note` | string | No | Nota breve para packs `high`. Texto del aviso amarillo previo a instalación. |
| `compatibility.warning` | string | Sí si `critical` | Texto del panel rojo de confirmación CRITICAL. |
| `compatibility.critical_actions` | list[string] | Sí si `critical` | Lista numerada de acciones que se tomarán. Lista no vacía. |
| `requires_root` | bool | No | Indica si el pack requiere operaciones root adicionales (e.g., remount rw). |
| `variants.stable` | objeto | No | Definición del canal stable. Al menos uno de `stable` o `git` debe estar presente. |
| `variants.stable.packages` | list[string] | No | Paquetes pacman a instalar (canal stable). |
| `variants.stable.aur` | list[string] | No | Paquetes AUR a instalar (canal stable). |
| `variants.stable.post_deploy` | string\|null | No | Script inline ejecutado tras instalación (como `$SUDO_USER`). |
| `variants.stable.version_hint` | string | No | Texto descriptivo de la versión stable. |
| `variants.git` | objeto | No | Definición del canal git. |
| `variants.git.packages` | list[string] | No | Paquetes pacman (canal git). |
| `variants.git.aur` | list[string] | No | Paquetes AUR (canal git). |
| `variants.git.post_deploy` | string\|null | No | Script inline (canal git). |
| `variants.git.version_hint` | string | No | Texto descriptivo del canal git. |
| `uninstall.packages` | list[string] | No | Paquetes pacman a remover en `-R`. |
| `uninstall.aur` | list[string] | No | Paquetes AUR a remover en `-R`. |
| `uninstall.post_remove` | string\|null | No | Script inline ejecutado tras desinstalación (como `$SUDO_USER`). |
| `uninstall.remove_config` | bool | No | Si `true`, elimina `~/.config/<id>` en `post_remove`. |
| `signature` | null | No | **Reservado.** Siempre `null` en v0.6.1. Futura firma criptográfica. |

#### Invariants del manifest

- `id` debe ser kebab-case, minúsculas, sin espacios.
- Si `compatibility.immutable == "critical"`: `compatibility.warning` DEBE ser no-nulo y `compatibility.critical_actions` DEBE ser una lista no vacía.
- Al menos uno de `variants.stable` o `variants.git` DEBE estar definido.
- `post_deploy` y `post_remove` deben ser `null` o un string inline (script shell). **No** pueden ser paths absolutos iniciados con `/`.
- Todos los campos `url` deben comenzar con `https://`.

#### Ejemplo completo — pack `noctalia` (LOW, stable + git)

```yaml
id: noctalia
name: Noctalia v4
description: |
  A Quickshell-based desktop shell layer for Niri and Hyprland compositors.
  Modular design: bar, notifications, clipboard history, night light, and
  calendar. Noctalia has the broadest distribution support of any shell in
  this catalog, available in official repos for Fedora, openSUSE, and Void,
  and via AUR for Arch. The explicit stable/git split makes it one of the
  safest choices for an immutable system.

credits:
  author: noctalia-dev team
  homepage: https://github.com/noctalia-dev/noctalia-shell
  docs: https://docs.noctalia.dev/v4/getting-started/installation/#arch
  license: null    # [I-05] license debe ser null o un identificador SPDX válido (e.g., "MIT")

compatibility:
  immutable: low
  profiles: [hyprland, niri]
  note: AUR package, user-space config — no root writes required

variants:
  stable:
    packages: []
    aur: [noctalia-shell]
    post_deploy: null
    version_hint: "v4 (stable)"
  git:
    packages: []
    aur: [noctalia-shell-git]
    post_deploy: null
    version_hint: "git (bleeding edge)"

uninstall:
  packages: []
  aur: [noctalia-shell, noctalia-shell-git]
  post_remove: null
  remove_config: false

signature: null
```

#### Ejemplo — pack `illogical-impulse` (CRITICAL, git-only)

> **[C-02]** Este pack define solo `variants.git` (sin `variants.stable`). El instalador detecta automáticamente canal `git` cuando `has_stable == false` y `has_git == true` (§11.4).

```yaml
id: illogical-impulse
name: illogical-impulse
description: |
  end-4's popular Hyprland rice built on Quickshell. Requires temporarily
  remounting / as writable to add an IgnoreGroup entry to /etc/pacman.conf.

credits:
  author: end-4
  homepage: https://ii.clsty.link/en/ii-qs/01setup/
  repo: https://github.com/end-4/dots-hyprland

compatibility:
  immutable: critical
  profiles: [hyprland]
  warning: |
    This pack requires modifying /etc/pacman.conf on a read-only root filesystem.
    ouroborOS will temporarily remount / as writable during the edit.
  critical_actions:
    - "Remount / as read-write (temporary)"
    - "Add 'IgnoreGroup=illogical-impulse' to /etc/pacman.conf"
    - "Remount / as read-only"
    - "Install dependencies via our-pac and our-aur"
    - "Clone dots-hyprland and run ./setup install as your user"

requires_root: true

variants:
  git:
    packages: [git]
    aur: []
    post_deploy: |
      git clone https://github.com/end-4/dots-hyprland /tmp/dots-hyprland
      cd /tmp/dots-hyprland && ./setup install
    version_hint: "rolling (git)"

uninstall:
  packages: []
  aur: []
  post_remove: |
    cd /tmp/dots-hyprland 2>/dev/null && ./setup uninstall 2>/dev/null || true
  remove_config: false

signature: null
```

#### Ejemplo — pack `danklinux` (HIGH, stable-only)

```yaml
id: danklinux
name: DankMaterialShell
description: |
  A Material You-themed Wayland shell supporting both Niri and Hyprland
  compositors, with automatic color generation from wallpapers via matugen.

credits:
  author: AvengeMedia
  homepage: https://danklinux.com/docs/dankinstall
  repo: https://github.com/AvengeMedia/DankMaterialShell

compatibility:
  immutable: high
  profiles: [hyprland, niri]
  note: |
    Installs dms-shell from extra repo + AUR builds (go, cmake, rustup).
    All via our-pac/our-aur — no direct pacman calls. Build time ~10 min.

variants:
  stable:
    packages: [dms-shell, rustup, go, cmake, ninja]
    aur: [quickshell, matugen-bin, dgop, dsearch]
    post_deploy: null
    version_hint: "1.4"

uninstall:
  packages: [dms-shell]
  aur: [quickshell, matugen-bin, dgop, dsearch]
  post_remove: null
  remove_config: false

signature: null
```

### 4.2 Schema de `system.yaml` — clave `dots_packs`

La clave `dots_packs` es una lista de objetos. Cada objeto representa un pack instalado.

```yaml
dots_packs:
  - id: "noctalia"
    channel: "stable"
    installed_version: "v4 (stable)"
    installed_at: "2026-06-07"
    origin: "builtin"
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | Identificador del pack instalado. |
| `channel` | string | Canal de instalación: `stable` o `git`. |
| `installed_version` | string | Value de `variants.<channel>.version_hint` al momento de instalación. |
| `installed_at` | date (ISO 8601) | Fecha de instalación (`YYYY-MM-DD`). |
| `origin` | string | Origen del pack: `builtin` o `extern`. |

**Invariant:** Solo puede existir una entrada por `id`. `sysyaml_add_pack` hace upsert (reemplaza si ya existe).

**Escritura:** Siempre atómica: `flock(system.yaml.lock)` + escribir a `.tmp` + `os.replace()`. Ver §7.5.

### 4.3 Schema de `dots-repos.yaml`

Ubicado en `/etc/ouroboros/dots-repos.yaml`. Registra repositorios externos.

```yaml
repos:
  - name: "mi-repo"
    url: "https://github.com/usuario/dots-manifests.git"
    type: "git"
    added_at: "2026-06-07"
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Nombre único del repositorio. |
| `url` | url (HTTPS) | URL del repositorio. Solo HTTPS admitido. |
| `type` | string | `git` si es repositorio Git; `http` si es índice HTTP. |
| `added_at` | date (ISO 8601) | Fecha de registro. |

- Si el archivo no existe: comportamiento de `repo-list` y `find_manifest()` es como si no hubiera repositorios externos.

### 4.4 Schema de `index.yaml` (repositorios HTTP)

Los repositorios HTTP deben exponer `index.yaml` en su URL base:

```yaml
name: "Community Dots"
description: "Descripción del repositorio"
maintainer: "nombre@email.com"
packs:
  - my-niri-pack
  - custom-hyprland
```

Cada ID en `packs` debe tener un archivo `<id>.yaml` accesible en `<url>/<id>.yaml` con el schema de manifest completo (§4.1).

### 4.5 Catálogo de Packs Built-in (v0.6.1)

| ID | Nombre | Compat | Perfiles | Canales |
|----|--------|--------|----------|---------|
| `ml4w` | ML4W Dotfiles | medium | hyprland | stable (v0.2.3) |
| `noctalia` | Noctalia v4 | low | hyprland, niri | stable, git |
| `caelestia` | Caelestia Shell | medium | hyprland | stable (AUR), git |
| `illogical-impulse` | illogical-impulse | critical | hyprland | **git** |
| `omarchy` | Omarchy | critical | hyprland | stable (rolling) |
| `ambxst` | Ambxst | medium | hyprland | **git** |
| `danklinux` | DankMaterialShell | high | hyprland, niri | stable (v1.4) |

> **[C-02]** `illogical-impulse` y `ambxst` son **git-only** (sin `variants.stable`). El PRD §6.4/§6.6 los documentaba como "stable (rolling)", en contradicción con el TRD §2.3. El canal canónico es `git`.

---

## 5. Algoritmos por Subcomando

### 5.0 Header del Script `our-dots`

Todo el pseudocódigo Bash de esta sección asume el siguiente header en el script:

```bash
#!/usr/bin/env bash
# our-dots — ouroborOS dotfiles pack manager
set -euo pipefail
```

> **[C-01] Requisito crítico:** `set -o pipefail` es **obligatorio**. Sin él, pipelines de la forma `cmd 2>&1 | tee -a "$logfile" || exit N` obtienen el exit code de `tee` (siempre 0). El `|| exit N` jamás se dispararía, ignorando silenciosamente errores de `our-pac`, `our-aur` o `post_deploy`.

---

### 5.1 `list` — Listar packs

```bash
cmd_list() {
    local packs=()

    # 1. Cargar manifests built-in
    for mf in "$MANIFEST_DIR"/*.yaml; do
        [[ -f "$mf" ]] || continue
        packs+=("$mf:builtin")
    done

    # 2. Cargar manifests externos (orden determinista: orden en dots-repos.yaml)
    if [[ -f "$REPOS_INDEX" ]]; then
        while IFS= read -r repo_name; do
            for mf in "$REPOS_DIR/$repo_name"/*.yaml; do
                [[ -f "$mf" ]] || continue
                packs+=("$mf:extern:$repo_name")
            done
        done < <(yaml_list "$REPOS_INDEX" "repos[].name")
    fi

    # 3. Renderizar tabla
    print_table_header
    for entry in "${packs[@]}"; do
        local mf="${entry%%:*}"
        local origin="${entry#*:}"
        local id name compat profiles channels status prefix

        id=$(yaml_get "$mf" "id")
        name=$(yaml_get "$mf" "name")
        compat=$(yaml_get "$mf" "compatibility.immutable")
        profiles=$(yaml_list "$mf" "compatibility.profiles" | paste -sd ',')
        channels=$(derive_channels "$mf")
        prefix=""
        [[ "$origin" == extern:* ]] && prefix="[EXTERN] "

        if sysyaml_is_installed "$id"; then
            status=$(sysyaml_get_version "$id")
        else
            status="—"
        fi

        print_table_row "${prefix}${name}" "$compat" "$profiles" "$channels" "$status"
    done
}

derive_channels() {
    local mf="$1"
    local has_stable has_git
    has_stable=$(yaml_get "$mf" "variants.stable.version_hint" 2>/dev/null && echo "yes" || echo "no")
    has_git=$(yaml_get "$mf" "variants.git.version_hint" 2>/dev/null && echo "yes" || echo "no")
    if [[ "$has_stable" == "yes" && "$has_git" == "yes" ]]; then
        echo "stable/git"
    elif [[ "$has_stable" == "yes" ]]; then
        echo "stable"
    else
        echo "git"
    fi
}
```

### 5.2 `-Si` — Información detallada

```bash
cmd_info() {
    local id="$1"
    local mf
    mf=$(find_manifest "$id") || die "Pack not found: $id"

    local origin="builtin"
    [[ "$mf" == "$REPOS_DIR"/* ]] && origin="extern"

    # Extraer campos
    local name author homepage docs repo license compat profiles note
    name=$(yaml_get "$mf" "name")
    author=$(yaml_get "$mf" "credits.author")
    homepage=$(yaml_get "$mf" "credits.homepage")
    docs=$(yaml_get "$mf" "credits.docs" 2>/dev/null || true)
    repo=$(yaml_get "$mf" "credits.repo" 2>/dev/null || true)
    license=$(yaml_get "$mf" "credits.license" 2>/dev/null || true)
    compat=$(yaml_get "$mf" "compatibility.immutable")
    profiles=$(yaml_list "$mf" "compatibility.profiles" | paste -sd ',')
    note=$(yaml_get "$mf" "compatibility.note" 2>/dev/null || true)

    # Prefijo EXTERN
    [[ "$origin" == "extern" ]] && name="[EXTERN] $name"

    # Panel de información
    print_info_panel \
        "Pack: $name" \
        "Author: $author" \
        "Homepage: $homepage" \
        "${docs:+Docs: $docs}" \
        "${repo:+Repo: $repo}" \
        "${license:+License: $license}" \
        "Compatibility: $compat" \
        "Profiles: $profiles" \
        "${note:+Note: $note}"

    # Canales disponibles
    print_channels "$mf"

    # Estado de instalación
    if sysyaml_is_installed "$id"; then
        local ch ver dat
        ch=$(sysyaml_get_field "$id" "channel")
        ver=$(sysyaml_get_field "$id" "installed_version")
        dat=$(sysyaml_get_field "$id" "installed_at")
        echo "Status: installed (channel: $ch, version: $ver, date: $dat)"
    else
        echo "Status: not installed"
    fi

    echo "Origin: $origin"
}
```

### 5.3 `-S` — Instalar pack

```bash
cmd_install() {
    local id="$1" channel="" noconfirm=false git_flag=false

    # Parsear flags
    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --git) git_flag=true ;;
            --noconfirm) noconfirm=true ;;
        esac
        shift
    done

    # Verificar root
    [[ $EUID -eq 0 ]] || die "our-dots -S requires root (use sudo)"

    # Localizar manifest
    local mf
    mf=$(find_manifest "$id") || die "Pack not found: $id"

    # Determinar origen
    local origin="builtin"
    [[ "$mf" == "$REPOS_DIR"/* ]] && origin="extern"

    # Aviso EXTERN antes de cualquier acción
    if [[ "$origin" == "extern" ]]; then
        log_warn "This pack is from an external repository not audited by the ouroborOS project."
    fi

    # Obtener nivel de compatibilidad
    local compat
    compat=$(yaml_get "$mf" "compatibility.immutable")

    # Flujo de confirmación por nivel
    case "$compat" in
        critical)
            if [[ "$noconfirm" == true && -z "${OUROBOROS_ALLOW_CRITICAL:-}" ]]; then
                die "CRITICAL pack requires OUROBOROS_ALLOW_CRITICAL=1 for unattended installation."
            fi
            if [[ -z "${OUROBOROS_ALLOW_CRITICAL:-}" ]]; then
                show_critical_panel "$mf" "$id"
                # Solicitar tipear exactamente "yes"
                local answer
                read -r -p "  Type 'yes' to proceed, anything else to cancel: " answer
                [[ "${answer,,}" == "yes" ]] || { log_info "Installation cancelled."; exit 1; }
            fi
            # Instalar trap de cleanup inmediatamente tras confirmación
            trap 'cleanup_critical "$id"' ERR EXIT
            ;;
        high)
            if [[ "$noconfirm" == false ]]; then
                local note
                note=$(yaml_get "$mf" "compatibility.note" 2>/dev/null || true)
                log_warn "⚠  HIGH compatibility impact: ${note:-see manifest for details}"
                read -r -p "  Continue? [y/N] " answer
                [[ "${answer,,}" == "y" ]] || { log_info "Installation cancelled."; exit 1; }
            fi
            ;;
        # low | medium: sin aviso especial
    esac

    # Selección de canal
    if [[ "$git_flag" == true ]]; then
        channel="git"
        # Verificar que variants.git existe
        yaml_get "$mf" "variants.git.version_hint" &>/dev/null || \
            die "Canal git no disponible para $id. Instalar sin --git para usar canal stable."
    else
        # Detectar canales disponibles
        local has_stable has_git
        has_stable=$(yaml_get "$mf" "variants.stable.version_hint" &>/dev/null && echo yes || echo no)
        has_git=$(yaml_get "$mf" "variants.git.version_hint" &>/dev/null && echo yes || echo no)

        if [[ "$has_stable" == "yes" && "$has_git" == "yes" && "$noconfirm" == false ]]; then
            # Ofrecer selección interactiva de canal
            channel=$(prompt_channel_selection)
        elif [[ "$has_git" == "yes" && "$has_stable" == "no" ]]; then
            channel="git"
        else
            channel="stable"
        fi
    fi

    # Verificar si ya está instalado (aviso de reinstalación)
    if sysyaml_is_installed "$id" && [[ "$noconfirm" == false ]]; then
        log_warn "Pack already installed. Reinstalling will overwrite the existing entry."
        read -r -p "  Continue? [y/N] " answer
        [[ "${answer,,}" == "y" ]] || { log_info "Reinstallation cancelled."; exit 1; }
    fi

    # Log path
    local timestamp logfile
    timestamp=$(date +%Y%m%d-%H%M%S)
    logfile="$LOG_DIR/${id}-${timestamp}.log"
    mkdir -p "$LOG_DIR"
    log_info "Log: $logfile"

    # Confirmar instalación (low/medium, si no --noconfirm)
    if [[ "$noconfirm" == false && "$compat" =~ ^(low|medium)$ ]]; then
        read -r -p "  Install $id ($channel)? [y/N] " answer
        [[ "${answer,,}" == "y" ]] || { log_info "Installation cancelled."; exit 1; }
    fi

    # Instalar paquetes pacman
    mapfile -t pkgs < <(yaml_list "$mf" "variants.${channel}.packages")
    if [[ ${#pkgs[@]} -gt 0 ]]; then
        log_info "Installing pacman packages: ${pkgs[*]}"
        our-pac -S "${pkgs[@]}" --noconfirm 2>&1 | tee -a "$logfile" || {
            log_error "pacman install failed. Check $logfile"
            exit 1
        }
    fi

    # Instalar paquetes AUR
    mapfile -t aur_pkgs < <(yaml_list "$mf" "variants.${channel}.aur")
    if [[ ${#aur_pkgs[@]} -gt 0 ]]; then
        log_info "Installing AUR packages: ${aur_pkgs[*]}"
        our-aur -S "${aur_pkgs[@]}" 2>&1 | tee -a "$logfile" || {
            log_error "AUR install failed. Check $logfile"
            exit 3
        }
    fi

    # Ejecutar post_deploy como $SUDO_USER
    local post_deploy
    post_deploy=$(yaml_get "$mf" "variants.${channel}.post_deploy" 2>/dev/null || true)
    if [[ -n "$post_deploy" && "$post_deploy" != "null" ]]; then
        log_info "Running post_deploy..."
        local run_user="${SUDO_USER:-$USER}"
        if [[ "$run_user" == "root" ]]; then
            bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || {
                log_error "post_deploy failed (exit $?). Check $logfile"
                exit 4
            }
        else
            sudo -u "$run_user" bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || {
                log_error "post_deploy failed (exit $?). Check $logfile"
                exit 4
            }
        fi
    fi

    # Registrar en system.yaml (solo si todo anterior tuvo éxito)
    local version_hint origin_val
    version_hint=$(yaml_get "$mf" "variants.${channel}.version_hint" 2>/dev/null || echo "$channel")
    [[ "$mf" == "$REPOS_DIR"/* ]] && origin_val="extern" || origin_val="builtin"
    sysyaml_add_pack "$id" "$channel" "$version_hint" "$(date +%Y-%m-%d)" "$origin_val"

    # Desinstalar trap (instalación exitosa)
    trap - ERR EXIT

    log_info "Pack $id ($channel) installed successfully."
}
```

### 5.4 `-R` — Desinstalar pack

```bash
cmd_remove() {
    local id="$1" force=false noconfirm=false

    shift
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)     force=true ;;
            --noconfirm) noconfirm=true ;;  # [M-03]
        esac
        shift
    done

    [[ $EUID -eq 0 ]] || die "our-dots -R requires root (use sudo)"

    # Verificar que el pack está registrado (a menos que --force)
    if ! sysyaml_is_installed "$id" && [[ "$force" == false ]]; then
        die "Pack $id is not installed. Use --force to remove orphaned packages."
    fi

    # Localizar manifest (puede no existir)
    local mf
    mf=$(find_manifest "$id" 2>/dev/null) || {
        log_warn "Manifest not found for $id. Removing from system.yaml entry only."
        sysyaml_remove_pack "$id"
        return 0
    }

    # [M-01] Log file para la operación de remoción
    local timestamp logfile
    timestamp=$(date +%Y%m%d-%H%M%S)
    logfile="$LOG_DIR/${id}-remove-${timestamp}.log"
    mkdir -p "$LOG_DIR"
    log_info "Log: $logfile"

    # [M-03] Confirmar (omitir si --noconfirm)
    if [[ "$noconfirm" == false ]]; then
        read -r -p "  Remove $id? [y/N] " answer
        [[ "${answer,,}" == "y" ]] || { log_info "Removal cancelled."; exit 1; }
    fi

    # Remover paquetes AUR primero
    mapfile -t aur_pkgs < <(yaml_list "$mf" "uninstall.aur")
    if [[ ${#aur_pkgs[@]} -gt 0 ]]; then
        our-aur -R "${aur_pkgs[@]}" 2>&1 | tee -a "$logfile" || log_warn "Some AUR packages could not be removed."
    fi

    # Remover paquetes pacman
    mapfile -t pkgs < <(yaml_list "$mf" "uninstall.packages")
    if [[ ${#pkgs[@]} -gt 0 ]]; then
        our-pac -R "${pkgs[@]}" 2>&1 | tee -a "$logfile" || log_warn "Some pacman packages could not be removed."
    fi

    # Ejecutar post_remove como $SUDO_USER
    local post_remove
    post_remove=$(yaml_get "$mf" "uninstall.post_remove" 2>/dev/null || true)
    if [[ -n "$post_remove" && "$post_remove" != "null" ]]; then
        local run_user="${SUDO_USER:-$USER}"
        if [[ "$run_user" == "root" ]]; then
            bash -c "$post_remove" 2>&1 | tee -a "$logfile" || log_warn "post_remove failed (non-fatal)"
        else
            sudo -u "$run_user" bash -c "$post_remove" 2>&1 | tee -a "$logfile" || log_warn "post_remove failed (non-fatal)"
        fi
    fi

    # Remover de system.yaml
    sysyaml_remove_pack "$id"

    log_info "Pack $id removed."
}
```

### 5.5 `-Q` / `-Qs` — Consultar packs instalados

```bash
cmd_query() {
    local pattern="${1:-}"

    # Leer dots_packs de system.yaml
    if [[ ! -f "$SYSYAML" ]]; then
        echo "(no packs installed)"
        return 0
    fi

    local packs
    mapfile -t packs < <(yaml_list "$SYSYAML" "dots_packs[].id" 2>/dev/null)

    if [[ ${#packs[@]} -eq 0 ]]; then
        echo "(no packs installed)"
        return 0
    fi

    print_query_header
    for id in "${packs[@]}"; do
        local ch installed_at
        ch=$(sysyaml_get_field "$id" "channel")
        installed_at=$(sysyaml_get_field "$id" "installed_at")

        # Filtro de búsqueda
        if [[ -n "$pattern" ]]; then
            local name desc
            local mf
            mf=$(find_manifest "$id" 2>/dev/null) || continue
            name=$(yaml_get "$mf" "name" 2>/dev/null || echo "")
            desc=$(yaml_get "$mf" "description" 2>/dev/null || echo "")
            if ! grep -qiE "$pattern" <<< "$id $name $desc"; then
                continue
            fi
        fi

        print_query_row "$id" "$ch" "$installed_at"
    done
}

# -Qs busca en el catálogo completo (no solo instalados)
cmd_search() {
    local pattern="${1:-}"

    # Sin patrón: equivalente a list
    if [[ -z "$pattern" ]]; then
        cmd_list
        return 0
    fi

    # Con patrón: iterar catálogo completo (built-in + externos)
    local found=0

    for mf in "$MANIFEST_DIR"/*.yaml; do
        [[ -f "$mf" ]] || continue
        _search_match_and_print "$mf" "builtin" "$pattern" && ((found++)) || true
    done

    if [[ -f "$REPOS_INDEX" ]]; then
        while IFS= read -r repo_name; do
            for mf in "$REPOS_DIR/$repo_name"/*.yaml; do
                [[ -f "$mf" ]] || continue
                _search_match_and_print "$mf" "extern" "$pattern" && ((found++)) || true
            done
        done < <(yaml_list "$REPOS_INDEX" "repos[].name")
    fi

    [[ $found -gt 0 ]] || true  # sin coincidencias: salida vacía, exit 0
}

_search_match_and_print() {
    local mf="$1" origin="$2" pattern="$3"
    local id name desc compat profiles channels status prefix

    id=$(yaml_get "$mf" "id" 2>/dev/null || true)
    name=$(yaml_get "$mf" "name" 2>/dev/null || true)
    desc=$(yaml_get "$mf" "description" 2>/dev/null || true)

    # Filtro case-insensitive sobre id, name y description
    if ! grep -qiE "$pattern" <<< "$id $name $desc"; then
        return 1
    fi

    compat=$(yaml_get "$mf" "compatibility.immutable")
    profiles=$(yaml_list "$mf" "compatibility.profiles" | paste -sd ',')
    channels=$(derive_channels "$mf")
    prefix=""
    [[ "$origin" == "extern" ]] && prefix="[EXTERN] "

    if sysyaml_is_installed "$id"; then
        status=$(sysyaml_get_version "$id")
    else
        status="—"
    fi

    print_table_row "${prefix}${name}" "$compat" "$profiles" "$channels" "$status"
}
```

### 5.6 `-Su` — Actualizar packs

```bash
cmd_upgrade() {
    [[ $EUID -eq 0 ]] || die "our-dots -Su requires root (use sudo)"

    local updated=0 skipped=0 failed=0

    mapfile -t pack_ids < <(yaml_list "$SYSYAML" "dots_packs[].id" 2>/dev/null)

    for id in "${pack_ids[@]}"; do
        local mf ch
        mf=$(find_manifest "$id" 2>/dev/null) || { log_warn "Manifest not found for $id — skip"; ((skipped++)); continue; }
        ch=$(sysyaml_get_field "$id" "channel")
        compat=$(yaml_get "$mf" "compatibility.immutable")

        # Excluir CRITICAL de actualización automática
        if [[ "$compat" == "critical" ]]; then
            log_warn "CRITICAL packs require manual update: sudo our-dots -S $id"
            ((skipped++))
            continue
        fi

        # Intentar actualización por tipo de canal
        local first_aur
        first_aur=$(yaml_list "$mf" "variants.${ch}.aur" | head -1 2>/dev/null || true)

        if [[ -n "$first_aur" ]]; then
            # Paquete AUR: comparar versiones via API AUR
            local current_ver available_ver
            current_ver=$(pacman -Q "$first_aur" 2>/dev/null | awk '{print $2}' || echo "")
            available_ver=$(curl -sfL \
                "https://aur.archlinux.org/rpc/?v=5&type=info&arg=${first_aur}" \
                | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['results'][0]['Version'] if d['results'] else '')" \
                2>/dev/null || echo "")

            if [[ -z "$available_ver" ]]; then
                log_warn "AUR API unavailable for $id — skip"
                ((skipped++))
            elif [[ "$available_ver" != "$current_ver" ]]; then
                log_info "Updating $id ($current_ver → $available_ver)"
                cmd_install "$id" --noconfirm && ((updated++)) || ((failed++))
            else
                log_info "$id is up to date ($current_ver)"
            fi

        elif [[ "$ch" == "git" ]]; then
            # Canal git sin AUR: git pull en directorio persistente
            # [I-02] Usar /var/lib/ouroboros/dots/repos/<id> en lugar de /tmp/<id>
            # /tmp se limpia al reiniciar; el directorio persistente sobrevive reboots.
            local repo_dir="$REPOS_DIR/${id}"
            if [[ -d "$repo_dir/.git" ]]; then
                git -C "$repo_dir" pull --ff-only 2>&1 && ((updated++)) || {
                    log_warn "git pull failed for $id — try: git pull --rebase in $repo_dir"
                    ((failed++))
                }
            else
                log_warn "No git directory found for $id at $repo_dir — reinstall manually: sudo our-dots -S $id"
                ((skipped++))
            fi
        else
            log_warn "$id has no update mechanism — reinstall manually: sudo our-dots -S $id"
            ((skipped++))
        fi
    done

    log_info "Update summary: updated=$updated skipped=$skipped failed=$failed"
}
```

### 5.7 `repo-add` — Registrar repositorio externo

```bash
cmd_repo_add() {
    local name="$1" url="$2"

    [[ $EUID -eq 0 ]] || die "our-dots repo-add requires root (use sudo)"

    # Verificar HTTPS
    [[ "$url" == https://* ]] || die "Repository URL must use HTTPS"

    local dest="$REPOS_DIR/$name"
    mkdir -p "$dest"

    # Detectar tipo de repositorio
    local repo_type="http"
    if git ls-remote "$url" HEAD &>/dev/null 2>&1 || [[ "$url" == *.git ]]; then
        repo_type="git"
    fi

    if [[ "$repo_type" == "git" ]]; then
        # Git: clonar con profundidad 1
        git clone --depth=1 "$url" "$dest" || die "Failed to clone repository: $url"
    else
        # HTTP: descargar index.yaml y cada manifest
        curl -sfL "${url}/index.yaml" -o "${dest}/index.yaml" || \
            die "Failed to fetch index.yaml from $url"

        mapfile -t pack_ids < <(yaml_list "${dest}/index.yaml" "packs")
        for pid in "${pack_ids[@]}"; do
            curl -sfL "${url}/${pid}.yaml" -o "${dest}/${pid}.yaml" 2>/dev/null || \
                log_warn "Failed to download manifest: ${pid}.yaml"
        done
    fi

    # Validar schema de cada manifest descargado
    local valid_count=0
    for mf in "$dest"/*.yaml; do
        [[ "$mf" == */index.yaml ]] && continue
        if validate_manifest_schema "$mf"; then
            ((valid_count++))
        else
            log_warn "Invalid manifest schema: $mf — ignoring"
        fi
    done

    [[ $valid_count -gt 0 ]] || log_warn "No valid manifests found in repository $name"

    # Registrar en dots-repos.yaml (upsert: reemplaza si el nombre ya existe)
    # [I-03] sysyaml_append_repo DEBE hacer upsert para evitar entradas duplicadas
    # cuando repo-update llama a repo-add en repositorios HTTP existentes.
    sysyaml_append_repo "$name" "$url" "$repo_type" "$(date +%Y-%m-%d)"

    log_info "Repository '$name' registered with $valid_count valid packs."
}

# Contrato de sysyaml_append_repo:
# - Si ya existe una entrada con el mismo 'name' en dots-repos.yaml → reemplazar (upsert).
# - Si no existe → insertar nueva entrada.
# - La operación es atómica: flock + write-to-tmp + rename (mismo patrón que sysyaml_add_pack).
# - Invariant: dots-repos.yaml no puede tener dos entradas con el mismo 'name'.
```

### 5.8 `repo-remove` — Eliminar repositorio externo

```bash
cmd_repo_remove() {
    local name="$1"

    [[ $EUID -eq 0 ]] || die "our-dots repo-remove requires root (use sudo)"

    # Verificar si el repositorio está registrado (noop si no existe)
    if ! yaml_list "$REPOS_INDEX" "repos[].name" | grep -q "^${name}$" 2>/dev/null; then
        log_info "Repository '$name' is not registered — nothing to do."
        return 0
    fi

    # Verificar packs instalados del repositorio
    local installed_from_repo=()
    if [[ -f "$SYSYAML" ]]; then
        while IFS= read -r pack_id; do
            local mf_path="$REPOS_DIR/$name/${pack_id}.yaml"
            [[ -f "$mf_path" ]] && installed_from_repo+=("$pack_id")
        done < <(yaml_list "$SYSYAML" "dots_packs[].id" 2>/dev/null)
    fi

    if [[ ${#installed_from_repo[@]} -gt 0 ]]; then
        log_warn "The following packs from '$name' are installed: ${installed_from_repo[*]}"
        read -r -p "  Remove repository anyway? [y/N] " answer
        [[ "${answer,,}" == "y" ]] || { log_info "Removal cancelled."; exit 1; }
    fi

    # Eliminar directorio
    rm -rf "$REPOS_DIR/$name" || log_warn "Could not remove $REPOS_DIR/$name — remove manually"

    # Actualizar dots-repos.yaml
    sysyaml_remove_repo "$name"

    log_info "Repository '$name' removed."
}
```

### 5.9 `repo-update` — Actualizar repositorios externos

```bash
cmd_repo_update() {
    [[ $EUID -eq 0 ]] || die "our-dots repo-update requires root (use sudo)"

    if [[ ! -f "$REPOS_INDEX" ]]; then
        log_info "No external repositories configured."
        return 0
    fi

    mapfile -t repo_names < <(yaml_list "$REPOS_INDEX" "repos[].name")

    local updated=0 failed=0

    for name in "${repo_names[@]}"; do
        local dest="$REPOS_DIR/$name"

        if [[ -d "$dest/.git" ]]; then
            # Repositorio Git: git pull --ff-only
            if git -C "$dest" pull --ff-only 2>&1; then
                log_info "Updated repository '$name'"
                ((updated++))
            else
                log_warn "Failed to update '$name'"
                ((failed++))
            fi
        else
            # HTTP: re-descargar
            local url
            url=$(yaml_get "$REPOS_INDEX" "repos[?name=='$name'].url" 2>/dev/null || true)
            if [[ -n "$url" ]]; then
                cmd_repo_add "$name" "$url" && ((updated++)) || ((failed++))
            else
                log_warn "Could not determine URL for '$name' — skip"
                ((failed++))
            fi
        fi
    done

    log_info "Repo update summary: updated=$updated failed=$failed"
}
```

### 5.10 `find_manifest()` — Resolución de manifests

```bash
find_manifest() {
    local id="$1"

    # 1. Built-in tiene prioridad absoluta
    local f="${MANIFEST_DIR}/${id}.yaml"
    [[ -f "$f" ]] && { echo "$f"; return 0; }

    # 2. Repositorios externos en orden de registro (orden determinista)
    if [[ -f "$REPOS_INDEX" ]]; then
        local repo_name
        while IFS= read -r repo_name; do
            local f="${REPOS_DIR}/${repo_name}/${id}.yaml"
            [[ -f "$f" ]] && { echo "$f"; return 0; }
        done < <(yaml_list "${REPOS_INDEX}" "repos[].name")
    fi

    return 1  # No encontrado
}
```

---

## 6. Máquinas de Estado

### 6.1 FSM del Instalador — Estado `DOTS_PACK`

#### Posición en el flujo global

```
INIT → NETWORK_SETUP → PREFLIGHT → LOCALE → USER → DESKTOP
     → DOTS_PACK → SECURE_BOOT → PARTITION → FORMAT → INSTALL
     → CONFIGURE → SNAPSHOT → FINISH
```

- Progreso global: steps 21–23 de 100.
- Descripción en barra: `"Selecting dotfiles pack"`.

#### Diagrama de estados de `DOTS_PACK`

```
                        ┌──────────────────────┐
                        │   Entry: DOTS_PACK   │
                        │  update_progress(0)  │
                        └──────────┬───────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   profile == "minimal"?      │
                    └──────────────┬──────────────┘
                    │ Sí           │ No
                    ▼              ▼
          ┌──────────────┐  ┌────────────────────┐
          │   log info   │  │   TUI activa?       │
          │   skip       │  └────────────┬───────┘
          └──────┬───────┘  │ Sí         │ No
                 │          ▼            ▼
                 │   ┌──────────────┐ ┌──────────────────────┐
                 │   │ show_dots_   │ │ Leer config.dots_pack │
                 │   │ pack_selec- │ │ directamente           │
                 │   │ tion(prof)  │ └──────────┬────────────┘
                 │   └──────┬──────┘            │
                 │          │                   │
                 │          ▼                   ▼
                 │   ┌──────────────────────────────┐
                 │   │  config.dots_pack.pack = id   │
                 │   │  config.dots_pack.channel = ch│
                 │   └──────────────┬───────────────┘
                 │                  │
                 └──────────────────┘
                                    │
                        ┌───────────▼───────────┐
                        │  update_progress(100) │
                        │  → SECURE_BOOT        │
                        └───────────────────────┘
```

#### Tabla de omisiones

| Condición | Comportamiento |
|-----------|---------------|
| `profile == "minimal"` | Omisión silenciosa. Log `info`. `dots_pack.pack = None`. |
| TUI: usuario selecciona "Ninguno" | `dots_pack.pack = None`. No se instala pack. |
| Unattended: `config.dots_pack.pack == None` | No se instala pack. FSM avanza a `SECURE_BOOT`. |
| Sin packs compatibles con el perfil | `packs_for_profile()` retorna `[]` → UI muestra solo "Ninguno". |

#### Handler Python

> **[C-03]** El handler incluye auto-corrección de canal (TRD §9.2). Si el pack seleccionado es git-only (`has_stable == False`, `has_git == True`), el canal se corrige a `"git"` independientemente del valor en `config.dots_pack.channel`. Aplica tanto en modo TUI como unattended.

```python
def _handle_dots_pack(self) -> None:
    """DOTS_PACK — optional dotfiles pack selection.

    Skipped silently when the desktop profile is 'minimal'.
    In unattended mode, reads from config.dots_pack directly.
    Auto-corrects channel when pack is git-only (TRD §9.2).
    """
    self._update_progress(State.DOTS_PACK, 0)

    if self.config.desktop.profile == "minimal":
        log.info("DOTS_PACK: profile is minimal — skipping dotfiles pack selection.")
        self._update_progress(State.DOTS_PACK, 100)
        return

    if self.tui:
        result = self.tui.show_dots_pack_selection(self.config.desktop.profile)
        self.config.dots_pack.pack = result.get("pack")
        self.config.dots_pack.channel = result.get("channel", "stable")

    # Auto-correct channel based on pack manifest (TRD §9.2)
    pack_id = self.config.dots_pack.pack
    if pack_id:
        catalog = {p.id: p for p in load_catalog()}
        pack = catalog.get(pack_id)
        if pack:
            if not pack.has_stable and pack.has_git:
                self.config.dots_pack.channel = "git"
            elif pack.has_stable and not pack.has_git:
                self.config.dots_pack.channel = "stable"

    log.info(
        "Dots pack: %s (channel: %s)",
        self.config.dots_pack.pack or "none",
        self.config.dots_pack.channel,
    )
    self._update_progress(State.DOTS_PACK, 100)
```

#### Integración con `configure.sh`

El pack seleccionado se pasa al script de configuración via variables de entorno:

```python
env.update({
    "DOTS_PACK": self.config.dots_pack.pack or "",
    "DOTS_CHANNEL": self.config.dots_pack.channel,
})
```

`configure.sh` ejecuta dentro del chroot (si `$DOTS_PACK` no está vacío):

```bash
channel_flag=""
[[ "$DOTS_CHANNEL" == "git" ]] && channel_flag="--git"
our-dots -S "$DOTS_PACK" $channel_flag --noconfirm
```

**Nota:** `--stable` no existe como flag. El canal stable es el comportamiento por defecto cuando no se pasa `--git`.

### 6.2 FSM de Instalación de Pack

```
┌──────────────┐
│    START     │ ← our-dots -S <id> [--git] [--noconfirm]
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ VERIFY_ROOT      │ ← EUID == 0?
└──────┬───────────┘
       │ No → die "requires root"
       │ Sí
       ▼
┌──────────────────┐
│ FIND_MANIFEST    │ ← find_manifest(id)
└──────┬───────────┘
       │ No encontrado → die "Pack not found"
       │ Encontrado
       ▼
┌──────────────────┐
│ EXTERN_WARNING   │ ← ¿origen externo?
└──────┬───────────┘   Sí → log_warn "[EXTERN]"
       │
       ▼
┌──────────────────────────────────────────────┐
│  CONFIRMATION_FLOW                            │
│  low/medium: prompt [y/N]                    │
│  high:       aviso amarillo + [y/N]          │
│  critical:   panel rojo + tipear "yes"       │
│              (o OUROBOROS_ALLOW_CRITICAL=1)  │
└──────┬───────────────────────────────────────┘
       │ Cancelado → exit 1 (sin efectos)
       │ Confirmado
       ▼
┌──────────────────┐
│ INSTALL_TRAP     │ ← Solo CRITICAL: instalar trap ERR/EXIT
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ SELECT_CHANNEL   │ ← --git | menú interactivo | auto-detect
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ REINSTALL_CHECK  │ ← ¿ya instalado? → aviso + [y/N]
└──────┬───────────┘
       │ Cancelado → exit 1
       │ Confirmado (o no instalado)
       ▼
┌──────────────────┐
│ INSTALL_PACMAN   │ ← our-pac -S <pkgs> --noconfirm
└──────┬───────────┘
       │ Fallo → exit 1
       │ Éxito (o sin paquetes)
       ▼
┌──────────────────┐
│ INSTALL_AUR      │ ← our-aur -S <aur_pkgs>
└──────┬───────────┘
       │ Fallo → exit 3
       │ Éxito (o sin paquetes AUR)
       ▼
┌──────────────────┐
│ POST_DEPLOY      │ ← bash -c "$script" (como $SUDO_USER)
└──────┬───────────┘
       │ Fallo → exit 4 (paquetes instalados, NO registrar)
       │ Éxito (o null)
       ▼
┌──────────────────┐
│ REGISTER         │ ← sysyaml_add_pack() — atomic write
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ UNINSTALL_TRAP   │ ← Solo CRITICAL: trap - ERR EXIT
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│    SUCCESS       │ ← log_info + exit 0
└──────────────────┘
```

### 6.3 FSM de Desinstalación de Pack

```
START: our-dots -R <id> [--force]
  │
  ├─ EUID != 0 → die "requires root"
  │
  ├─ !sysyaml_is_installed && !--force → die "not installed"
  │
  ├─ find_manifest → No encontrado:
  │     sysyaml_remove_pack(id)
  │     return 0   (mensaje: eliminación manual del manifest)
  │
  ├─ Confirmación [y/N] → Cancelado → exit 1
  │
  ├─ REMOVE_AUR_PKGS → best-effort (fallo = warning, no fatal)
  │
  ├─ REMOVE_PACMAN_PKGS → best-effort (fallo = warning, no fatal)
  │
  ├─ POST_REMOVE (como $SUDO_USER) → best-effort (fallo = warning)
  │
  └─ sysyaml_remove_pack(id) → exit 0
```

---

## 7. Contratos: Pre/Post Condiciones

### 7.1 `cmd_install`

**Precondiciones:**
- `EUID == 0` (root).
- `id` es un string no vacío.
- `our-pac` y `our-aur` están disponibles en `$PATH`.
- `MANIFEST_DIR` existe (o `find_manifest` retorna desde `REPOS_DIR`).
- Si `--git`: el manifest define `variants.git`.
- Si pack CRITICAL sin `--noconfirm`: el usuario tipea exactamente `"yes"`.
- Si pack CRITICAL con `--noconfirm`: `OUROBOROS_ALLOW_CRITICAL=1` está en el entorno.

**Postcondiciones en éxito (exit 0):**
- Todos los paquetes `variants.<channel>.packages` están instalados via pacman.
- Todos los paquetes `variants.<channel>.aur` están instalados via AUR.
- `post_deploy` completó con exit 0 (o era `null`).
- `system.yaml.dots_packs` contiene una entrada con `id`, `channel`, `installed_version`, `installed_at`, `origin`.
- Log escrito en `/var/log/our-dots/<id>-<timestamp>.log`.

**Postcondiciones en fallo:**
- Exit 1: paquetes pacman no instalados. `system.yaml` sin cambios.
- Exit 3: paquetes AUR no instalados. Paquetes pacman pueden estar instalados. `system.yaml` sin cambios.
- Exit 4: `post_deploy` falló. Paquetes instalados. **`system.yaml` sin cambios** (pack no registrado).
- Exit 5 (solo CRITICAL): trap de cleanup ejecutado. Ver §13.3.

**Invariants:**
- `system.yaml` solo se escribe si todos los pasos previos (pacman + AUR + post_deploy) completaron sin error.
- `system.yaml` siempre se escribe de forma atómica (§7.5).
- Pack CRITICAL con `--noconfirm` sin `OUROBOROS_ALLOW_CRITICAL=1` NUNCA instala nada.

### 7.2 `cmd_remove`

**Precondiciones:**
- `EUID == 0`.
- Con `--force` o el pack está registrado en `system.yaml`.

**Postcondiciones en éxito:**
- Paquetes `uninstall.packages` y `uninstall.aur` removidos del sistema (best-effort).
- `post_remove` ejecutado (best-effort, no fatal).
- Entrada eliminada de `system.yaml.dots_packs`.

**Invariant:** La remoción de paquetes es best-effort — un fallo no aborta la operación completa. La entrada en `system.yaml` se elimina de todas formas.

### 7.3 `load_catalog()` (Python)

**Precondiciones:** Ninguna (función pura con respecto al sistema de archivos).

**Postcondiciones:**
- Si `manifest_dir` no existe → retorna `[]` (sin excepción).
- Manifests con estructura YAML inválida → ignorados (sin crash).
- Los manifests válidos se retornan como lista de `DotsPack` en orden alfabético de nombre de archivo.

**Invariant:** La función nunca lanza excepción al llamador. Todos los errores son silenciados internamente.

### 7.4 `packs_for_profile()` (Python)

**Precondiciones:** `profile` es un string (puede ser desconocido).

**Postcondiciones:**
- Retorna sublista de `load_catalog()` donde `profile in pack.profiles`.
- Perfil desconocido → retorna `[]` (sin error).

### 7.5 `sysyaml_add_pack()` — Escritura Atómica

**Precondiciones:** `EUID == 0`. `system.yaml` existe o se creará.

**Algoritmo Python:**

```python
import fcntl, os, time, yaml
from pathlib import Path

SYSYAML = Path("/etc/ouroboros/system.yaml")
LOCK_TIMEOUT = 5.0  # segundos

def sysyaml_add_pack(id, channel, installed_version, installed_at, origin):
    lock_path = SYSYAML.with_suffix(".yaml.lock")
    deadline = time.monotonic() + LOCK_TIMEOUT

    with open(lock_path, "w") as lock_fh:
        # Intentar adquirir lock con timeout
        while True:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "system.yaml is locked by another our-dots process."
                    )
                time.sleep(0.1)

        # Leer estado actual
        doc = {}
        if SYSYAML.exists():
            with SYSYAML.open() as f:
                doc = yaml.safe_load(f) or {}

        # Upsert (reemplazar si ya existe el mismo id)
        packs = doc.setdefault("dots_packs", [])
        packs = [p for p in packs if p.get("id") != id]
        packs.append({
            "id": id,
            "channel": channel,
            "installed_version": installed_version,
            "installed_at": installed_at,
            "origin": origin,
        })
        doc["dots_packs"] = packs

        # Escribir a .tmp
        tmp = SYSYAML.with_suffix(".yaml.tmp")
        with open(tmp, "w") as f:
            yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)

        # Reemplazar atómicamente
        try:
            os.replace(tmp, SYSYAML)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        # Lock liberado al salir del context manager
```

**Postcondiciones:**
- `system.yaml` contiene la entrada del pack (upsert).
- Si el archivo no existía, se crea con schema mínimo.
- La operación es atómica — ningún lector externo verá un estado intermedio.

**Invariant:** Si el proceso muere durante la escritura, el archivo `.tmp` puede quedar en disco. El proceso siguiente lo ignorará (no hay `.tmp` en la lectura).

---

## 8. Manejo de Errores

### 8.1 Tabla de Exit Codes

| Exit Code | Nombre | Descripción | Estado del Sistema |
|-----------|--------|-------------|-------------------|
| 0 | `OK` | Operación completada exitosamente. | Pack instalado/removido. |
| 1 | `ERROR_GENERIC` | Error genérico: pack no encontrado, root requerido, usuario canceló, CRITICAL sin `OUROBOROS_ALLOW_CRITICAL=1`, canal git no disponible. | Sin cambios. |
| 3 | `AUR_FAIL` | Fallo en instalación de paquetes AUR. | Paquetes pacman pueden estar instalados. Pack no registrado. |
| 4 | `POST_DEPLOY_FAIL` | `post_deploy` retornó exit code ≠ 0. | Paquetes instalados. Pack **no** registrado en `system.yaml`. |
| 5 | `CRITICAL_FAIL_CLEANUP` | Fallo durante instalación CRITICAL + trap ejecutado. | Sistema restaurado a estado inmutable (best-effort). |

### 8.2 Mensajes de Error

| Condición | Mensaje | Destino |
|-----------|---------|---------|
| Pack no encontrado | `die "Pack not found: <id>"` | stderr + exit 1 |
| Root requerido | `die "our-dots -S requires root (use sudo)"` | stderr + exit 1 |
| CRITICAL + --noconfirm | `die "CRITICAL pack requires OUROBOROS_ALLOW_CRITICAL=1 for unattended installation."` | stderr + exit 1 |
| Canal git no disponible | `die "Canal git no disponible para <id>. Instalar sin --git para usar canal stable."` | stderr + exit 1 |
| URL no HTTPS | `die "Repository URL must use HTTPS"` | stderr + exit 1 |
| Clone falla | `die "Failed to clone repository: <url>"` | stderr + exit 1 |
| index.yaml no disponible | `die "Failed to fetch index.yaml from <url>"` | stderr + exit 1 |
| system.yaml bloqueado | `RuntimeError: "system.yaml is locked by another our-dots process."` | stderr + exit 1 |
| fallo our-pac | `log_error "pacman install failed. Check <logfile>"` | stderr + exit 1 |
| fallo our-aur | `log_error "AUR install failed. Check <logfile>"` | stderr + exit 3 |
| fallo post_deploy | `log_error "post_deploy failed (exit $?). Check <logfile>"` | stderr + exit 4 |

### 8.3 Recovery por Escenario

| Escenario | Estado del Sistema | Acción del Usuario |
|-----------|-------------------|-------------------|
| Exit 1 (genérico) | Sin cambios | Revisar mensaje de error. |
| Exit 3 (AUR fail) | Paquetes pacman instalados, AUR no | `our-dots -R --force <id>` para limpiar paquetes huérfanos. |
| Exit 4 (post_deploy fail) | Paquetes instalados, pack no registrado | Revisar log. `our-dots -R --force <id>` para limpiar. |
| Exit 5 (CRITICAL cleanup) | Sistema restaurado a read-only (best-effort) | Si cleanup falló: `mount -o remount,ro /` manualmente. Revisar `/etc/pacman.conf.our-dots-bak`. |

---

## 9. Validaciones

### 9.1 Validación de Schema de Manifests Externos

Ejecutada **antes de registrar el repositorio y antes de ejecutar cualquier hook**. Campos validados:

```bash
validate_manifest_schema() {
    local mf="$1"
    local valid=true

    # Campos requeridos
    local id compat profiles
    id=$(yaml_get "$mf" "id" 2>/dev/null || true)
    compat=$(yaml_get "$mf" "compatibility.immutable" 2>/dev/null || true)
    profiles=$(yaml_list "$mf" "compatibility.profiles" 2>/dev/null | head -1 || true)

    [[ -z "$id" ]] && { log_warn "Missing field 'id' in $mf"; valid=false; }
    [[ ! "$compat" =~ ^(low|medium|high|critical)$ ]] && {
        log_warn "Invalid 'compatibility.immutable' value '$compat' in $mf"
        valid=false
    }
    [[ -z "$profiles" ]] && { log_warn "Empty 'compatibility.profiles' in $mf"; valid=false; }

    # Validación adicional para CRITICAL
    if [[ "$compat" == "critical" ]]; then
        local warning critical_actions
        warning=$(yaml_get "$mf" "compatibility.warning" 2>/dev/null || true)
        critical_actions=$(yaml_list "$mf" "compatibility.critical_actions" 2>/dev/null | head -1 || true)

        [[ -z "$warning" || "$warning" == "null" ]] && {
            log_warn "CRITICAL pack missing 'compatibility.warning' in $mf"
            valid=false
        }
        [[ -z "$critical_actions" ]] && {
            log_warn "CRITICAL pack missing 'compatibility.critical_actions' in $mf"
            valid=false
        }
    fi

    # Validar que post_deploy no es un path absoluto
    local pd
    pd=$(yaml_get "$mf" "variants.stable.post_deploy" 2>/dev/null || true)
    [[ "$pd" == /* ]] && { log_warn "post_deploy must not be an absolute path in $mf"; valid=false; }
    pd=$(yaml_get "$mf" "variants.git.post_deploy" 2>/dev/null || true)
    [[ "$pd" == /* ]] && { log_warn "post_deploy must not be an absolute path in $mf"; valid=false; }

    # [I-06] Validar también post_remove
    local pr
    pr=$(yaml_get "$mf" "uninstall.post_remove" 2>/dev/null || true)
    [[ "$pr" == /* ]] && { log_warn "post_remove must not be an absolute path in $mf"; valid=false; }

    [[ "$valid" == true ]]
}
```

**Resultado:** Manifest inválido → warning con path y campos faltantes. El manifest se ignora (no aparece en el catálogo, no se ejecutan hooks). El repositorio puede registrarse de todos modos.

### 9.2 Validación de Canal

```bash
# Validar --git: el manifest debe definir variants.git
if [[ "$git_flag" == true ]]; then
    yaml_get "$mf" "variants.git.version_hint" &>/dev/null || \
        die "Canal git no disponible para $id. Instalar sin --git para usar canal stable."
fi
```

### 9.3 Detección de Conflicto de ID

Cuando el mismo ID existe en múltiples fuentes:

1. **Built-in prevalece** sobre cualquier fuente externa (sin warning).
2. **Entre externos**: el primero registrado en `dots-repos.yaml` prevalece.
3. Misma fuente y mismo ID: imposible (un directorio solo puede tener un archivo por ID).

### 9.4 Validación de URL

```bash
# repo-add: rechazar HTTP simple
[[ "$url" == https://* ]] || die "Repository URL must use HTTPS"
```

### 9.5 Verificación de Compatibilidad de Perfil (TUI)

```python
# dots_profiles.py
def packs_for_profile(profile: str, manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Return packs compatible with the given desktop profile."""
    return [p for p in load_catalog(manifest_dir) if profile in p.profiles]
```

Un pack con `compatibility.profiles: [hyprland]` **no aparece** en la TUI para un usuario con perfil `niri`. El CLI no filtra por perfil — el filtrado es responsabilidad de la TUI.

### 9.6 Validación de `DotsPackConfig` (Python/YAML)

El archivo `install-config.yaml` puede especificar un pack en modo unattended:

```yaml
dots_pack:
  pack: noctalia    # o null para omitir
  channel: stable   # o "git"
```

Reglas de loading (`config.py`):

```python
raw_dots = data.get("dots_pack") or {}
cfg.dots_pack.pack = raw_dots.get("pack") or None
cfg.dots_pack.channel = raw_dots.get("channel") or "stable"
```

- `pack: null` → `dots_pack.pack = None` (omite selección).
- `channel` ausente → default `"stable"`.

---

## 10. Diagramas de Secuencia

### 10.1 Instalación de Pack LOW (happy path)

```
Usuario          our-dots       find_manifest   our-pac    our-aur   system.yaml
  │                │                  │            │          │           │
  │ -S noctalia    │                  │            │          │           │
  │──────────────>│                  │            │          │           │
  │                │ find_manifest(noctalia)       │          │           │
  │                │─────────────────>│            │          │           │
  │                │<─ /path/noctalia.yaml ────────│          │           │
  │                │                  │            │          │           │
  │<─ log_info "Log: /var/log/…" ────│            │          │           │
  │                │                  │            │          │           │
  │<─ prompt [y/N] ──────────────────│            │          │           │
  │ y              │                  │            │          │           │
  │──────────────>│                  │            │          │           │
  │                │ our-pac -S noctalia-shell --noconfirm   │           │
  │                │──────────────────────────────>│         │           │
  │                │<─ exit 0 ──────────────────────│         │           │
  │                │ our-aur -S noctalia-shell (AUR)│         │           │
  │                │──────────────────────────────────────>│  │           │
  │                │<─ exit 0 ───────────────────────────────│           │
  │                │ sysyaml_add_pack(noctalia, stable, …)  │           │
  │                │──────────────────────────────────────────────────>│  │
  │                │<─ OK ──────────────────────────────────────────────│  │
  │<─ log_info "installed successfully" ─────────│            │          │
  │                │                  │            │          │           │
```

### 10.2 Instalación de Pack CRITICAL con confirmación

```
Usuario          our-dots            system.yaml
  │                │                     │
  │ -S omarchy     │                     │
  │──────────────>│                     │
  │                │ find_manifest(omarchy) → OK
  │                │                     │
  │<═ CRITICAL PANEL (panel rojo) ══════│
  │  (warning + critical_actions)        │
  │                │                     │
  │<─ "Type 'yes'…"──────────────────────│
  │ yes            │                     │
  │──────────────>│                     │
  │                │ trap ERR/EXIT → cleanup_critical
  │                │                     │
  │                │ our-pac -S git curl --noconfirm
  │                │                     │
  │                │ post_deploy (bash as $SUDO_USER)
  │                │  └─ git clone omarchy /tmp/omarchy
  │                │  └─ cd /tmp/omarchy && bash install
  │                │                     │
  │                │ sysyaml_add_pack(omarchy, …)
  │                │────────────────────>│
  │                │ trap - ERR EXIT     │
  │<─ "installed successfully" ──────────│
```

### 10.3 Instalación CRITICAL con fallo + cleanup

```
our-dots                     system (/)            system.yaml
  │                               │                    │
  │ [confirm "yes"]               │                    │
  │ trap ERR/EXIT → cleanup       │                    │
  │                               │                    │
  │ our-pac -S git curl → OK      │                    │
  │                               │                    │
  │ post_deploy:                  │                    │
  │   mount -o remount,rw /       │                    │
  │───────────────────────────────>│                   │
  │   editar /etc/pacman.conf      │                   │
  │   FALLO EN MITAD               │                   │
  │                               │                    │
  │ ERR trap activado             │                    │
  │ cleanup_critical():           │                    │
  │   mount -o remount,ro /       │                    │
  │───────────────────────────────>│                   │
  │   restaurar pacman.conf.bak   │                    │
  │   our-pac -R git curl (best-effort)                │
  │   log cleanup                 │                    │
  │ exit 5                        │                    │
  │ (system.yaml sin cambios)     │                   NO WRITE
```

### 10.4 `repo-add` (repositorio Git)

```
Usuario          our-dots          git/HTTPS           REPOS_DIR    dots-repos.yaml
  │                │                   │                   │              │
  │ repo-add name url.git              │                   │              │
  │──────────────>│                   │                   │              │
  │                │ verificar HTTPS   │                   │              │
  │                │ git ls-remote url │                   │              │
  │                │──────────────────>│                   │              │
  │                │<─ OK              │                   │              │
  │                │ git clone --depth=1 url REPOS_DIR/name│              │
  │                │──────────────────────────────────────>│              │
  │                │<─ OK              │                   │              │
  │                │ validate_manifest_schema(*.yaml)      │              │
  │                │──────────────────────────────────────>│              │
  │                │<─ 3 válidos, 0 inválidos              │              │
  │                │ sysyaml_append_repo(name, url, git)   │              │
  │                │──────────────────────────────────────────────────>│  │
  │<─ "registered with 3 valid packs" ─────────────────────────────────│  │
```

### 10.5 Selección de Pack en TUI del Instalador

```
InstallerFSM    TUI.show_dots_pack_selection()    dots_profiles.py
     │                      │                          │
     │ DOTS_PACK entered     │                          │
     │ profile="hyprland"   │                          │
     │──────────────────────>│                          │
     │                       │ packs_for_profile("hyprland")
     │                       │──────────────────────────>│
     │                       │<─ [ml4w, caelestia, …]   │
     │                       │                          │
     │                       │ Select widget:           │
     │                       │ [Ninguno, ML4W, Caelestia, …]
     │                       │                          │
     │<─ {"pack": "ml4w", "channel": "stable"} ────────│
     │                       │                          │
     │ config.dots_pack.pack = "ml4w"
     │ config.dots_pack.channel = "stable"
     │ update_progress(100)
     │ → SECURE_BOOT
```

---

## 11. Configuración y Variables de Entorno

### 11.1 Variables de Entorno

| Variable | Tipo | Descripción |
|----------|------|-------------|
| `OUROBOROS_ALLOW_CRITICAL` | string | Si es `"1"`, permite instalación de packs CRITICAL sin panel de confirmación. Solo para CI/automatización. `--noconfirm` sin esta variable + pack CRITICAL → error. |
| `SUDO_USER` | string | Usuario que invocó `sudo`. Establecido por `sudo`. `post_deploy` y `post_remove` se ejecutan como este usuario. |
| `DOTS_PACK` | string | Pasado por `state_machine.py` a `configure.sh`. ID del pack a instalar, o string vacío si ninguno. |
| `DOTS_CHANNEL` | string | Pasado por `state_machine.py` a `configure.sh`. Canal del pack: `"stable"` o `"git"`. |

### 11.2 Rutas Configurables (Variables Internas)

Estas variables son definidas en el header del script `our-dots`:

| Variable | Valor por Defecto | Descripción |
|----------|-------------------|-------------|
| `MANIFEST_DIR` | `/usr/local/lib/ouroboros/dots/packs` | Directorio de manifests built-in (read-only). |
| `REPOS_DIR` | `/var/lib/ouroboros/dots/repos` | Directorio de repositorios externos (mutable). |
| `REPOS_INDEX` | `/etc/ouroboros/dots-repos.yaml` | Índice de repositorios externos. |
| `SYSYAML` | `/etc/ouroboros/system.yaml` | Archivo de estado del sistema. |
| `LOG_DIR` | `/var/log/our-dots` | Directorio de logs. |

### 11.3 Valores por Defecto

| Parámetro | Valor por Defecto | Descripción |
|-----------|-------------------|-------------|
| Canal de instalación | `stable` | Usado si no se pasa `--git` y el pack solo tiene un canal. |
| `DotsPackConfig.channel` | `"stable"` | Default en Python config; corregido automáticamente si el pack es git-only. |
| `DotsPackConfig.pack` | `None` | No instala pack si no se selecciona. |
| Timeout de lock | 5 segundos | Tiempo máximo de espera por `flock` en `system.yaml`. |

### 11.4 Overrides de Canal en Modo Unattended

El handler `_handle_dots_pack()` en modo unattended corrige el canal si `DotsPackConfig` tiene un valor inconsistente con el manifest:

```python
if pack_id:
    catalog = {p.id: p for p in load_catalog()}
    pack = catalog.get(pack_id)
    if pack:
        if not pack.has_stable and pack.has_git:
            self.config.dots_pack.channel = "git"   # corregir auto
        elif pack.has_stable and not pack.has_git:
            self.config.dots_pack.channel = "stable"
```

> **[M-05] Nota de implementación — Plan de migración `dots_profiles.py`:** La versión actual de `dots_profiles.py` lee campos planos (`compatibility`, `profiles`, `has_stable`, `has_git`) en lugar del schema canónico anidado (`compatibility.immutable`, `compatibility.profiles`, derivados de `variants.*`). Los manifests ya usan el schema canónico (TRD §2.3).
>
> **Plan de migración:**
> 1. Actualizar `DotsPack` dataclass para leer `compatibility.immutable` → `self.compat_level` y derivar `has_stable`/`has_git` de la presencia de claves bajo `variants.*`.
> 2. `load_catalog()` debe parsear con `yaml.safe_load` y mapear al schema TRD §2.3.
> 3. `packs_for_profile()` filtra por `compatibility.profiles` (lista anidada), no por campo plano `profiles`.
> 4. El handler `_handle_dots_pack()` ya usa `pack.has_stable` / `pack.has_git` — funcionará correctamente tras la migración.
> 5. No hay cambios en el formato de manifests: la migración es exclusivamente en el código Python.

---

## 12. Logging

### 12.1 Directorio de Logs

```
/var/log/our-dots/
├── <id>-<YYYYMMDD-HHMMSS>.log              # Log de instalación principal
└── <id>-cleanup-<YYYYMMDD-HHMMSS>.log      # Log de cleanup (CRITICAL fallido)
```

- El directorio se crea automáticamente (`mkdir -p "$LOG_DIR"`) al inicio de cada instalación.
- El path completo del log se informa al usuario **antes** de comenzar la instalación.
- Los logs capturan stdout + stderr de `our-pac`, `our-aur` y los scripts `post_deploy`.

### 12.2 Funciones de Logging

| Función | Color | Destino | Formato | Uso |
|---------|-------|---------|---------|-----|
| `log_info()` | Verde | stdout | `[our-dots] INFO: <msg>` | Progreso normal. |
| `log_warn()` | Amarillo | stderr | `[our-dots] WARNING: <msg>` | Condiciones no fatales. |
| `log_error()` | Rojo | stderr | `[our-dots] ERROR: <msg>` | Errores antes de salir. |
| `die()` | Rojo | stderr | `[our-dots] FATAL: <msg>` | Error fatal + `exit 1`. |

### 12.3 Formato del Log de Instalación

Cada línea en el log de instalación sigue el formato del output de los comandos subyacentes (captura directa de `our-pac`, `our-aur`, `bash`). El log incluye:

```
=== our-dots install: <id> (<channel>) — <YYYY-MM-DD HH:MM:SS> ===
[pacman] ...
[aur] ...
[post_deploy] ...
=== Result: SUCCESS / FAILED (exit <code>) ===
```

### 12.4 Rotación

- En v0.6.1 **no hay rotación automática**. Los logs se acumulan en `/var/log/our-dots/`.
- Los archivos son gestionables via `logrotate` en versiones futuras.
- Política prevista (v0.6.2+): rotación diaria, máximo 10 archivos por pack, compresión gzip.

---

## 13. Seguridad

### 13.1 Restricción de Paths en Hooks

Los hooks `post_deploy` y `post_remove` en manifests **deben ser scripts inline** (strings YAML), no paths absolutos.

Regla de validación:
```bash
[[ "$post_deploy" == /* ]] && log_warn "post_deploy must not be an absolute path"
```

Esto previene que un manifest externo ejecute binarios arbitrarios del sistema referenciados por path. Los scripts inline son inspeccionables por el usuario antes de confirmar.

### 13.2 Solo HTTPS para Repositorios Externos

```bash
[[ "$url" == https://* ]] || die "Repository URL must use HTTPS"
```

HTTP simple es rechazado en `repo-add`. No hay override de esta validación.

### 13.3 Trap de Cleanup para Packs CRITICAL

Instalado **inmediatamente tras confirmación** del usuario (antes de cualquier operación de sistema):

```bash
cleanup_critical() {
    local pack_id="${1:-unknown}"
    local ts
    ts=$(date +%Y%m%d-%H%M%S)
    local cleanup_log="$LOG_DIR/${pack_id}-cleanup-${ts}.log"

    {
        echo "=== CRITICAL cleanup for $pack_id — $ts ==="

        # 1. Restaurar / a read-only si fue remontado
        if mount | grep -q "on / .*rw"; then
            mount -o remount,ro / 2>&1 && echo "OK: remounted / as ro" || \
                echo "WARN: failed to remount /. Run: mount -o remount,ro /"
        fi

        # 2. Restaurar pacman.conf desde backup
        if [[ -f /etc/pacman.conf.our-dots-bak ]]; then
            cp /etc/pacman.conf.our-dots-bak /etc/pacman.conf 2>&1 && \
                echo "OK: pacman.conf restored" || \
                echo "WARN: failed to restore pacman.conf. Backup: /etc/pacman.conf.our-dots-bak"
        fi

        # 3. Intentar revertir paquetes instalados (best-effort)
        if [[ ${#_INSTALLED_PKGS[@]} -gt 0 ]]; then
            our-pac -R "${_INSTALLED_PKGS[@]}" 2>&1 || echo "WARN: could not revert packages"
        fi

        echo "=== Cleanup complete. Exiting with code 5. ==="
    } | tee -a "$cleanup_log" >&2

    exit 5
}
trap 'cleanup_critical "$id"' ERR EXIT
```

**Garantías:**
- Si el remount de `/` falla: mensaje crítico al usuario con instrucciones manuales.
- Si la restauración de `pacman.conf` falla: mensaje crítico con path del backup.
- La reversión de paquetes es best-effort (no fatal).
- El log de cleanup siempre se escribe (si `/var/log/` es accesible).

**Desinstalación del trap:** Inmediatamente tras instalación exitosa:
```bash
trap - ERR EXIT
```

### 13.4 Ejecución de Hooks como `$SUDO_USER`

```bash
local run_user="${SUDO_USER:-$USER}"
if [[ "$run_user" == "root" ]]; then
    bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || exit 4
else
    sudo -u "$run_user" bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || exit 4
fi
```

- Los hooks **nunca corren como root** a menos que el usuario invocara `our-dots` directamente sin `sudo`.
- El mismo patrón aplica para `post_remove`.

### 13.5 Indicador `[EXTERN]`

Todos los packs provenientes de `REPOS_DIR` se marcan con `[EXTERN]` en:

1. `our-dots list` — columna NAME.
2. `our-dots -Si <id>` — nombre del pack y línea de origen.
3. Aviso previo a instalación (no suprimible via flag):

```
[our-dots] WARNING: This pack is from an external repository not audited by the ouroborOS project.
```

### 13.6 Validación de Schema Pre-Ejecución

Para manifests externos, la validación de schema (§9.1) es **obligatoria y previa** a cualquier ejecución de hook. Un manifest con schema inválido jamás ejecuta `post_deploy` o `post_remove`.

### 13.7 Campo `signature` (Reservado)

El campo `signature: null` está reservado para firma criptográfica futura. En v0.6.1:
- Siempre es `null`.
- Manifests con `signature` no nula son aceptados sin verificación (la verificación es futura).
- En versiones futuras, `signature` contendrá la firma GPG/minisign del manifest.

### 13.8 Política CRITICAL y `OUROBOROS_ALLOW_CRITICAL=1`

| Escenario | Comportamiento |
|-----------|---------------|
| Pack CRITICAL + sin flags | Panel rojo + tipear `"yes"` |
| Pack CRITICAL + `--noconfirm` | **Error** (exit 1). Sin instalación. |
| Pack CRITICAL + `OUROBOROS_ALLOW_CRITICAL=1` | Sin panel, procede directamente |
| Pack CRITICAL + `--noconfirm` + `OUROBOROS_ALLOW_CRITICAL=1` | Sin panel, procede directamente |

`OUROBOROS_ALLOW_CRITICAL=1` es exclusivo para CI y automatización. No hay otra forma de instalar packs CRITICAL en modo no-interactivo.

---

## 14. Glosario

| Término | Definición |
|---------|-----------|
| **built-in** | Pack incluido en el catálogo oficial de ouroborOS, distribuido dentro del ISO en `MANIFEST_DIR`. Read-only. |
| **canal git** | Canal de distribución que apunta al último commit del repositorio del pack. Identificado como `git` en manifests, `system.yaml`, y CLI. |
| **canal stable** | Canal de distribución que apunta a una versión etiquetada o release estable del pack. |
| **compatibility level** | Nivel de impacto de un pack sobre el sistema inmutable. Valores: `low`, `medium`, `high`, `critical`. |
| **CRITICAL** | Pack cuya instalación requiere acciones que modifican el sistema raíz de forma temporal (remount rw, edición de `/etc`). Requiere confirmación explícita `"yes"` o `OUROBOROS_ALLOW_CRITICAL=1`. |
| **DOTS_PACK** | Estado en la FSM del instalador (`state_machine.py`) que gestiona la selección opcional de pack de dotfiles. Posición: entre DESKTOP y SECURE_BOOT. |
| **DotsPackConfig** | Dataclass Python en `config.py` que persiste la selección de pack durante la instalación. Campos: `pack` (str\|None), `channel` (str). |
| **DotsPack** | Dataclass Python en `dots_profiles.py` que representa un pack del catálogo tal como lo consume la TUI del instalador. |
| **EXTERN** | Prefijo visual `[EXTERN]` que indica que un pack proviene de un repositorio externo no auditado por ouroborOS. |
| **find_manifest()** | Función Bash que localiza el archivo `.yaml` de un pack. Prioridad: built-in > externos (en orden de registro). |
| **hook** | Script inline (string en el YAML) ejecutado tras instalación (`post_deploy`) o desinstalación (`post_remove`). Corre como `$SUDO_USER`. |
| **index.yaml** | Archivo de índice de un repositorio HTTP de manifests. Lista los IDs de packs disponibles. |
| **load_catalog()** | Función Python que carga todos los manifests de `MANIFEST_DIR` y retorna una lista de `DotsPack`. |
| **MANIFEST_DIR** | Directorio de manifests built-in en el ISO. Path: `/usr/local/lib/ouroboros/dots/packs/`. Read-only. |
| **manifest** | Archivo `<id>.yaml` que describe un pack de dotfiles: créditos, compatibilidad, variantes de canal, hooks de instalación/desinstalación. Schema definido en §4.1 (TRD §2.3). |
| **origin** | Campo en `system.yaml.dots_packs` que indica el origen de un pack instalado: `"builtin"` o `"extern"`. |
| **OUROBOROS_ALLOW_CRITICAL=1** | Variable de entorno que habilita instalación de packs CRITICAL en modo no-interactivo. Solo para CI/automatización. |
| **pack** | Conjunto de dotfiles, configuraciones y dependencias que definen un entorno de escritorio Linux, gestionado por `our-dots`. |
| **packs_for_profile()** | Función Python que filtra el catálogo por perfil desktop compatible. Usada por la TUI del instalador. |
| **post_deploy** | Hook ejecutado tras la instalación de paquetes de un pack. Script inline. Corre como `$SUDO_USER`. |
| **post_remove** | Hook ejecutado tras la desinstalación de paquetes. Script inline. Corre como `$SUDO_USER`. |
| **REPOS_DIR** | Directorio donde se almacenan los manifests de repositorios externos. Path: `/var/lib/ouroboros/dots/repos/`. Mutable. |
| **REPOS_INDEX** | Archivo de índice de repositorios externos. Path: `/etc/ouroboros/dots-repos.yaml`. |
| **SUDO_USER** | Variable de entorno con el nombre del usuario original que invocó `sudo`. |
| **system.yaml** | Archivo de configuración declarativa de ouroborOS. Path: `/etc/ouroboros/system.yaml`. Fuente de verdad del estado del sistema. Clave `dots_packs` registra packs instalados. |
| **trap de cleanup** | Trap Bash `ERR`/`EXIT` instalado para packs CRITICAL que garantiza restauración del sistema (remount ro, pacman.conf backup) en caso de fallo. |
| **upsert** | Operación que inserta una nueva entrada o reemplaza la existente con el mismo `id` en `system.yaml.dots_packs`. |
| **variants** | Sección del manifest que define los canales de distribución disponibles para un pack (`stable`, `git`). |
| **version_hint** | Campo descriptivo de la versión de un canal en el manifest (e.g., `"v4 (stable)"`, `"git (bleeding edge)"`). Usado como `installed_version` en `system.yaml`. |

---

## 15. Referencias Cruzadas

### 15.1 Mapeo PRD (User Stories) → SPEC

| PRD US | SPEC Sección |
|--------|-------------|
| US-01 Descubrir packs | §3.2 `list`, §5.1 |
| US-02 Ver info detallada | §3.2 `-Si`, §5.2 |
| US-03 Instalar pack stable | §3.2 `-S`, §5.3, §6.2 |
| US-04 Instalar pack git | §3.2 `-S --git`, §5.3, §11.3 |
| US-05 Pack CRITICAL con confirmación | §3.3 CRITICAL, §5.3, §6.2, §13.3 |
| US-06 Eliminar pack | §3.2 `-R`, §5.4, §6.3 |
| US-07 Consultar instalados | §3.2 `-Q`, §5.5 |
| US-08 Buscar por patrón | §3.2 `-Qs`, §5.5 |
| US-09 Actualizar packs | §3.2 `-Su`, §5.6 |
| US-10 Agregar repo externo | §3.3 `repo-add`, §5.7 |
| US-11 Eliminar repo externo | §3.3 `repo-remove`, §5.8 |
| US-12 Listar repositorios | §3.3 `repo-list`, §5.9 |
| US-13 Actualizar repos | §3.3 `repo-update`, §5.9 |
| US-14 Instalar sin interacción | §3.2 `--noconfirm`, §11.1 |
| US-15 Ver versión | §3.4 `--version` |
| US-16 Ver ayuda | §3.4 `--help` |
| US-17 Estado en info pack | §3.2 `-Si`, §5.2 |
| US-18 Pack HIGH con aviso simple | §3.3 HIGH flow, §5.3 |
| US-19 Pack durante instalación | §6.1, §9.6 |
| US-20 Pack de repo externo | §5.3, §7.6, §9.1 |
| US-21 Log de instalación | §12.1, §12.3 |
| US-22 Catálogo filtrado por perfil | §9.5, §6.1 |

### 15.2 Mapeo PRD (Casos de Uso) → SPEC

| PRD CU | SPEC Sección |
|--------|-------------|
| CU-01 Exploración del catálogo | §3.2 `list`, §5.1, §10.1 |
| CU-02 Consulta de info de pack | §3.2 `-Si`, §5.2 |
| CU-03 Instalación low/medium | §5.3, §6.2, §7.1 |
| CU-04 Instalación HIGH | §3.3 HIGH, §5.3 |
| CU-05 Instalación CRITICAL | §3.3 CRITICAL, §5.3, §13.3, §10.2, §10.3 |
| CU-06 Desinstalación | §5.4, §6.3, §7.2 |
| CU-07 Consulta instalados | §5.5 |
| CU-08 Búsqueda por patrón | §5.5 |
| CU-09 Actualización | §5.6 |
| CU-10 Alta repo externo (Git) | §5.7, §9.1, §10.4 |
| CU-11 Alta repo externo (HTTP) | §5.7, §4.4 |
| CU-12 Baja repo externo | §5.8 |
| CU-13 Listado de repositorios | §3.3 `repo-list` |
| CU-14 Actualización de repos | §5.9 |
| CU-15 Selección en TUI | §6.1, §10.5 |
| CU-16 Instalación unattended | §3.2 `--noconfirm`, §11.1 |
| CU-17 Fallo de post_deploy | §8.1, §8.3, §7.1 |
| CU-18 Pack ya instalado | §5.3 (reinstall check) |
| CU-19 Carga catálogo Python | §5.10 (load_catalog), §6.1 |
| CU-20 Filtrado por perfil | §9.5 |
| CU-21 Verificación estado system.yaml | §5.5, §7.5 |
| CU-22 Escritura atómica system.yaml | §7.5, §4.2 |
| CU-23 Cleanup CRITICAL | §13.3, §8.3, §10.3 |
| CU-24 Canal git | §3.2 `--git`, §5.3, §9.2 |
| CU-25 Pack de repo externo | §5.3, §9.1, §13.5 |

### 15.3 Mapeo TRD → SPEC

| TRD Sección | SPEC Sección |
|-------------|-------------|
| §1 Arquitectura General | §2 |
| §2.1 DotsPack dataclass | §9.5, §6.1 |
| §2.2 DotsPackConfig dataclass | §9.6, §6.1 |
| §2.3 Schema de Manifest YAML | §4.1 (autoritativo) |
| §2.4 Schema system.yaml dots_packs | §4.2 |
| §2.5 Schema dots-repos.yaml | §4.3 |
| §2.6 Schema index.yaml | §4.4 |
| §3 Flujos de Confirmación | §3.3, §5.3, §6.2 |
| §4 Integración con Snapshots | §13.3, §8.3 |
| §5 Integración our-pac/our-aur | §5.3, §5.4 |
| §6 Comando -Su | §5.6 |
| §7 Sistema de Repositorios | §5.7, §5.8, §5.9, §9.1 |
| §8 Wiring con system.yaml | §7.5, §4.2 |
| §9 Integración FSM | §6.1, §9.6, §11.4 |
| §10 Seguridad | §13 |
| §11 Logging y Debug | §12 |
| §12 Exit Codes | §8.1 |
| §13 Dependencias del Sistema | §7.1 (precondiciones) |
| §14 Restricciones Técnicas | §9, §13, §11 |
