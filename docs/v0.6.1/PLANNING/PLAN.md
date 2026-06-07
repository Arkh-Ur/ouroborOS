# PLAN — ouroborOS v0.6.1: Gestor de Dotfiles `our-dots`

**Versión:** 1.0  
**Fecha:** 2026-06-07  
**Autor:** ouroborOS dev team  

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Dependencias](#2-dependencias)
3. [Fase 1: Foundation](#3-fase-1-foundation)
4. [Fase 2: CLI Core](#4-fase-2-cli-core)
5. [Fase 3: Advanced](#5-fase-3-advanced)
6. [Fase 4: FSM Integration](#6-fase-4-fsm-integration)
7. [Fase 5: Testing](#7-fase-5-testing)
8. [Fase 6: Polish](#8-fase-6-polish)
9. [Timeline](#9-timeline)
10. [Riesgos y Mitigaciones](#10-riesgos-y-mitigaciones)
11. [Criterios de Aceptación](#11-criterios-de-aceptación)
12. [Entregables](#12-entregables)
13. [Rollback Plan](#13-rollback-plan)
14. [Referencias Cruzadas](#14-referencias-cruzadas)

---

## 1. Resumen Ejecutivo

Implementación del gestor de dotfiles `our-dots` para ouroborOS v0.6.1, soportando **7 packs de dotfiles** seleccionables durante la instalación, con CLI Bash (`our-dots`), módulo Python para el instalador TUI (`dots_profiles.py`), y sistema de snapshots Btrfs integrado.

**6 fases**, estimación total: **~95 horas** (~12 jornadas de 8h).

| Fase | Nombre | Horas | Depende de |
|------|--------|-------|------------|
| 1 | Foundation | 18h | — |
| 2 | CLI Core | 24h | F1 |
| 3 | Advanced | 16h | F2 |
| 4 | FSM Integration | 14h | F2 |
| 5 | Testing | 16h | F4 |
| 6 | Polish | 7h | F5 |

**Critical path:** F1 → F2 → F4 → F5 → F6 (~79h, ~10 jornadas).

---

## 2. Dependencias

### 2.1 Externas (paquetes Arch)

| Paquete | Versión | Propósito | ¿En ISO? |
|---------|---------|-----------|----------|
| `bash` | ≥5.0 | CLI runtime | ✅ |
| `python` | ≥3.11 | Installer, yaml_get/yaml_list helpers | ✅ |
| `python-pyyaml` | ≥6.0 | Parsing YAML | ✅ |
| `git` | ≥2.40 | Clone/pull repos externos | ✅ |
| `curl` | ≥8.0 | HTTP fetch manifests | ✅ |
| `flock` (util-linux) | ≥2.38 | Escritura atómica system.yaml | ✅ |
| `pacman` | ≥6.0 | Instalación paquetes (via our-pac) | ✅ |
| `textual` | ≥0.40 | TUI del instalador | ✅ |

### 2.2 Internas (código existente)

| Componente | Path | Uso |
|------------|------|-----|
| `our-pac` | `/usr/local/bin/our-pac` | Wrapper pacman para sistema inmutable |
| `our-aur` | `/usr/local/bin/our-aur` | Wrapper AUR helper |
| `our-rollback` | `/usr/local/bin/our-rollback` | Btrfs snapshot/rollback |
| `state_machine.py` | `src/state_machine.py` | FSM del instalador |
| `config.py` | `src/config.py` | Dataclass InstallerConfig |
| Manifests YAML | `src/dots/*.yaml` | Catálogo de packs |

---

## 3. Fase 1: Foundation

**Objetivo:** Infraestructura base — schema YAML, carga de catálogo, helpers.

### Tareas

| ID | Tarea | Archivos | Horas | CU |
|----|-------|----------|-------|-----|
| F1-01 | Definir schema manifest YAML (TRD §2.3) | `src/dots/*.yaml` (7 manifests) | 3h | — |
| F1-02 | Implementar `load_catalog()` Python | `src/dots_profiles.py` | 4h | CU-01 |
| F1-03 | Implementar `DotsPack` dataclass | `src/dots_profiles.py` | 2h | CU-01 |
| F1-04 | Implementar `DotsPackConfig` dataclass | `src/config.py` | 1h | CU-15 |
| F1-05 | Implementar `yaml_get()` Bash helper | `src/our-dots` | 2h | CU-01 |
| F1-06 | Implementar `yaml_list()` Bash helper | `src/our-dots` | 2h | CU-01 |
| F1-07 | Implementar `validate_manifest_schema()` | `src/our-dots` | 3h | CU-19 |
| F1-08 | Crear 7 manifests YAML completos | `src/dots/{ml4w,noctalia,caelestia,illogical-impulse,omarchy,ambxst,danklinux}.yaml` | 4h | — |

**Total F1:** 21h (ajustado con overlap)

### Detalle de manifests (F1-08)

Cada manifest sigue schema TRD §2.3:

```yaml
id: ml4w                    # Identificador único
name: ML4W Dotfiles         # Nombre display
description: "Stephan Raabe's Hyprland setup"
compatibility: high          # low|medium|high|critical
credits:
  author: Stephan Raabe
  homepage: https://github.com/mylinuxforwork/dotfiles
  license: GPL-3.0
has_stable: true
has_git: true
variants:
  stable:
    packages: [hyprland, waybar, rofi-wayland]
    aur: [ml4w-hyprland]
    post_deploy: null
    version_hint: "4.0"
  git:
    url: https://github.com/mylinuxforwork/dotfiles
    packages: [hyprland, waybar, rofi-wayland]
    aur: [ml4w-hyprland-git]
    post_deploy: "cp -r ~/.config/hypr ~/.config/hypr.bak 2>/dev/null; echo 'ML4W deployed'"
    version_hint: "rolling"
```

**Canales por pack:**

| Pack | stable | git | Nivel |
|------|--------|-----|-------|
| ML4W | ✅ | ✅ | high |
| Noctalia v4 | ✅ | ✅ | medium |
| Caelestia Shell | ✅ | — | low |
| illogical impulse | — | ✅ | medium |
| Omarchy | — | ✅ | high |
| Ambxst | — | ✅ | low |
| DankMaterialShell | ✅ | — | low |

---

## 4. Fase 2: CLI Core

**Objetivo:** Subcomandos básicos de `our-dots`.

### Tareas

| ID | Tarea | Archivos | Horas | CU |
|----|-------|----------|-------|-----|
| F2-01 | Implementar `cmd_list()` | `src/our-dots` | 2h | CU-01 |
| F2-02 | Implementar `cmd_info()` (-Si) | `src/our-dots` | 3h | CU-02 |
| F2-03 | Implementar `cmd_install()` (-S) — flujo LOW/MED | `src/our-dots` | 6h | CU-03 |
| F2-04 | Implementar confirmación HIGH | `src/our-dots` | 2h | CU-04 |
| F2-05 | Implementar confirmación CRITICAL + remount + trap | `src/our-dots` | 4h | CU-05 |
| F2-06 | Implementar `cmd_remove()` (-R) | `src/our-dots` | 4h | CU-06 |
| F2-07 | Implementar `cmd_query()` (-Q) | `src/our-dots` | 2h | CU-07 |
| F2-08 | Implementar `cmd_search()` (-Qs) | `src/our-dots` | 3h | CU-08 |
| F2-09 | Implementar `sysyaml_add_pack()` / `sysyaml_remove_pack()` | `src/our-dots` | 4h | CU-03/06 |
| F2-10 | Implementar logging + rotation | `src/our-dots` | 2h | — |
| F2-11 | Implementar cleanup trap CRITICAL | `src/our-dots` | 2h | CU-05/23 |
| F2-12 | Implementar `--noconfirm` + `OUROBOROS_ALLOW_CRITICAL` | `src/our-dots` | 2h | CU-16 |
| F2-13 | Agregar `set -euo pipefail` header | `src/our-dots` | 0.5h | — |
| F2-14 | Implementar `_autocorrect_channel_flag()` | `src/our-dots` | 1h | CU-03 |

**Total F2:** 37.5h → ajustado a **24h** (algunos overlaps con F1)

---

## 5. Fase 3: Advanced

**Objetivo:** Upgrade y repositorios externos.

### Tareas

| ID | Tarea | Archivos | Horas | CU |
|----|-------|----------|-------|-----|
| F3-01 | Implementar `cmd_upgrade()` (-Su) | `src/our-dots` | 4h | CU-09 |
| F3-02 | Implementar detección versión AUR API | `src/our-dots` | 3h | CU-09 |
| F3-03 | Implementar exclusión CRITICAL en -Su | `src/our-dots` | 2h | CU-09 |
| F3-04 | Implementar `cmd_repo_add()` Git | `src/our-dots` | 2h | CU-10 |
| F3-05 | Implementar `cmd_repo_add()` HTTP | `src/our-dots` | 2h | CU-11 |
| F3-06 | Implementar `cmd_repo_remove()` | `src/our-dots` | 1h | CU-12 |
| F3-07 | Implementar `cmd_repo_list()` | `src/our-dots` | 1h | CU-13 |
| F3-08 | Implementar `cmd_repo_update()` | `src/our-dots` | 2h | CU-14 |
| F3-09 | Implementar `find_manifest()` con prioridad | `src/our-dots` | 2h | CU-25 |
| F3-10 | Implementar validación HTTPS + schema externo | `src/our-dots` | 2h | CU-19 |
| F3-11 | Implementar marca `[EXTERN]` no suprimible | `src/our-dots` | 1h | CU-20 |

**Total F3:** 22h → ajustado a **16h**

---

## 6. Fase 4: FSM Integration

**Objetivo:** Integración con el instalador Textual.

### Tareas

| ID | Tarea | Archivos | Horas | CU |
|----|-------|----------|-------|-----|
| F4-01 | Implementar `_handle_dots_pack()` en state_machine.py | `src/state_machine.py` | 4h | CU-15 |
| F4-02 | Implementar auto-corrección canal git-only | `src/state_machine.py` | 1h | CU-15 |
| F4-03 | Implementar TUI selección pack + canal | `src/installer/tui.py` | 4h | CU-15 |
| F4-04 | Implementar omisión automática (4 condiciones) | `src/state_machine.py` | 2h | CU-15 |
| F4-05 | Implementar `packs_for_profile()` | `src/dots_profiles.py` | 2h | CU-15 |
| F4-06 | Integrar `configure.sh` con env vars | `src/configure.sh` | 2h | CU-15 |
| F4-07 | Progreso steps 21-23 de 100 | `src/state_machine.py` | 1h | — |

**Total F4:** 16h → ajustado a **14h**

---

## 7. Fase 5: Testing

**Objetivo:** Suite completa de tests según TEST v1.1.

### Tareas

| ID | Tarea | Archivos | Horas | CU |
|----|-------|----------|-------|-----|
| F5-01 | Unit tests Python: load_catalog, DotsPack | `tests/test_dots_profiles.py` | 4h | CU-01 |
| F5-02 | Unit tests Python: sysyaml helpers | `tests/test_sysyaml.py` | 3h | CU-03/06 |
| F5-03 | Unit tests Bash (bats): CLI subcomandos | `tests/test_our_dots.bats` | 4h | CU-01-08 |
| F5-04 | Integration tests: flujos completos | `tests/test_integration.py` | 4h | CU-03/05/09 |
| F5-05 | Security tests: inyección, HTTPS, CRITICAL | `tests/test_security.py` | 2h | CU-19/20 |
| F5-06 | Concurrency tests: flock, atomic write | `tests/test_concurrency.py` | 2h | CU-22 |
| F5-07 | Regression tests: C-01 a M-05 | `tests/test_regression.py` | 2h | — |
| F5-08 | GitHub Actions CI/CD workflow | `.github/workflows/test-dots.yml` | 2h | — |
| F5-09 | Coverage ≥93% + fail-under gate | `pyproject.toml` / CI | 1h | — |

**Total F5:** 24h → ajustado a **16h** (tests escritos en paralelo con código)

---

## 8. Fase 6: Polish

**Objetivo:** Detalles finales antes de release.

### Tareas

| ID | Tarea | Archivos | Horas |
|----|-------|----------|-------|
| F6-01 | Implementar `NO_COLOR=1` en funciones de log | `src/our-dots` | 1h |
| F6-02 | Implementar i18n (es/en) con gettext o env vars | `src/our-dots` | 3h |
| F6-03 | Generar manpage `our-dots.1` | `docs/man/our-dots.1` | 1h |
| F6-04 | Actualizar README.md con ejemplos | `README.md` | 1h |
| F6-05 | Review final de código (lint, shellcheck) | `src/` | 1h |

**Total F6:** 7h

---

## 9. Timeline

### 9.1 Gantt Simplificado

```
Semana 1: [F1----][F2-------->
Semana 2: [F2--------][F3----][F4---->
Semana 3: [F5--------][F6--]
```

### 9.2 Milestones

| Milestone | Fecha Target | Entregable |
|-----------|-------------|------------|
| M1: Foundation completa | Día 3 | 7 manifests + load_catalog + helpers |
| M2: CLI Core funcional | Día 7 | our-dots con -S/-R/-Q/-Qs/-Si/list |
| M3: Advanced completa | Día 10 | -Su + repos externos |
| M4: FSM integrada | Día 12 | Instalador TUI con dotfiles |
| M5: Testing ≥93% | Día 14 | CI verde, coverage达标 |
| M6: Release v0.6.1 | Día 15 | ISO con our-dots completo |

### 9.3 Critical Path

```
F1-02 (load_catalog) → F2-03 (cmd_install) → F4-01 (FSM handler) → F5-01 (tests) → F6-05 (review)
```

**Duración critical path:** ~79h (~10 jornadas)

---

## 10. Riesgos y Mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|--------|-------------|---------|------------|
| R1 | Manifests de packs reales cambian | Media | Bajo | Versionar manifests, fallback a git sha |
| R2 | AUR API cambia o cae | Baja | Medio | Cache local + timeout + retry |
| R3 | Btrfs remount falla en CI | Media | Alto | Skip CRITICAL tests en CI, solo E2E |
| R4 | Textual TUI cambia API | Baja | Medio | Pin versión en requirements |
| R5 | Packs CRITICAL rompen sistema | Baja | Crítico | Snapshot pre-install + trap cleanup + OUROBOROS_ALLOW_CRITICAL |
| R6 | CC session limit bloquea desarrollo | Alta | Medio | Generar docs en horas valle, distribuir carga |

---

## 11. Criterios de Aceptación

### Por Fase

| Fase | Criterio | PRD CU | Verificación |
|------|----------|--------|-------------|
| F1 | `load_catalog()` carga 7 packs sin error | CU-01 | Unit test |
| F1 | Schema validation rechaza manifest inválido | CU-19 | Unit test |
| F2 | `our-dots -S ml4w` instala correctamente | CU-03 | Integration test |
| F2 | `our-dots -R ml4w` remueve correctamente | CU-06 | Integration test |
| F2 | CRITICAL pack requiere confirmación interactiva | CU-05 | Integration test |
| F2 | `--noconfirm` ignora CRITICAL sin OUROBOROS_ALLOW_CRITICAL | CU-16 | Integration test |
| F3 | `our-dots -Su` detecta updates via AUR | CU-09 | Integration test |
| F3 | `repo-add` con HTTPS funciona | CU-11 | Integration test |
| F4 | FSM instala pack en modo unattended | CU-15 | E2E test (QEMU) |
| F4 | Pack git-only se auto-corrige a canal git | CU-15 | Unit test |
| F5 | Coverage ≥93% en dots_profiles.py | — | CI gate |
| F5 | CI verde en PR | — | GitHub Actions |
| F6 | `NO_COLOR=1` suprime colores | — | Unit test |

---

## 12. Entregables

### 12.1 Por Fase

| Fase | Archivos nuevos | Archivos modificados |
|------|----------------|---------------------|
| F1 | `src/dots/*.yaml` (7), helpers en `src/our-dots` | `src/dots_profiles.py`, `src/config.py` |
| F2 | Funciones en `src/our-dots` | — |
| F3 | Funciones en `src/our-dots` | — |
| F4 | Handler en `src/state_machine.py` | `src/configure.sh` |
| F5 | `tests/*.py`, `tests/*.bats`, `.github/workflows/test-dots.yml` | — |
| F6 | `docs/man/our-dots.1` | `README.md` |

### 12.2 PR Checklist

- [ ] Todos los manifests YAML pasan `validate_manifest_schema`
- [ ] `our-dots list` muestra 7 packs
- [ ] `our-dots -S <pack>` instala LOW/MED sin confirmación
- [ ] `our-dots -S <pack>` requiere confirmación HIGH
- [ ] `our-dots -S <pack>` remount + trap para CRITICAL
- [ ] `--noconfirm` respeta OUROBOROS_ALLOW_CRITICAL
- [ ] `our-dots -R <pack>` remueve y limpia system.yaml
- [ ] `our-dots -Su` detecta updates
- [ ] `repo-add` HTTPS funciona
- [ ] FSM TUI muestra selección de packs
- [ ] Unattended mode instala pack sin interacción
- [ ] Coverage ≥93%
- [ ] CI verde
- [ ] `shellcheck` sin errores
- [ ] E2E test en QEMU pasa

---

## 13. Rollback Plan

| Escenario | Acción |
|-----------|--------|
| F1 falla (schema incompatible) | Revertir manifests, mantener código existente |
| F2 falla (CLI roto) | `git revert` en branch, mantener F1 |
| F3 falla (upgrade roto) | Desactivar -Su, release sin upgrade |
| F4 falla (FSM rota) | Skip DOTS_PACK state, instalar manualmente post-ISO |
| F5 falla (coverage <93%) | Extender deadline, no bloquear release |
| F6 falla (i18n) | Release sin i18n, agregar en v0.6.2 |

**Principio:** Cada fase es incremental. Si una falla, las anteriores siguen funcionando.

---

## 14. Referencias Cruzadas

### 14.1 PRD → PLAN

| PRD Sección | PLAN Fase | Notas |
|-------------|-----------|-------|
| §6 (7 packs) | F1-08 | Manifests YAML |
| CU-01 (list) | F2-01 | cmd_list |
| CU-02 (info) | F2-02 | cmd_info |
| CU-03 (install) | F2-03/04/05 | cmd_install |
| CU-04 (HIGH warn) | F2-04 | Confirmación HIGH |
| CU-05 (CRITICAL) | F2-05 | Remount + trap |
| CU-06 (remove) | F2-06 | cmd_remove |
| CU-07 (query) | F2-07 | cmd_query |
| CU-08 (search) | F2-08 | cmd_search |
| CU-09 (upgrade) | F3-01 | cmd_upgrade |
| CU-10-14 (repos) | F3-04/05/06/07/08 | repo subcomandos |
| CU-15 (FSM) | F4-01/02/03 | Integración instalador |
| CU-16 (--noconfirm) | F2-12 | Flags |
| CU-19 (validación) | F1-07 | Schema validation |
| CU-20 ([EXTERN]) | F3-11 | Marca visual |
| CU-22 (concurrency) | F5-06 | Tests flock |
| CU-23 (cleanup) | F2-11 | Trap cleanup |

### 14.2 TRD → PLAN

| TRD Sección | PLAN Fase |
|-------------|-----------|
| §2.3 Schema Manifest | F1-01/08 |
| §3 Flujos Confirmación | F2-04/05/12 |
| §4 Snapshots | F2-05 (integrado) |
| §5 our-pac/our-aur | F2-03 (integrado) |
| §6 -Su | F3-01/02/03 |
| §7 Repos Externos | F3-04 a F3-11 |
| §8 system.yaml | F2-09 |
| §9 FSM Integration | F4-01 a F4-07 |

### 14.3 SPEC → PLAN

| SPEC Sección | PLAN Fase |
|-------------|-----------|
| §3 CLI Interfaces | F2 |
| §4 Formato Datos | F1 |
| §5 Algoritmos | F2/F3 |
| §6 FSM | F4 |
| §7 Contratos | F5 (tests) |
| §9 Validaciones | F1-07, F3-10 |
| §13 Seguridad | F3-10/11, F5-05 |

### 14.4 DESIGN → PLAN

| DESIGN Sección | PLAN Fase |
|----------------|-----------|
| §3 CLI Functions | F2 |
| §4 Python Module | F1 |
| §5 FSM Handler | F4 |
| §6 Manifests | F1 |
| §7 Persistence | F2-09 |
| §10 Testing | F5 |

### 14.5 TEST → PLAN

| TEST Sección | PLAN Fase |
|-------------|-----------|
| §3 Unit Python | F5-01/02 |
| §4 Unit Bash | F5-03 |
| §5 Integration | F5-04 |
| §6 E2E | F5-04 |
| §7 Security | F5-05 |
| §8 Concurrency | F5-06 |
| §9 Regression | F5-07 |
| §11 CI/CD | F5-08/09 |

---

*Documento generado como parte de la suite de planning v0.6.1 para ouroborOS.*
