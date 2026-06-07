# DESIGN — ouroborOS v0.6.1: Gestor de Dotfiles `our-dots`

**Versión:** 1.2  
**Fecha:** 2026-06-07  
**Autor:** ouroborOS dev team  
**Estado:** Borrador (Ciclo 2 aplicado)  
**Referencias:** PRD v1.1 · TRD v1.2 · SPEC v1.1

---

## Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Estructura de Archivos](#2-estructura-de-archivos)
3. [CLI (`our-dots`)](#3-cli-our-dots)
4. [Módulo Python (`dots_profiles.py`)](#4-módulo-python-dots_profilespy)
5. [FSM del Instalador — Estado `DOTS_PACK`](#5-fsm-del-instalador--estado-dots_pack)
6. [Manifests](#6-manifests)
7. [Persistencia](#7-persistencia)
8. [Flujos de Datos](#8-flujos-de-datos)
9. [Seguridad](#9-seguridad)
10. [Testing](#10-testing)
11. [Internacionalización](#11-internacionalización)
12. [Accesibilidad](#12-accesibilidad)
13. [Rendimiento](#13-rendimiento)
14. [Dependencias](#14-dependencias)
15. [Glosario](#15-glosario)
16. [Referencias Cruzadas](#16-referencias-cruzadas)

---

## 1. Visión General

`our-dots` es el gestor de packs de dotfiles de ouroborOS v0.6.1. Sigue el patrón de la familia `our-*` (interfaz estilo pacman, delegación a `our-pac`/`our-aur`, escritura declarativa en `system.yaml`) y está diseñado explícitamente para sistemas con raíz de solo lectura (Btrfs read-only).

### 1.1 Diagrama de Componentes

```
┌───────────────────────────────────────────────────────────────────────┐
│                       Usuario / Instalador TUI                         │
└──────────────────────────────┬────────────────────────────────────────┘
                               │ CLI / Python API
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       our-dots (Bash CLI)                             │
│  /usr/local/bin/our-dots                                              │
│                                                                       │
│  cmd_list · cmd_info · cmd_install · cmd_remove · cmd_query           │
│  cmd_search · cmd_upgrade · cmd_repo_{add,remove,list,update}         │
│                                                                       │
│  Helpers internos:                                                    │
│    yaml_get · yaml_list · find_manifest · derive_channels             │
│    sysyaml_add_pack · sysyaml_remove_pack · sysyaml_is_installed      │
│    sysyaml_get_field · sysyaml_get_version · sysyaml_append_repo      │
│    sysyaml_remove_repo · validate_manifest_schema · compat_badge      │
│    show_critical_panel · cleanup_critical                             │
│    log_info · log_warn · log_error · die                              │
└────┬────────────┬─────────────────┬──────────────────────┬───────────┘
     │            │                 │                      │
     ▼            ▼                 ▼                      ▼
┌─────────┐ ┌──────────┐  ┌─────────────────┐  ┌──────────────────────┐
│MANIFEST │ │ REPOS    │  │  system.yaml    │  │  our-pac / our-aur   │
│  _DIR   │ │  _DIR    │  │ /etc/ouroboros/ │  │  (instalación de     │
│(builtin)│ │(externos)│  │ (fuente verdad) │  │   paquetes)          │
│read-only│ │ mutable  │  │ flock + atomic  │  └──────────────────────┘
└─────────┘ └──────────┘  └─────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│              dots_profiles.py (módulo Python)                         │
│              src/installer/dots_profiles.py                           │
│                                                                       │
│  DotsPack · load_catalog() · packs_for_profile()                      │
│  Consumido por el instalador Textual TUI (estado DOTS_PACK)           │
└──────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│              InstallerFSM (state_machine.py)                          │
│              Estado DOTS_PACK: DESKTOP → DOTS_PACK → SECURE_BOOT     │
│              InstallerConfig.dots_pack (DotsPackConfig)               │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Tabla de Componentes

| Componente | Tipo | Ubicación | Responsabilidad |
|------------|------|-----------|-----------------|
| `our-dots` | Bash 5+ script | `/usr/local/bin/our-dots` | CLI principal: parseo de manifests, flujos de confirmación, delegación a `our-pac`/`our-aur`, escritura en `system.yaml`. |
| `MANIFEST_DIR` | Directorio read-only | `/usr/local/lib/ouroboros/dots/packs/` | Manifests built-in del ISO. No mutables en el sistema instalado. |
| `REPOS_DIR` | Directorio mutable | `/var/lib/ouroboros/dots/repos/` | Manifests de repositorios externos clonados o descargados. |
| `REPOS_INDEX` | Archivo YAML | `/etc/ouroboros/dots-repos.yaml` | Índice de repositorios externos (nombre, URL, tipo, fecha). |
| `system.yaml` | Archivo YAML | `/etc/ouroboros/system.yaml` | Fuente de verdad del sistema. Clave `dots_packs` registra estado instalado. |
| `dots_profiles.py` | Python 3.11+ | `src/installer/dots_profiles.py` | Carga el catálogo para el instalador TUI. |
| `DotsPackConfig` | dataclass Python | `src/installer/config.py` | Selección de pack en la configuración del instalador. |
| `InstallerFSM` | Python | `src/installer/state_machine.py` | Estado `DOTS_PACK` en la FSM del instalador. |
| `LOG_DIR` | Directorio | `/var/log/our-dots/` | Logs de instalación/remoción por pack. |

### 1.3 Decisiones de Diseño

| Decisión | Justificación |
|----------|---------------|
| CLI en Bash | Consistencia con toda la familia `our-*`. No introduce dependencias de runtime adicionales para el binario principal. |
| Manifests en YAML | Legible por humanos, validable, compatible con `system.yaml`. El schema es anidado (`credits.*`, `compatibility.*`, `variants.*`) para evitar colisiones de claves. |
| Módulo Python separado (`dots_profiles.py`) | El instalador TUI es Python puro (Textual). Un módulo Python que parsea los mismos manifests YAML evita duplicar lógica en el script Bash. |
| `system.yaml` como fuente de verdad | No hay base de datos propia. Consistente con el resto del ecosistema `our-*`. |
| Escritura atómica con `flock` + `os.replace` | Previene corrupción de `system.yaml` ante escrituras concurrentes o fallos mid-write. `os.replace` mapea a `rename(2)`, que es atómica en el mismo filesystem. |
| `post_deploy` como script inline | Previene que manifests externos referencien binarios arbitrarios del sistema mediante paths absolutos. El script es inspeccionable antes de confirmar. |
| Solo HTTPS para repos externos | Previene ataques MITM en descarga de manifests. Sin override. |

---

## 2. Estructura de Archivos

### 2.1 Layout del Filesystem

```
/
├── usr/
│   └── local/
│       ├── bin/
│       │   └── our-dots                    # CLI principal (Bash)
│       └── lib/
│           └── ouroboros/
│               └── dots/
│                   └── packs/              # MANIFEST_DIR (read-only)
│                       ├── ml4w.yaml
│                       ├── noctalia.yaml
│                       ├── caelestia.yaml
│                       ├── illogical-impulse.yaml
│                       ├── omarchy.yaml
│                       ├── ambxst.yaml
│                       └── danklinux.yaml
├── etc/
│   └── ouroboros/
│       ├── system.yaml                     # Fuente de verdad (mutable)
│       ├── system.yaml.lock                # Advisory lock para escritura
│       └── dots-repos.yaml                 # Índice de repos externos
├── var/
│   ├── lib/
│   │   └── ouroboros/
│   │       └── dots/
│   │           └── repos/                  # REPOS_DIR (mutable)
│   │               └── <repo-name>/
│   │                   ├── index.yaml      # Solo repos HTTP
│   │                   └── <id>.yaml       # Manifests externos
│   └── log/
│       └── our-dots/                       # LOG_DIR
│           ├── <id>-<YYYYMMDD-HHMMSS>.log
│           └── <id>-cleanup-<YYYYMMDD-HHMMSS>.log
└── src/
    └── installer/
        ├── dots_profiles.py                # Módulo Python (dev path)
        ├── config.py                       # DotsPackConfig dataclass
        └── state_machine.py               # Handler DOTS_PACK
```

### 2.2 Permisos y Ownership

| Ruta | Permisos | Owner | Notas |
|------|----------|-------|-------|
| `/usr/local/bin/our-dots` | `0755` | `root:root` | Executable. Parte del ISO. |
| `/usr/local/lib/ouroboros/dots/packs/` | `0755` | `root:root` | Directorio read-only post-instalación. |
| `/usr/local/lib/ouroboros/dots/packs/*.yaml` | `0644` | `root:root` | Manifests built-in. No modificables. |
| `/etc/ouroboros/system.yaml` | `0644` | `root:root` | Legible por todos. Solo `our-dots` con root escribe. |
| `/etc/ouroboros/system.yaml.lock` | `0600` | `root:root` | Lock file. No debe ser legible por usuarios. |
| `/etc/ouroboros/dots-repos.yaml` | `0644` | `root:root` | Legible por todos. Requiere root para modificar. |
| `/var/lib/ouroboros/dots/repos/` | `0755` | `root:root` | Mutable. Requiere root para modificar contenido. |
| `/var/log/our-dots/` | `0755` | `root:root` | Directorio de logs. Creado automáticamente. |
| `/var/log/our-dots/*.log` | `0644` | `root:root` | Legibles por usuarios no-root para diagnóstico. |

### 2.3 Montaje y Compatibilidad con Raíz Read-Only

Los paths bajo `/usr/` son parte del sistema raíz montado como read-only (Btrfs). Solo los paths bajo `/etc/ouroboros/`, `/var/lib/ouroboros/` y `/var/log/` son mutables:

- `/usr/local/bin/our-dots` → parte del sistema inmutable.
- `/usr/local/lib/ouroboros/dots/packs/` → inmutable.
- `/etc/ouroboros/` → mutable via subvolumen `@etc`.
- `/var/lib/ouroboros/` → mutable via subvolumen `@var`.
- `/var/log/` → mutable via subvolumen `@var`.

Los packs CRITICAL que requieren modificar `/etc/pacman.conf` deben remontar `/` temporalmente como lectura-escritura. Este remount es explícitamente documentado en el panel CRITICAL y revertido por el trap de cleanup en caso de fallo.

---

## 3. CLI (`our-dots`)

### 3.1 Estructura del Script

El script `our-dots` se organiza en las siguientes secciones:

```
1. Header + set options
2. Variables de configuración (rutas)
3. Funciones de logging
4. Helpers YAML (yaml_get, yaml_list)
5. Helpers system.yaml (sysyaml_*)
6. find_manifest() + derive_channels()
7. validate_manifest_schema()
8. Funciones de UI (show_critical_panel, compat_badge, print_table_*)
9. cleanup_critical() + trap
10. Comandos principales (cmd_*)
11. Router principal (main / case "$cmd")
```

### 3.2 Header del Script

```bash
#!/usr/bin/env bash
# our-dots — ouroborOS dotfiles pack manager
# Part of the our-* tool family. Requires root for install/remove.
set -euo pipefail

readonly VERSION="0.6.1"
readonly MANIFEST_DIR="/usr/local/lib/ouroboros/dots/packs"
readonly REPOS_DIR="/var/lib/ouroboros/dots/repos"
readonly REPOS_INDEX="/etc/ouroboros/dots-repos.yaml"
readonly SYSYAML="/etc/ouroboros/system.yaml"
readonly LOG_DIR="/var/log/our-dots"
```

> **Crítico:** `set -o pipefail` (incluido en `set -euo pipefail`) es obligatorio. Sin él, pipelines como `cmd 2>&1 | tee -a "$logfile" || exit N` obtienen el exit code de `tee` (siempre 0), ignorando silenciosamente fallos de `our-pac`, `our-aur` o `post_deploy`. (SPEC §5.0 C-01)

### 3.3 Funciones de Logging

```bash
# NO_COLOR support (M-03): set variables before log functions are called.
if [[ "${NO_COLOR:-}" == "1" ]]; then
    _C_GREEN="" _C_YELLOW="" _C_RED="" _C_RESET=""
else
    _C_GREEN="\033[0;32m" _C_YELLOW="\033[0;33m"
    _C_RED="\033[0;31m"   _C_RESET="\033[0m"
fi

# Destino: stdout. Uso: progreso normal.
log_info()  { echo -e "${_C_GREEN}[our-dots] INFO:${_C_RESET} $*"; }

# Destino: stderr. Uso: condiciones no fatales.
log_warn()  { echo -e "${_C_YELLOW}[our-dots] WARNING:${_C_RESET} $*" >&2; }

# Destino: stderr. Uso: errores antes de salir.
log_error() { echo -e "${_C_RED}[our-dots] ERROR:${_C_RESET} $*" >&2; }

# Destino: stderr. Error fatal + exit 1.
die()       { echo -e "${_C_RED}[our-dots] FATAL:${_C_RESET} $*" >&2; exit 1; }
```

### 3.4 Helpers YAML

El script no puede usar Python para cada consulta (overhead). Se implementan helpers ligeros basados en `python3 -c` inline:

```bash
# Obtiene un campo escalar de un archivo YAML.
# Uso: yaml_get <archivo> <clave.anidada>
# Retorna: string o falla con exit non-zero si el campo no existe.
# [C-01] Usa heredoc + sys.argv — evita inyección de shell en $file/$key.
yaml_get() {
    local file="$1" key="$2"
    python3 - "$file" "$key" <<'PYEOF' 2>/dev/null
import yaml, sys
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f) or {}
keys = sys.argv[2].split('.')
val = d
for k in keys:
    if isinstance(val, dict):
        val = val.get(k)
    else:
        val = None
    if val is None:
        sys.exit(1)
print('' if val is None else val)
PYEOF
}

# Obtiene una lista de valores de un archivo YAML.
# Uso: yaml_list <archivo> <clave.anidada>
# Retorna: una línea por elemento.
# [C-01] Usa heredoc + sys.argv — evita inyección de shell en $file/$key.
yaml_list() {
    local file="$1" key="$2"
    python3 - "$file" "$key" <<'PYEOF' 2>/dev/null
import yaml, sys
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f) or {}
keys = sys.argv[2].split('.')
val = d
for k in keys:
    if isinstance(val, dict):
        val = val.get(k)
    elif isinstance(val, list) and k.endswith(']'):
        # soporte simple para repos[].name
        field = k.split('[')[0]
        val = [item.get(field.split('.')[-1]) for item in val if isinstance(item, dict)]
        break
    else:
        val = None
    if val is None:
        break
if isinstance(val, list):
    for item in val:
        if item is not None:
            print(item)
elif val is not None:
    print(val)
PYEOF
}
```

> **Nota de implementación:** Para expresiones de tipo `repos[].name`, `yaml_list` usa un parser inline simple. Si la complejidad de queries crece, considerar migrar a un helper Python dedicado en `/usr/local/lib/ouroboros/yaml_helper.py`.

### 3.5 Helpers `system.yaml`

```bash
# Verifica si un pack está registrado en system.yaml.
# Retorna 0 (instalado) o 1 (no instalado).
# [C-01] Usa heredoc + sys.argv — evita inyección de shell en $SYSYAML/$id.
sysyaml_is_installed() {
    local id="$1"
    [[ -f "$SYSYAML" ]] || return 1
    python3 - "$SYSYAML" "$id" <<'PYEOF' 2>/dev/null
import yaml, sys
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f) or {}
ids = [p.get('id') for p in d.get('dots_packs', [])]
sys.exit(0 if sys.argv[2] in ids else 1)
PYEOF
}

# Obtiene un campo específico de la entrada de un pack en system.yaml.
# Uso: sysyaml_get_field <id> <campo>
# [C-01] Usa heredoc + sys.argv — evita inyección de shell en $SYSYAML/$id/$field.
sysyaml_get_field() {
    local id="$1" field="$2"
    python3 - "$SYSYAML" "$id" "$field" <<'PYEOF' 2>/dev/null
import yaml, sys
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f) or {}
for p in d.get('dots_packs', []):
    if p.get('id') == sys.argv[2]:
        print(p.get(sys.argv[3], ''))
        sys.exit(0)
sys.exit(1)
PYEOF
}

# Obtiene la versión instalada de un pack (para columna STATUS en list).
# [M-02] Fallback explícito cuando channel o version están vacíos.
sysyaml_get_version() {
    local id="$1"
    local ch ver
    ch=$(sysyaml_get_field "$id" "channel" 2>/dev/null || echo "")
    ver=$(sysyaml_get_field "$id" "installed_version" 2>/dev/null || echo "")
    if [[ -z "$ver" && -z "$ch" ]]; then
        echo "(unknown)"
    elif [[ -z "$ver" ]]; then
        echo "(${ch})"
    else
        echo "${ver} (${ch})"
    fi
}

# Agrega o actualiza (upsert) la entrada de un pack en system.yaml.
# Escritura atómica: flock + .tmp + os.replace.
# Uso: sysyaml_add_pack <id> <channel> <version_hint> <date> <origin>
sysyaml_add_pack() {
    local id="$1" channel="$2" version="$3" date="$4" origin="$5"
    python3 - "$id" "$channel" "$version" "$date" "$origin" <<'EOF'
import fcntl, os, time, yaml, sys
from pathlib import Path

SYSYAML = Path("/etc/ouroboros/system.yaml")
LOCK_TIMEOUT = 5.0
id_, channel, version, date, origin = sys.argv[1:]
lock_path = SYSYAML.with_suffix(".yaml.lock")
deadline = time.monotonic() + LOCK_TIMEOUT

with open(lock_path, "w") as lock_fh:
    while True:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                print("system.yaml is locked by another our-dots process.", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.1)

    doc = {}
    if SYSYAML.exists():
        with SYSYAML.open() as f:
            doc = yaml.safe_load(f) or {}

    packs = doc.setdefault("dots_packs", [])
    packs = [p for p in packs if p.get("id") != id_]
    packs.append({
        "id": id_,
        "channel": channel,
        "installed_version": version,
        "installed_at": date,
        "origin": origin,
    })
    doc["dots_packs"] = packs

    tmp = SYSYAML.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
    try:
        os.replace(tmp, SYSYAML)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
EOF
}

# Elimina la entrada de un pack de system.yaml (escritura atómica).
sysyaml_remove_pack() {
    local id="$1"
    python3 - "$id" <<'EOF'
import fcntl, os, time, yaml, sys
from pathlib import Path

SYSYAML = Path("/etc/ouroboros/system.yaml")
LOCK_TIMEOUT = 5.0
id_ = sys.argv[1]
lock_path = SYSYAML.with_suffix(".yaml.lock")
deadline = time.monotonic() + LOCK_TIMEOUT

with open(lock_path, "w") as lock_fh:
    while True:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                print("system.yaml is locked.", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.1)

    if not SYSYAML.exists():
        sys.exit(0)
    with SYSYAML.open() as f:
        doc = yaml.safe_load(f) or {}
    packs = [p for p in doc.get("dots_packs", []) if p.get("id") != id_]
    doc["dots_packs"] = packs
    tmp = SYSYAML.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
    try:
        os.replace(tmp, SYSYAML)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
EOF
}

# Registra o actualiza (upsert) un repositorio en dots-repos.yaml.
# Invariant: no puede existir dos entradas con el mismo 'name'.
sysyaml_append_repo() {
    local name="$1" url="$2" type="$3" date="$4"
    python3 - "$name" "$url" "$type" "$date" <<'EOF'
import fcntl, os, time, yaml, sys
from pathlib import Path

REPOS_INDEX = Path("/etc/ouroboros/dots-repos.yaml")
LOCK_TIMEOUT = 5.0
name, url, type_, date = sys.argv[1:]
lock_path = Path("/etc/ouroboros/dots-repos.yaml.lock")
deadline = time.monotonic() + LOCK_TIMEOUT

with open(lock_path, "w") as lock_fh:
    while True:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                sys.exit(1)
            time.sleep(0.1)

    doc = {"repos": []}
    if REPOS_INDEX.exists():
        with REPOS_INDEX.open() as f:
            doc = yaml.safe_load(f) or {"repos": []}

    repos = doc.get("repos", [])
    repos = [r for r in repos if r.get("name") != name]
    repos.append({"name": name, "url": url, "type": type_, "added_at": date})
    doc["repos"] = repos

    tmp = REPOS_INDEX.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
    os.replace(tmp, REPOS_INDEX)
EOF
}

# Elimina un repositorio de dots-repos.yaml.
sysyaml_remove_repo() {
    local name="$1"
    python3 - "$name" <<'EOF'
import fcntl, os, time, yaml, sys
from pathlib import Path

REPOS_INDEX = Path("/etc/ouroboros/dots-repos.yaml")
LOCK_TIMEOUT = 5.0
name = sys.argv[1]
if not REPOS_INDEX.exists():
    sys.exit(0)
lock_path = Path("/etc/ouroboros/dots-repos.yaml.lock")
deadline = time.monotonic() + LOCK_TIMEOUT

with open(lock_path, "w") as lock_fh:
    while True:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                sys.exit(1)
            time.sleep(0.1)

    with REPOS_INDEX.open() as f:
        doc = yaml.safe_load(f) or {"repos": []}
    repos = [r for r in doc.get("repos", []) if r.get("name") != name]
    doc["repos"] = repos
    tmp = REPOS_INDEX.with_suffix(".yaml.tmp")
    with open(tmp, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)
    os.replace(tmp, REPOS_INDEX)
EOF
}
```

### 3.6 `find_manifest()` y `derive_channels()`

```bash
# Localiza el archivo .yaml de un pack.
# Prioridad: built-in > externos (en orden de registro en dots-repos.yaml).
# Retorna: path al archivo. Falla con exit 1 si no encontrado.
find_manifest() {
    local id="$1"
    # 1. Built-in tiene prioridad absoluta
    local f="${MANIFEST_DIR}/${id}.yaml"
    [[ -f "$f" ]] && { echo "$f"; return 0; }
    # 2. Repositorios externos — orden determinista via dots-repos.yaml
    if [[ -f "$REPOS_INDEX" ]]; then
        local repo_name
        while IFS= read -r repo_name; do
            local f="${REPOS_DIR}/${repo_name}/${id}.yaml"
            [[ -f "$f" ]] && { echo "$f"; return 0; }
        done < <(yaml_list "${REPOS_INDEX}" "repos[].name")
    fi
    return 1
}

# Deriva la cadena de canales disponibles de un manifest.
# Retorna: "stable" | "git" | "stable/git"
# [M-01] Detecta presencia del bloque variants.stable/git (no version_hint).
#         Un pack puede omitir version_hint y aun así tener el canal definido.
derive_channels() {
    local mf="$1"
    local has_stable has_git
    has_stable=$(yaml_get "$mf" "variants.stable" 2>/dev/null && echo "yes" || echo "no")
    has_git=$(yaml_get "$mf" "variants.git" 2>/dev/null && echo "yes" || echo "no")
    if [[ "$has_stable" == "yes" && "$has_git" == "yes" ]]; then
        echo "stable/git"
    elif [[ "$has_stable" == "yes" ]]; then
        echo "stable"
    else
        echo "git"
    fi
}
```

### 3.7 Funciones de Comandos

Las signatures completas de todas las funciones públicas del script:

| Función | Firma | Descripción |
|---------|-------|-------------|
| `cmd_list` | `cmd_list()` | Lista todos los packs del catálogo. |
| `cmd_info` | `cmd_info <id>` | Muestra información detallada de un pack. |
| `cmd_install` | `cmd_install <id> [--git] [--noconfirm]` | Instala un pack. Requiere root. |
| `cmd_remove` | `cmd_remove <id> [--force] [--noconfirm]` | Desinstala un pack. Requiere root. |
| `cmd_query` | `cmd_query [patrón]` | Lista packs instalados (`-Q`) o busca entre instalados. |
| `cmd_search` | `cmd_search [patrón]` | Busca en el catálogo completo (`-Qs`). |
| `cmd_upgrade` | `cmd_upgrade()` | Actualiza todos los packs instalados. Requiere root. |
| `cmd_repo_add` | `cmd_repo_add <nombre> <url>` | Registra un repositorio externo. Requiere root. |
| `cmd_repo_remove` | `cmd_repo_remove <nombre>` | Elimina un repositorio externo. Requiere root. |
| `cmd_repo_list` | `cmd_repo_list()` | Lista repositorios configurados. |
| `cmd_repo_update` | `cmd_repo_update()` | Actualiza manifests de repos externos. Requiere root. |
| `validate_manifest_schema` | `validate_manifest_schema <archivo>` | Valida campos requeridos del manifest. Retorna 0 si válido. |
| `show_critical_panel` | `show_critical_panel <manifest> <id>` | Imprime el panel rojo de confirmación CRITICAL. |
| `cleanup_critical` | `cleanup_critical [id]` | Trap de cleanup para packs CRITICAL fallidos. |

### 3.8 Router Principal

```bash
# [C-03] Auto-corrects --git flag for git-only packs before dispatching to
# cmd_install. This mirrors the FSM auto-correction in _handle_dots_pack()
# (§5.3) and ensures --noconfirm unattended installs never fail on channel.
_autocorrect_channel_flag() {
    local id="${1:-}" args=("${@:2}")
    local mf
    mf=$(find_manifest "$id" 2>/dev/null) || { echo "${args[@]}"; return; }
    local channels
    channels=$(derive_channels "$mf")
    # If git-only and --git not already requested, inject it
    if [[ "$channels" == "git" ]]; then
        local has_git_flag=false
        for a in "${args[@]}"; do [[ "$a" == "--git" ]] && has_git_flag=true; done
        if [[ "$has_git_flag" == "false" ]]; then
            args=("--git" "${args[@]}")
        fi
    fi
    echo "${args[@]}"
}

main() {
    local cmd="${1:-}"
    shift 2>/dev/null || true

    case "$cmd" in
        list)          cmd_list "$@" ;;
        -Si)           cmd_info "$@" ;;
        -S)
            local pack="${1:-}"
            # Auto-correct channel for git-only packs (C-03)
            if [[ -n "$pack" ]]; then
                local corrected
                read -r -a corrected <<< "$(_autocorrect_channel_flag "$@")"
                cmd_install "${corrected[@]}"
            else
                cmd_install "$@"
            fi
            ;;
        -R)            cmd_remove "$@" ;;
        -Q)            cmd_query ;;
        -Qs)           cmd_search "$@" ;;
        -Su)           cmd_upgrade ;;
        repo-add)      cmd_repo_add "$@" ;;
        repo-remove)   cmd_repo_remove "$@" ;;
        repo-list)     cmd_repo_list ;;
        repo-update)   cmd_repo_update ;;
        --version)     echo "our-dots ${VERSION}"; exit 0 ;;
        --help|help)   cmd_help; exit 0 ;;
        "")            cmd_help; exit 0 ;;
        *)             cmd_help; exit 1 ;;
    esac
}

main "$@"
```

### 3.9 Trap de Cleanup CRITICAL

El trap se instala inmediatamente tras la confirmación del usuario para packs CRITICAL y se desinstala tras una instalación exitosa:

```bash
# Array para rastrear paquetes instalados (best-effort para reversión)
_INSTALLED_PKGS=()

cleanup_critical() {
    local pack_id="${1:-unknown}"
    local ts
    ts=$(date +%Y%m%d-%H%M%S)
    local cleanup_log="${LOG_DIR}/${pack_id}-cleanup-${ts}.log"
    # [C-02] mkdir failure (disk full) must not silence cleanup output.
    mkdir -p "$LOG_DIR" || true

    {
        echo "=== CRITICAL cleanup for $pack_id — $ts ==="

        # 1. Restaurar / a read-only si fue remontado
        if mount | grep -q "on / .*rw"; then
            mount -o remount,ro / 2>&1 \
                && echo "OK: remounted / as ro" \
                || echo "WARN: failed to remount /. Run manually: mount -o remount,ro /"
        fi

        # 2. Restaurar pacman.conf desde backup
        if [[ -f /etc/pacman.conf.our-dots-bak ]]; then
            cp /etc/pacman.conf.our-dots-bak /etc/pacman.conf 2>&1 \
                && echo "OK: pacman.conf restored" \
                || echo "WARN: restore failed. Backup at /etc/pacman.conf.our-dots-bak"
        fi

        # 3. Intentar revertir paquetes instalados (best-effort)
        if [[ ${#_INSTALLED_PKGS[@]} -gt 0 ]]; then
            our-pac -R "${_INSTALLED_PKGS[@]}" 2>&1 \
                || echo "WARN: could not revert packages — remove manually"
        fi

        echo "=== Cleanup complete. Exit code: 5. ==="
    # [C-02] || true: tee failure (disk full) must not swallow cleanup msgs.
    #         Fallback to syslog if tee cannot write the log file.
    } | tee -a "$cleanup_log" >&2 || logger -t our-dots \
        "CRITICAL cleanup for $pack_id: log write failed (disk full?)" || true

    exit 5
}
# Instalación del trap — solo CRITICAL, inmediatamente tras confirmación:
# trap 'cleanup_critical "$id"' ERR EXIT
# Desinstalación del trap tras éxito:
# trap - ERR EXIT
```

---

## 4. Módulo Python (`dots_profiles.py`)

### 4.1 Implementación Actual (Estado Actual)

La versión actual en `src/installer/dots_profiles.py` lee campos planos (`compatibility`, `profiles`, `has_stable`, `has_git`) que no existen en los manifests con el schema canónico TRD §2.3. Esto es una brecha conocida documentada en SPEC §11.4 [M-05].

```python
# Estado actual — campos planos (LEGACY, debe migrarse)
pack = DotsPack(
    compatibility=str(data.get("compatibility", "medium")),   # <-- campo plano
    profiles=list(data.get("profiles", [])),                   # <-- campo plano
    has_stable=bool(data.get("has_stable", True)),             # <-- campo plano
    has_git=bool(data.get("has_git", False)),                  # <-- campo plano
    ...
)
```

### 4.2 Implementación Target (Schema Canónico)

Tras la migración (SPEC §11.4 [M-05]), `load_catalog()` debe leer el schema anidado canónico:

```python
"""dots_profiles.py — Dotfiles pack catalog reader for the ouroborOS installer."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# [I-02] Production path (installed system). During development the installer
# runs from source (src/installer/). Override via env var or pass manifest_dir
# explicitly to load_catalog() — the default is the production path.
# Dev: Path(__file__).parent / "dots" / "packs"  (src/installer/dots/packs/)
# Prod: Path("/usr/local/lib/ouroboros/dots/packs")
MANIFEST_DIR = Path(
    os.environ.get("OUR_DOTS_MANIFEST_DIR", "/usr/local/lib/ouroboros/dots/packs")
)


@dataclass
class DotsPack:
    """Represents a dotfiles pack as consumed by the installer TUI.

    Field mapping from manifest YAML (TRD §2.3):
      id                          <- manifest.id
      name                        <- manifest.name
      description                 <- manifest.description
      author                      <- manifest.credits.author
      homepage                    <- manifest.credits.homepage
      compatibility               <- manifest.compatibility.immutable
      profiles                    <- manifest.compatibility.profiles
      has_stable                  <- bool(manifest.variants.stable is not None)
      has_git                     <- bool(manifest.variants.git is not None)
      stable_version_hint         <- manifest.variants.stable.version_hint or ""
      git_version_hint            <- manifest.variants.git.version_hint or ""
    """

    id: str
    name: str
    description: str
    author: str
    homepage: str
    compatibility: str           # "low" | "medium" | "high" | "critical"
    profiles: list[str]
    has_stable: bool
    has_git: bool
    stable_version_hint: str = ""
    git_version_hint: str = ""


def load_catalog(manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Load all pack manifests from manifest_dir.

    Returns empty list (never raises) if:
    - manifest_dir does not exist
    - a manifest file is malformed YAML
    - a manifest lacks required fields

    Manifests are returned in alphabetical order by filename.
    """
    if not manifest_dir.exists():
        return []

    packs: list[DotsPack] = []
    for manifest_path in sorted(manifest_dir.glob("*.yaml")):
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                continue

            compat_block = data.get("compatibility") or {}
            credits_block = data.get("credits") or {}
            variants_block = data.get("variants") or {}
            stable_block = variants_block.get("stable") or {}
            git_block = variants_block.get("git") or {}

            pack = DotsPack(
                id=str(data.get("id", manifest_path.stem)),
                name=str(data.get("name", "")),
                description=str(data.get("description", "")),
                author=str(credits_block.get("author", "")),
                homepage=str(credits_block.get("homepage", "")),
                compatibility=str(compat_block.get("immutable", "medium")),
                profiles=list(compat_block.get("profiles") or []),
                has_stable=bool(stable_block),
                has_git=bool(git_block),
                stable_version_hint=str(stable_block.get("version_hint", "")),
                git_version_hint=str(git_block.get("version_hint", "")),
            )
            packs.append(pack)
        except Exception:  # noqa: BLE001
            continue

    return packs


def packs_for_profile(profile: str, manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Return packs compatible with the given desktop profile.

    Returns empty list for unknown profiles (no error).
    """
    return [p for p in load_catalog(manifest_dir) if profile in p.profiles]
```

### 4.3 Relaciones entre Clases

```
┌──────────────────────────────────────────┐
│              DotsPack                     │
│ + id: str                                 │
│ + name: str                               │
│ + description: str                        │
│ + author: str                             │
│ + homepage: str                           │
│ + compatibility: str                      │   ← "low"|"medium"|"high"|"critical"
│ + profiles: list[str]                     │   ← ["hyprland", "niri"]
│ + has_stable: bool                        │
│ + has_git: bool                           │
│ + stable_version_hint: str               │
│ + git_version_hint: str                  │
└──────────────────────────────────────────┘
         ▲
         │ producida por
┌────────┴─────────────────────────────────┐
│           load_catalog(manifest_dir)      │
│           → list[DotsPack]                │
└────────┬─────────────────────────────────┘
         │ consumida por
         ▼
┌──────────────────────────────────────────┐
│       packs_for_profile(profile)          │
│       → list[DotsPack]                    │
└────────┬─────────────────────────────────┘
         │ consumida por
         ▼
┌──────────────────────────────────────────┐
│  TUI.show_dots_pack_selection(profile)    │   (tui_textual.py)
│  _handle_dots_pack() en state_machine.py  │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│              DotsPackConfig               │   (config.py)
│ + pack: str | None = None                 │
│ + channel: str = "stable"                 │
└──────────────────────────────────────────┘
         ▲
         │ campo de
┌────────┴─────────────────────────────────┐
│           InstallerConfig                 │
│ + dots_pack: DotsPackConfig               │
└──────────────────────────────────────────┘
```

### 4.4 Precondiciones y Postcondiciones

| Función | Precondiciones | Postcondiciones |
|---------|---------------|-----------------|
| `load_catalog(manifest_dir)` | Ninguna (función pura respecto al llamador). | Si `manifest_dir` no existe → `[]`. Manifests inválidos → ignorados. Retorna lista de `DotsPack` en orden alfabético. Nunca lanza excepción. |
| `packs_for_profile(profile, manifest_dir)` | `profile` es string (puede ser desconocido). | Retorna sublista de `load_catalog()` donde `profile in pack.profiles`. Perfil desconocido → `[]`. |

---

## 5. FSM del Instalador — Estado `DOTS_PACK`

### 5.1 Posición en el Flujo Global

```
INIT → NETWORK_SETUP → PREFLIGHT → LOCALE → USER → DESKTOP
     → DOTS_PACK → SECURE_BOOT → PARTITION → FORMAT → INSTALL
     → CONFIGURE → SNAPSHOT → FINISH
```

Progreso global: steps 21–23 de 100. Descripción: `"Selecting dotfiles pack"`.

### 5.2 Definición del Estado en `state_machine.py`

```python
class State(Enum):
    ...
    DESKTOP = auto()
    DOTS_PACK = auto()     # Entre DESKTOP y SECURE_BOOT
    SECURE_BOOT = auto()
    ...

_STATE_PROGRESS: dict[State, tuple[int, int]] = {
    ...
    State.DOTS_PACK: (21, 23),
    ...
}

_STATE_DESCRIPTION: dict[State, str] = {
    ...
    State.DOTS_PACK: "Selecting dotfiles pack",
    ...
}
```

### 5.3 Handler `_handle_dots_pack()` — Implementación Target

La implementación actual en `state_machine.py` **no incluye** la auto-corrección de canal (TRD §9.2 / SPEC §6.1 C-03). La versión target es:

```python
def _handle_dots_pack(self) -> None:
    """DOTS_PACK — optional dotfiles pack selection.

    Skipped silently when the desktop profile is 'minimal'.
    In unattended mode, reads from config.dots_pack directly.
    Auto-corrects channel when pack is single-channel (TRD §9.2).
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

    # Auto-correct channel based on manifest availability (TRD §9.2, SPEC C-03).
    # DotsPackConfig.channel defaults to "stable", but packs like
    # illogical-impulse and ambxst are git-only — installation would fail
    # if channel is not corrected here.
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

> **Brecha de implementación:** La versión actual en `state_machine.py` omite la sección de auto-corrección de canal. Esta debe añadirse antes del release v0.6.1. Sin ella, packs git-only (`illogical-impulse`, `ambxst`) configurados en modo unattended fallarían con error de canal no disponible.

### 5.4 Tabla de Omisiones del Estado

| Condición | Comportamiento |
|-----------|---------------|
| `profile == "minimal"` | Omisión silenciosa. Log `info`. `dots_pack.pack = None`. |
| TUI: usuario selecciona "Ninguno" | `dots_pack.pack = None`. No se instala pack. |
| Unattended: `config.dots_pack.pack == None` | No se instala pack. FSM avanza a `SECURE_BOOT`. |
| Sin packs compatibles con el perfil | `packs_for_profile()` retorna `[]` → UI muestra solo "Ninguno". |

### 5.5 TUI: `show_dots_pack_selection()`

```python
# En tui_textual.py — firma y comportamiento esperado
def show_dots_pack_selection(self, profile: str) -> dict:
    """Show dotfiles pack selection screen.

    Returns {"pack": <id or None>, "channel": <"stable"|"git">}.
    """
    packs = packs_for_profile(profile)
    # Opciones: [("Ninguno", None)] + [(pack.name, pack.id) for pack in packs]
    # Si pack seleccionado no es None:
    #   - has_stable AND has_git → presentar selección de canal
    #   - solo has_git → channel = "git" sin menú
    #   - solo has_stable → channel = "stable" sin menú
    ...
```

### 5.6 Integración con `configure.sh`

El pack seleccionado se pasa mediante variables de entorno:

```python
env.update({
    "DOTS_PACK": self.config.dots_pack.pack or "",
    "DOTS_CHANNEL": self.config.dots_pack.channel,
})
```

`configure.sh` dentro del chroot:

```bash
if [[ -n "$DOTS_PACK" ]]; then
    channel_flag=""
    [[ "$DOTS_CHANNEL" == "git" ]] && channel_flag="--git"
    our-dots -S "$DOTS_PACK" $channel_flag --noconfirm
fi
```

> **Nota:** El flag `--stable` no existe. El canal stable es el comportamiento por defecto cuando no se pasa `--git`.

---

## 6. Manifests

### 6.1 Schema YAML Canónico

El schema autoritativo es TRD §2.3 (y SPEC §4.1). Esta sección lo documenta desde la perspectiva de implementación.

#### Estructura de Árbol

```yaml
id: <kebab-case>           # Requerido. Único en el catálogo.
name: <string>             # Requerido. Nombre de display.
description: |             # Requerido. Multiline OK.
  <texto>

credits:                   # Requerido como bloque.
  author: <string>         # Requerido.
  homepage: <url-https>    # Requerido.
  docs: <url>              # Opcional.
  repo: <url>              # Opcional.
  license: <spdx|null>     # Opcional.

compatibility:             # Requerido como bloque.
  immutable: <enum>        # Requerido. low|medium|high|critical.
  profiles: [<string>]     # Requerido. Lista no vacía. hyprland|niri.
  note: <string|null>      # Opcional. Texto del aviso HIGH.
  warning: <string|null>   # Requerido si critical.
  critical_actions: [<string>]  # Requerido si critical. Lista no vacía.

requires_root: <bool>      # Opcional. True si el pack requiere remount rw.

variants:                  # Al menos uno de stable/git debe estar presente.
  stable:                  # Opcional.
    packages: [<string>]
    aur: [<string>]
    post_deploy: <script-inline|null>
    version_hint: <string>
  git:                     # Opcional.
    packages: [<string>]
    aur: [<string>]
    post_deploy: <script-inline|null>
    version_hint: <string>

uninstall:                 # Opcional como bloque.
  packages: [<string>]
  aur: [<string>]
  post_remove: <script-inline|null>
  remove_config: <bool>    # Si true, elimina ~/.config/<id>

signature: null            # Reservado. Siempre null en v0.6.1.
```

### 6.2 Invariants de Validación

| Invariant | Verificado en |
|-----------|--------------|
| `id` es kebab-case, minúsculas | `validate_manifest_schema()` |
| `compatibility.immutable` es uno de `low|medium|high|critical` | `validate_manifest_schema()` |
| `compatibility.profiles` es lista no vacía | `validate_manifest_schema()` |
| Si `critical`: `compatibility.warning` no nulo | `validate_manifest_schema()` |
| Si `critical`: `compatibility.critical_actions` no vacío | `validate_manifest_schema()` |
| Al menos uno de `variants.stable` o `variants.git` presente | load time |
| `post_deploy`/`post_remove` no son paths absolutos (`/`) | `validate_manifest_schema()` |
| URLs comienzan con `https://` | load time (manifests externos) |
| ID único en el catálogo | resolución por `find_manifest()` (prioridad built-in) |

> **[I-04] Limitación conocida:** `validate_manifest_schema()` valida un manifest en aislamiento; no detecta IDs duplicados entre manifests en `MANIFEST_DIR`. La unicidad se garantiza por `find_manifest()` vía prioridad built-in > externo — si dos packs tienen el mismo ID, el built-in siempre gana y el externo es inaccesible. Para detección explícita de duplicados en repos externos, se recomienda añadir un pass en `cmd_repo_add` que compruebe si el ID ya existe en `MANIFEST_DIR` antes de registrar el repo.

### 6.3 Manifests Built-in (v0.6.1)

| ID | Compat | Perfiles | Canales | Canal Default |
|----|--------|----------|---------|---------------|
| `ml4w` | medium | hyprland | stable | stable |
| `noctalia` | low | hyprland, niri | stable, git | stable |
| `caelestia` | medium | hyprland | stable, git | stable |
| `illogical-impulse` | critical | hyprland | **git** | **git** (git-only) |
| `omarchy` | critical | hyprland | git | git |
| `ambxst` | medium | hyprland | **git** | **git** (git-only) |
| `danklinux` | high | hyprland, niri | stable | stable |

> **[C-02/C-03]** `illogical-impulse` y `ambxst` son git-only. El canal default debe auto-corregirse a `"git"` (a) en el handler FSM §5.3 y (b) en el router CLI §3.8 `_autocorrect_channel_flag()`. Sin ambas correcciones, el modo unattended falla con "channel not available".
>
> **[M-04]** Los manifests YAML concretos de `illogical-impulse` (incluyendo `compatibility.critical_actions` y `post_deploy`) están documentados en **SPEC §4.5**. Este DESIGN es normativo para el schema; consultar SPEC §4.5 para los valores de ejemplo canónicos de cada pack.

### 6.4 Validación de Schema (`validate_manifest_schema`)

```bash
validate_manifest_schema() {
    local mf="$1"
    local valid=true

    local id compat profiles
    id=$(yaml_get "$mf" "id" 2>/dev/null || true)
    compat=$(yaml_get "$mf" "compatibility.immutable" 2>/dev/null || true)
    profiles=$(yaml_list "$mf" "compatibility.profiles" 2>/dev/null | head -1 || true)

    [[ -z "$id" ]] && { log_warn "Missing field 'id' in $mf"; valid=false; }
    [[ ! "$compat" =~ ^(low|medium|high|critical)$ ]] && {
        log_warn "Invalid 'compatibility.immutable' value '${compat}' in $mf"
        valid=false
    }
    [[ -z "$profiles" ]] && { log_warn "Empty 'compatibility.profiles' in $mf"; valid=false; }

    if [[ "$compat" == "critical" ]]; then
        local warning critical_actions
        warning=$(yaml_get "$mf" "compatibility.warning" 2>/dev/null || true)
        critical_actions=$(yaml_list "$mf" "compatibility.critical_actions" 2>/dev/null | head -1 || true)
        [[ -z "$warning" || "$warning" == "null" ]] && {
            log_warn "CRITICAL pack missing 'compatibility.warning' in $mf"; valid=false
        }
        [[ -z "$critical_actions" ]] && {
            log_warn "CRITICAL pack missing 'compatibility.critical_actions' in $mf"; valid=false
        }
    fi

    # Hooks no pueden ser paths absolutos (seguridad)
    local pd pr
    for key in "variants.stable.post_deploy" "variants.git.post_deploy"; do
        pd=$(yaml_get "$mf" "$key" 2>/dev/null || true)
        [[ "$pd" == /* ]] && {
            log_warn "${key} must not be an absolute path in $mf"; valid=false
        }
    done
    pr=$(yaml_get "$mf" "uninstall.post_remove" 2>/dev/null || true)
    [[ "$pr" == /* ]] && { log_warn "post_remove must not be an absolute path in $mf"; valid=false; }

    [[ "$valid" == true ]]
}
```

---

## 7. Persistencia

### 7.1 `system.yaml` — Clave `dots_packs`

```yaml
dots_packs:
  - id: "noctalia"
    channel: "stable"
    installed_version: "v4 (stable)"
    installed_at: "2026-06-07"
    origin: "builtin"
  - id: "danklinux"
    channel: "stable"
    installed_version: "1.4"
    installed_at: "2026-06-07"
    origin: "builtin"
```

**Campos:**

| Campo | Fuente en el código | Descripción |
|-------|---------------------|-------------|
| `id` | `manifest.id` | Identificador del pack. |
| `channel` | argumento CLI / selección TUI | `"stable"` o `"git"`. |
| `installed_version` | `variants.<channel>.version_hint` | Texto descriptivo de la versión al instalar. |
| `installed_at` | `date +%Y-%m-%d` | Fecha ISO 8601. |
| `origin` | `find_manifest()` path | `"builtin"` si está bajo `MANIFEST_DIR`, `"extern"` si está bajo `REPOS_DIR`. |

### 7.2 Protocolo de Escritura Atómica

Toda escritura en `system.yaml` sigue este protocolo (implementado en `sysyaml_add_pack` y `sysyaml_remove_pack`):

```
1. Abrir system.yaml.lock
2. flock(LOCK_EX | LOCK_NB) con retry hasta 5 segundos
   → Timeout: RuntimeError "system.yaml is locked by another our-dots process."
3. Leer system.yaml actual (yaml.safe_load)
4. Modificar en memoria (upsert por id)
5. Escribir a system.yaml.tmp
6. os.replace(system.yaml.tmp, system.yaml)  ← rename(2), atómica
7. Lock liberado al salir del context manager
```

**Propiedad de atomicidad:** `os.replace` (syscall `rename(2)`) es atómica en el mismo filesystem. Ningún lector verá un estado intermedio. Si el proceso muere durante el paso 5, el `.tmp` queda en disco pero no afecta al archivo principal.

### 7.3 `dots-repos.yaml`

```yaml
repos:
  - name: "community-dots"
    url: "https://github.com/user/community-dots.git"
    type: "git"
    added_at: "2026-06-07"
  - name: "niri-packs"
    url: "https://example.com/niri-packs"
    type: "http"
    added_at: "2026-06-07"
```

Mismo protocolo de escritura atómica que `system.yaml` (lock separado en `dots-repos.yaml.lock`).

**Invariant:** No puede existir más de una entrada con el mismo `name`. `sysyaml_append_repo` hace upsert.

### 7.4 `index.yaml` (Repositorios HTTP)

```yaml
name: "Community Dots"
description: "Packs de la comunidad de ouroborOS"
maintainer: "mantainer@example.com"
packs:
  - my-niri-pack
  - custom-hyprland
```

Cada ID en `packs` requiere un archivo `<id>.yaml` accesible en `<url>/<id>.yaml`. El `index.yaml` en sí no es validado como manifest — solo su lista de `packs`.

### 7.5 Índice de Archivos de Persistencia

| Archivo | Tipo | Propietario | Lock | Operaciones |
|---------|------|-------------|------|-------------|
| `/etc/ouroboros/system.yaml` | YAML mutable | `root:root` 0644 | `system.yaml.lock` | Lectura libre, escritura: flock + atomic |
| `/etc/ouroboros/dots-repos.yaml` | YAML mutable | `root:root` 0644 | `dots-repos.yaml.lock` | Lectura libre, escritura: flock + atomic |
| `/var/lib/ouroboros/dots/repos/<name>/` | Directorio | `root:root` 0755 | — | Creado por `git clone` o `curl` |
| `/var/log/our-dots/` | Directorio | `root:root` 0755 | — | `mkdir -p` en cada operación |

---

## 8. Flujos de Datos

### 8.1 Instalación de Pack LOW/MEDIUM (Happy Path)

```
Usuario          our-dots        find_manifest    our-pac    our-aur   system.yaml
  │                │                  │              │          │           │
  │ sudo our-dots -S noctalia         │              │          │           │
  │──────────────>│                  │              │          │           │
  │                │ [EUID==0 ✓]     │              │          │           │
  │                │ find_manifest("noctalia")       │          │           │
  │                │─────────────────>│              │          │           │
  │                │<─ /path/noctalia.yaml            │          │           │
  │                │ compat = "low"  │              │          │           │
  │                │ channels = "stable/git"         │          │           │
  │                │                  │              │          │           │
  │<─ "Log: /var/log/our-dots/noctalia-20260607.log" │          │           │
  │<─ "Install noctalia (stable)? [y/N]"             │          │           │
  │ y              │                  │              │          │           │
  │──────────────>│                  │              │          │           │
  │                │ pkgs=[] aur_pkgs=[noctalia-shell]          │           │
  │                │ our-pac -S --noconfirm (pkgs vacío)        │           │
  │                │ our-aur -S noctalia-shell                  │           │
  │                │──────────────────────────────────────────>│           │
  │                │<─ exit 0 ─────────────────────────────────│           │
  │                │ post_deploy = null (noop)                  │           │
  │                │ sysyaml_add_pack("noctalia", "stable", …)             │
  │                │──────────────────────────────────────────────────────>│
  │                │<─ OK (atomic write) ───────────────────────────────────│
  │<─ "Pack noctalia (stable) installed successfully."           │           │
```

### 8.2 Instalación de Pack CRITICAL

```
Usuario          our-dots              cleanup_trap      system.yaml
  │                │                       │                 │
  │ sudo our-dots -S illogical-impulse     │                 │
  │──────────────>│                       │                 │
  │                │ compat = "critical"   │                 │
  │                │                       │                 │
  │<═══════════════╪═══ PANEL ROJO ════════╪═════════════════│
  │  "CRITICAL COMPATIBILITY WARNING"      │                 │
  │  [acciones críticas listadas]          │                 │
  │  "Type 'yes' to proceed:"              │                 │
  │ yes            │                       │                 │
  │──────────────>│                       │                 │
  │                │ trap 'cleanup_critical "illogical-impulse"' ERR EXIT
  │                │                       │                 │
  │                │ mount -o remount,rw / │                 │
  │                │ cp pacman.conf pacman.conf.our-dots-bak  │
  │                │ echo "IgnoreGroup=illogical-impulse" >> /etc/pacman.conf
  │                │ mount -o remount,ro / │                 │
  │                │ our-pac -S git --noconfirm               │
  │                │ our-aur -S … (si hay AUR)                │
  │                │ post_deploy (como $SUDO_USER)            │
  │                │ sysyaml_add_pack(…) ──────────────────> │
  │                │ trap - ERR EXIT       │                 │
  │<─ "installed successfully"             │                 │
```

### 8.3 Instalación CRITICAL con Fallo + Cleanup

```
our-dots                         sistema (/)          system.yaml
  │                                   │                    │
  │ [confirmación "yes"]              │                    │
  │ trap ERR/EXIT → cleanup_critical  │                    │
  │                                   │                    │
  │ mount -o remount,rw / ───────────>│                    │
  │ editar /etc/pacman.conf            │                    │
  │ FALLO AQUÍ (post_deploy falla)    │                    │
  │                                   │                    │
  │ ERR trap activado                 │                    │
  │ cleanup_critical():               │                    │
  │   mount -o remount,ro / ─────────>│                    │
  │   cp pacman.conf.our-dots-bak /etc/pacman.conf         │
  │   our-pac -R <pkgs> (best-effort) │                    │
  │   escribir cleanup log            │                    │
  │ exit 5                            │               NO WRITE
  │ (system.yaml sin cambios)         │                    │
```

### 8.4 `repo-add` (Repositorio Git)

```
Usuario      our-dots       git/HTTPS         REPOS_DIR    dots-repos.yaml
  │             │                │                 │              │
  │ repo-add mi-repo url.git     │                 │              │
  │────────────>│                │                 │              │
  │             │ verificar HTTPS│                 │              │
  │             │ git ls-remote  │                 │              │
  │             │───────────────>│                 │              │
  │             │<─ OK           │                 │              │
  │             │ git clone --depth=1 url REPOS_DIR/mi-repo       │
  │             │────────────────────────────────>│              │
  │             │<─ OK           │                 │              │
  │             │ validate_manifest_schema(*.yaml) │              │
  │             │ (per manifest: valid/invalid)    │              │
  │             │ sysyaml_append_repo("mi-repo", …)              │
  │             │────────────────────────────────────────────────>│
  │<─ "registered with N valid packs"               │              │
```

### 8.5 Selección de Pack en TUI del Instalador

```
InstallerFSM    _handle_dots_pack()   TUI.show_dots_pack_selection()   dots_profiles.py
     │                 │                          │                         │
     │ DOTS_PACK entry │                          │                         │
     │─────────────────>                          │                         │
     │                 │ profile = "hyprland"     │                         │
     │                 │──────────────────────────>                         │
     │                 │                          │ packs_for_profile("hyprland")
     │                 │                          │─────────────────────────>
     │                 │                          │<─ [ml4w, caelestia, …]  │
     │                 │                          │                         │
     │                 │                          │ Select widget:          │
     │                 │                          │ [Ninguno, ML4W, …]      │
     │                 │<─ {"pack": "ml4w", "channel": "stable"} ──────────│
     │                 │ auto-correct channel (if git-only)                │
     │                 │ config.dots_pack.pack = "ml4w"                    │
     │                 │ config.dots_pack.channel = "stable"               │
     │                 │ update_progress(100)     │                         │
     │                 │ → SECURE_BOOT            │                         │
```

---

## 9. Seguridad

### 9.1 Modelo de Amenazas

| Amenaza | Impacto | Probabilidad | Mitigación |
|---------|---------|-------------|------------|
| Manifest externo malicioso con `post_deploy` arbitrario | Alto | Baja | Solo HTTPS; validación de schema obligatoria; scripts inline (no paths absolutos); aviso `[EXTERN]`; el usuario debe auditar. |
| MITM en descarga de manifests externos | Alto | Muy baja | Solo HTTPS (`[[ "$url" == https://* ]]`). Sin override. |
| Ejecución de `post_deploy` como root | Alto | Baja | `post_deploy` siempre corre como `$SUDO_USER`, no como root (a menos que el usuario directamente ejecute `our-dots` como root sin sudo). |
| Corrupción de `system.yaml` ante kill mid-write | Alto | Muy baja | Escritura atómica: flock + `.tmp` + `os.replace` (`rename(2)`). |
| Pack CRITICAL daña sistema inmutable sin advertencia | Alto | Media | Panel rojo explícito + tipear "yes" + lista de acciones; trap de cleanup revierte en caso de fallo. |
| `--noconfirm` con pack CRITICAL en CI sin protección | Medio | Baja | `--noconfirm` produce error con pack CRITICAL. Solo `OUROBOROS_ALLOW_CRITICAL=1` permite bypass. |
| Conflicto de lock concurrente en `system.yaml` | Medio | Muy baja | Timeout de 5 segundos. Error claro con nombre del proceso bloqueante. |

### 9.2 Restricciones de Seguridad Implementadas

1. **Solo HTTPS para repos externos:**
   ```bash
   [[ "$url" == https://* ]] || die "Repository URL must use HTTPS"
   ```

2. **Hooks como scripts inline, no paths:**
   ```bash
   [[ "$pd" == /* ]] && { log_warn "post_deploy must not be an absolute path"; valid=false; }
   ```

3. **Ejecución de hooks como `$SUDO_USER`:**
   ```bash
   local run_user="${SUDO_USER:-$USER}"
   if [[ "$run_user" == "root" ]]; then
       bash -c "$post_deploy" ...
   else
       sudo -u "$run_user" bash -c "$post_deploy" ...
   fi
   ```

4. **Política CRITICAL:**

   | Escenario | Comportamiento |
   |-----------|---------------|
   | Pack CRITICAL + interactivo | Panel rojo + tipear `"yes"` |
   | Pack CRITICAL + `--noconfirm` | **Error** exit 1. Sin instalación. |
   | Pack CRITICAL + `OUROBOROS_ALLOW_CRITICAL=1` | Sin panel, procede directamente |
   | Pack CRITICAL + `--noconfirm` + `OUROBOROS_ALLOW_CRITICAL=1` | Procede directamente |

5. **Indicador `[EXTERN]` no suprimible:** Los packs externos se marcan en `list`, `-Si`, y aviso previo a instalación. No hay flag para suprimir este aviso.

6. **Validación de schema pre-ejecución:** Para manifests externos, `validate_manifest_schema()` se ejecuta antes de registrar el repositorio y antes de ejecutar cualquier hook. Un manifest inválido no ejecuta `post_deploy` ni `post_remove`.

### 9.3 Trap de Cleanup CRITICAL

Instalado inmediatamente tras confirmación del usuario, garantiza restauración del sistema inmutable:

- Si `/` fue remontado como rw → `mount -o remount,ro /`
- Si `/etc/pacman.conf` fue modificado → restaurar desde `/etc/pacman.conf.our-dots-bak`
- Paquetes instalados antes del fallo → `our-pac -R` (best-effort)
- Log de cleanup en `/var/log/our-dots/<id>-cleanup-<YYYYMMDD-HHMMSS>.log`
- Exit code 5 siempre

### 9.4 Campo `signature` (Reservado para Versión Futura)

El campo `signature: null` en cada manifest está reservado para firma criptográfica (GPG/minisign) en versiones futuras. En v0.6.1:
- Siempre `null`.
- Manifests con `signature` no-nula son aceptados sin verificación.
- La verificación de firma es futura.

---

## 10. Testing

### 10.1 Estrategia

| Nivel | Herramienta | Scope | Cobertura Objetivo |
|-------|-------------|-------|-------------------|
| Unit | pytest | `dots_profiles.py`, `DotsPackConfig`, helpers Python en `our-dots` | ≥ 93% (gate CI existente) |
| Integration | pytest + subprocess | `our-dots` CLI end-to-end en sandbox, `system.yaml` write/read | — |
| E2E | QEMU + suite existente | Instalación completa con pack `noctalia` (LOW) en perfil hyprland | 100% pass |

### 10.2 Casos de Test Unitarios — `dots_profiles.py`

```python
# tests/test_dots_profiles.py

class TestLoadCatalog:
    def test_missing_dir_returns_empty(self, tmp_path):
        """load_catalog() con directorio inexistente retorna []."""
        result = load_catalog(tmp_path / "nonexistent")
        assert result == []

    def test_valid_manifest_loads_correctly(self, tmp_path):
        """Manifest con schema canónico se parsea correctamente."""
        manifest = tmp_path / "noctalia.yaml"
        manifest.write_text(NOCTALIA_MANIFEST_YAML)
        packs = load_catalog(tmp_path)
        assert len(packs) == 1
        assert packs[0].id == "noctalia"
        assert packs[0].compatibility == "low"
        assert packs[0].profiles == ["hyprland", "niri"]
        assert packs[0].has_stable is True
        assert packs[0].has_git is True

    def test_invalid_manifest_is_ignored(self, tmp_path):
        """Manifest con YAML inválido se ignora sin crash."""
        (tmp_path / "bad.yaml").write_text("{{invalid yaml{{")
        (tmp_path / "good.yaml").write_text(NOCTALIA_MANIFEST_YAML)
        packs = load_catalog(tmp_path)
        assert len(packs) == 1

    def test_git_only_manifest_correct_flags(self, tmp_path):
        """Pack git-only: has_stable=False, has_git=True."""
        (tmp_path / "illogical-impulse.yaml").write_text(ILLOGICAL_MANIFEST_YAML)
        packs = load_catalog(tmp_path)
        assert packs[0].has_stable is False
        assert packs[0].has_git is True

    def test_alphabetical_order(self, tmp_path):
        """Manifests se cargan en orden alfabético."""
        for name in ["z-pack.yaml", "a-pack.yaml", "m-pack.yaml"]:
            (tmp_path / name).write_text(make_minimal_manifest(name.split(".")[0]))
        packs = load_catalog(tmp_path)
        assert [p.id for p in packs] == ["a-pack", "m-pack", "z-pack"]

    def test_load_catalog_canonical_schema(self, tmp_path):
        """load_catalog() lee credits.author y compatibility.immutable (schema canónico)."""
        manifest = tmp_path / "test.yaml"
        manifest.write_text(CANONICAL_SCHEMA_MANIFEST)
        packs = load_catalog(tmp_path)
        assert packs[0].author == "Test Author"
        assert packs[0].compatibility == "medium"


class TestPacksForProfile:
    def test_hyprland_filter(self, catalog_dir):
        """packs_for_profile('hyprland') retorna solo packs compatibles."""
        packs = packs_for_profile("hyprland", catalog_dir)
        assert all("hyprland" in p.profiles for p in packs)

    def test_niri_filter(self, catalog_dir):
        """Solo noctalia y danklinux son compatibles con niri."""
        packs = packs_for_profile("niri", catalog_dir)
        ids = {p.id for p in packs}
        assert ids == {"noctalia", "danklinux"}

    def test_unknown_profile_returns_empty(self, catalog_dir):
        """Perfil desconocido retorna lista vacía sin error."""
        assert packs_for_profile("gnome", catalog_dir) == []

    def test_minimal_profile_returns_empty(self, catalog_dir):
        """Perfil 'minimal' retorna lista vacía."""
        assert packs_for_profile("minimal", catalog_dir) == []
```

### 10.3 Casos de Test de Integración — CLI `our-dots`

```bash
# tests/test_our_dots_cli.sh — ejecutable en CI con sandbox

test_list_shows_builtin_packs() {
    # our-dots list debe mostrar los 7 packs built-in
    output=$(our-dots list)
    assert_contains "$output" "ml4w"
    assert_contains "$output" "noctalia"
    assert_contains "$output" "illogical-impulse"
}

test_si_pack_found() {
    # -Si con pack válido retorna exit 0
    our-dots -Si noctalia
    assert_exit_code 0
}

test_si_pack_not_found() {
    # -Si con pack inexistente retorna exit 1
    our-dots -Si nonexistent-pack 2>/dev/null
    assert_exit_code 1
}

test_critical_with_noconfirm_fails() {
    # Pack CRITICAL + --noconfirm sin OUROBOROS_ALLOW_CRITICAL → exit 1
    sudo our-dots -S illogical-impulse --noconfirm 2>/dev/null
    assert_exit_code 1
}

test_critical_with_allow_env_proceeds() {
    # OUROBOROS_ALLOW_CRITICAL=1 + --noconfirm → no panel (en entorno sandbox)
    OUROBOROS_ALLOW_CRITICAL=1 sudo our-dots -S mock-critical --noconfirm
    # Verificar que se registró en system.yaml
    assert_in_system_yaml "mock-critical"
}

test_atomic_write_under_concurrent_access() {
    # Dos escrituras concurrentes → flock garantiza que no hay corrupción
    for i in 1 2 3 4 5; do
        sudo our-dots -S "pack-$i" --noconfirm &
    done
    wait
    # system.yaml debe ser YAML válido
    python3 -c "import yaml; yaml.safe_load(open('/etc/ouroboros/system.yaml'))"
    assert_exit_code 0
    # [I-03] Todos los 5 packs deben estar registrados (sin pérdida por race)
    local count
    count=$(python3 -c "
import yaml
d = yaml.safe_load(open('/etc/ouroboros/system.yaml')) or {}
print(len(d.get('dots_packs', [])))
")
    assert_equals "$count" "5"
}

test_sysyaml_not_written_on_post_deploy_fail() {
    # Fallo en post_deploy → pack NO registrado en system.yaml
    # Usar pack mock con post_deploy que retorna exit 1
    sudo our-dots -S mock-post-deploy-fail --noconfirm 2>/dev/null
    assert_exit_code 4
    assert_not_in_system_yaml "mock-post-deploy-fail"
}
```

### 10.4 Casos de Test E2E (QEMU)

Adiciones al suite QEMU existente (72/72 base):

| Test | Pack | Perfil | Canal | Verifica |
|------|------|--------|-------|---------|
| `test_dots_install_noctalia` | noctalia | hyprland | stable | Pack instalado, `system.yaml` actualizado, log generado. |
| `test_dots_query_shows_installed` | — | — | — | `-Q` lista packs instalados tras instalación. |
| `test_dots_remove_noctalia` | noctalia | hyprland | — | `-R` desinstala y elimina de `system.yaml`. |
| `test_dots_list_has_7_builtin_packs` | — | — | — | `list` muestra los 7 packs con columnas correctas. |
| `test_installer_dots_pack_state` | noctalia | hyprland | stable | Instalador TUI configura `DOTS_PACK`, pack instalado en chroot. |

### 10.5 Mocks y Stubs

Para tests unitarios que requieran `our-pac` o `our-aur`:

```python
# Fixture para simular our-pac y our-aur como comandos exitosos
@pytest.fixture
def mock_pac_aur(monkeypatch, tmp_path):
    """Replace our-pac and our-aur with stubs that succeed."""
    stub = tmp_path / "stub.sh"
    stub.write_text("#!/bin/bash\nexit 0\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    (tmp_path / "our-pac").symlink_to(stub)
    (tmp_path / "our-aur").symlink_to(stub)
```

Para tests que simulan `system.yaml` inexistente o en blanco:

```python
@pytest.fixture
def empty_sysyaml(tmp_path, monkeypatch):
    sysyaml = tmp_path / "system.yaml"
    monkeypatch.setattr("our_dots.SYSYAML", str(sysyaml))
    return sysyaml
```

---

## 11. Internacionalización

### 11.1 Estado en v0.6.1

El sistema i18n de ouroborOS usa `gettext` via `src/installer/i18n.py` (`init_i18n(lang)` llamado una vez tras la selección de idioma). En v0.6.1, `our-dots` y el módulo `dots_profiles.py` **no están internacionalizados**.

- Los mensajes del CLI (`log_info`, `log_warn`, `log_error`, `die`) están en inglés.
- El panel de información de pack (`-Si`) está en inglés.
- El panel CRITICAL y los avisos HIGH están en inglés.
- La TUI del instalador (`show_dots_pack_selection`) mostrará las opciones en el idioma del sistema si el módulo TUI lo soporta.

### 11.2 Alcance de i18n en v0.6.1

| Componente | i18n v0.6.1 | Plan Futuro |
|------------|-------------|-------------|
| CLI `our-dots` | No (mensajes en inglés) | v0.7.0: envolver mensajes en `_()` de gettext |
| Panel CRITICAL | No (en inglés) | v0.7.0: strings localizables |
| `dots_profiles.py` | No | v0.7.0 |
| Manifests (description, note, warning) | No | Manifests serán monolingüe (inglés). La descripción en display puede mostrarse en el idioma del manifest. |

### 11.3 Strings Mínimos Identificados para Traducción Futura

Los strings clave que deberán ser localizables en versiones futuras:

```python
# Mensajes que requerirán _() wrapper
_("Pack already installed. Reinstalling will overwrite the existing entry.")
_("This pack is from an external repository not audited by the ouroborOS project.")
_("CRITICAL pack requires OUROBOROS_ALLOW_CRITICAL=1 for unattended installation.")
_("Type 'yes' to proceed, anything else to cancel: ")
_("Installation cancelled.")
_("(no packs installed)")
```

---

## 12. Accesibilidad

### 12.1 TUI del Instalador (Textual)

La pantalla `show_dots_pack_selection()` implementada en Textual debe cumplir:

- **Navegación por teclado:** El widget `Select` de Textual soporta navegación con `↑`/`↓` y selección con `Enter` por defecto. No se requiere configuración adicional.
- **Labels descriptivos:** Cada opción del `Select` muestra el nombre de display del pack (no el ID técnico). El texto `"Ninguno"` es la primera opción y permite omitir la selección.
- **Indicación de compatibilidad:** El nivel de compatibilidad se muestra junto al nombre (e.g., `"Noctalia v4 (low)"`), permitiendo que el usuario evalúe el impacto sin necesidad de otro paso.
- **Estado de foco visible:** El widget Textual implementa foco visual por defecto.
- **Compatibilidad con lectores de pantalla:** Textual v1.x soporta accesibilidad básica via `aria`-equivalentes en terminal. El nivel de soporte depende del terminal y lector en uso.

### 12.2 CLI `our-dots`

- **Colores opcionales:** Los colores ANSI en `log_info`/`log_warn`/`log_error` se pueden deshabilitar configurando `NO_COLOR=1` en el entorno (convención universal). Implementar con:
  ```bash
  [[ "${NO_COLOR:-}" == "1" ]] && GREEN="" YELLOW="" RED="" RESET="" || {
      GREEN="\033[0;32m"; YELLOW="\033[0;33m"
      RED="\033[0;31m"; RESET="\033[0m"
  }
  ```
- **Output estructurado:** Las tablas de `list`, `-Q`, y `repo-list` usan alineación por espacios. En v0.6.1 no se provee output JSON/YAML machine-readable. Plan futuro: flag `--json` para integración con scripts.
- **Panel CRITICAL legible sin color:** El panel rojo de confirmación usa bordes ASCII (`╔╣╚`) legibles en terminales sin soporte de color. El contenido es comprensible sin depender del color.

---

## 13. Rendimiento

### 13.1 Budgets de Tiempo

| Operación | Budget | Medición |
|-----------|--------|---------|
| `our-dots list` (7 packs builtin) | < 500ms | Lectura de 7 archivos YAML con Python inline |
| `our-dots -Si <id>` | < 300ms | 1 lectura YAML + 1 lectura system.yaml |
| Instalación pack LOW/MEDIUM (sin compilación) | < 5 min | Medido en QEMU E2E |
| Instalación pack HIGH (con builds AUR) | < 15 min | DankLinux: Go + CMake + Rust (~10 min de build) |
| Escritura atómica `system.yaml` | < 100ms | I/O + lock acquisition |
| `load_catalog()` Python (7 manifests) | < 200ms | Sorted glob + 7 yaml.safe_load |

### 13.2 Uso de Disco

| Componente | Tamaño Estimado |
|------------|----------------|
| `our-dots` script | < 20 KB |
| 7 manifests YAML built-in | < 50 KB total |
| Repos externos clonados | Variable (depende del repo) |
| Logs por instalación | < 1 MB por operación típica |
| `system.yaml` con 7 packs | < 5 KB |

### 13.3 Consideraciones de Rendimiento

- **`yaml_get` inline:** Cada llamada a `yaml_get` o `yaml_list` abre un proceso `python3`. Para `cmd_list` con 7 manifests y ~5 campos por manifest, esto implica ~35 procesos `python3`. En hardware típico (i5/Ryzen 5) el tiempo es aceptable (< 500ms). Para N manifests externos grandes, puede ser un cuello de botella.
  - **Mitigación v0.6.1:** Aceptable para el catálogo built-in de 7 packs.
  - **Plan futuro:** Consolidar lectura de manifest en un único proceso Python que devuelva JSON, reduciendo el overhead de fork.
- **`git clone --depth=1`:** Para repos Git grandes con historial profundo, `--depth=1` reduce el tiempo significativamente. El tiempo de clone depende del ancho de banda de red y no es controlable por `our-dots`.
- **AUR builds (HIGH/CRITICAL):** El tiempo de build de DankLinux (~10 min con Go + CMake + Rust) no es un problema de rendimiento de `our-dots` — es inherente al proceso de compilación. El log en tiempo real da feedback al usuario.

---

## 14. Dependencias

### 14.1 Dependencias del Sistema

| Dependencia | Versión Mínima | Justificación |
|-------------|---------------|---------------|
| Bash | 5.0+ | `set -euo pipefail`, `mapfile`, arrays asociativos. Sin Bash 5 las arrays no son confiables en todos los contexts. |
| Python | 3.11+ | `yaml.safe_load`, `os.replace`, `fcntl.flock`, `dataclasses`, `match` statements. La versión 3.11 es la incluida en Arch Linux base. |
| PyYAML | 6.0+ | `yaml.safe_load` / `yaml.dump`. `safe_load` en lugar de `load` previene ejecución de constructores YAML arbitrarios. |
| `our-pac` | v0.6.0+ | Instala/remove paquetes pacman. `our-dots` no llama a `pacman` directamente — toda la gestión de paquetes pasa por `our-pac` para mantener la auditoría de cambios. |
| `our-aur` | v0.6.0+ | Instala/remove paquetes AUR. Idem. |
| git | 2.30+ | `git clone --depth=1` para repos externos Git. `git pull --ff-only` para actualizaciones. `git ls-remote` para detección de tipo de repo. |
| curl | 7.80+ | `curl -sfL` para repos HTTP y API AUR v5. `-s` silencia el progress bar, `-f` falla con exit non-zero en error HTTP, `-L` sigue redirects. |
| util-linux (`flock`) | 2.37+ | Advisory lock para prevenir escrituras concurrentes en `system.yaml`. Alternativa Python vía `fcntl` — se usa `fcntl.flock` dentro de los helpers Python para portabilidad. |

### 14.2 Paquetes en el ISO

Estos paquetes deben estar en `packages.x86_64` del perfil archiso para que `our-dots` funcione en el sistema instalado:

```
python-yaml    # PyYAML
git            # Repos externos y packs git
curl           # Repos HTTP y API AUR
util-linux     # flock
```

> **Nota:** `python-yaml` es el nombre del paquete Arch Linux para PyYAML. No confundir con `python3-yaml` (Debian/Ubuntu).

### 14.3 Dependencias de Desarrollo

| Dependencia | Uso |
|-------------|-----|
| pytest | Suite de tests unitarios |
| pytest-cov | Medición de cobertura (gate ≥ 93%) |
| ruff | Linter Python (mismo ruleset que CI) |
| shellcheck | Lint de scripts Bash (`shellcheck -S style`) |

---

## 15. Glosario

| Término | Definición en este documento |
|---------|------------------------------|
| **built-in** | Pack incluido en el catálogo oficial de ouroborOS, distribuido en `MANIFEST_DIR` dentro del ISO. Read-only. |
| **canal git** | Canal de distribución que apunta al último commit del repositorio del pack. Identificado como `"git"` en manifests, `system.yaml` y CLI. |
| **canal stable** | Canal de distribución que apunta a una versión etiquetada o release del pack. |
| **cleanup trap** | Trap Bash `ERR`/`EXIT` instalado para packs CRITICAL que garantiza restauración del sistema inmutable (remount ro, restauración de `pacman.conf`) en caso de fallo. |
| **compatibility level** | Nivel de impacto de un pack sobre el sistema inmutable. Valores: `low`, `medium`, `high`, `critical`. |
| **CRITICAL** | Pack cuya instalación requiere modificar temporalmente el sistema raíz (remount rw, edición de `/etc`). Requiere confirmación explícita `"yes"` o `OUROBOROS_ALLOW_CRITICAL=1`. |
| **DOTS_PACK** | Estado en la FSM del instalador que gestiona la selección opcional de pack de dotfiles. Posición: DESKTOP → DOTS_PACK → SECURE_BOOT. |
| **DotsPackConfig** | Dataclass Python (`config.py`) que persiste la selección de pack (`pack: str\|None`, `channel: str`) durante la instalación. |
| **DotsPack** | Dataclass Python (`dots_profiles.py`) que representa un pack del catálogo tal como lo consume la TUI. |
| **EXTERN** | Prefijo visual `[EXTERN]` que indica que un pack proviene de un repositorio externo no auditado. |
| **find_manifest()** | Función Bash que localiza el `.yaml` de un pack. Prioridad: built-in > externos (en orden de registro). |
| **hook** | Script inline (string en YAML) ejecutado tras instalación (`post_deploy`) o desinstalación (`post_remove`). Corre como `$SUDO_USER`. |
| **index.yaml** | Archivo de índice de repositorio HTTP. Lista los IDs de packs disponibles. |
| **load_catalog()** | Función Python que carga todos los manifests de `MANIFEST_DIR` y retorna lista de `DotsPack`. Nunca lanza excepción. |
| **MANIFEST_DIR** | `/usr/local/lib/ouroboros/dots/packs/`. Directorio read-only de manifests built-in. |
| **manifest** | Archivo `<id>.yaml` que describe un pack: créditos, compatibilidad, variantes de canal, hooks. Schema autoritativo: TRD §2.3. |
| **OUROBOROS_ALLOW_CRITICAL=1** | Variable de entorno que permite instalación de packs CRITICAL en modo no-interactivo. Solo CI/automatización. |
| **packs_for_profile()** | Función Python que filtra `load_catalog()` por perfil desktop. |
| **post_deploy** | Hook ejecutado tras instalación de paquetes. Script inline. Corre como `$SUDO_USER`. |
| **post_remove** | Hook ejecutado tras desinstalación. Script inline. Corre como `$SUDO_USER`. |
| **REPOS_DIR** | `/var/lib/ouroboros/dots/repos/`. Directorio mutable de manifests externos. |
| **REPOS_INDEX** | `/etc/ouroboros/dots-repos.yaml`. Índice de repositorios externos. |
| **schema canónico** | El schema de manifest documentado en TRD §2.3 y SPEC §4.1, con campos anidados (`credits.*`, `compatibility.*`, `variants.*`). Es autoritativo sobre PRD §6.8. |
| **upsert** | Operación que inserta o reemplaza una entrada con el mismo `id` en `system.yaml.dots_packs`. |
| **version_hint** | Campo descriptivo de la versión de un canal (e.g., `"v4 (stable)"`). Usado como `installed_version` en `system.yaml`. |
| **yaml_get / yaml_list** | Helpers Bash que usan `python3 -c` inline para consultar campos YAML. |

---

## 16. Referencias Cruzadas

### 16.1 Mapeo PRD → DESIGN

| PRD Sección | DESIGN Sección |
|-------------|----------------|
| §1 Resumen Ejecutivo | §1.1 Diagrama de Componentes |
| §2.1 Objetivos Primarios | §1.3 Decisiones de Diseño |
| §5.3 CU-03 Instalación low/medium | §3.7 `cmd_install`, §8.1 |
| §5.5 CU-05 Instalación CRITICAL | §3.9 Trap de Cleanup, §8.2, §9.2 |
| §5.6 CU-06 Desinstalación | §3.7 `cmd_remove` |
| §5.15 CU-15 Selección en TUI | §5.3 Handler, §5.5 TUI, §8.5 |
| §5.22 CU-22 Escritura atómica | §3.5 `sysyaml_add_pack`, §7.2 |
| §5.23 CU-23 Cleanup CRITICAL | §3.9, §9.3 |
| §6.8 Schema de Manifest (histórico) | §6.1 Schema Canónico (ver nota autoridad TRD) |
| §8 Métricas de Éxito | §10.1 Estrategia, §13.1 Budgets |
| §9 Stack Tecnológico | §14 Dependencias |
| §10 Riesgos y Mitigaciones | §9.1 Modelo de Amenazas |

### 16.2 Mapeo TRD → DESIGN

| TRD Sección | DESIGN Sección |
|-------------|----------------|
| §1.1 Diagrama de Componentes | §1.1 (refinado con decisiones de diseño) |
| §2.1 DotsPack dataclass | §4.2 Implementación Target |
| §2.2 DotsPackConfig dataclass | §4.3 Relaciones entre Clases |
| §2.3 Schema de Manifest YAML (autoritativo) | §6.1 Schema Canónico |
| §2.4 Schema system.yaml dots_packs | §7.1 |
| §2.5 Schema dots-repos.yaml | §7.3 |
| §2.6 Schema index.yaml | §7.4 |
| §3 Flujos de Confirmación por Nivel | §8.1, §8.2 (diagramas de secuencia) |
| §4.3 Rollback | §9.3 Trap de Cleanup |
| §5.1 Flujo instalación pacman | §3.5 `sysyaml_add_pack`, §3.7 `cmd_install` |
| §5.3 Ejecución post_deploy | §9.2 Restricciones de Seguridad (ítem 3) |
| §7.4 Resolución conflictos de ID | §3.6 `find_manifest()` |
| §7.5 Validación schema pre-ejecución | §6.4 `validate_manifest_schema` |
| §8.2 Concurrencia flock + atomic | §3.5, §7.2 Protocolo de Escritura Atómica |
| §9.2 Handler _handle_dots_pack() | §5.3 (incluye brecha actual + fix requerido) |
| §10 Seguridad | §9 Seguridad |
| §11 Logging | §3.3 Logging, §10.3 (casos de test de log) |
| §12 Exit Codes | §10.3 `test_sysyaml_not_written_on_post_deploy_fail` |
| §13 Dependencias del Sistema | §14 Dependencias |
| §14 Restricciones Técnicas | §2.3 Montaje y Compatibilidad con Raíz Read-Only |

### 16.3 Mapeo SPEC → DESIGN

| SPEC Sección | DESIGN Sección |
|--------------|----------------|
| §2 Contexto y Arquitectura | §1 Visión General |
| §3 Interfaces CLI | §3 CLI (`our-dots`) |
| §4.1 Schema de Manifest | §6 Manifests |
| §4.2 Schema system.yaml | §7.1 |
| §4.3 dots-repos.yaml | §7.3 |
| §5.0 Header del Script | §3.2 Header del Script |
| §5.1 `cmd_list` | §3.7 Tabla de Funciones |
| §5.3 `cmd_install` | §3.7, §8.1, §8.2 |
| §5.4 `cmd_remove` | §3.7 |
| §5.5 `cmd_query` / `cmd_search` | §3.7 |
| §5.6 `cmd_upgrade` | §3.7 |
| §5.7-5.9 `cmd_repo_*` | §3.7, §8.4 |
| §5.10 `find_manifest()` | §3.6 |
| §6.1 FSM DOTS_PACK | §5 FSM del Instalador |
| §6.2 FSM Instalación de Pack | §8 Flujos de Datos |
| §7.5 `sysyaml_add_pack()` | §3.5 Helpers system.yaml |
| §9.1 Validación de Schema | §6.4 |
| §11.4 M-05 Plan migración dots_profiles | §4.1 (brecha actual), §4.2 (target) |
| §12 Logging | §3.3 |
| §13 Seguridad | §9 |
| §14 Glosario | §15 |

### 16.4 Brechas de Implementación Identificadas

Las siguientes brechas entre el estado actual del código y el diseño target deben resolverse antes del release v0.6.1:

| ID | Brecha | Archivo Afectado | SPEC Referencia | Timeline |
|----|--------|-----------------|-----------------|---------|
| GAP-01 | `dots_profiles.py` lee campos planos (`compatibility`, `profiles`, `has_stable`) en lugar del schema canónico anidado (`compatibility.immutable`, `compatibility.profiles`, derivados de `variants.*`). | `src/installer/dots_profiles.py` | SPEC §11.4 M-05 | **v0.6.1** — bloqueante para DOTS_PACK state en TUI. |
| GAP-02 | `_handle_dots_pack()` en `state_machine.py` no implementa auto-corrección de canal para packs git-only (`has_stable=False`, `has_git=True`). Sin este fix, packs como `illogical-impulse` y `ambxst` fallan en modo unattended. | `src/installer/state_machine.py` | SPEC §6.1 C-03, TRD §9.2 | **v0.6.1** — bloqueante para instalación unattended con packs git-only. |
| GAP-03 | Los manifests built-in no existen aún en `MANIFEST_DIR`. Deben crearse los 7 archivos YAML con el schema canónico TRD §2.3. | `src/installer/dots/packs/*.yaml` (por crear) | SPEC §4.5 | **v0.6.1** — requerido para `our-dots list` y `cmd_install`. |
| GAP-04 | El binario `our-dots` no existe aún. | `/usr/local/bin/our-dots` (por crear) | SPEC §3 | **v0.6.1** — feature principal del release. |
