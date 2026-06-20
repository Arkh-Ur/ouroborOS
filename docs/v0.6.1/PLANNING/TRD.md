# TRD — ouroborOS v0.6.1: Gestor de Dotfiles `our-dots`

**Versión:** 1.2  
**Fecha:** 2026-06-07  
**Autor:** ouroborOS dev team  
**Estado:** Borrador  
**Referencia:** PRD v1.1 — 2026-06-07

---

## Tabla de Contenidos

1. [Arquitectura General](#1-arquitectura-general)
2. [Modelo de Datos](#2-modelo-de-datos)
3. [Flujos de Confirmación por Nivel](#3-flujos-de-confirmación-por-nivel)
4. [Integración con Sistema de Snapshots](#4-integración-con-sistema-de-snapshots)
5. [Integración con our-pac y our-aur](#5-integración-con-our-pac-y-our-aur)
6. [Comando -Su (Update)](#6-comando--su-update)
7. [Sistema de Repositorios Externos](#7-sistema-de-repositorios-externos)
8. [Wiring con system.yaml](#8-wiring-con-systemyaml)
9. [Integración con el Instalador (FSM)](#9-integración-con-el-instalador-fsm)
10. [Seguridad](#10-seguridad)
11. [Logging y Debug](#11-logging-y-debug)
12. [Tabla de Exit Codes](#12-tabla-de-exit-codes)
13. [Dependencias del Sistema](#13-dependencias-del-sistema)
14. [Restricciones Técnicas](#14-restricciones-técnicas)

---

## 1. Arquitectura General

### 1.1 Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Usuario / Instalador                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ CLI: our-dots -S / -R / -Q / repo-add…
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                       our-dots (Bash CLI)                           │
│  /usr/local/bin/our-dots                                            │
│                                                                     │
│  cmd_list · cmd_info · cmd_install · cmd_remove · cmd_query        │
│  cmd_search · cmd_upgrade · cmd_repo_{add,remove,list,update}      │
│                                                                     │
│  Helpers: yaml_get · yaml_list · sysyaml_add/remove/is_installed   │
│           find_manifest · compat_badge                              │
└──────┬──────────────┬───────────────────┬───────────────────┬──────┘
       │              │                   │                   │
       ▼              ▼                   ▼                   ▼
 ┌──────────┐  ┌─────────────┐   ┌─────────────────┐  ┌──────────────┐
 │ MANIFEST │  │  REPOS_DIR  │   │   system.yaml   │  │  our-pac /   │
 │   _DIR   │  │  (externos) │   │ /etc/ouroboros/ │  │  our-aur     │
 │ (builtin)│  │/var/lib/…   │   │ (fuente verdad) │  │  (paquetes)  │
 └──────────┘  └─────────────┘   └─────────────────┘  └──────────────┘
       │              │                   │
       │  find_manifest() prioriza        │ sysyaml_add/remove (atomic)
       │  builtin > externo               │ flock + os.replace + .tmp
       ▼              ▼                   ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │              dots_profiles.py (módulo Python)                     │
 │              /usr/local/lib/ouroboros/installer/                  │
 │                                                                   │
 │  DotsPack dataclass · load_catalog() · packs_for_profile()       │
 │  Consumido por el instalador Textual TUI (estado DOTS_PACK)       │
 └──────────────────────────────────────────────────────────────────┘
       │
       ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │              Instalador FSM (state_machine.py)                    │
 │              Estado DOTS_PACK: DESKTOP → DOTS_PACK → SECURE_BOOT │
 │              InstallerConfig.dots_pack (DotsPackConfig)           │
 └──────────────────────────────────────────────────────────────────┘
```

### 1.2 Descripción de Componentes

| Componente | Tipo | Ubicación | Responsabilidad |
|------------|------|-----------|-----------------|
| `our-dots` | Bash 5+ | `/usr/local/bin/our-dots` | CLI principal. Parsea manifests, gestiona flujos de confirmación, delega instalación a our-pac/our-aur, escribe en system.yaml. |
| `MANIFEST_DIR` | Directorio (read-only) | `/usr/local/lib/ouroboros/dots/packs/` | Manifests built-in distribuidos en el ISO. No mutables post-instalación. |
| `REPOS_DIR` | Directorio (mutable) | `/var/lib/ouroboros/dots/repos/` | Manifests de repositorios externos clonados o descargados. |
| `REPOS_INDEX` | Archivo YAML | `/etc/ouroboros/dots-repos.yaml` | Índice de repositorios externos registrados (nombre + URL). |
| `system.yaml` | Archivo YAML | `/etc/ouroboros/system.yaml` | Fuente de verdad del sistema. Clave `dots_packs` registra estado instalado. |
| `dots_profiles.py` | Python 3.11+ | `src/installer/dots_profiles.py` | Carga el catálogo para el instalador TUI. Expone `DotsPack`, `load_catalog()`, `packs_for_profile()`. |
| `DotsPackConfig` | dataclass Python | `src/installer/config.py` | Selección de pack durante instalación. Campos: `pack` (str|None), `channel` (str). |
| `InstallerFSM` | Python | `src/installer/state_machine.py` | Estado `DOTS_PACK` en la FSM. Ejecuta `_handle_dots_pack()` entre DESKTOP y SECURE_BOOT. |
| `LOG_DIR` | Directorio | `/var/log/our-dots/` | Logs de instalación por pack, con timestamp. Rotación según política FHS. |

---

## 2. Modelo de Datos

### 2.1 Dataclass `DotsPack` (Python)

Definida en `src/installer/dots_profiles.py`. Usada exclusivamente por el instalador TUI para filtrar y presentar el catálogo.

```python
@dataclass
class DotsPack:
    id: str                       # Identificador único del pack (kebab-case)
    name: str                     # Nombre de display
    description: str              # Descripción breve
    author: str                   # Nombre del autor u organización
    homepage: str                 # URL del proyecto
    compatibility: str            # "low" | "medium" | "high" | "critical"
    profiles: list[str]           # Perfiles desktop compatibles
    has_stable: bool              # True si el manifest define variants.stable
    has_git: bool                 # True si el manifest define variants.git
    stable_version_hint: str = ""  # Texto descriptivo del canal stable
    git_version_hint: str = ""     # Texto descriptivo del canal git (opcional)
```

**Nota de implementación:** `load_catalog()` puebla `compatibility` desde `compatibility.immutable` y `profiles` desde `compatibility.profiles` del manifest YAML. Los campos `has_stable`/`has_git` se derivan de la presencia de `variants.stable` y `variants.git` respectivamente.

### 2.2 Dataclass `DotsPackConfig` (Python)

Definida en `src/installer/config.py`. Persiste la selección del usuario durante la instalación.

```python
@dataclass
class DotsPackConfig:
    pack: str | None = None    # ID del pack seleccionado, o None si omitido
    channel: str = "stable"    # "stable" | "git"
```

Integrada en `InstallerConfig.dots_pack` (campo de la FSM).

**Nota sobre canal por defecto:** El valor `channel = "stable"` es el default inicial. El handler `_handle_dots_pack()` y la TUI `show_dots_pack_selection()` corrigen automáticamente el canal según los canales disponibles en el pack seleccionado — si el pack es git-only, el canal se ajusta a `"git"` antes de continuar (ver §9.2).

### 2.3 Schema de Manifest YAML

> **Nota:** Este schema es el documento autoritativo del formato de manifest `our-dots`. Reemplaza y supersede PRD §6.8. Ante cualquier discrepancia entre este documento y el PRD, prevalece este schema.

Cada pack del catálogo (built-in o externo) se describe en un archivo `<id>.yaml`. Los manifests externos son validados contra este schema antes de ejecutar cualquier hook.

#### Tabla de campos

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `id` | string | **Sí** | Identificador único (kebab-case, minúsculas) |
| `name` | string | **Sí** | Nombre de display |
| `description` | string (multiline) | **Sí** | Descripción completa del pack |
| `credits.author` | string | **Sí** | Nombre del autor u organización |
| `credits.homepage` | url | **Sí** | URL del proyecto (HTTPS) |
| `credits.docs` | url | No | URL de documentación |
| `credits.repo` | url | No | URL del repositorio de código |
| `credits.license` | string | No | Identificador SPDX (e.g., `MIT`, `GPL-2.0`) |
| `compatibility.immutable` | enum | **Sí** | `low` \| `medium` \| `high` \| `critical` |
| `compatibility.profiles` | list | **Sí** | Perfiles desktop compatibles (`hyprland`, `niri`, etc.) |
| `compatibility.note` | string | No | Nota breve para packs `high` (texto del aviso amarillo) |
| `compatibility.warning` | string | Sí si `critical` | Texto del panel rojo de confirmación |
| `compatibility.critical_actions` | list | Sí si `critical` | Lista numerada de acciones que se tomarán |
| `requires_root` | bool | No | Indica si el pack requiere root para instalación |
| `variants.stable` | objeto | No | Definición del canal stable |
| `variants.stable.packages` | list | No | Paquetes pacman a instalar (canal stable) |
| `variants.stable.aur` | list | No | Paquetes AUR a instalar (canal stable) |
| `variants.stable.post_deploy` | string\|null | No | Script inline ejecutado tras instalación |
| `variants.stable.version_hint` | string | No | Texto descriptivo de la versión stable |
| `variants.git` | objeto | No | Definición del canal git |
| `variants.git.packages` | list | No | Paquetes pacman (canal git) |
| `variants.git.aur` | list | No | Paquetes AUR (canal git) |
| `variants.git.post_deploy` | string\|null | No | Script inline (canal git) |
| `variants.git.version_hint` | string | No | Texto descriptivo del canal git |
| `uninstall.packages` | list | No | Paquetes pacman a remover en `-R` |
| `uninstall.aur` | list | No | Paquetes AUR a remover en `-R` |
| `uninstall.post_remove` | string\|null | No | Script inline ejecutado tras desinstalación |
| `uninstall.remove_config` | bool | No | Si true, elimina `~/.config/<id>` en post_remove |
| `signature` | null | No | **Reservado.** Siempre `null` en v0.6.1. Futura firma criptográfica. |

#### Ejemplo completo (pack `noctalia`)

```yaml
id: noctalia
name: Noctalia v4
description: |
  A Quickshell-based desktop shell layer for Niri and Hyprland compositors.
  Modular design: bar, notifications, clipboard history, night light, and
  calendar. The explicit stable/git split makes it one of the safest choices
  for an immutable system.

credits:
  author: noctalia-dev team
  homepage: https://github.com/noctalia-dev/noctalia-shell
  docs: https://docs.noctalia.dev/v4/getting-started/installation/#arch
  license: ~

compatibility:
  immutable: low
  profiles:
    - niri
    - hyprland
  note: AUR package, user-space config — no root writes required
  warning: ~
  critical_actions: []

variants:
  stable:
    packages: []
    aur:
      - noctalia-shell
    post_deploy: null
    version_hint: "v4 (stable)"
  git:
    packages: []
    aur:
      - noctalia-shell-git
    post_deploy: null
    version_hint: "git (bleeding edge)"

uninstall:
  packages: []
  aur:
    - noctalia-shell
    - noctalia-shell-git
  post_remove: null
  remove_config: false

signature: null
```

### 2.4 Schema de `system.yaml` — clave `dots_packs`

La clave `dots_packs` es una lista de objetos. Cada objeto representa un pack instalado.

```yaml
dots_packs:
  - id: "noctalia"
    channel: "stable"
    installed_version: "v4 (stable)"
    installed_at: "2026-06-07"
    origin: "builtin"          # "builtin" | "extern"
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | Identificador del pack instalado |
| `channel` | string | Canal de instalación: `stable` o `git` |
| `installed_version` | string | Versión o hint de versión al momento de instalación |
| `installed_at` | date (ISO 8601) | Fecha de instalación (`YYYY-MM-DD`) |
| `origin` | string | Origen del pack: `builtin` o `extern` |

La escritura siempre es **atómica**: `flock` sobre `system.yaml.lock` + escritura a `.tmp` + `os.replace()`.

### 2.5 Schema de `dots-repos.yaml`

Registra los repositorios externos configurados. Ubicado en `/etc/ouroboros/dots-repos.yaml`.

```yaml
repos:
  - name: "mi-repo"
    url: "https://github.com/usuario/dots-manifests.git"
    type: "git"          # "git" | "http"
    added_at: "2026-06-07"
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Nombre único del repositorio |
| `url` | url (HTTPS) | URL del repositorio. Solo HTTPS admitido. |
| `type` | string | `git` si es repositorio Git; `http` si es índice HTTP |
| `added_at` | date | Fecha de registro |

### 2.6 Schema de `index.yaml` (repositorios HTTP)

Los repositorios HTTP deben exponer un `index.yaml` en su raíz con la lista de packs disponibles.

```yaml
name: "Nombre del repositorio"
description: "Descripción breve"
maintainer: "nombre@email.com"
packs:
  - noctalia-custom
  - my-hyprland-pack
```

---

## 3. Flujos de Confirmación por Nivel

El nivel de compatibilidad (`compatibility.immutable`) determina el flujo de interacción antes de instalar.

### 3.1 LOW / MEDIUM — Sin aviso especial

- No se muestra ningún aviso previo de compatibilidad.
- Flujo directo: panel de info del pack → selección de canal (si aplica) → `[y/N]`.
- `--noconfirm` omite el `[y/N]` final.

### 3.2 HIGH — Aviso amarillo + `[y/N]`

```
⚠  HIGH compatibility impact: <note>
  Continue? [y/N]
```

- El aviso aparece **antes** del panel de info del pack.
- Solicita confirmación con una sola tecla (`y`), no "yes".
- `--noconfirm` **omite** el aviso y la confirmación HIGH.
- Si el usuario no confirma → salida limpia (exit 1, sin efectos secundarios).

### 3.3 CRITICAL — Panel rojo + tipear "yes" + bypass `OUROBOROS_ALLOW_CRITICAL=1`

```
╔══════════════════════════════════════════════════════════════╗
║  ⚠  CRITICAL COMPATIBILITY WARNING — <id>
╠══════════════════════════════════════════════════════════════╣

  <compatibility.warning>

  Actions that will be taken on your system:
    1. <critical_actions[0]>
    2. <critical_actions[1]>
    ...

╚══════════════════════════════════════════════════════════════╝

  Type 'yes' to proceed, anything else to cancel:
```

- El usuario debe tipear exactamente `yes` (case-insensitive).
- Si la respuesta no es `yes` → salida limpia (exit 1).
- `--noconfirm` es **ignorado** para packs CRITICAL. El sistema sale con error:
  `"CRITICAL pack requires OUROBOROS_ALLOW_CRITICAL=1 for unattended installation."`
- `OUROBOROS_ALLOW_CRITICAL=1` en el entorno → omite el panel y procede directamente.
  Solo para CI/automatización.
- Inmediatamente tras confirmación: se instala un trap `ERR`/`EXIT` de cleanup (ver §4).

### 3.4 Tabla de Comportamiento por Nivel y Flag

| Nivel | Sin flags | `--noconfirm` | `OUROBOROS_ALLOW_CRITICAL=1` |
|-------|-----------|---------------|------------------------------|
| low | Prompt `[y/N]` | Sin prompt | N/A |
| medium | Prompt `[y/N]` | Sin prompt | N/A |
| high | Aviso amarillo + `[y/N]` | Sin aviso, sin prompt | N/A |
| critical | Panel rojo + tipear "yes" | **Error** (exit 1) | Sin panel, procede directo |

---

## 4. Integración con Sistema de Snapshots

### 4.1 Snapshot pre-instalación

`our-dots` no crea snapshots por sí mismo. La protección se delega al sistema Btrfs existente:

- Antes de instalar un pack CRITICAL, el usuario debe tener un snapshot reciente via `our-rollback`.
- El CLI advierte al usuario sobre esta responsabilidad en el panel CRITICAL.
- No existe rollback automático de packs — la restauración usa `our-rollback` sobre snapshots Btrfs.

### 4.2 Snapshot post-instalación

No hay snapshot automático post-instalación de pack. El snapshot post-instalación del sistema es el creado por el estado `SNAPSHOT` de la FSM durante la instalación inicial.

### 4.3 Rollback

Si un pack falla durante la instalación:

- **Packs LOW/MEDIUM**: pacman/AUR pueden quedar parcialmente instalados. El usuario puede limpiar con `our-dots -R --force <id>` para remover paquetes huérfanos.
  > **`--force`:** Permite ejecutar `-R` aunque el pack no esté registrado en `system.yaml`. Sin este flag, `-R` sale con error si el pack no aparece en `dots_packs`. Con `--force`, se intentan remover los paquetes listados en el manifest sin verificar el registro previo.
- **Packs CRITICAL**: el trap de cleanup (CU-23 del PRD) intenta revertir las acciones críticas:
  1. Remontar `/` como read-only si fue remontado.
  2. Restaurar `/etc/pacman.conf` desde backup (`/etc/pacman.conf.our-dots-bak`).
  3. Intentar revertir paquetes instalados via `our-pac -R` (best-effort).
  4. Log de cleanup en `/var/log/our-dots/<id>-cleanup-<timestamp>.log`.
  5. Exit code 5.

---

## 5. Integración con our-pac y our-aur

### 5.1 Flujo de instalación de dependencias pacman

```bash
# Extrae packages del manifest (canal elegido)
mapfile -t pkgs < <(yaml_list "$mf" "variants.${channel}.packages")

if [[ ${#pkgs[@]} -gt 0 ]]; then
    our-pac -S "${pkgs[@]}" --noconfirm 2>&1 | tee -a "$logfile"
fi
```

- Se usa `our-pac -S` con `--noconfirm` (la confirmación ya fue obtenida por `our-dots`).
- El stdout y stderr de `our-pac` se capturan en el log de instalación.
- Fallo de `our-pac` → exit 1.

### 5.2 Flujo de instalación de dependencias AUR

```bash
# Extrae paquetes AUR del manifest
mapfile -t aur_pkgs < <(yaml_list "$mf" "variants.${channel}.aur")

if [[ ${#aur_pkgs[@]} -gt 0 ]]; then
    our-aur -S "${aur_pkgs[@]}" 2>&1 | tee -a "$logfile" || {
        log_error "AUR install failed. Check $logfile"
        exit 3
    }
fi
```

- AUR no acepta `--noconfirm` — `our-aur` maneja la interacción de build.
- Fallo de `our-aur` → exit 3 (diferenciado de error genérico).
- El tiempo de build puede ser largo para packs HIGH (DankLinux: ~10 min con toolchains Go/CMake/Rust).

### 5.3 Ejecución de post_deploy

```bash
local run_user="${SUDO_USER:-$USER}"
if [[ "$run_user" == "root" ]]; then
    bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || exit 4
else
    sudo -u "$run_user" bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || exit 4
fi
```

- `post_deploy` se ejecuta como `$SUDO_USER` (el usuario que invocó sudo), no como root.
- Si `SUDO_USER` no está definido (ejecución directa como root), corre como root.
- Fallo de `post_deploy` → exit 4. Los paquetes pacman/AUR ya instalados **quedan en el sistema**.
- El pack **no se registra en `system.yaml`** si `post_deploy` falla.

### 5.4 Manejo de errores

| Fallo | Exit code | Acción |
|-------|-----------|--------|
| `our-pac` falla | 1 | Log + salida. Pack no registrado. |
| `our-aur` falla | 3 | Log + salida. Pack no registrado. |
| `post_deploy` falla | 4 | Log + salida. Paquetes instalados, pack no registrado. |
| Pack CRITICAL + cleanup | 5 | Trap ejecutado. Log de cleanup. |

---

## 6. Comando -Su (Update)

### 6.1 Algoritmo de actualización

```
para cada pack en system.yaml.dots_packs:
    si pack.immutable == "critical":
        imprimir aviso → omitir del ciclo automático
        continuar
    
    obtener primer paquete AUR del pack (canal instalado)
    si paquete AUR existe:
        current_ver = pacman -Q <pkg> | awk '{print $2}'
        available_ver = AUR API (https://aur.archlinux.org/rpc/?v=5&type=info&arg=<pkg>)
        si available_ver != current_ver:
            cmd_install <id> --noconfirm
    sino si canal == "git":
        git -C <repo_dir> pull --ff-only
    sino:
        imprimir "update not available — reinstall manually"
```

### 6.2 Detección de actualizaciones por tipo de canal

| Tipo | Mecanismo | Endpoint |
|------|-----------|----------|
| AUR | API v5 de AUR, campo `Version` | `https://aur.archlinux.org/rpc/?v=5&type=info&arg=<pkg>` |
| git (sin AUR) | `git pull --ff-only` en directorio clonado | — |
| stable (sin AUR) | Sin mecanismo automático | Mensaje de reinstalación manual |

### 6.3 Exclusión de packs CRITICAL

Los packs CRITICAL son **excluidos** de `-Su` automático. Para actualizarlos:

```bash
sudo our-dots -S <id>   # reinstalación con confirmación completa
```

El log de `-Su` imprime por cada pack CRITICAL omitido:
```
[our-dots] WARNING: CRITICAL packs require manual update: sudo our-dots -S <id>
```

### 6.4 Manejo de errores en -Su

- API AUR no disponible → warning por pack, continúa con el siguiente.
- `git pull` falla → warning con sugerencia de `git pull --rebase`.
- Si un pack individual falla la actualización → continúa con el resto del lote.
- El resumen final indica: packs actualizados, omitidos y fallidos.

---

## 7. Sistema de Repositorios Externos

### 7.1 Formato de index.yaml (repositorios HTTP)

Los repositorios HTTP deben exponer `index.yaml` en su URL base con la lista de IDs de packs disponibles. Cada `<id>.yaml` debe ser accesible en `<url>/<id>.yaml`.

```yaml
name: "Community Dots"
packs:
  - my-niri-pack
  - custom-hyprland
```

### 7.2 Flujo de registro (Git)

```
1. Verificar que URL comienza con https://
2. git ls-remote "$url" HEAD (detecta si es repo Git)
3. git clone --depth=1 "$url" "$REPOS_DIR/$name"
4. Validar schema de cada *.yaml descargado
5. Registrar en dots-repos.yaml
```

### 7.3 Flujo de registro (HTTP)

```
1. Verificar HTTPS
2. curl -sfL "${url}/index.yaml" -o "${REPOS_DIR}/${name}/index.yaml"
3. Para cada ID en index.yaml.packs:
   - curl -sfL "${url}/${id}.yaml" -o "${dest}/${id}.yaml"
4. Validar schema de cada manifest descargado
5. Registrar en dots-repos.yaml
```

### 7.4 Resolución de conflictos de ID

Cuando el mismo ID de pack existe en múltiples fuentes:

1. **Built-in tiene prioridad absoluta** sobre cualquier fuente externa.
2. **Entre repositorios externos**: el primero registrado en `dots-repos.yaml` tiene prioridad.
3. No se emite warning cuando built-in sobreescribe externo (`find_manifest` simplemente retorna el built-in primero).

```bash
find_manifest() {
    local id="$1"
    # 1. Built-in primero
    local f="${MANIFEST_DIR}/${id}.yaml"
    [[ -f "$f" ]] && { echo "$f"; return 0; }
    # 2. Repositorios externos en orden de registro (dots-repos.yaml)
    #    Itera sobre el índice para garantizar orden determinista.
    #    `find` no se usa aquí porque retorna en orden de inodo.
    if [[ -f "$REPOS_INDEX" ]]; then
        local repo_name
        while IFS= read -r repo_name; do
            local f="${REPOS_DIR}/${repo_name}/${id}.yaml"
            [[ -f "$f" ]] && { echo "$f"; return 0; }
        done < <(yaml_list "${REPOS_INDEX}" "repos[].name")
    fi
    return 1
}
```

### 7.5 Validación de schema pre-ejecución

Antes de ejecutar cualquier hook (`post_deploy`, `post_remove`) de un manifest externo, `our-dots` valida los campos requeridos:

- `id` presente y no vacío
- `compatibility.immutable` con valor válido (`low`|`medium`|`high`|`critical`)
- `compatibility.profiles` es una lista no vacía
- Si `compatibility.immutable == "critical"`: `compatibility.warning` presente y `compatibility.critical_actions` no vacío

Manifest con schema inválido → warning con path y campos faltantes. El manifest se ignora (no se ejecuta ningún hook). El repositorio puede registrarse de todos modos; los manifests inválidos se omiten silenciosamente del catálogo.

### 7.6 Indicador `[EXTERN]`

Los packs provenientes de `REPOS_DIR` se marcan visualmente con `[EXTERN]` en:
- `our-dots list` (columna NAME)
- `our-dots -Si <id>` (línea de origen)
- Mensaje previo a instalación: `"This pack is from an external repository not audited by the ouroborOS project."`

### 7.7 Actualización de repositorios (`repo-update`)

```
para cada repo en dots-repos.yaml:
    si REPOS_DIR/<name>/.git existe:
        git -C "$dest" pull --ff-only
    sino:
        re-ejecutar cmd_repo_add (HTTP re-download)
    
    si falla:
        warning, continuar con siguiente repo
```

---

## 8. Wiring con system.yaml

### 8.1 Campos de la entrada `dots_packs`

```yaml
dots_packs:
  - id: "caelestia"
    channel: "git"
    installed_version: "AUR (git)"
    installed_at: "2026-06-07"
    origin: "builtin"
```

| Campo | Fuente | Descripción |
|-------|--------|-------------|
| `id` | manifest `id` | Identificador del pack |
| `channel` | argumento CLI / selección TUI | `stable` o `git` |
| `installed_version` | `variants.<channel>.version_hint` | Hint descriptivo de versión |
| `installed_at` | `datetime.date.today().isoformat()` | Fecha ISO 8601 |
| `origin` | `find_manifest()` — si path está bajo `MANIFEST_DIR` → `builtin`, else `extern` | Origen del manifest |

### 8.2 Concurrencia: flock + atomic write

Todas las escrituras en `system.yaml` siguen el protocolo:

```python
# 1. Adquirir advisory lock
with open(path + ".lock", "w") as lock_fh:
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Reintentar hasta 5 segundos
        time.sleep(0.1)
        ...
    # Timeout de 5 segundos → abortar con error

# 2. Leer estado actual
with open(path) as f:
    doc = yaml.safe_load(f) or {}

# 3. Modificar en memoria (upsert por id)
packs = doc.setdefault("dots_packs", [])
packs = [p for p in packs if p.get("id") != id]
packs.append({...})
doc["dots_packs"] = packs

# 4. Escribir a .tmp
tmp = path + ".tmp"
with open(tmp, "w") as f:
    yaml.dump(doc, f, default_flow_style=False, allow_unicode=True)

# 5. Reemplazar atómicamente
os.replace(tmp, path)

# 6. Lock liberado al salir del context manager
```

- El lock tiene **timeout de 5 segundos**. Si no se obtiene → error: `"system.yaml is locked by another our-dots process."`.
- `os.replace()` es atómica en el mismo filesystem (syscall `rename(2)`).
- El archivo `.tmp` siempre se borra si `os.replace()` falla (manejo de excepción).

### 8.3 Comportamiento con system.yaml inexistente

- `sysyaml_is_installed()` → retorna 1 (no instalado) sin error.
- `sysyaml_add_pack()` → requiere root; si `system.yaml` no existe, lo crea con el esquema mínimo.
- `cmd_query()` → imprime `"(no packs installed)"` sin error.

---

## 9. Integración con el Instalador (FSM)

### 9.1 Estado `DOTS_PACK` en la FSM

El estado `DOTS_PACK` está definido en `src/installer/state_machine.py`:

```python
class State(Enum):
    ...
    DESKTOP = auto()
    DOTS_PACK = auto()    # Nuevo en v0.6.1
    SECURE_BOOT = auto()
    ...
```

Posición en el orden de ejecución:
```
INIT → NETWORK_SETUP → PREFLIGHT → LOCALE → USER → DESKTOP
     → DOTS_PACK → SECURE_BOOT → PARTITION → FORMAT → INSTALL
     → CONFIGURE → SNAPSHOT → FINISH
```

Progreso en la barra global: steps 21–23 (de 100).

### 9.2 Handler `_handle_dots_pack()`

```python
def _handle_dots_pack(self) -> None:
    self._update_progress(State.DOTS_PACK, 0)

    # Omisión automática para perfil minimal
    if self.config.desktop.profile == "minimal":
        log.info("DOTS_PACK: profile is minimal — skipping dotfiles pack selection.")
        self._update_progress(State.DOTS_PACK, 100)
        return

    # Modo interactivo: mostrar TUI
    if self.tui:
        result = self.tui.show_dots_pack_selection(self.config.desktop.profile)
        self.config.dots_pack.pack = result.get("pack")
        self.config.dots_pack.channel = result.get("channel", "stable")
    else:
        # Modo unattended: corregir canal si el pack es single-channel.
        # DotsPackConfig.channel defaults to "stable"; si el pack solo tiene
        # canal git (e.g. illogical-impulse, omarchy), la instalación fallaría.
        pack_id = self.config.dots_pack.pack
        if pack_id:
            catalog = {p.id: p for p in load_catalog()}
            pack = catalog.get(pack_id)
            if pack:
                if not pack.has_stable and pack.has_git:
                    self.config.dots_pack.channel = "git"
                elif pack.has_stable and not pack.has_git:
                    self.config.dots_pack.channel = "stable"

    log.info("Dots pack: %s (channel: %s)",
             self.config.dots_pack.pack or "none",
             self.config.dots_pack.channel)
    self._update_progress(State.DOTS_PACK, 100)
```

### 9.3 Omisión automática

El estado `DOTS_PACK` se omite (FSM avanza a `SECURE_BOOT`) en los siguientes casos:

| Condición | Comportamiento |
|-----------|---------------|
| `profile == "minimal"` | Omisión silenciosa. Log informativo. |
| TUI: usuario selecciona "Ninguno" | `dots_pack.pack = None`. No se instala pack. |
| Unattended: `config.dots_pack.pack == None` | No se instala pack. |
| Sin packs compatibles con el perfil | `packs_for_profile()` retorna lista vacía → UI muestra solo "Ninguno". |

### 9.4 Pantalla TUI `show_dots_pack_selection()`

La función `TUI.show_dots_pack_selection(profile)` (implementada en `tui_textual.py`):

1. Llama a `dots_profiles.packs_for_profile(profile)` para obtener el catálogo filtrado.
2. Presenta un widget `Select` con las opciones: `[("Ninguno", None)] + [(pack.name, pack.id) for pack in packs]`.
3. Para el pack seleccionado (si no es `None`):
   - Si `has_stable=True` y `has_git=True` → presenta selección de canal al usuario.
   - Si solo `has_git=True` → fija automáticamente `channel="git"` sin mostrar selección.
   - Si solo `has_stable=True` → fija automáticamente `channel="stable"` sin mostrar selección.
4. Retorna `{"pack": <id o None>, "channel": <"stable"|"git">}`.

### 9.5 Integración con `configure.sh`

El pack seleccionado se pasa a `configure.sh` via variables de entorno:

```python
env.update({
    ...
    "DOTS_PACK": self.config.dots_pack.pack or "",
    "DOTS_CHANNEL": self.config.dots_pack.channel,
})
```

`configure.sh` ejecuta el siguiente fragmento dentro del chroot si `$DOTS_PACK` no está vacío:

```bash
channel_flag=""
[[ "$DOTS_CHANNEL" == "git" ]] && channel_flag="--git"
our-dots -S "$DOTS_PACK" $channel_flag --noconfirm
```

El flag `--stable` no existe; el canal stable es el comportamiento por defecto cuando no se pasa `--git`.

### 9.6 Función `packs_for_profile()`

```python
def packs_for_profile(profile: str, manifest_dir: Path = MANIFEST_DIR) -> list[DotsPack]:
    """Return packs compatible with the given desktop profile."""
    return [p for p in load_catalog(manifest_dir) if profile in p.profiles]
```

- Retorna lista vacía si no hay packs compatibles (sin error).
- Perfil desconocido → lista vacía (no error).

---

## 10. Seguridad

### 10.1 Validación de manifests externos

- **Obligatoria** antes de ejecutar cualquier hook de manifest externo.
- Campos validados: `id`, `compatibility.immutable` (enum válido), `compatibility.profiles` (lista no vacía).
- Para CRITICAL: también `compatibility.warning` y `compatibility.critical_actions`.
- Manifest inválido → warning + ignorar. El repositorio puede registrarse pero los manifests inválidos no se ejecutan.

### 10.2 Indicador `[EXTERN]`

Todos los packs provenientes de `REPOS_DIR` se marcan con `[EXTERN]` en toda la UI. El aviso explícito es obligatorio antes de la instalación:

```
This pack is from an external repository not audited by the ouroborOS project.
```

No hay supresión de este aviso via flag.

### 10.3 Ejecución de `post_deploy` como `SUDO_USER`

```bash
local run_user="${SUDO_USER:-$USER}"
if [[ "$run_user" == "root" ]]; then
    bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || exit 4
else
    sudo -u "$run_user" bash -c "$post_deploy" 2>&1 | tee -a "$logfile" || exit 4
fi
```

- Los hooks nunca corren como root a menos que el usuario haya invocado `our-dots` directamente como root (sin sudo).
- Los scripts `post_deploy` y `post_remove` se ejecutan con el entorno del usuario original.
- El mismo patrón aplica a `post_remove` (ver §5.3).

### 10.4 Restricción de paths en hooks

Los hooks (`post_deploy`, `post_remove`) en manifests externos deben ser **scripts inline** (strings YAML), no paths absolutos a archivos del sistema. Esto previene que un manifest externo referencie y ejecute binarios arbitrarios del sistema.

La validación de schema verifica que `post_deploy`/`post_remove` sean `null` o strings (script inline), no paths que comiencen con `/`.

### 10.5 Solo HTTPS para repositorios externos

```bash
[[ "$url" == https://* ]] || die "Repository URL must use HTTPS"
```

HTTP simple es rechazado en `repo-add`. Esto aplica tanto para repos Git como para repos HTTP de manifests.

### 10.6 Firma criptográfica (reservado)

El campo `signature: null` está reservado para firma criptográfica futura de manifests. En v0.6.1 siempre es `null`. Los manifests externos son aceptados sin firma. En una versión futura, `signature` contendrá la firma GPG/minisign del manifest para verificación antes de ejecución de hooks.

### 10.7 Trap de cleanup para CRITICAL

Instalado inmediatamente tras confirmación de un pack CRITICAL:

```bash
cleanup_critical() {
    # Restaurar / a read-only si fue remontado
    mount -o remount,ro / 2>/dev/null || true
    # Restaurar pacman.conf desde backup
    [[ -f /etc/pacman.conf.our-dots-bak ]] && \
        cp /etc/pacman.conf.our-dots-bak /etc/pacman.conf
    # Intentar revertir paquetes instalados (best-effort) y salir con exit 5.
    # Flujo completo documentado en §4.3.
    log_warn "CRITICAL cleanup executed. System state restored."
}
trap cleanup_critical ERR EXIT
```

---

## 11. Logging y Debug

### 11.1 Directorio de logs

```
/var/log/our-dots/
├── <id>-<YYYYMMDD-HHMMSS>.log         # Log de instalación principal
└── <id>-cleanup-<YYYYMMDD-HHMMSS>.log  # Log de cleanup (solo packs CRITICAL fallidos)
```

- El directorio se crea automáticamente al inicio de cada instalación (`mkdir -p "$LOG_DIR"`).
- El path del log se informa al usuario antes de iniciar la instalación.
- Los logs capturan stdout + stderr de `our-pac`, `our-aur` y los scripts `post_deploy`.

### 11.2 Rotación de logs

- Los logs en `/var/log/our-dots/` no se rotan automáticamente en v0.6.1.
- Política FHS: los archivos son gestionables via logrotate en versiones futuras.
- Los logs de instalaciones antiguas no se borran automáticamente.
- **Futuro (v0.6.2+):** Se instalará `/etc/logrotate.d/our-dots` con política: rotación diaria, máximo 10 archivos, compresión gzip.

### 11.3 Niveles de log en CLI

| Función | Color | Destino | Uso |
|---------|-------|---------|-----|
| `log_info()` | Verde | stdout | Progreso normal |
| `log_warn()` | Amarillo | stderr | Condiciones no fatales |
| `log_error()` | Rojo | stderr | Errores antes de salir |
| `die()` | Rojo | stderr | Error fatal + exit 1 |

---

## 12. Tabla de Exit Codes

| Exit Code | Nombre | Descripción |
|-----------|--------|-------------|
| 0 | OK | Operación completada exitosamente |
| 1 | ERROR_GENERIC | Error genérico: pack no encontrado, root requerido, usuario canceló, CRITICAL sin OUROBOROS_ALLOW_CRITICAL=1 |
| 3 | AUR_FAIL | Fallo en instalación de paquetes AUR |
| 4 | POST_DEPLOY_FAIL | `post_deploy` retornó exit code ≠ 0. Paquetes instalados, pack no registrado en system.yaml. |
| 5 | CRITICAL_FAIL_CLEANUP | Fallo durante instalación CRITICAL + trap de cleanup ejecutado. Sistema restaurado a estado inmutable. |

---

## 13. Dependencias del Sistema

| Dependencia | Versión Mínima | Rol |
|-------------|---------------|-----|
| Bash | 5.0+ | Runtime de `our-dots` CLI |
| Python | 3.11+ | Parsing de YAML, escritura atómica de `system.yaml` |
| PyYAML | 6.0+ | `yaml.safe_load()` / `yaml.dump()` |
| `our-pac` | v0.6.0+ | Instalación y remoción de paquetes pacman |
| `our-aur` | v0.6.0+ | Instalación y remoción de paquetes AUR |
| git | 2.30+ | Clonar repositorios externos; `post_deploy` de packs git |
| curl | 7.80+ | Descargar `index.yaml` de repos HTTP; API AUR en `-Su` |
| util-linux (`flock`) | 2.37+ | Advisory lock para escritura concurrente de `system.yaml` |
| Python stdlib (`os.replace`) | — | Reemplazamiento atómico de archivos (syscall `rename(2)`) |

### Paquetes en `packages.x86_64` del ISO

Para que `our-dots` funcione desde el sistema instalado (no el live), estos paquetes deben estar incluidos en el perfil de archiso:

- `python-yaml` — parsing de manifests
- `git` — repos externos y packs git
- `curl` — repos HTTP y API AUR
- `util-linux` — `flock`

---

## 14. Restricciones Técnicas

1. **`our-dots` requiere root** para: escritura en `/etc/`, `/var/`, instalación de paquetes. `post_deploy`/`post_remove` se ejecutan como `$SUDO_USER`, no como root.

2. **`MANIFEST_DIR` es read-only**. Los manifests built-in forman parte del ISO y no son modificables en el sistema instalado. Solo `REPOS_DIR` es mutable.

3. **`system.yaml` es la única fuente de verdad** para el estado de instalación. No hay base de datos propia. La ausencia de `system.yaml` implica que ningún pack puede estar instalado.

4. **Escritura atómica obligatoria en `system.yaml`**: siempre `flock` + `.tmp` + `os.replace()`. Nunca escritura directa al archivo.

5. **No instalación simultánea de múltiples packs CRITICAL** en una sola invocación. El diseño es secuencial e interactivo para CRITICAL.

6. **Solo HTTPS para repos externos.** HTTP simple es rechazado en `repo-add`.

7. **Manifests externos validados antes de ejecución de hooks.** Schema inválido → manifest ignorado, sin ejecución de código.

8. **`post_deploy` y `post_remove` son scripts inline** (strings en el YAML), no paths a archivos. Esto previene ejecución de binarios arbitrarios referenciados por manifests externos.

9. **Todos los scripts `.sh` deben pasar `shellcheck -S style`** y comenzar con `set -euo pipefail`.

10. **Packs con `compatibility.profiles` que no incluyen el perfil activo** no aparecen en la TUI del instalador, aunque sean instalables via CLI. El CLI no filtra por perfil.

11. **Canal git solo disponible si `variants.git` está definido** en el manifest. `--git` con un pack sin canal git → error descriptivo.

12. **El campo `signature` siempre es `null` en v0.6.1.** Manifests con signature no nula no son rechazados, pero la firma no es verificada. La verificación es futura.

13. **Timeout de lock en `system.yaml`: 5 segundos.** Proceso bloqueante → abortar con mensaje indicando el proceso que mantiene el lock.

14. **`dots_profiles.py` lee el manifest con schema canónico**: `compatibility.immutable` (no `compatibility` plano), `compatibility.profiles` (no `profiles` plano). Las funciones `load_catalog()` y `packs_for_profile()` reflejan la estructura real de los manifests YAML.
