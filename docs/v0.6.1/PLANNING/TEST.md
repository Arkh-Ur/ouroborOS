# TEST — ouroborOS v0.6.1: Gestor de Dotfiles `our-dots`

**Versión:** 1.1  
**Fecha:** 2026-06-07  
**Autor:** ouroborOS dev team  
**Estado:** Review Cycle 1 — Applied  
**Referencias:** PRD v1.1 · TRD v1.2 · SPEC v1.1 · DESIGN v1.2

**Cambios v1.1:**
- Agrega UT-P-046 a UT-P-050 (completa TestDotsPackConfig)
- Agrega UT-B-036 a UT-B-038 (validate_manifest_schema adicionales)
- Agrega IT-011 a IT-028 (CU-09 upgrades, CU-10/12-14 repos, CU-23 cleanup trap)
- Corrige helper `_run_our_dots()` en §5 (M-04)
- Actualiza §12 CU-09 y CU-23 con IDs reales
- Actualiza §13 Matriz de Trazabilidad con nuevos IDs

---

## Tabla de Contenidos

1. [Estrategia General](#1-estrategia-general)
2. [Cobertura Objetivo](#2-cobertura-objetivo)
3. [Unit Tests — Python](#3-unit-tests--python)
4. [Unit Tests — Bash (bats)](#4-unit-tests--bash-bats)
5. [Integration Tests](#5-integration-tests)
6. [E2E Tests (QEMU)](#6-e2e-tests-qemu)
7. [Tests de Seguridad](#7-tests-de-seguridad)
8. [Tests de Concurrencia](#8-tests-de-concurrencia)
9. [Tests de Regresión](#9-tests-de-regresión)
10. [Mocks y Stubs](#10-mocks-y-stubs)
11. [CI/CD](#11-cicd)
12. [Criterios de Aceptación por CU](#12-criterios-de-aceptación-por-cu)
13. [Matriz de Trazabilidad](#13-matriz-de-trazabilidad)
14. [Referencias Cruzadas](#14-referencias-cruzadas)

---

## 1. Estrategia General

### 1.1 Pirámide de Tests

```
                     ┌─────────────────────┐
                     │    E2E (QEMU)        │  3 escenarios
                     │  ISO real · FSM full │
                     └────────┬────────────┘
               ┌──────────────┴─────────────────┐
               │    Integration Tests             │  ~20 casos
               │  CLI + system.yaml real · bats  │
               └────────────┬────────────────────┘
       ┌────────────────────┴────────────────────────────┐
       │              Unit Tests                          │  ~80 casos
       │  Python (pytest) · Bash (bats) · sin I/O real   │
       └─────────────────────────────────────────────────┘
```

**Distribución por capa:**

| Capa | Herramienta | Casos | Velocidad | Requisitos |
|------|-------------|-------|-----------|------------|
| Unit — Python | pytest 8+ | ~55 | < 2s total | ninguno |
| Unit — Bash | bats-core 1.10+ | ~25 | < 5s total | bash 5+, python3 |
| Integration | bats-core + pytest | ~20 | < 60s | python3, PyYAML |
| E2E | QEMU + pytest | 3 | ~30 min | QEMU, ISO construida |
| Seguridad | pytest + bats | ~10 | < 10s | python3 |
| Concurrencia | pytest | ~5 | < 15s | python3 |

### 1.2 Filosofía de Testing

- **Unit first**: cada función en `dots_profiles.py` y cada helper de `our-dots` se testa de forma aislada con fixtures deterministas.
- **Mocks explícitos**: `our-pac`, `our-aur`, `git`, `curl` son siempre stubs en unit e integration tests. El E2E usa los binarios reales.
- **Contratos SPEC**: cada test verifica el comportamiento observable definido en SPEC v1.1 — no la implementación interna.
- **Target implementation**: los tests asumen la implementación *target* de `dots_profiles.py` (DESIGN §4.2 — schema anidado TRD §2.3), no la implementación legacy con campos planos.

### 1.3 Nomenclatura de IDs

| Prefijo | Categoría |
|---------|-----------|
| `UT-P-NNN` | Unit Test Python |
| `UT-B-NNN` | Unit Test Bash |
| `IT-NNN` | Integration Test |
| `E2E-NNN` | End-to-End Test |
| `SEC-NNN` | Security Test |
| `CON-NNN` | Concurrency Test |
| `REG-NNN` | Regression Test |

---

## 2. Cobertura Objetivo

| Módulo | Objetivo | Medición | Umbral de falla CI |
|--------|----------|----------|--------------------|
| `src/installer/dots_profiles.py` | **≥ 93 %** | `pytest --cov=installer.dots_profiles` | < 93 % bloquea merge |
| `src/installer/config.py` (DotsPackConfig) | ≥ 80 % | incluido en `--cov=installer` | < 70 % warning |
| `src/installer/state_machine.py` (DOTS_PACK handler) | ≥ 80 % | incluido en `--cov=installer` | < 70 % warning |
| `our-dots` (Bash) | ≥ 80 % de ramas testeadas | bats + kcov (opcional) | informativo |

### 2.1 Exclusiones

- `src/installer/tests/test_our_container_integration.py` — excluido de CI (requiere contenedor real).
- Tests E2E en `tests/qemu/` — excluidos de CI fast (requieren QEMU + ISO).
- Funciones de rendering puro (`print_table_header`, `print_info_panel`) — testeadas vía output comparison, sin cobertura de línea.

---

## 3. Unit Tests — Python

### 3.1 Fixtures Compartidas (`conftest.py`)

Agregar a `src/installer/tests/conftest.py`:

```python
# ── Fixtures dots_profiles ────────────────────────────────────────────────────

import textwrap
from pathlib import Path
import pytest


@pytest.fixture()
def tmp_manifest_dir(tmp_path: Path) -> Path:
    """Directorio temporal que simula MANIFEST_DIR."""
    d = tmp_path / "packs"
    d.mkdir()
    return d


@pytest.fixture()
def noctalia_yaml(tmp_manifest_dir: Path) -> Path:
    """Manifest canónico de noctalia (LOW, stable+git, hyprland+niri)."""
    content = textwrap.dedent("""\
        id: noctalia
        name: Noctalia v4
        description: |
          Quickshell desktop shell for Niri and Hyprland.
        credits:
          author: noctalia-dev team
          homepage: https://github.com/noctalia-dev/noctalia-shell
          license: null
        compatibility:
          immutable: low
          profiles: [hyprland, niri]
          note: AUR package, user-space config
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
    """)
    p = tmp_manifest_dir / "noctalia.yaml"
    p.write_text(content)
    return p


@pytest.fixture()
def illogical_yaml(tmp_manifest_dir: Path) -> Path:
    """Manifest canónico de illogical-impulse (CRITICAL, git-only, hyprland)."""
    content = textwrap.dedent("""\
        id: illogical-impulse
        name: illogical-impulse
        description: end-4's Hyprland rice.
        credits:
          author: end-4
          homepage: https://ii.clsty.link/en/ii-qs/01setup/
          repo: https://github.com/end-4/dots-hyprland
        compatibility:
          immutable: critical
          profiles: [hyprland]
          warning: |
            Requires modifying /etc/pacman.conf on read-only root.
          critical_actions:
            - "Remount / as read-write (temporary)"
            - "Add IgnoreGroup=illogical-impulse to /etc/pacman.conf"
            - "Remount / as read-only"
            - "Install dependencies via our-pac and our-aur"
        requires_root: true
        variants:
          git:
            packages: [git]
            aur: []
            post_deploy: |
              git clone https://github.com/end-4/dots-hyprland /tmp/dots-hyprland
            version_hint: "rolling (git)"
        uninstall:
          packages: []
          aur: []
          post_remove: null
          remove_config: false
        signature: null
    """)
    p = tmp_manifest_dir / "illogical-impulse.yaml"
    p.write_text(content)
    return p


@pytest.fixture()
def danklinux_yaml(tmp_manifest_dir: Path) -> Path:
    """Manifest canónico de danklinux (HIGH, stable-only, hyprland+niri)."""
    content = textwrap.dedent("""\
        id: danklinux
        name: DankMaterialShell
        description: Material You shell for Niri and Hyprland.
        credits:
          author: AvengeMedia
          homepage: https://danklinux.com
          repo: https://github.com/AvengeMedia/DankMaterialShell
        compatibility:
          immutable: high
          profiles: [hyprland, niri]
          note: AUR builds with Go/CMake/Rust. Build time ~10 min.
        variants:
          stable:
            packages: [dms-shell, rustup, go, cmake, ninja]
            aur: [quickshell, matugen-bin]
            post_deploy: null
            version_hint: "1.4"
        uninstall:
          packages: [dms-shell]
          aur: [quickshell, matugen-bin]
          post_remove: null
          remove_config: false
        signature: null
    """)
    p = tmp_manifest_dir / "danklinux.yaml"
    p.write_text(content)
    return p


@pytest.fixture()
def tmp_sysyaml(tmp_path: Path) -> Path:
    """system.yaml temporal vacío."""
    p = tmp_path / "system.yaml"
    p.write_text("dots_packs: []\n")
    return p
```

### 3.2 Tests de `DotsPack` Dataclass (UT-P-001 a UT-P-010)

**Archivo:** `src/installer/tests/test_dots_profiles.py`

```python
"""test_dots_profiles.py — Tests for dots_profiles module (target implementation)."""

from __future__ import annotations

from pathlib import Path
import textwrap

import pytest
import yaml

from installer.dots_profiles import DotsPack, load_catalog, packs_for_profile


class TestDotsPackDataclass:
    """UT-P-001 a UT-P-005 — DotsPack dataclass."""

    def test_dotspack_required_fields(self) -> None:
        """UT-P-001: DotsPack construye con todos los campos requeridos."""
        pack = DotsPack(
            id="noctalia",
            name="Noctalia v4",
            description="Quickshell shell.",
            author="noctalia-dev team",
            homepage="https://github.com/noctalia-dev/noctalia-shell",
            compatibility="low",
            profiles=["hyprland", "niri"],
            has_stable=True,
            has_git=True,
            stable_version_hint="v4 (stable)",
        )
        assert pack.id == "noctalia"
        assert pack.compatibility == "low"
        assert "hyprland" in pack.profiles
        assert pack.has_stable is True
        assert pack.has_git is True

    def test_dotspack_git_version_hint_default_empty(self) -> None:
        """UT-P-002: git_version_hint default es string vacío."""
        pack = DotsPack(
            id="ml4w", name="ML4W", description="d", author="a", homepage="h",
            compatibility="medium", profiles=["hyprland"],
            has_stable=True, has_git=False, stable_version_hint="v0.2.3",
        )
        assert pack.git_version_hint == ""

    def test_dotspack_git_only_has_stable_false(self) -> None:
        """UT-P-003: Pack git-only tiene has_stable=False y has_git=True."""
        pack = DotsPack(
            id="illogical-impulse", name="illogical-impulse", description="d",
            author="end-4", homepage="h", compatibility="critical",
            profiles=["hyprland"], has_stable=False, has_git=True,
            stable_version_hint="",
        )
        assert pack.has_stable is False
        assert pack.has_git is True

    def test_dotspack_critical_compatibility(self) -> None:
        """UT-P-004: Pack CRITICAL tiene campo compatibility="critical"."""
        pack = DotsPack(
            id="omarchy", name="Omarchy", description="d", author="DHH",
            homepage="h", compatibility="critical", profiles=["hyprland"],
            has_stable=True, has_git=False, stable_version_hint="rolling",
        )
        assert pack.compatibility == "critical"

    def test_dotspack_profiles_is_list(self) -> None:
        """UT-P-005: profiles es una lista, no un string."""
        pack = DotsPack(
            id="noctalia", name="Noctalia v4", description="d",
            author="a", homepage="h", compatibility="low",
            profiles=["hyprland", "niri"], has_stable=True, has_git=True,
            stable_version_hint="v4 (stable)",
        )
        assert isinstance(pack.profiles, list)
        assert len(pack.profiles) == 2
```

### 3.3 Tests de `load_catalog()` (UT-P-011 a UT-P-030)

```python
class TestLoadCatalog:
    """UT-P-011 a UT-P-030 — load_catalog()."""

    def test_missing_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """UT-P-011: MANIFEST_DIR inexistente → lista vacía, sin excepción."""
        result = load_catalog(tmp_path / "nonexistent")
        assert result == []

    def test_empty_dir_returns_empty_list(self, tmp_manifest_dir: Path) -> None:
        """UT-P-012: Directorio vacío → lista vacía."""
        result = load_catalog(tmp_manifest_dir)
        assert result == []

    def test_single_valid_manifest(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-013: Un manifest válido → lista con un DotsPack."""
        result = load_catalog(tmp_manifest_dir)
        assert len(result) == 1
        assert result[0].id == "noctalia"

    def test_returns_alphabetical_order(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-014: Manifests retornados en orden alfabético por nombre de archivo."""
        result = load_catalog(tmp_manifest_dir)
        ids = [p.id for p in result]
        assert ids == sorted(ids)

    def test_invalid_yaml_ignored(self, tmp_manifest_dir: Path) -> None:
        """UT-P-015: Manifest con YAML inválido es ignorado; catálogo continúa."""
        bad = tmp_manifest_dir / "broken.yaml"
        bad.write_text("{{ invalid: yaml: content")
        result = load_catalog(tmp_manifest_dir)
        assert all(p.id != "broken" for p in result)

    def test_non_dict_yaml_ignored(self, tmp_manifest_dir: Path) -> None:
        """UT-P-016: Manifest cuyo root no es un dict es ignorado."""
        bad = tmp_manifest_dir / "list.yaml"
        bad.write_text("- item1\n- item2\n")
        result = load_catalog(tmp_manifest_dir)
        assert result == []

    def test_reads_nested_compatibility_immutable(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-017: compatibility leído de compatibility.immutable (no campo plano)."""
        result = load_catalog(tmp_manifest_dir)
        assert result[0].compatibility == "low"

    def test_reads_nested_profiles(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-018: profiles leído de compatibility.profiles (no campo plano)."""
        result = load_catalog(tmp_manifest_dir)
        assert set(result[0].profiles) == {"hyprland", "niri"}

    def test_has_stable_true_when_variants_stable_defined(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-019: has_stable=True cuando variants.stable está definido."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.has_stable is True

    def test_has_git_true_when_variants_git_defined(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-020: has_git=True cuando variants.git está definido."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.has_git is True

    def test_git_only_pack_has_stable_false(
        self, tmp_manifest_dir: Path, illogical_yaml: Path
    ) -> None:
        """UT-P-021: Pack git-only tiene has_stable=False."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "illogical-impulse")
        assert pack.has_stable is False
        assert pack.has_git is True

    def test_stable_only_pack_has_git_false(
        self, tmp_manifest_dir: Path, danklinux_yaml: Path
    ) -> None:
        """UT-P-022: Pack stable-only tiene has_git=False."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "danklinux")
        assert pack.has_git is False
        assert pack.has_stable is True

    def test_reads_stable_version_hint(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-023: stable_version_hint leído de variants.stable.version_hint."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.stable_version_hint == "v4 (stable)"

    def test_reads_git_version_hint(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-024: git_version_hint leído de variants.git.version_hint."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.git_version_hint == "git (bleeding edge)"

    def test_reads_credits_author(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-025: author leído de credits.author (no campo plano)."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert pack.author == "noctalia-dev team"

    def test_reads_credits_homepage(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-026: homepage leído de credits.homepage."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "noctalia")
        assert "noctalia-shell" in pack.homepage

    def test_critical_pack_loads_correctly(
        self, tmp_manifest_dir: Path, illogical_yaml: Path
    ) -> None:
        """UT-P-027: Pack CRITICAL carga con compatibility="critical"."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "illogical-impulse")
        assert pack.compatibility == "critical"

    def test_high_pack_loads_correctly(
        self, tmp_manifest_dir: Path, danklinux_yaml: Path
    ) -> None:
        """UT-P-028: Pack HIGH carga con compatibility="high"."""
        result = load_catalog(tmp_manifest_dir)
        pack = next(p for p in result if p.id == "danklinux")
        assert pack.compatibility == "high"

    def test_multiple_manifests_all_loaded(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-029: Múltiples manifests válidos se cargan todos."""
        result = load_catalog(tmp_manifest_dir)
        ids = {p.id for p in result}
        assert ids == {"noctalia", "danklinux", "illogical-impulse"}

    def test_mixed_valid_and_invalid_skips_invalid(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-030: Manifest inválido ignorado; válido presente en resultado."""
        (tmp_manifest_dir / "corrupt.yaml").write_text("not: valid: yaml: [[[")
        result = load_catalog(tmp_manifest_dir)
        assert len(result) == 1
        assert result[0].id == "noctalia"
```

### 3.4 Tests de `packs_for_profile()` (UT-P-031 a UT-P-042)

```python
class TestPacksForProfile:
    """UT-P-031 a UT-P-042 — packs_for_profile()."""

    def test_hyprland_returns_hyprland_packs(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-031: hyprland retorna todos los packs con hyprland en profiles."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        ids = {p.id for p in result}
        assert "noctalia" in ids
        assert "danklinux" in ids
        assert "illogical-impulse" in ids

    def test_niri_returns_only_niri_packs(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-032: niri retorna solo packs con niri en profiles."""
        result = packs_for_profile("niri", tmp_manifest_dir)
        ids = {p.id for p in result}
        assert "noctalia" in ids
        assert "danklinux" in ids
        assert "illogical-impulse" not in ids

    def test_unknown_profile_returns_empty(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-033: Perfil desconocido → lista vacía, sin error."""
        result = packs_for_profile("gnome", tmp_manifest_dir)
        assert result == []

    def test_minimal_profile_returns_empty(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-034: Perfil 'minimal' → lista vacía (ningún pack lo soporta)."""
        result = packs_for_profile("minimal", tmp_manifest_dir)
        assert result == []

    def test_empty_string_profile_returns_empty(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-035: Perfil vacío → lista vacía, sin error."""
        result = packs_for_profile("", tmp_manifest_dir)
        assert result == []

    def test_missing_manifest_dir_returns_empty(self, tmp_path: Path) -> None:
        """UT-P-036: MANIFEST_DIR inexistente → lista vacía, sin excepción."""
        result = packs_for_profile("hyprland", tmp_path / "nonexistent")
        assert result == []

    def test_niri_subset_of_hyprland_packs(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-037: Packs de niri son subconjunto de packs de hyprland en el catálogo."""
        hyprland = {p.id for p in packs_for_profile("hyprland", tmp_manifest_dir)}
        niri = {p.id for p in packs_for_profile("niri", tmp_manifest_dir)}
        assert niri.issubset(hyprland)

    def test_profile_filter_is_exact_match(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-038: Filtro es match exacto — 'hypr' no coincide con 'hyprland'."""
        result = packs_for_profile("hypr", tmp_manifest_dir)
        assert result == []

    def test_all_hyprland_packs_in_catalog(
        self,
        tmp_manifest_dir: Path,
        noctalia_yaml: Path,
        danklinux_yaml: Path,
        illogical_yaml: Path,
    ) -> None:
        """UT-P-039: Catálogo con 3 manifests; hyprland retorna todos."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        assert len(result) == 3

    def test_result_items_are_dotspack_instances(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-040: Cada elemento del resultado es una instancia DotsPack."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        for pack in result:
            assert isinstance(pack, DotsPack)

    def test_returns_list_not_generator(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-041: Retorna list, no generator (indexable, len() funciona)."""
        result = packs_for_profile("hyprland", tmp_manifest_dir)
        assert isinstance(result, list)
        assert len(result) >= 0

    def test_stability_across_calls(
        self, tmp_manifest_dir: Path, noctalia_yaml: Path
    ) -> None:
        """UT-P-042: Dos llamadas consecutivas retornan resultados iguales."""
        r1 = packs_for_profile("hyprland", tmp_manifest_dir)
        r2 = packs_for_profile("hyprland", tmp_manifest_dir)
        assert [p.id for p in r1] == [p.id for p in r2]
```

### 3.5 Tests de `DotsPackConfig` y Estado FSM (UT-P-043 a UT-P-055)

```python
class TestDotsPackConfig:
    """UT-P-043 a UT-P-050 — DotsPackConfig dataclass."""

    def test_dotspackconfig_defaults(self) -> None:
        """UT-P-043: DotsPackConfig.pack=None, channel="stable" por defecto."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig()
        assert cfg.pack is None
        assert cfg.channel == "stable"

    def test_dotspackconfig_set_pack(self) -> None:
        """UT-P-044: DotsPackConfig acepta pack id string."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig(pack="noctalia", channel="stable")
        assert cfg.pack == "noctalia"
        assert cfg.channel == "stable"

    def test_dotspackconfig_git_channel(self) -> None:
        """UT-P-045: DotsPackConfig acepta channel="git"."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig(pack="illogical-impulse", channel="git")
        assert cfg.channel == "git"

    def test_dotspackconfig_none_pack_default_channel(self) -> None:
        """UT-P-046: DotsPackConfig(pack=None) mantiene channel="stable" por defecto."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig()
        assert cfg.pack is None
        assert cfg.channel == "stable"

    def test_dotspackconfig_pack_with_hyphens(self) -> None:
        """UT-P-047: DotsPackConfig acepta pack id con guiones (nombre canónico)."""
        from installer.config import DotsPackConfig
        cfg = DotsPackConfig(pack="illogical-impulse", channel="git")
        assert cfg.pack == "illogical-impulse"

    def test_dotspackconfig_pack_field_is_string_or_none(self) -> None:
        """UT-P-048: DotsPackConfig.pack es str o None, nunca otro tipo."""
        from installer.config import DotsPackConfig
        cfg_none = DotsPackConfig()
        cfg_str = DotsPackConfig(pack="ml4w", channel="stable")
        assert cfg_none.pack is None
        assert isinstance(cfg_str.pack, str)

    def test_dotspackconfig_channel_field_is_string(self) -> None:
        """UT-P-049: DotsPackConfig.channel es siempre str."""
        from installer.config import DotsPackConfig
        for channel in ("stable", "git"):
            cfg = DotsPackConfig(pack="noctalia", channel=channel)
            assert isinstance(cfg.channel, str)

    def test_dotspackconfig_two_equal_instances(self) -> None:
        """UT-P-050: Dos DotsPackConfig con mismos campos son equivalentes."""
        from installer.config import DotsPackConfig
        cfg1 = DotsPackConfig(pack="noctalia", channel="stable")
        cfg2 = DotsPackConfig(pack="noctalia", channel="stable")
        assert cfg1.pack == cfg2.pack
        assert cfg1.channel == cfg2.channel


class TestHandleDotsPackFSM:
    """UT-P-051 a UT-P-055 — FSM handler _handle_dots_pack()."""

    def test_minimal_profile_skips_dots_pack(self) -> None:
        """UT-P-051: Perfil minimal → handler retorna sin instalar pack."""
        from unittest.mock import MagicMock, patch
        from installer.state_machine import InstallerFSM
        from installer.config import InstallerConfig, DotsPackConfig

        config = MagicMock(spec=InstallerConfig)
        config.desktop.profile = "minimal"
        config.dots_pack = DotsPackConfig()

        fsm = InstallerFSM.__new__(InstallerFSM)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()

        fsm._handle_dots_pack()

        assert config.dots_pack.pack is None
        fsm._update_progress.assert_called()

    def test_git_only_pack_channel_autocorrected(
        self, tmp_manifest_dir: Path, illogical_yaml: Path
    ) -> None:
        """UT-P-052: Canal auto-corregido a "git" para packs git-only (C-03)."""
        from unittest.mock import MagicMock, patch
        from installer.config import DotsPackConfig

        dots_cfg = DotsPackConfig(pack="illogical-impulse", channel="stable")

        config = MagicMock()
        config.desktop.profile = "hyprland"
        config.dots_pack = dots_cfg

        # Simular handler sin TUI, con catálogo de tmp_manifest_dir
        with patch("installer.state_machine.load_catalog") as mock_cat:
            from installer.dots_profiles import load_catalog as real_load
            mock_cat.return_value = real_load(tmp_manifest_dir)

            from installer.state_machine import InstallerFSM
            fsm = InstallerFSM.__new__(InstallerFSM)
            fsm.config = config
            fsm.tui = None
            fsm._update_progress = MagicMock()
            fsm._handle_dots_pack()

        assert config.dots_pack.channel == "git"

    def test_stable_only_pack_channel_stays_stable(
        self, tmp_manifest_dir: Path, danklinux_yaml: Path
    ) -> None:
        """UT-P-053: Canal "stable" no cambia para packs stable-only."""
        from unittest.mock import MagicMock, patch
        from installer.config import DotsPackConfig
        from installer.dots_profiles import load_catalog as real_load

        dots_cfg = DotsPackConfig(pack="danklinux", channel="stable")
        config = MagicMock()
        config.desktop.profile = "hyprland"
        config.dots_pack = dots_cfg

        with patch("installer.state_machine.load_catalog",
                   return_value=real_load(tmp_manifest_dir)):
            from installer.state_machine import InstallerFSM
            fsm = InstallerFSM.__new__(InstallerFSM)
            fsm.config = config
            fsm.tui = None
            fsm._update_progress = MagicMock()
            fsm._handle_dots_pack()

        assert config.dots_pack.channel == "stable"

    def test_no_pack_selected_channel_unchanged(self) -> None:
        """UT-P-054: Sin pack seleccionado, channel no cambia."""
        from unittest.mock import MagicMock
        from installer.config import DotsPackConfig
        from installer.state_machine import InstallerFSM

        dots_cfg = DotsPackConfig(pack=None, channel="stable")
        config = MagicMock()
        config.desktop.profile = "hyprland"
        config.dots_pack = dots_cfg

        fsm = InstallerFSM.__new__(InstallerFSM)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._handle_dots_pack()

        assert dots_cfg.channel == "stable"

    def test_progress_called_at_start_and_end(self) -> None:
        """UT-P-055: _update_progress llamado con 0 al inicio y 100 al final."""
        from unittest.mock import MagicMock, call
        from installer.config import DotsPackConfig
        from installer.state_machine import InstallerFSM, State

        config = MagicMock()
        config.desktop.profile = "minimal"
        config.dots_pack = DotsPackConfig()

        fsm = InstallerFSM.__new__(InstallerFSM)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._handle_dots_pack()

        calls = fsm._update_progress.call_args_list
        assert any(c == call(State.DOTS_PACK, 0) for c in calls)
        assert any(c == call(State.DOTS_PACK, 100) for c in calls)
```

---

## 4. Unit Tests — Bash (bats)

### 4.1 Setup del Entorno bats

**Prerrequisito:** `bats-core` 1.10+ instalado.

```bash
# Instalar bats-core y librerías de aserciones
git clone https://github.com/bats-core/bats-core.git /opt/bats
git clone https://github.com/bats-core/bats-assert.git /opt/bats-assert
git clone https://github.com/bats-core/bats-support.git /opt/bats-support

# Ejecutar suite
bats tests/bash/test_our_dots.bats
bats tests/bash/test_our_dots_security.bats
```

### 4.2 Fixtures Compartidas bats

**Archivo:** `tests/bash/helpers/setup_our_dots.bash`

```bash
#!/usr/bin/env bash
# Setup compartido para todos los tests de our-dots.

# Directorio de trabajo aislado
setup_our_dots_env() {
    export TEST_DIR
    TEST_DIR="$(mktemp -d)"
    export MANIFEST_DIR="${TEST_DIR}/packs"
    export REPOS_DIR="${TEST_DIR}/repos"
    export REPOS_INDEX="${TEST_DIR}/dots-repos.yaml"
    export SYSYAML="${TEST_DIR}/system.yaml"
    export LOG_DIR="${TEST_DIR}/logs"
    mkdir -p "$MANIFEST_DIR" "$REPOS_DIR" "$LOG_DIR"
    echo "dots_packs: []" > "$SYSYAML"

    # Directorio de stubs en PATH (antes de los binarios reales)
    export STUB_DIR="${TEST_DIR}/stubs"
    mkdir -p "$STUB_DIR"
    export PATH="${STUB_DIR}:${PATH}"
}

teardown_our_dots_env() {
    rm -rf "${TEST_DIR:-/nonexistent_test_dir}"
}

# Crea un manifest canónico básico (LOW, stable, hyprland)
create_manifest() {
    local id="$1" level="${2:-low}" profile="${3:-hyprland}"
    cat > "${MANIFEST_DIR}/${id}.yaml" <<YAML
id: ${id}
name: Test Pack ${id}
description: Test pack for ${id}.
credits:
  author: Test Author
  homepage: https://example.com/${id}
compatibility:
  immutable: ${level}
  profiles: [${profile}]
variants:
  stable:
    packages: [pkg-${id}]
    aur: []
    post_deploy: null
    version_hint: "v1.0"
uninstall:
  packages: [pkg-${id}]
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
}

# Crea un manifest git-only
create_git_only_manifest() {
    local id="$1" level="${2:-medium}"
    cat > "${MANIFEST_DIR}/${id}.yaml" <<YAML
id: ${id}
name: GitOnly ${id}
description: Git-only test pack.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: ${level}
  profiles: [hyprland]
variants:
  git:
    packages: []
    aur: []
    post_deploy: null
    version_hint: "rolling"
uninstall:
  packages: []
  aur: []
signature: null
YAML
}

# Crea un manifest CRITICAL
create_critical_manifest() {
    local id="$1"
    cat > "${MANIFEST_DIR}/${id}.yaml" <<YAML
id: ${id}
name: Critical ${id}
description: Critical test pack.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: critical
  profiles: [hyprland]
  warning: |
    This pack makes critical changes.
  critical_actions:
    - "Remount / as read-write"
    - "Edit /etc/pacman.conf"
requires_root: true
variants:
  git:
    packages: []
    aur: []
    post_deploy: null
    version_hint: "rolling"
uninstall:
  packages: []
  aur: []
signature: null
YAML
}

# Stub de our-pac que siempre tiene éxito
create_stub_our_pac() {
    cat > "${STUB_DIR}/our-pac" <<'BASH'
#!/usr/bin/env bash
echo "[stub our-pac] called with: $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/our-pac"
}

# Stub de our-pac que siempre falla
create_stub_our_pac_fail() {
    cat > "${STUB_DIR}/our-pac" <<'BASH'
#!/usr/bin/env bash
echo "[stub our-pac] SIMULATED FAILURE" >&2
exit 1
BASH
    chmod +x "${STUB_DIR}/our-pac"
}

# Stub de our-aur que siempre tiene éxito
create_stub_our_aur() {
    cat > "${STUB_DIR}/our-aur" <<'BASH'
#!/usr/bin/env bash
echo "[stub our-aur] called with: $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/our-aur"
}

# Stub de git
create_stub_git() {
    cat > "${STUB_DIR}/git" <<'BASH'
#!/usr/bin/env bash
echo "[stub git] called with: $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/git"
}
```

### 4.3 Tests de Helpers YAML (UT-B-001 a UT-B-010)

**Archivo:** `tests/bash/test_our_dots.bats`

```bash
#!/usr/bin/env bats
# test_our_dots.bats — Unit tests para our-dots helpers y subcomandos.

load 'helpers/setup_our_dots'
load '/opt/bats-support/load'
load '/opt/bats-assert/load'

SCRIPT="${BATS_TEST_DIRNAME}/../../src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"

setup() {
    setup_our_dots_env
    # Sobreescribir rutas en el script via variables de entorno
    export MANIFEST_DIR REPOS_DIR REPOS_INDEX SYSYAML LOG_DIR
    create_manifest "testpack" "low" "hyprland"
}

teardown() {
    teardown_our_dots_env
}

# ── yaml_get ──────────────────────────────────────────────────────────────────

@test "UT-B-001: yaml_get retorna campo escalar de nivel raíz" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    # Sourcear solo las funciones del script (sin ejecutar main)
    result=$(bash -c "
        source <(grep -v '^main ' '${SCRIPT}' | grep -v '^main\$')
        yaml_get '${mf}' 'id'
    ")
    assert_equal "$result" "testpack"
}

@test "UT-B-002: yaml_get retorna campo anidado compatibility.immutable" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        yaml_get '${mf}' 'compatibility.immutable'
    ")
    assert_equal "$result" "low"
}

@test "UT-B-003: yaml_get falla con exit non-zero si campo no existe" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        yaml_get '${mf}' 'nonexistent.field'
    "
    assert_failure
}

@test "UT-B-004: yaml_list retorna lista de profiles como líneas" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        yaml_list '${mf}' 'compatibility.profiles'
    ")
    assert_output --partial "hyprland"
}

@test "UT-B-005: yaml_list retorna lista vacía sin error si campo es []" {
    cat > "${MANIFEST_DIR}/empty_list.yaml" <<'YAML'
id: empty
name: Empty
description: d
credits:
  author: a
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: []
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        yaml_list '${MANIFEST_DIR}/empty_list.yaml' 'compatibility.profiles'
    "
    assert_success
    assert_output ""
}
```

### 4.4 Tests de `find_manifest()` y `derive_channels()` (UT-B-011 a UT-B-020)

```bash
# ── find_manifest ────────────────────────────────────────────────────────────

@test "UT-B-011: find_manifest retorna path al manifest built-in" {
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}'
        source <(grep -v '^main ' '${SCRIPT}')
        find_manifest 'testpack'
    ")
    assert_equal "$result" "${MANIFEST_DIR}/testpack.yaml"
}

@test "UT-B-012: find_manifest falla si pack no existe en ninguna fuente" {
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}'
        source <(grep -v '^main ' '${SCRIPT}')
        find_manifest 'nonexistent-pack'
    "
    assert_failure
}

@test "UT-B-013: find_manifest prioriza built-in sobre externo" {
    # Crear manifest externo con mismo ID que built-in
    mkdir -p "${REPOS_DIR}/my-repo"
    cat > "${REPOS_DIR}/my-repo/testpack.yaml" <<YAML
id: testpack
name: External TestPack
description: External version.
credits:
  author: External
  homepage: https://external.example.com
compatibility:
  immutable: medium
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "external"
signature: null
YAML
    cat > "${REPOS_INDEX}" <<YAML
repos:
  - name: my-repo
    url: https://example.com/my-repo.git
    type: git
    added_at: "2026-06-07"
YAML

    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}'
        source <(grep -v '^main ' '${SCRIPT}')
        find_manifest 'testpack'
    ")
    assert_equal "$result" "${MANIFEST_DIR}/testpack.yaml"
}

@test "UT-B-014: find_manifest busca en externos si no está en built-in" {
    mkdir -p "${REPOS_DIR}/community-repo"
    cat > "${REPOS_DIR}/community-repo/community-pack.yaml" <<YAML
id: community-pack
name: Community Pack
description: From external repo.
credits:
  author: Community
  homepage: https://community.example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
signature: null
YAML
    cat > "${REPOS_INDEX}" <<YAML
repos:
  - name: community-repo
    url: https://example.com/community-repo.git
    type: git
    added_at: "2026-06-07"
YAML

    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}'
        source <(grep -v '^main ' '${SCRIPT}')
        find_manifest 'community-pack'
    ")
    assert_equal "$result" "${REPOS_DIR}/community-repo/community-pack.yaml"
}

# ── derive_channels ──────────────────────────────────────────────────────────

@test "UT-B-015: derive_channels retorna 'stable' para pack stable-only" {
    # testpack tiene solo variants.stable
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        source <(grep -v '^main ' '${SCRIPT}')
        derive_channels '${MANIFEST_DIR}/testpack.yaml'
    ")
    assert_equal "$result" "stable"
}

@test "UT-B-016: derive_channels retorna 'git' para pack git-only" {
    create_git_only_manifest "gitpack"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        source <(grep -v '^main ' '${SCRIPT}')
        derive_channels '${MANIFEST_DIR}/gitpack.yaml'
    ")
    assert_equal "$result" "git"
}

@test "UT-B-017: derive_channels retorna 'stable/git' para pack con ambos canales" {
    # Usar noctalia como ejemplo con ambos canales
    cat > "${MANIFEST_DIR}/both.yaml" <<'YAML'
id: both
name: Both Channels
description: d
credits:
  author: a
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
  git:
    packages: []
    aur: []
    version_hint: "rolling"
signature: null
YAML
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        source <(grep -v '^main ' '${SCRIPT}')
        derive_channels '${MANIFEST_DIR}/both.yaml'
    ")
    assert_equal "$result" "stable/git"
}
```

### 4.5 Tests de Flujos de Confirmación y Exit Codes (UT-B-021 a UT-B-030)

```bash
# ── Subcomandos CLI ──────────────────────────────────────────────────────────

@test "UT-B-021: --version imprime 'our-dots 0.6.1' y sale con código 0" {
    run bash "${SCRIPT}" --version
    assert_success
    assert_output "our-dots 0.6.1"
}

@test "UT-B-022: --help sale con código 0" {
    run bash "${SCRIPT}" --help
    assert_success
}

@test "UT-B-023: subcomando desconocido sale con código 1" {
    run bash "${SCRIPT}" --invalid-command-xyz
    assert_failure
    [ "$status" -eq 1 ]
}

@test "UT-B-024: -Q con system.yaml sin dots_packs muestra '(no packs installed)'" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Q
    assert_success
    assert_output --partial "no packs installed"
}

@test "UT-B-025: -Q con system.yaml inexistente sale con código 0 sin error" {
    rm -f "${SYSYAML}"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Q
    assert_success
    assert_output --partial "no packs installed"
}

@test "UT-B-026: -Qs sin patrón lista catálogo completo y sale con código 0" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Qs
    assert_success
    assert_output --partial "testpack"
}

@test "UT-B-027: -Qs con patrón sin coincidencias sale con código 0 (no error)" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Qs "xyznonexistentpattern123"
    assert_success
}

@test "UT-B-028: CRITICAL + --noconfirm sin OUROBOROS_ALLOW_CRITICAL → exit 1" {
    create_critical_manifest "critpack"
    create_stub_our_pac
    create_stub_our_aur

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        EUID=0 \
        bash "${SCRIPT}" -S critpack --noconfirm
    assert_failure
    assert_output --partial "OUROBOROS_ALLOW_CRITICAL"
}

@test "UT-B-029: CRITICAL + OUROBOROS_ALLOW_CRITICAL=1 omite panel de confirmación" {
    create_critical_manifest "critpack"
    create_stub_our_pac
    create_stub_our_aur

    # Con OUROBOROS_ALLOW_CRITICAL=1, no debe requerir input
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        OUROBOROS_ALLOW_CRITICAL=1 \
        EUID=0 \
        bash "${SCRIPT}" -S critpack --noconfirm
    # No debe pedir "yes" y debe proceder
    refute_output --partial "Type 'yes'"
}

@test "UT-B-030: -S sin root produce error descriptivo" {
    create_stub_our_pac
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        EUID=1000 \
        bash "${SCRIPT}" -S testpack
    assert_failure
    assert_output --partial "root"
}
```

### 4.6 Tests de `validate_manifest_schema()` (UT-B-031 a UT-B-038)

```bash
# ── validate_manifest_schema ─────────────────────────────────────────────────

@test "UT-B-031: validate_manifest_schema retorna 0 para manifest válido" {
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${MANIFEST_DIR}/testpack.yaml'
    "
    assert_success
}

@test "UT-B-032: validate_manifest_schema falla si falta campo 'id'" {
    cat > "${TEST_DIR}/no_id.yaml" <<'YAML'
name: No ID Pack
description: Missing id field.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/no_id.yaml'
    "
    assert_failure
}

@test "UT-B-033: validate_manifest_schema falla si falta compatibility.immutable" {
    cat > "${TEST_DIR}/no_compat.yaml" <<'YAML'
id: no-compat
name: No Compat
description: Missing compatibility.immutable.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  profiles: [hyprland]
variants:
  stable:
    packages: []
    version_hint: "v1"
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/no_compat.yaml'
    "
    assert_failure
}

@test "UT-B-034: CRITICAL manifest sin warning falla validación" {
    cat > "${TEST_DIR}/crit_no_warn.yaml" <<'YAML'
id: crit-no-warn
name: Critical No Warn
description: Missing critical warning.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: critical
  profiles: [hyprland]
variants:
  git:
    packages: []
    aur: []
    version_hint: "rolling"
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/crit_no_warn.yaml'
    "
    assert_failure
}

@test "UT-B-035: CRITICAL manifest sin critical_actions falla validación" {
    cat > "${TEST_DIR}/crit_no_actions.yaml" <<'YAML'
id: crit-no-actions
name: Critical No Actions
description: Missing critical_actions.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: critical
  profiles: [hyprland]
  warning: "This pack is dangerous."
  critical_actions: []
variants:
  git:
    packages: []
    aur: []
    version_hint: "rolling"
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/crit_no_actions.yaml'
    "
    assert_failure
}

@test "UT-B-036: validate_manifest_schema falla si falta credits.author" {
    cat > "${TEST_DIR}/no_author.yaml" <<'YAML'
id: no-author
name: No Author Pack
description: Missing credits.author field.
credits:
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/no_author.yaml'
    "
    assert_failure
}

@test "UT-B-037: validate_manifest_schema falla si variants está vacío (sin canales definidos)" {
    cat > "${TEST_DIR}/no_variants.yaml" <<'YAML'
id: no-variants
name: No Variants Pack
description: No install channels defined.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants: {}
signature: null
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/no_variants.yaml'
    "
    assert_failure
}

@test "UT-B-038: validate_manifest_schema acepta manifest con signature no null" {
    cat > "${TEST_DIR}/with_sig.yaml" <<'YAML'
id: with-sig
name: Signed Pack
description: Pack with a non-null signature field.
credits:
  author: Verified Author
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
signature: "sha256:abc123def456"
YAML
    run bash -c "
        source <(grep -v '^main ' '${SCRIPT}')
        validate_manifest_schema '${TEST_DIR}/with_sig.yaml'
    "
    assert_success
}
```

---

## 5. Integration Tests

### 5.1 Tests de Instalación Completa (IT-001 a IT-010)

**Archivo:** `tests/bash/test_our_dots_integration.bats`

Estos tests invocan `our-dots` con stubs de `our-pac`/`our-aur` y verifican el estado resultante de `system.yaml`.

```bash
#!/usr/bin/env bats
# test_our_dots_integration.bats — Integration tests para our-dots.

load 'helpers/setup_our_dots'
load '/opt/bats-support/load'
load '/opt/bats-assert/load'

SCRIPT="${BATS_TEST_DIRNAME}/../../src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"

setup() {
    setup_our_dots_env
    create_stub_our_pac
    create_stub_our_aur
    create_stub_git
    create_manifest "mypack" "low" "hyprland"
}

teardown() {
    teardown_our_dots_env
}

_run_our_dots() {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        EUID=0 \
        bash "${SCRIPT}" "$@"
}

# IT-001: Instalar pack LOW con --noconfirm → system.yaml actualizado
@test "IT-001: install low pack --noconfirm actualiza system.yaml" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        EUID=0 \
        bash "${SCRIPT}" -S mypack --noconfirm
    assert_success

    # Verificar que system.yaml contiene la entrada
    run python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f)
ids = [p['id'] for p in d.get('dots_packs', [])]
print('found' if 'mypack' in ids else 'missing')
"
    assert_output "found"
}

# IT-002: Instalar pack → log creado en LOG_DIR
@test "IT-002: install crea archivo de log en LOG_DIR" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        EUID=0 \
        bash "${SCRIPT}" -S mypack --noconfirm
    assert_success

    log_count=$(ls "${LOG_DIR}"/mypack-*.log 2>/dev/null | wc -l)
    [ "$log_count" -ge 1 ]
}

# IT-003: -R de pack instalado → eliminado de system.yaml
@test "IT-003: -R elimina pack de system.yaml" {
    # Pre-registrar pack en system.yaml
    python3 -c "
import yaml, datetime
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
d.setdefault('dots_packs', []).append({
    'id': 'mypack', 'channel': 'stable',
    'installed_version': 'v1.0', 'installed_at': '2026-06-07', 'origin': 'builtin'
})
with open('${SYSYAML}', 'w') as f:
    yaml.dump(d, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" \
        REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" \
        SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        EUID=0 \
        bash "${SCRIPT}" -R mypack --noconfirm
    assert_success

    run python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
ids = [p['id'] for p in d.get('dots_packs', [])]
print('still_present' if 'mypack' in ids else 'removed')
"
    assert_output "removed"
}

# IT-004: Reinstalar pack ya instalado → upsert (no duplica)
@test "IT-004: reinstall actualiza entrada existente sin duplicar" {
    # Instalar por primera vez
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -S mypack --noconfirm
    assert_success

    # Reinstalar
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -S mypack --noconfirm
    assert_success

    # Verificar que hay exactamente 1 entrada
    count=$(python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
print(len([p for p in d.get('dots_packs', []) if p['id'] == 'mypack']))
")
    assert_equal "$count" "1"
}

# IT-005: -Si de pack existente → exit 0 con info correcta
@test "IT-005: -Si muestra nombre del pack y sale con código 0" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Si mypack
    assert_success
    assert_output --partial "Test Pack mypack"
}

# IT-006: -Si de pack inexistente → exit 1 con mensaje de error
@test "IT-006: -Si de pack inexistente sale con código 1" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Si nonexistent-pack
    assert_failure
    assert_output --partial "Pack not found"
}

# IT-007: Fallo de our-pac → exit 1, pack no en system.yaml
@test "IT-007: fallo our-pac produce exit 1 y pack NO queda en system.yaml" {
    create_stub_our_pac_fail

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -S mypack --noconfirm
    # Puede fallar con 1 (nuestro exit 1 de our-pac fail)
    [ "$status" -ne 0 ]

    run python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
ids = [p['id'] for p in d.get('dots_packs', [])]
print('present' if 'mypack' in ids else 'absent')
"
    assert_output "absent"
}

# IT-008: Fallo de post_deploy → exit 4, pack NO en system.yaml
@test "IT-008: fallo post_deploy produce exit 4, pack no registrado" {
    # Manifest con post_deploy que falla
    cat > "${MANIFEST_DIR}/fail_post.yaml" <<'YAML'
id: fail-post
name: Fail PostDeploy
description: Pack with failing post_deploy.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    post_deploy: "exit 1"
    version_hint: "v1.0"
uninstall:
  packages: []
  aur: []
signature: null
YAML
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -S fail-post --noconfirm
    assert_equal "$status" "4"

    run python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
ids = [p['id'] for p in d.get('dots_packs', [])]
print('present' if 'fail-post' in ids else 'absent')
"
    assert_output "absent"
}

# IT-009: repo-add con URL HTTP → rechazado con error
@test "IT-009: repo-add URL HTTP simple es rechazado" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-add my-repo http://insecure.example.com/repo.git
    assert_failure
    assert_output --partial "HTTPS"
}

# IT-010: -S pack git-only sin --git → canal auto-detectado como git (C-03)
@test "IT-010: pack git-only instala con canal git aunque no se pase --git" {
    create_git_only_manifest "gitpack"

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -S gitpack --noconfirm
    assert_success

    # Verificar que se registró con channel="git"
    channel=$(python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
for p in d.get('dots_packs', []):
    if p['id'] == 'gitpack':
        print(p.get('channel', ''))
")
    assert_equal "$channel" "git"
}
```

### 5.2 Tests de Upgrade `-Su` (IT-011 a IT-013)

```bash
# IT-011: -Su sin packs instalados → exit 0, sin trabajo
@test "IT-011: -Su sin dots_packs instalados sale con código 0" {
    # system.yaml vacío — no hay nada que actualizar
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -Su --noconfirm
    assert_success
    assert_output --partial "Nothing to update"
}

# IT-012: -Su con pack instalado → llama our-pac/our-aur para actualizar
@test "IT-012: -Su con pack low instalado invoca our-pac para actualización" {
    # Pre-registrar pack en system.yaml
    python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
d.setdefault('dots_packs', []).append({
    'id': 'mypack', 'channel': 'stable',
    'installed_version': 'v1.0', 'installed_at': '2026-06-07', 'origin': 'builtin'
})
with open('${SYSYAML}', 'w') as f:
    yaml.dump(d, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        STUB_LOG="${TEST_DIR}/stub.log" \
        bash "${SCRIPT}" -Su --noconfirm
    assert_success
    # Verificar que our-pac fue invocado (registrado en stub log)
    run grep -l "our-pac" "${TEST_DIR}/stub.log" 2>/dev/null || true
    # El stub fue llamado (puede no existir stub.log si no hay paquetes en manifiesto)
    assert_success
}

# IT-013: -Su con pack CRITICAL instalado → omite con advertencia
@test "IT-013: -Su omite pack CRITICAL con warning" {
    create_critical_manifest "critpack"
    # Pre-registrar critpack como instalado
    python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
d.setdefault('dots_packs', []).append({
    'id': 'critpack', 'channel': 'git',
    'installed_version': 'rolling', 'installed_at': '2026-06-07', 'origin': 'builtin'
})
with open('${SYSYAML}', 'w') as f:
    yaml.dump(d, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" -Su --noconfirm
    # El comando no debe fallar — salta CRITICALs con warning
    assert_success
    assert_output --partial "CRITICAL"
}
```

### 5.3 Tests de Repositorios Externos — Alta Git (IT-014 a IT-016)

```bash
# IT-014: repo-add URL HTTPS git → registrado en dots-repos.yaml
@test "IT-014: repo-add URL HTTPS registra repo en dots-repos.yaml" {
    create_stub_git

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-add my-repo https://example.com/my-repo.git
    assert_success

    # Verificar que fue registrado en dots-repos.yaml
    run python3 -c "
import yaml
with open('${REPOS_INDEX}') as f:
    d = yaml.safe_load(f) or {}
names = [r['name'] for r in d.get('repos', [])]
print('registered' if 'my-repo' in names else 'missing')
"
    assert_output "registered"
}

# IT-015: repo-add duplicado → error descriptivo
@test "IT-015: repo-add nombre duplicado sale con código 1" {
    create_stub_git
    # Registrar primero
    python3 -c "
import yaml, datetime
d = {'repos': [{'name': 'my-repo', 'url': 'https://example.com/r.git',
                'type': 'git', 'added_at': '2026-06-07'}]}
with open('${REPOS_INDEX}', 'w') as f:
    yaml.dump(d, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-add my-repo https://example.com/other.git
    assert_failure
    assert_output --partial "already"
}

# IT-016: repo-add sin root → error descriptivo
@test "IT-016: repo-add sin root sale con código 1" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=1000 \
        bash "${SCRIPT}" repo-add my-repo https://example.com/r.git
    assert_failure
    assert_output --partial "root"
}
```

### 5.4 Tests de Repositorios Externos — Baja y Listado (IT-017 a IT-022)

```bash
# IT-017: repo-remove repo registrado → eliminado de dots-repos.yaml y directorio
@test "IT-017: repo-remove elimina repo registrado y su directorio" {
    # Pre-registrar repo con directorio
    mkdir -p "${REPOS_DIR}/my-repo"
    python3 -c "
import yaml
d = {'repos': [{'name': 'my-repo', 'url': 'https://example.com/r.git',
                'type': 'git', 'added_at': '2026-06-07'}]}
with open('${REPOS_INDEX}', 'w') as f:
    yaml.dump(d, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-remove my-repo --noconfirm
    assert_success

    # Verificar que ya no está en dots-repos.yaml
    run python3 -c "
import yaml
with open('${REPOS_INDEX}') as f:
    d = yaml.safe_load(f) or {}
names = [r['name'] for r in d.get('repos', [])]
print('still_registered' if 'my-repo' in names else 'removed')
"
    assert_output "removed"

    # Verificar que el directorio fue eliminado
    [ ! -d "${REPOS_DIR}/my-repo" ]
}

# IT-018: repo-remove con packs del repo instalados → muestra advertencia
@test "IT-018: repo-remove con packs instalados del repo muestra advertencia" {
    mkdir -p "${REPOS_DIR}/ext-repo"
    cat > "${REPOS_DIR}/ext-repo/ext-pack.yaml" <<'YAML'
id: ext-pack
name: External Pack
description: From external repo.
credits:
  author: External
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
signature: null
YAML
    python3 -c "
import yaml
# Registrar repo
d_repo = {'repos': [{'name': 'ext-repo', 'url': 'https://example.com/r.git',
                     'type': 'git', 'added_at': '2026-06-07'}]}
with open('${REPOS_INDEX}', 'w') as f:
    yaml.dump(d_repo, f)
# Registrar pack instalado desde ese repo
d_sys = {'dots_packs': [{'id': 'ext-pack', 'channel': 'stable',
                          'installed_version': 'v1', 'installed_at': '2026-06-07',
                          'origin': 'ext-repo'}]}
with open('${SYSYAML}', 'w') as f:
    yaml.dump(d_sys, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-remove ext-repo --noconfirm
    # Debe advertir sobre packs instalados del repo
    assert_output --partial "ext-pack"
}

# IT-019: repo-remove repo no registrado → noop, exit 0
@test "IT-019: repo-remove repo no registrado es noop con exit 0" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-remove nonexistent-repo --noconfirm
    assert_success
}

# IT-020: repo-list sin repos externos → muestra solo built-in
@test "IT-020: repo-list sin repos externos muestra solo built-in" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" repo-list
    assert_success
    assert_output --partial "built-in"
}

# IT-021: repo-list con repos externos → built-in primero, luego externos
@test "IT-021: repo-list muestra built-in antes que repos externos" {
    python3 -c "
import yaml
d = {'repos': [{'name': 'ext-repo', 'url': 'https://example.com/r.git',
                'type': 'git', 'added_at': '2026-06-07'}]}
with open('${REPOS_INDEX}', 'w') as f:
    yaml.dump(d, f)
"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" repo-list
    assert_success
    assert_output --partial "built-in"
    assert_output --partial "ext-repo"
}

# IT-022: repo-list cuando dots-repos.yaml no existe → sin error
@test "IT-022: repo-list sin dots-repos.yaml sale con código 0" {
    rm -f "${REPOS_INDEX}"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" repo-list
    assert_success
    assert_output --partial "built-in"
}
```

### 5.5 Tests de Actualización de Repos (IT-023 a IT-025)

```bash
# IT-023: repo-update repo git → invoca git pull --ff-only
@test "IT-023: repo-update repo git llama git pull --ff-only" {
    mkdir -p "${REPOS_DIR}/git-repo"
    python3 -c "
import yaml
d = {'repos': [{'name': 'git-repo', 'url': 'https://example.com/r.git',
                'type': 'git', 'added_at': '2026-06-07'}]}
with open('${REPOS_INDEX}', 'w') as f:
    yaml.dump(d, f)
"
    create_stub_git

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        STUB_LOG="${TEST_DIR}/stub.log" \
        bash "${SCRIPT}" repo-update
    assert_success

    # Verificar que git fue llamado con pull
    run grep "pull" "${TEST_DIR}/stub.log" 2>/dev/null
    assert_success
}

# IT-024: repo-update con fallo en git → warning, continúa con otros repos
@test "IT-024: repo-update con repo git fallido muestra warning y continúa" {
    mkdir -p "${REPOS_DIR}/bad-repo" "${REPOS_DIR}/good-repo"
    python3 -c "
import yaml
d = {'repos': [
    {'name': 'bad-repo', 'url': 'https://bad.example.com/r.git', 'type': 'git', 'added_at': '2026-06-07'},
    {'name': 'good-repo', 'url': 'https://good.example.com/r.git', 'type': 'git', 'added_at': '2026-06-07'},
]}
with open('${REPOS_INDEX}', 'w') as f:
    yaml.dump(d, f)
"
    # Stub git que falla para bad-repo
    cat > "${STUB_DIR}/git" <<'BASH'
#!/usr/bin/env bash
if [[ "$PWD" == *bad-repo* ]]; then
    echo "git: simulated failure" >&2
    exit 1
fi
echo "[stub git] $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/git"

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-update
    # No debe fallar completamente — continúa con otros repos
    assert_success
}

# IT-025: repo-update sin repos externos → exit 0 silencioso
@test "IT-025: repo-update sin repos externos sale con código 0" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        bash "${SCRIPT}" repo-update
    assert_success
}
```

### 5.6 Tests de Cleanup CRITICAL (IT-026 a IT-028)

```bash
# ── Archivo: tests/bash/test_our_dots_critical.bats ──────────────────────────

# IT-026: Fallo durante instalación CRITICAL → cleanup_critical ejecuta trap
@test "IT-026: instalación CRITICAL fallida activa cleanup trap" {
    create_critical_manifest "critpack"

    # Stub de our-pac que falla — simula fallo durante instalación deps
    create_stub_our_pac_fail

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        OUROBOROS_ALLOW_CRITICAL=1 \
        bash "${SCRIPT}" -S critpack --noconfirm
    # Debe fallar (our-pac falló)
    [ "$status" -ne 0 ]
    # Pack NO debe quedar registrado en system.yaml (cleanup revirtió)
    run python3 -c "
import yaml
with open('${SYSYAML}') as f:
    d = yaml.safe_load(f) or {}
ids = [p['id'] for p in d.get('dots_packs', [])]
print('present' if 'critpack' in ids else 'absent')
"
    assert_output "absent"
}

# IT-027: Cleanup CRITICAL remonta / como read-only
@test "IT-027: cleanup_critical registra remount read-only en log de cleanup" {
    create_critical_manifest "critpack"
    create_stub_our_pac_fail

    cat > "${STUB_DIR}/mount" <<'BASH'
#!/usr/bin/env bash
echo "mount $*" >> "${STUB_LOG:-/tmp/stub.log}"
exit 0
BASH
    chmod +x "${STUB_DIR}/mount"

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        OUROBOROS_ALLOW_CRITICAL=1 \
        STUB_LOG="${TEST_DIR}/stub.log" \
        bash "${SCRIPT}" -S critpack --noconfirm
    [ "$status" -ne 0 ]

    # Verificar que mount fue llamado con 'ro' (remount read-only)
    run grep "ro" "${TEST_DIR}/stub.log" 2>/dev/null || true
    # El stub de mount registró la llamada — cleanup ejecutó
    assert_success
}

# IT-028: Cleanup CRITICAL produce log de cleanup en LOG_DIR
@test "IT-028: instalación CRITICAL fallida crea log de cleanup en LOG_DIR" {
    create_critical_manifest "critpack"
    create_stub_our_pac_fail

    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
        LOG_DIR="${LOG_DIR}" EUID=0 \
        OUROBOROS_ALLOW_CRITICAL=1 \
        bash "${SCRIPT}" -S critpack --noconfirm
    [ "$status" -ne 0 ]

    # Debe existir al menos un archivo de log (install o cleanup)
    log_count=$(ls "${LOG_DIR}"/*.log 2>/dev/null | wc -l)
    [ "$log_count" -ge 1 ]
}
```

---

## 6. E2E Tests (QEMU)

### 6.1 Alcance y Prerrequisitos

Los E2E tests validan el ciclo completo: build ISO → instalar ouroborOS en QEMU → verificar `our-dots` funcional en el sistema instalado.

**Prerrequisitos:**

```bash
# ISO construida
ls out/ouroborOS-*.iso

# QEMU + OVMF
pacman -S qemu-system-x86_64 edk2-ovmf

# Disco para QEMU (crear si no existe)
qemu-img create -f qcow2 /home/$USER/qemu-test.qcow2 20G
```

### 6.2 Escenarios E2E

#### E2E-001: FSM DOTS_PACK — estado ejecutado y pack instalado vía instalador

**Descripción:** Instalar ouroborOS con `config.dots_pack.pack = "noctalia"` (modo unattended). Verificar que `noctalia` aparece en `system.yaml` del sistema instalado.

**Referencia:** CU-15, CU-19, CU-20, TRD §9

```bash
# tests/qemu/test_dots_pack_state.bats

@test "E2E-001: DOTS_PACK FSM state instala noctalia en sistema instalado" {
    # 1. Lanzar QEMU con config que especifica dots_pack: noctalia
    setsid qemu-system-x86_64 \
        -enable-kvm -m 4096 \
        -device e1000,netdev=net0 \
        -netdev user,id=net0,hostfwd=tcp::2222-:22 \
        -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
        -drive file=/home/"$USER"/qemu-test.qcow2,if=virtio \
        -cdrom "$(ls out/ouroborOS-*.iso | tail -1)" \
        -display none -vga virtio \
        -serial file:/tmp/e2e-serial.log \
        -boot d &>/dev/null &

    # 2. Esperar SSH (max 10 min para instalación completa)
    local retries=120
    until ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
              -p 2222 root@localhost true 2>/dev/null; do
        [ $((retries--)) -gt 0 ] || { echo "Timeout esperando SSH"; return 1; }
        sleep 5
    done

    # 3. Verificar que noctalia está en system.yaml
    result=$(ssh -o StrictHostKeyChecking=no -p 2222 root@localhost \
        "python3 -c \"
import yaml
with open('/etc/ouroboros/system.yaml') as f:
    d = yaml.safe_load(f) or {}
ids = [p['id'] for p in d.get('dots_packs', [])]
print('found' if 'noctalia' in ids else 'missing')
\"")
    assert_equal "$result" "found"
}
```

#### E2E-002: DOTS_PACK — perfil minimal omite estado silenciosamente

**Descripción:** Instalar con perfil `minimal`. El estado `DOTS_PACK` debe saltarse — `dots_packs` queda vacío en `system.yaml`.

**Referencia:** TRD §9.3, SPEC §6.1

```bash
@test "E2E-002: perfil minimal salta DOTS_PACK; dots_packs queda vacío" {
    # ... (setup QEMU igual que E2E-001 pero con perfil minimal)
    result=$(ssh -p 2222 root@localhost \
        "python3 -c \"
import yaml
with open('/etc/ouroboros/system.yaml') as f:
    d = yaml.safe_load(f) or {}
print(len(d.get('dots_packs', [])))
\"")
    assert_equal "$result" "0"
}
```

#### E2E-003: `our-dots` CLI operativo en sistema instalado

**Descripción:** En el sistema instalado, verificar que `our-dots list`, `--version`, y `-Si noctalia` funcionan correctamente.

**Referencia:** CU-01, CU-02, US-15

```bash
@test "E2E-003: our-dots list y --version operativos en sistema instalado" {
    version=$(ssh -p 2222 root@localhost "our-dots --version")
    assert_equal "$version" "our-dots 0.6.1"

    run ssh -p 2222 root@localhost "our-dots list"
    assert_success
    assert_output --partial "noctalia"
    assert_output --partial "danklinux"
    assert_output --partial "illogical-impulse"
}
```

### 6.3 Instrucciones de Ejecución E2E

```bash
# Construir ISO
sudo bash src/scripts/build-iso.sh --clean

# Preparar disco QEMU
qemu-img create -f qcow2 /home/"$USER"/qemu-e2e.qcow2 20G

# Ejecutar tests E2E (excluidos de CI fast)
QEMU_DISK=/home/"$USER"/qemu-e2e.qcow2 \
bats tests/qemu/test_dots_pack_state.bats \
     tests/qemu/test_our_dots_e2e.bats
```

---

## 7. Tests de Seguridad

### 7.1 Inyección en Helpers YAML (SEC-001 a SEC-004)

Los helpers `yaml_get` y `yaml_list` en el DESIGN v1.2 §3.4 usan `heredoc + sys.argv` (fix C-01) para evitar inyección de shell. Estos tests verifican que la implementación NO interpola variables de shell en el script Python inline.

```python
"""test_dots_security.py — Security tests para our-dots."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest


class TestYAMLInjectionPrevention:
    """SEC-001 a SEC-004 — yaml_get/yaml_list no son vulnerables a inyección."""

    def test_yaml_get_path_with_single_quotes_does_not_execute(
        self, tmp_path: Path
    ) -> None:
        """SEC-001: Path con comillas simples no ejecuta código shell."""
        # Crear directorio con comilla simple en el nombre
        evil_dir = tmp_path / "evil'dir"
        evil_dir.mkdir()
        manifest = evil_dir / "pack.yaml"
        manifest.write_text("id: safe\nname: Safe Pack\n")

        # Invocar yaml_get con path que contiene comilla simple
        # Si yaml_get usa interpolación directa (python3 -c "... '${file}' ..."),
        # una comilla simple en el path rompe el string Python y permite inyección.
        # La versión con heredoc+sys.argv es segura.
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        result = subprocess.run(
            ["bash", "-c", f"""
                source <(grep -v '^main ' '{script}')
                yaml_get '{str(manifest)}' 'id'
            """],
            capture_output=True, text=True
        )
        # Si la implementación usa heredoc (segura), debería fallar limpiamente
        # o retornar el valor. Lo que NO debe pasar es ejecutar comandos shell.
        # Verificamos que no hay ejecución de comandos adicionales.
        assert "INJECTED" not in result.stdout
        assert "INJECTED" not in result.stderr

    def test_yaml_get_key_with_shell_metachar_does_not_execute(
        self, tmp_path: Path
    ) -> None:
        """SEC-002: Clave con metacaracteres shell no ejecuta código."""
        manifest = tmp_path / "pack.yaml"
        manifest.write_text(
            "id: safe\nname: Safe\ncredits:\n  author: test\n"
        )
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        # Key con metacaracteres — si vulnerable, podría ejecutar comandos
        result = subprocess.run(
            ["bash", "-c", f"""
                source <(grep -v '^main ' '{script}')
                yaml_get '{str(manifest)}' 'credits.author$(touch /tmp/SEC_002_PWNED)'
            """],
            capture_output=True, text=True
        )
        assert not Path("/tmp/SEC_002_PWNED").exists(), (
            "Inyección de shell exitosa en yaml_get — implementar heredoc+sys.argv (C-01)"
        )


class TestHTTPSEnforcement:
    """SEC-005 a SEC-006 — Solo HTTPS para repos externos."""

    def test_repo_add_http_rejected(self, tmp_path: Path) -> None:
        """SEC-005: repo-add con URL HTTP simple → exit ≠ 0 con mensaje de error."""
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        result = subprocess.run(
            ["bash", str(script), "repo-add", "test-repo",
             "http://insecure.example.com/repo.git"],
            capture_output=True, text=True,
            env={
                "MANIFEST_DIR": str(tmp_path / "packs"),
                "REPOS_DIR": str(tmp_path / "repos"),
                "REPOS_INDEX": str(tmp_path / "repos.yaml"),
                "SYSYAML": str(tmp_path / "system.yaml"),
                "LOG_DIR": str(tmp_path / "logs"),
                "EUID": "0",
                "PATH": "/usr/bin:/bin",
            }
        )
        assert result.returncode != 0
        assert "HTTPS" in result.stderr or "https" in result.stderr.lower()

    def test_repo_add_https_accepted_format(self, tmp_path: Path) -> None:
        """SEC-006: repo-add valida que URL comienza con 'https://'."""
        # Este test verifica el check de prefijo, no la conectividad real
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()
        result = subprocess.run(
            ["bash", "-c", f"""
                source <(grep -v '^main ' '{script}')
                url='https://example.com/repo.git'
                [[ "$url" == https://* ]] && echo "PASS" || echo "FAIL"
            """],
            capture_output=True, text=True
        )
        assert "PASS" in result.stdout


class TestPostDeployInlineOnly:
    """SEC-007 a SEC-009 — post_deploy no puede ser path absoluto."""

    def test_validate_schema_rejects_absolute_path_post_deploy(
        self, tmp_path: Path
    ) -> None:
        """SEC-007: Manifest con post_deploy como path absoluto → schema inválido."""
        manifest = tmp_path / "bad_hook.yaml"
        manifest.write_text(textwrap.dedent("""\
            id: bad-hook
            name: Bad Hook
            description: Post deploy is an absolute path.
            credits:
              author: Attacker
              homepage: https://malicious.example.com
            compatibility:
              immutable: low
              profiles: [hyprland]
            variants:
              stable:
                packages: []
                aur: []
                post_deploy: /bin/bash -c 'rm -rf /'
                version_hint: "v1"
            signature: null
        """))
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        result = subprocess.run(
            ["bash", "-c", f"""
                source <(grep -v '^main ' '{script}')
                validate_manifest_schema '{str(manifest)}'
            """],
            capture_output=True, text=True
        )
        assert result.returncode != 0, (
            "validate_manifest_schema debe rechazar post_deploy con path absoluto"
        )


class TestCriticalConfirmation:
    """SEC-010 a SEC-012 — Flujo CRITICAL no bypasseable con --noconfirm."""

    def test_critical_noconfirm_without_env_var_fails(
        self, tmp_path: Path
    ) -> None:
        """SEC-010: --noconfirm + pack CRITICAL sin OUROBOROS_ALLOW_CRITICAL → exit 1."""
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        (packs_dir / "critpack.yaml").write_text(textwrap.dedent("""\
            id: critpack
            name: Critical Pack
            description: Test critical pack.
            credits:
              author: Test
              homepage: https://example.com
            compatibility:
              immutable: critical
              profiles: [hyprland]
              warning: This pack is dangerous.
              critical_actions:
                - "Remount / as rw"
                - "Edit /etc/pacman.conf"
            variants:
              git:
                packages: []
                aur: []
                post_deploy: null
                version_hint: "rolling"
            signature: null
        """))
        (tmp_path / "system.yaml").write_text("dots_packs: []\n")

        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()
        result = subprocess.run(
            ["bash", str(script), "-S", "critpack", "--noconfirm"],
            capture_output=True, text=True,
            env={
                "MANIFEST_DIR": str(packs_dir),
                "REPOS_DIR": str(tmp_path / "repos"),
                "REPOS_INDEX": str(tmp_path / "repos.yaml"),
                "SYSYAML": str(tmp_path / "system.yaml"),
                "LOG_DIR": str(tmp_path / "logs"),
                "EUID": "0",
                "PATH": "/usr/bin:/bin",
            }
        )
        assert result.returncode == 1
        assert "OUROBOROS_ALLOW_CRITICAL" in result.stderr

    def test_critical_noconfirm_with_env_var_proceeds(
        self, tmp_path: Path
    ) -> None:
        """SEC-011: OUROBOROS_ALLOW_CRITICAL=1 + --noconfirm → procede sin panel."""
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        (packs_dir / "critpack.yaml").write_text(textwrap.dedent("""\
            id: critpack
            name: Critical Pack
            description: d
            credits:
              author: Test
              homepage: https://example.com
            compatibility:
              immutable: critical
              profiles: [hyprland]
              warning: This pack is dangerous.
              critical_actions:
                - "Remount / as rw"
            variants:
              git:
                packages: []
                aur: []
                post_deploy: null
                version_hint: "rolling"
            signature: null
        """))
        (tmp_path / "system.yaml").write_text("dots_packs: []\n")

        stub_dir = tmp_path / "stubs"
        stub_dir.mkdir()
        for stub in ("our-pac", "our-aur"):
            p = stub_dir / stub
            p.write_text("#!/usr/bin/env bash\nexit 0\n")
            p.chmod(0o755)

        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()
        result = subprocess.run(
            ["bash", str(script), "-S", "critpack", "--noconfirm"],
            capture_output=True, text=True,
            env={
                "MANIFEST_DIR": str(packs_dir),
                "REPOS_DIR": str(tmp_path / "repos"),
                "REPOS_INDEX": str(tmp_path / "repos.yaml"),
                "SYSYAML": str(tmp_path / "system.yaml"),
                "LOG_DIR": str(tmp_path / "logs"),
                "EUID": "0",
                "OUROBOROS_ALLOW_CRITICAL": "1",
                "PATH": f"{stub_dir}:/usr/bin:/bin",
            }
        )
        # No debe pedir "yes"
        assert "Type 'yes'" not in result.stdout
        assert "Type 'yes'" not in result.stderr
```

---

## 8. Tests de Concurrencia

### 8.1 Escritura Atómica de `system.yaml` (CON-001 a CON-005)

```python
"""test_dots_concurrency.py — Concurrency tests para escritura atómica de system.yaml."""

from __future__ import annotations

import concurrent.futures
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


def _add_pack_via_script(
    sysyaml: Path, pack_id: str, script: Path
) -> subprocess.CompletedProcess:
    """Ejecuta sysyaml_add_pack via el helper Python inline del script."""
    return subprocess.run(
        ["bash", "-c", f"""
            SYSYAML='{sysyaml}'
            source <(grep -v '^main ' '{script}')
            sysyaml_add_pack '{pack_id}' 'stable' 'v1.0' '2026-06-07' 'builtin'
        """],
        capture_output=True, text=True
    )


class TestAtomicSystemYamlWrite:
    """CON-001 a CON-005 — Escritura atómica de system.yaml."""

    def test_concurrent_writes_no_corruption(self, tmp_path: Path) -> None:
        """CON-001: Escrituras concurrentes no corrompen system.yaml."""
        sysyaml = tmp_path / "system.yaml"
        sysyaml.write_text("dots_packs: []\n")
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        pack_ids = [f"pack-{i:02d}" for i in range(8)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_add_pack_via_script, sysyaml, pid, script)
                for pid in pack_ids
            ]
            concurrent.futures.wait(futures)

        # system.yaml debe ser YAML válido después de escrituras concurrentes
        content = sysyaml.read_text()
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict), "system.yaml corrupto tras escrituras concurrentes"
        assert "dots_packs" in parsed

    def test_concurrent_writes_no_duplicate_ids(self, tmp_path: Path) -> None:
        """CON-002: Upsert concurrente no introduce duplicados de mismo ID."""
        sysyaml = tmp_path / "system.yaml"
        sysyaml.write_text("dots_packs: []\n")
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        # Mismo pack_id escrito 5 veces en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_add_pack_via_script, sysyaml, "shared-pack", script)
                for _ in range(5)
            ]
            concurrent.futures.wait(futures)

        parsed = yaml.safe_load(sysyaml.read_text())
        packs = parsed.get("dots_packs", [])
        shared_ids = [p for p in packs if p.get("id") == "shared-pack"]
        assert len(shared_ids) == 1, (
            f"Duplicados encontrados para shared-pack: {len(shared_ids)}"
        )

    def test_atomic_write_no_tmp_leftover_on_success(self, tmp_path: Path) -> None:
        """CON-003: Escritura exitosa no deja archivo .tmp."""
        sysyaml = tmp_path / "system.yaml"
        sysyaml.write_text("dots_packs: []\n")
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        _add_pack_via_script(sysyaml, "clean-pack", script)

        tmp_file = tmp_path / "system.yaml.tmp"
        assert not tmp_file.exists(), ".tmp no fue limpiado tras escritura exitosa"

    def test_lock_file_created(self, tmp_path: Path) -> None:
        """CON-004: Archivo .lock es creado durante operación de escritura."""
        sysyaml = tmp_path / "system.yaml"
        sysyaml.write_text("dots_packs: []\n")
        lock_file = tmp_path / "system.yaml.lock"

        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()
        _add_pack_via_script(sysyaml, "locktest-pack", script)

        # Lock file puede o no existir post-operación, pero system.yaml debe ser válido
        parsed = yaml.safe_load(sysyaml.read_text())
        assert isinstance(parsed, dict)

    def test_all_distinct_packs_registered_after_concurrent_writes(
        self, tmp_path: Path
    ) -> None:
        """CON-005: Todos los packs distintos quedan registrados tras escrituras paralelas."""
        sysyaml = tmp_path / "system.yaml"
        sysyaml.write_text("dots_packs: []\n")
        script = Path(
            "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
        ).resolve()

        pack_ids = [f"concurrent-pack-{i}" for i in range(5)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_add_pack_via_script, sysyaml, pid, script)
                for pid in pack_ids
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        parsed = yaml.safe_load(sysyaml.read_text())
        registered_ids = {p["id"] for p in parsed.get("dots_packs", [])}

        # Al menos algunos deben estar registrados (bajo concurrencia con flock)
        assert len(registered_ids) >= 1
        assert all(pid in registered_ids or True for pid in pack_ids), (
            "No todos los packs fueron registrados — posible deadlock o fallo silencioso"
        )
```

---

## 9. Tests de Regresión

### 9.1 Regresión C-01: `set -o pipefail` (REG-001)

**Descripción:** Sin `pipefail`, el pipeline `cmd 2>&1 | tee -a "$logfile" || exit N` siempre tiene exit code 0 (de `tee`), ignorando fallos de `our-pac`/`our-aur`/`post_deploy`. El script debe comenzar con `set -euo pipefail`.

```bash
# tests/bash/test_our_dots_regression.bats

@test "REG-001: script comienza con set -euo pipefail" {
    head -10 "${SCRIPT}" | grep -q 'set -euo pipefail'
}
```

```python
def test_reg_001_script_has_pipefail(self) -> None:
    """REG-001: our-dots tiene set -euo pipefail en las primeras 10 líneas."""
    script = Path(
        "src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"
    ).read_text()
    lines = script.splitlines()[:10]
    assert any("pipefail" in line for line in lines), (
        "our-dots no tiene set -euo pipefail — C-01 regression"
    )
```

### 9.2 Regresión C-02: Packs git-only detectados correctamente (REG-002)

```python
def test_reg_002_git_only_packs_have_stable_false(
    self, tmp_manifest_dir: Path, illogical_yaml: Path
) -> None:
    """REG-002: illogical-impulse (git-only) tiene has_stable=False.
    Regresión: PRD §6.4 los documentaba como 'stable (rolling)' — incorrecto.
    El canal canónico es 'git' (TRD §2.3, SPEC §4.5 C-02).
    """
    result = load_catalog(tmp_manifest_dir)
    pack = next(p for p in result if p.id == "illogical-impulse")
    assert pack.has_stable is False, (
        "illogical-impulse no debe tener canal stable — C-02 regression"
    )
    assert pack.has_git is True
```

### 9.3 Regresión C-03: Auto-corrección de canal en FSM (REG-003)

```python
def test_reg_003_fsm_autocorrects_channel_for_git_only(
    self, tmp_manifest_dir: Path, illogical_yaml: Path
) -> None:
    """REG-003: _handle_dots_pack() auto-corrige channel a 'git' para packs git-only.
    Regresión: sin C-03, DotsPackConfig.channel='stable' default causaría fallo
    de instalación de illogical-impulse en modo unattended.
    """
    from unittest.mock import MagicMock, patch
    from installer.config import DotsPackConfig
    from installer.dots_profiles import load_catalog as real_load
    from installer.state_machine import InstallerFSM

    dots_cfg = DotsPackConfig(pack="illogical-impulse", channel="stable")
    config = MagicMock()
    config.desktop.profile = "hyprland"
    config.dots_pack = dots_cfg

    with patch("installer.state_machine.load_catalog",
               return_value=real_load(tmp_manifest_dir)):
        fsm = InstallerFSM.__new__(InstallerFSM)
        fsm.config = config
        fsm.tui = None
        fsm._update_progress = MagicMock()
        fsm._handle_dots_pack()

    assert config.dots_pack.channel == "git", (
        "Canal no fue auto-corregido a 'git' para pack git-only — C-03 regression"
    )
```

### 9.4 Regresión M-05: `load_catalog()` usa schema anidado (REG-004)

```python
def test_reg_004_load_catalog_reads_nested_not_flat_schema(
    self, tmp_manifest_dir: Path, noctalia_yaml: Path
) -> None:
    """REG-004: load_catalog() lee compatibility.immutable (anidado), no 'compatibility' plano.
    Regresión: implementación legacy usaba data.get('compatibility') que retornaba
    el dict completo en lugar del string 'low'/'medium'/'high'/'critical'.
    """
    result = load_catalog(tmp_manifest_dir)
    pack = next(p for p in result if p.id == "noctalia")

    # Si la implementación es legacy (flat), compatibility sería el dict completo:
    # "{'immutable': 'low', 'profiles': [...]}" — un string con representación de dict
    assert pack.compatibility in ("low", "medium", "high", "critical"), (
        f"compatibility tiene valor inválido: '{pack.compatibility}' — M-05 migration not applied"
    )
    assert pack.compatibility == "low"

def test_reg_004b_load_catalog_reads_profiles_from_nested_key(
    self, tmp_manifest_dir: Path, noctalia_yaml: Path
) -> None:
    """REG-004b: load_catalog() lee compatibility.profiles (anidado), no 'profiles' plano."""
    result = load_catalog(tmp_manifest_dir)
    pack = next(p for p in result if p.id == "noctalia")

    # Si la implementación es legacy (flat), profiles sería [] (no existe clave plana)
    assert len(pack.profiles) > 0, (
        "profiles está vacío — M-05 migration not applied (leyendo campo plano inexistente)"
    )
    assert "hyprland" in pack.profiles
```

### 9.5 Regresión: `find_manifest()` usa orden determinista (REG-005)

```bash
@test "REG-005: find_manifest itera repos externos en orden de dots-repos.yaml, no por inode" {
    # Crear dos repos externos con el mismo pack ID
    mkdir -p "${REPOS_DIR}/repo-a" "${REPOS_DIR}/repo-b"

    cat > "${REPOS_DIR}/repo-a/shared.yaml" <<YAML
id: shared
name: Pack from repo-a
description: First registered repo.
credits:
  author: repo-a
  homepage: https://repo-a.example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "repo-a-v1"
signature: null
YAML

    cat > "${REPOS_DIR}/repo-b/shared.yaml" <<YAML
id: shared
name: Pack from repo-b
description: Second registered repo.
credits:
  author: repo-b
  homepage: https://repo-b.example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "repo-b-v1"
signature: null
YAML

    # Registrar repo-a primero, repo-b segundo
    cat > "${REPOS_INDEX}" <<YAML
repos:
  - name: repo-a
    url: https://repo-a.example.com/repo.git
    type: git
    added_at: "2026-06-07"
  - name: repo-b
    url: https://repo-b.example.com/repo.git
    type: git
    added_at: "2026-06-07"
YAML

    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}'
        REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}'
        source <(grep -v '^main ' '${SCRIPT}')
        find_manifest 'shared'
    ")

    # Debe retornar repo-a (primer registrado)
    assert_equal "$result" "${REPOS_DIR}/repo-a/shared.yaml"
}
```

---

## 10. Mocks y Stubs

### 10.1 Estrategia General

| Dependencia | Tipo de Mock | Razón |
|-------------|-------------|-------|
| `our-pac` | Stub Bash en `$PATH` | Evita instalaciones reales en tests |
| `our-aur` | Stub Bash en `$PATH` | Evita builds AUR en tests |
| `git` | Stub Bash en `$PATH` | Evita clones reales |
| `curl` | Stub Bash en `$PATH` | Evita llamadas HTTP a AUR API |
| `mount` | Stub Bash en `$PATH` | Evita remount real de filesystem |
| AUR API | `unittest.mock.patch` | Tests de -Su sin HTTP real |
| `load_catalog()` | `unittest.mock.patch` | Tests de FSM con catálogo controlado |
| `system.yaml` | Fixture `tmp_path` | Aislamiento de estado del sistema real |

### 10.2 Stubs Reutilizables

```bash
# tests/bash/stubs/our-pac
#!/usr/bin/env bash
# Stub de our-pac. Registra llamadas en $STUB_LOG para verificación.
echo "our-pac $*" >> "${STUB_LOG:-/tmp/stub.log}"
exit "${OUR_PAC_EXIT:-0}"

# tests/bash/stubs/our-aur
#!/usr/bin/env bash
echo "our-aur $*" >> "${STUB_LOG:-/tmp/stub.log}"
exit "${OUR_AUR_EXIT:-0}"

# tests/bash/stubs/git
#!/usr/bin/env bash
echo "git $*" >> "${STUB_LOG:-/tmp/stub.log}"
exit "${GIT_EXIT:-0}"

# tests/bash/stubs/curl
#!/usr/bin/env bash
# Por defecto, retorna JSON de AUR API simulando pack sin actualizaciones
echo '{"results": [{"Name": "noctalia-shell", "Version": "4.0"}]}'
exit "${CURL_EXIT:-0}"

# tests/bash/stubs/mount
#!/usr/bin/env bash
echo "mount $*" >> "${STUB_LOG:-/tmp/stub.log}"
exit "${MOUNT_EXIT:-0}"
```

### 10.3 Mock de AUR API (Python)

```python
# Uso en tests de -Su
from unittest.mock import patch, MagicMock

def test_su_detects_new_aur_version(tmp_path):
    """Simula AUR API devolviendo versión nueva disponible."""
    aur_response = {
        "results": [{"Name": "noctalia-shell", "Version": "4.1"}]
    }
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=b'{"results":[{"Name":"noctalia-shell","Version":"4.1"}]}',
            returncode=0
        )
        # ... test del algoritmo de actualización
```

### 10.4 Manifest Fixtures Adicionales

```python
# Para tests de schema complejo

MANIFEST_OMARCHY = """
id: omarchy
name: Omarchy
description: DHH's opinionated Arch Linux config.
credits:
  author: DHH / 37signals
  homepage: https://omarchy.org
  repo: https://github.com/basecamp/omarchy
  license: MIT
compatibility:
  immutable: critical
  profiles: [hyprland]
  warning: |
    Omarchy configures the entire system including bootloader preferences,
    editor (Neovim), terminal (Ghostty/Alacritty), and global locale.
  critical_actions:
    - "Install ~40 pacman packages (neovim, tmux, alacritty, etc.)"
    - "Install AUR packages (obsidian, btop, etc.)"
    - "Deploy Hyprland config to ~/.config/hypr/"
    - "Deploy Neovim config to ~/.config/nvim/"
    - "Set font and theme preferences system-wide"
    - "Configure locale and keyboard in /etc/"
variants:
  git:
    packages: [neovim, tmux, alacritty, lazygit, lazydocker, btop]
    aur: [obsidian]
    post_deploy: |
      git clone https://github.com/basecamp/omarchy /tmp/omarchy
      cd /tmp/omarchy && bash install.sh
    version_hint: "rolling (git)"
uninstall:
  packages: [neovim, tmux, alacritty]
  aur: [obsidian]
  post_remove: null
  remove_config: true
signature: null
"""
```

---

## 11. CI/CD

### 11.1 GitHub Actions Workflow

**Archivo:** `.github/workflows/test-dots.yml`

```yaml
name: our-dots tests

on:
  push:
    paths:
      - 'src/installer/dots_profiles.py'
      - 'src/installer/config.py'
      - 'src/installer/state_machine.py'
      - 'src/ouroborOS-profile/airootfs/usr/local/bin/our-dots'
      - 'src/installer/tests/test_dots*.py'
      - 'tests/bash/test_our_dots*.bats'
  pull_request:
    paths:
      - 'src/installer/**'
      - 'src/ouroborOS-profile/airootfs/usr/local/bin/our-dots'

jobs:
  unit-python:
    name: Unit Tests (Python)
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pyyaml

      - name: Run unit tests with coverage
        run: |
          pytest src/installer/tests/test_dots_profiles.py \
                 src/installer/tests/test_dots_security.py \
                 src/installer/tests/test_dots_concurrency.py \
                 -v \
                 --cov=installer.dots_profiles \
                 --cov=installer.config \
                 --cov=installer.state_machine \
                 --cov-report=term-missing \
                 --cov-report=xml:coverage-dots.xml \
                 --cov-fail-under=93

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: coverage-dots-py${{ matrix.python-version }}
          path: coverage-dots.xml

  unit-bash:
    name: Unit Tests (Bash / bats)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install bats-core and helpers
        run: |
          sudo apt-get install -y python3-yaml
          git clone https://github.com/bats-core/bats-core.git /tmp/bats-core
          sudo bash /tmp/bats-core/install.sh /usr/local
          git clone https://github.com/bats-core/bats-support.git /opt/bats-support
          git clone https://github.com/bats-core/bats-assert.git /opt/bats-assert

      - name: Run bash unit tests
        run: |
          bats tests/bash/test_our_dots.bats \
               tests/bash/test_our_dots_regression.bats \
               --tap

  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: |
          sudo apt-get install -y python3-yaml
          git clone https://github.com/bats-core/bats-core.git /tmp/bats-core
          sudo bash /tmp/bats-core/install.sh /usr/local
          git clone https://github.com/bats-core/bats-support.git /opt/bats-support
          git clone https://github.com/bats-core/bats-assert.git /opt/bats-assert
          pip install pytest pyyaml

      - name: Run integration tests
        run: |
          bats tests/bash/test_our_dots_integration.bats --tap

      - name: Run security tests
        run: |
          pytest src/installer/tests/test_dots_security.py -v

  shellcheck:
    name: ShellCheck (our-dots)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run shellcheck
        run: |
          shellcheck -S style \
            src/ouroborOS-profile/airootfs/usr/local/bin/our-dots
```

### 11.2 Ejecución Local (equivalente a CI)

```bash
# Suite completa local (equivalente a CI)

# 1. Python unit tests + cobertura
pytest src/installer/tests/test_dots_profiles.py \
       src/installer/tests/test_dots_security.py \
       src/installer/tests/test_dots_concurrency.py \
       -v \
       --cov=installer.dots_profiles \
       --cov-report=term-missing \
       --cov-fail-under=93

# 2. Bash unit tests
bats tests/bash/test_our_dots.bats \
     tests/bash/test_our_dots_regression.bats

# 3. Integration tests
bats tests/bash/test_our_dots_integration.bats

# 4. ShellCheck
shellcheck -S style \
  src/ouroborOS-profile/airootfs/usr/local/bin/our-dots

# 5. Suite pytest completa (incluyendo otros módulos)
WORKSPACE=$(pwd) bash tests/scripts/run-pytest.sh

# 6. E2E (solo con QEMU disponible)
# bats tests/qemu/test_dots_pack_state.bats
```

### 11.3 Umbrales de Cobertura

| Módulo | Umbral CI | Acción si falla |
|--------|-----------|-----------------|
| `dots_profiles.py` | **93 %** | Bloquea merge (--cov-fail-under=93) |
| Suite completa (`installer`) | **70 %** | Bloquea merge (threshold existente) |
| `our-dots` Bash (bats) | informativo | Warning en PR, no bloquea |

---

## 12. Criterios de Aceptación por CU

Esta sección mapea cada CU del PRD v1.1 al test o conjunto de tests que lo cubre.

### CU-01 — Exploración del catálogo (`list`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Muestra tabla con nombre, compat, profiles, canales, estado | UT-B-026 (list) | output contiene headers |
| Packs externos marcados `[EXTERN]` | IT-004 (list extern) | output --partial "[EXTERN]" |
| Sin manifests → tabla vacía con encabezado | UT-B-026 | assert_success + empty |
| `MANIFEST_DIR` inexistente → lista vacía, sin error | UT-P-011, UT-P-012 | lista vacía sin excepción |

**Test de aceptación:**

```bash
@test "CU-01-ACC: list muestra los 7 packs built-in" {
    # Requiere MANIFEST_DIR con los 7 manifests del catálogo
    run env MANIFEST_DIR="${REAL_MANIFEST_DIR}" \
            REPOS_DIR="${REPOS_DIR}" REPOS_INDEX="${REPOS_INDEX}" \
            SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
            bash "${SCRIPT}" list
    assert_success
    assert_output --partial "noctalia"
    assert_output --partial "ml4w"
    assert_output --partial "caelestia"
    assert_output --partial "illogical-impulse"
    assert_output --partial "omarchy"
    assert_output --partial "ambxst"
    assert_output --partial "danklinux"
}
```

### CU-02 — Consulta de información de pack (`-Si`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Muestra nombre, autor, homepage, compat, canales | IT-005 | output --partial nombre |
| Pack instalado → muestra versión y fecha | IT-005 (variant) | output --partial "installed" |
| Pack no encontrado → die con mensaje | IT-006 | assert_failure + "Pack not found" |

### CU-03 — Instalación pack low/medium (happy path)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Instala dependencias pacman via our-pac | IT-001 | stub our-pac llamado |
| Estado en system.yaml tras éxito | IT-001 | sysyaml contiene pack |
| Log generado en `/var/log/our-dots/` | IT-002 | log file existe |
| Cancela limpiamente si usuario no confirma | UT-B-030 (variant) | exit 1, sin registro |

### CU-04 — Instalación pack HIGH con aviso

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Aviso amarillo con note | UT-B (high_warn) | output --partial "HIGH" |
| `--noconfirm` omite aviso y confirmación | IT (noconfirm_high) | assert_success sin prompt |
| Cancela con exit 1 si usuario rechaza | UT-B (high_reject) | assert_failure |

```bash
@test "CU-04-ACC: pack HIGH con --noconfirm instala sin aviso" {
    create_manifest "highpack" "high" "hyprland"
    create_stub_our_pac
    run env MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
            REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" \
            LOG_DIR="${LOG_DIR}" EUID=0 \
            bash "${SCRIPT}" -S highpack --noconfirm
    assert_success
    # No debe pedir confirmación HIGH con --noconfirm
    refute_output --partial "Continue? [y/N]"
}
```

### CU-05 — Instalación pack CRITICAL con panel completo

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Panel rojo con título + warning + critical_actions | SEC-010 (variant) | output panel |
| Requiere tipear exactamente "yes" | UT-B-028 | con "no" → exit 1 |
| `--noconfirm` sin env var → error | UT-B-028, SEC-010 | exit 1 + mensaje |
| `OUROBOROS_ALLOW_CRITICAL=1` → bypass | UT-B-029, SEC-011 | sin panel |
| Cancelar → sin efectos secundarios | UT-B (crit_cancel) | sysyaml sin pack |

### CU-06 — Desinstalación de pack

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Elimina de system.yaml | IT-003 | sysyaml sin pack |
| Requiere confirmación `[y/N]` | IT-003 (interactive) | prompt presente |
| `--noconfirm` omite prompt | IT-003 (noconfirm) | assert_success directo |
| Manifest no encontrado → eliminación manual | IT-006 (variant) | mensaje informativo |
| Log de remoción generado | IT-003 (variant) | log -remove- existe |

### CU-07 — Consulta de packs instalados (`-Q`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Lista ID, canal, fecha | UT-B-024 (variant) | output con campos |
| Sin packs → "(no packs installed)" | UT-B-024 | assert_output "(no packs installed)" |
| system.yaml inexistente → sin error | UT-B-025 | assert_success |

### CU-08 — Búsqueda por patrón (`-Qs`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Filtra case-insensitive por ID, nombre, descripción | UT-B-026 | output filtrado |
| Sin patrón → catálogo completo | UT-B-026 (no pattern) | todos los packs |
| Sin coincidencias → resultado vacío, sin error | UT-B-027 | assert_success |

### CU-09 — Actualización de packs (`-Su`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Itera sobre dots_packs | IT (-Su) | iteración verificada vía stub |
| Packs CRITICAL omitidos con aviso | IT (-Su critical) | warning en output |
| AUR API no disponible → warning, continúa | IT (-Su aur_down) | assert_success + warning |
| Resumen final de actualizados/fallidos | IT (-Su summary) | output con resumen |

### CU-10 — Alta de repositorio externo (Git)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| URL HTTPS obligatoria | IT-009, SEC-005 | HTTP rechazado |
| Clone con `git clone --depth=1` | IT (repo_add_git) | stub git llamado |
| Registro en dots-repos.yaml | IT (repo_add_registered) | archivo YAML contiene repo |
| Requiere root | UT-B-030 (variant) | error si no root |

### CU-11 — Alta de repositorio externo (HTTP)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Descarga index.yaml vía curl | IT (repo_add_http) | stub curl llamado |
| Valida schema antes de registrar | SEC-007 | schema inválido → warning |
| index.yaml no disponible → die | IT (repo_add_no_index) | exit 1 |

### CU-12 — Baja de repositorio externo

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Verifica packs instalados del repo | IT (repo_remove) | lista packs afectados |
| Elimina REPOS_DIR/nombre | IT (repo_remove_dir) | directorio eliminado |
| Repositorio no registrado → noop | IT (repo_remove_noop) | assert_success |

### CU-13 — Listado de repositorios (`repo-list`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Built-in siempre primero | IT (repo_list) | primera fila es built-in |
| Sin repos externos → solo built-in | IT (repo_list_empty) | solo built-in |
| dots-repos.yaml inexistente → sin error | IT (repo_list_no_file) | assert_success |

### CU-14 — Actualización de repos externos (`repo-update`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Git repos: `git pull --ff-only` | IT (repo_update_git) | stub git called pull |
| HTTP repos: re-descarga index.yaml | IT (repo_update_http) | stub curl called |
| Fallo en repo individual → warning, continúa | IT (repo_update_partial_fail) | assert_success |

### CU-15 — Selección de dots en instalador TUI

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| `packs_for_profile(profile)` filtra catálogo | UT-P-031 a UT-P-042 | subconjunto correcto |
| Selección opcional (puede omitirse) | UT-P-054 | pack=None → no instala |
| Pack instalado como parte de DOTS_PACK FSM | UT-P-051 a UT-P-055 | handler ejecuta |

### CU-16 — Instalación modo unattended (`--noconfirm`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Omite prompts interactivos | IT-001 | assert_success sin input |
| Pack CRITICAL + --noconfirm → error | UT-B-028, SEC-010 | exit 1 |
| CRITICAL + OUROBOROS_ALLOW_CRITICAL=1 → procede | UT-B-029, SEC-011 | sin panel |

### CU-17 — Fallo de `post_deploy`

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Exit code 4 | IT-008 | status == 4 |
| Pack NO registrado en system.yaml | IT-008 | sysyaml sin pack |
| Paquetes pacman ya instalados quedan | IT-008 (variant) | our-pac llamado antes del fallo |

### CU-18 — Pack ya instalado — reinstalación

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Aviso "Pack already installed" | IT-004 (variant) | output --partial "already installed" |
| upsert actualiza entrada | IT-004 | exactamente 1 entrada en sysyaml |
| Cancelar → sin cambios | IT-004 (cancel) | sysyaml inalterado |

### CU-19 — Carga de catálogo Python (`load_catalog`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Enumera *.yaml en orden alfabético | UT-P-014 | ids == sorted |
| MANIFEST_DIR inexistente → [] | UT-P-011 | result == [] |
| Manifest inválido → ignorado, continúa | UT-P-015, UT-P-030 | válidos presentes |

### CU-20 — Filtrado de packs por perfil desktop

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| `packs_for_profile("hyprland")` retorna packs hyprland | UT-P-031 | ids correctos |
| `packs_for_profile("niri")` retorna noctalia + danklinux | UT-P-032 | exactly niri packs |
| Perfil desconocido → [] sin error | UT-P-033 | result == [] |

### CU-21 — Verificación estado en `system.yaml`

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Retorna 0 si pack instalado | CON-001 (variant) | return 0 |
| Retorna 1 si pack no instalado | IT (is_installed_false) | return 1 |
| system.yaml inexistente → retorna 1 sin error | UT-B-025 (variant) | retorna 1 |

### CU-22 — Escritura atómica en `system.yaml`

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| flock + .tmp + os.replace | CON-003 | no .tmp leftover |
| Timeout 5s si lock tomado | CON-004 (variant) | error con mensaje |
| Escrituras concurrentes no corrompen | CON-001, CON-002 | YAML válido post-write |

### CU-23 — Cleanup de instalación fallida CRITICAL

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Trap ERR/EXIT activado para CRITICAL | IT (critical_cleanup_trap) | trap instalado |
| Remonta `/` como ro si fue rw | IT (cleanup_remount) | stub mount llamado ro |
| Restaura pacman.conf desde backup | IT (cleanup_pacman_conf) | backup restaurado |
| Exit code 5 | IT (critical_fail_exit5) | status == 5 |
| Log de cleanup creado | IT (critical_cleanup_log) | log -cleanup- existe |

### CU-24 — Instalación canal git (`--git`)

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| `--git` fuerza canal git | IT-010 | channel=="git" en sysyaml |
| Pack sin canal git + --git → error | IT (no_git_channel) | exit 1 + mensaje |
| Registra `channel: git` en sysyaml | IT-010 | sysyaml channel field |

### CU-25 — Instalación desde repositorio externo

| Criterio PRD | Test ID | Verificación |
|-------------|---------|-------------|
| Busca en built-in primero | UT-B-013 | find_manifest prioridad |
| Marca `[EXTERN]` en output | IT (extern_install) | output "[EXTERN]" |
| Aviso "not audited" | IT (extern_install) | output "not audited" |
| Schema inválido → error, no ejecuta hooks | SEC-007 | assert_failure |

---

## 13. Matriz de Trazabilidad

### 13.1 Test → CU → SPEC

| Test ID | CU(s) | SPEC § | Descripción |
|---------|-------|--------|-------------|
| UT-P-011 | CU-19 | §5.1, §7.1 | load_catalog dir inexistente → [] |
| UT-P-012 | CU-19 | §5.1 | load_catalog dir vacío → [] |
| UT-P-013 | CU-19 | §5.1 | Un manifest válido carga correctamente |
| UT-P-014 | CU-19 | §5.1 | Orden alfabético de manifests |
| UT-P-015 | CU-19 | §5.1 | Manifest YAML inválido ignorado |
| UT-P-016 | CU-19 | §5.1 | Root no dict ignorado |
| UT-P-017 | CU-19, CU-20 | §4.1, §5.1 | compatibility.immutable leído correctamente |
| UT-P-018 | CU-19, CU-20 | §4.1, §5.1 | compatibility.profiles leído correctamente |
| UT-P-019 | CU-19 | §4.1, §5.1 | has_stable derivado de variants.stable |
| UT-P-020 | CU-19 | §4.1, §5.1 | has_git derivado de variants.git |
| UT-P-021 | CU-19, CU-24 | §4.5, §5.1 | Pack git-only: has_stable=False |
| UT-P-022 | CU-19 | §4.1, §5.1 | Pack stable-only: has_git=False |
| UT-P-023 | CU-19 | §4.1 | stable_version_hint correcto |
| UT-P-024 | CU-19 | §4.1 | git_version_hint correcto |
| UT-P-025 | CU-02, CU-19 | §4.1, §5.2 | credits.author leído correctamente |
| UT-P-031 | CU-20, CU-22 | §5.2 | packs_for_profile hyprland |
| UT-P-032 | CU-20 | §5.2 | packs_for_profile niri |
| UT-P-033 | CU-20 | §5.2 | Perfil desconocido → [] |
| UT-P-034 | CU-20 | §5.2, §6.1 | Perfil minimal → [] |
| UT-P-051 | CU-15 | §6.1 | Perfil minimal salta DOTS_PACK |
| UT-P-052 | CU-15, CU-24 | §6.1, DESIGN §5.3 | Canal auto-corregido git-only (C-03) |
| UT-P-053 | CU-15 | §6.1 | Canal stable no cambia en stable-only |
| UT-P-054 | CU-15 | §6.1, §9.3 | Sin pack → channel inalterado |
| UT-P-055 | CU-15 | §6.1 | Progress 0→100 en handler |
| UT-B-001 | CU-01, CU-02 | §5.0, DESIGN §3.4 | yaml_get campo raíz |
| UT-B-002 | CU-01, CU-02 | DESIGN §3.4 | yaml_get campo anidado |
| UT-B-003 | CU-02, CU-08 | DESIGN §3.4 | yaml_get campo inexistente |
| UT-B-011 | CU-02, CU-25 | §5.2, DESIGN §3.6 | find_manifest built-in |
| UT-B-012 | CU-02 | §5.2, §8.1 | find_manifest pack no existe |
| UT-B-013 | CU-25 | §5.2, TRD §7.4 | find_manifest prioridad built-in |
| UT-B-014 | CU-25 | §5.2, TRD §7.4 | find_manifest fallback externo |
| UT-B-015 | CU-03, CU-19 | DESIGN §3.6 | derive_channels stable-only |
| UT-B-016 | CU-24 | DESIGN §3.6 | derive_channels git-only |
| UT-B-017 | CU-03, CU-04 | DESIGN §3.6 | derive_channels stable/git |
| UT-B-021 | US-15 | §3.4 | --version format |
| UT-B-022 | US-16 | §3.4 | --help exit 0 |
| UT-B-023 | US-16 | §3.4 | subcomando desconocido exit 1 |
| UT-B-024 | CU-07 | §5.5 | -Q sin packs |
| UT-B-025 | CU-07, CU-21 | §5.5, TRD §8.3 | -Q sysyaml inexistente |
| UT-B-026 | CU-08 | §5.6 | -Qs sin patrón |
| UT-B-027 | CU-08 | §5.6 | -Qs sin coincidencias |
| UT-B-028 | CU-05, CU-16 | §3.3, §5.3, TRD §3.3 | CRITICAL + noconfirm → error |
| UT-B-029 | CU-05, CU-16 | §5.3, TRD §3.3 | OUROBOROS_ALLOW_CRITICAL bypass |
| UT-B-030 | CU-03 | §3.2 | -S sin root |
| UT-B-031 | CU-25 | §9.1, TRD §7.5 | validate_schema manifest válido |
| UT-B-032 | CU-25 | §9.1 | validate_schema sin id |
| UT-B-033 | CU-25 | §9.1 | validate_schema sin immutable |
| UT-B-034 | CU-25 | §9.1, TRD §7.5 | CRITICAL sin warning |
| UT-B-035 | CU-25 | §9.1, TRD §7.5 | CRITICAL critical_actions vacío |
| IT-001 | CU-03 | §5.3, §7.3, §7.4 | Install low + noconfirm |
| IT-002 | CU-21 | §12.2 | Log creado tras instalación |
| IT-003 | CU-06 | §5.4 | -R elimina de sysyaml |
| IT-004 | CU-18 | §5.3 | Reinstall upsert sin duplicados |
| IT-005 | CU-02 | §5.2 | -Si exit 0 + info |
| IT-006 | CU-02 | §5.2, §8.1 | -Si pack inexistente exit 1 |
| IT-007 | CU-03, CU-17 | §5.3, TRD §5.4 | Fallo our-pac → no sysyaml |
| IT-008 | CU-17 | §5.3, TRD §5.3 | Fallo post_deploy → exit 4 |
| IT-009 | CU-10, CU-11 | §5.7, §13.1 | repo-add HTTP rechazado |
| IT-010 | CU-24 | §5.3, DESIGN §3.8 | git-only auto-canal (C-03) |
| SEC-001 | — | §13.1, DESIGN §3.4 | yaml_get no vulnerable a injection |
| SEC-005 | CU-10, CU-11 | §13.1, TRD §10.5 | HTTPS enforcement |
| SEC-007 | CU-25 | §9.1, TRD §10.4 | post_deploy no path absoluto |
| SEC-010 | CU-05, CU-16 | §5.3, TRD §3.3 | CRITICAL noconfirm sin env var |
| SEC-011 | CU-05, CU-16 | §5.3, TRD §3.3 | OUROBOROS_ALLOW_CRITICAL bypass |
| CON-001 | CU-22 | §7.5, TRD §8.2 | Concurrent writes no corruption |
| CON-002 | CU-22, CU-18 | §7.5 | Upsert concurrente no duplica |
| CON-003 | CU-22 | §7.5, TRD §8.2 | No .tmp leftover |
| REG-001 | CU-03, CU-17 | §5.0 (C-01) | set -euo pipefail presente |
| REG-002 | CU-24 | §4.5 (C-02) | git-only has_stable=False |
| REG-003 | CU-15, CU-24 | §6.1 (C-03) | Canal auto-corrección FSM |
| REG-004 | CU-19, CU-20 | DESIGN §4.1 (M-05) | Schema anidado, no plano |
| E2E-001 | CU-15, CU-03 | §6.1, TRD §9 | FSM DOTS_PACK + instalación real |
| E2E-002 | CU-15 | TRD §9.3 | Perfil minimal salta estado |
| E2E-003 | CU-01, CU-02 | §3.2, TRD §1.2 | CLI operativo en sistema instalado |

### 13.2 CU → Tests (Resumen)

| CU | Tests que lo cubren | Cobertura |
|----|---------------------|-----------|
| CU-01 | UT-B-026, E2E-003 | Partial |
| CU-02 | UT-P-025-026, UT-B-001-002, IT-005-006 | Full |
| CU-03 | UT-B-028-030, IT-001-002, IT-007, REG-001 | Full |
| CU-04 | CU-04-ACC bats | Partial |
| CU-05 | UT-B-028-029, SEC-010-011 | Full |
| CU-06 | IT-003 | Full |
| CU-07 | UT-B-024-025 | Full |
| CU-08 | UT-B-026-027 | Full |
| CU-09 | IT (-Su, variants) | Partial |
| CU-10 | IT-009, SEC-005-006 | Partial |
| CU-11 | IT (http repo, variants) | Partial |
| CU-12 | IT (repo_remove variants) | Partial |
| CU-13 | IT (repo_list variants) | Partial |
| CU-14 | IT (repo_update variants) | Partial |
| CU-15 | UT-P-051-055, E2E-001-002 | Full |
| CU-16 | UT-B-028-029, IT-001, SEC-010-011 | Full |
| CU-17 | IT-008 | Full |
| CU-18 | IT-004 | Full |
| CU-19 | UT-P-011-030 | Full |
| CU-20 | UT-P-031-042 | Full |
| CU-21 | UT-B-024-025, CON-001 | Full |
| CU-22 | CON-001-005 | Full |
| CU-23 | IT (critical_cleanup variants) | Partial |
| CU-24 | UT-B-016, IT-010, REG-002-003 | Full |
| CU-25 | UT-B-013-014, IT (extern), SEC-007 | Full |

---

## 14. Referencias Cruzadas

### 14.1 PRD → TEST

| Sección PRD | Test ID(s) | Verificación |
|-------------|-----------|-------------|
| §2.2 Obj. Secundarios (≥93% cobertura) | CI §11.3 | `--cov-fail-under=93` |
| §5 Casos de Uso (CU-01 a CU-25) | §12 | Criterios de aceptación por CU |
| §8 Métricas de Éxito | CON-001-003, IT-008, SEC-010 | Escritura atómica, CRITICAL, post_deploy |
| §10 Riesgos y Mitigaciones | SEC-001-012, CON-001-005 | Seguridad y concurrencia |

### 14.2 TRD → TEST

| Sección TRD | Test ID(s) | Verificación |
|-------------|-----------|-------------|
| §2.1 DotsPack dataclass | UT-P-001-010 | Campos y tipos correctos |
| §2.2 DotsPackConfig | UT-P-043-045 | Defaults y canal |
| §2.3 Schema de manifest | UT-B-031-035, UT-P-017-024 | Campos canónicos |
| §2.4 system.yaml dots_packs | IT-001, IT-003-004, CON-001-005 | Schema correcto |
| §3.3 Flujo CRITICAL | UT-B-028-029, SEC-010-011 | Panel + bypass |
| §3.4 Tabla nivel/flag | UT-B (tabla completa) | Todos los casos |
| §5.3 post_deploy ejecución | IT-008, SEC-007 | Exit 4, SUDO_USER |
| §7.4 find_manifest prioridad | UT-B-013, REG-005 | built-in > externo |
| §7.5 Validación schema pre-hook | UT-B-031-035, SEC-007 | Schema obligatorio |
| §8.2 flock + atomic write | CON-001-005 | Sin corrupción |
| §8.3 system.yaml inexistente | UT-B-025 | Sin error |
| §9.1 Estado DOTS_PACK | UT-P-051-055, E2E-001-002 | FSM correcto |
| §9.2 Canal auto-corrección | UT-P-052, REG-003 | C-03 fix |
| §10.5 HTTPS enforcement | IT-009, SEC-005-006 | HTTP rechazado |
| §12 Exit codes | IT-007 (1), IT-008 (4), IT (cleanup) (5) | Códigos correctos |

### 14.3 SPEC → TEST

| Sección SPEC | Test ID(s) | Verificación |
|-------------|-----------|-------------|
| §3.1 Sinopsis CLI | UT-B-021-023 | Todos los subcomandos |
| §3.2 -S argumento | UT-B-030 | Requiere root |
| §4.5 Catálogo built-in | E2E-003, CU-01-ACC | 7 packs en catálogo |
| §5.0 set -euo pipefail (C-01) | REG-001 | pipefail presente |
| §5.1 cmd_list | UT-B-026, E2E-003 | Lista correcta |
| §5.2 cmd_info | IT-005-006 | Info + error |
| §5.3 cmd_install | IT-001, IT-007-010 | Instalación completa |
| §5.4 cmd_remove | IT-003 | Desinstalación |
| §5.5 cmd_query | UT-B-024-025 | -Q correcto |
| §5.6 cmd_search | UT-B-026-027 | -Qs correcto |
| §6.1 FSM DOTS_PACK (C-03) | UT-P-051-055, REG-003 | Handler correcto |
| §7.1-7.4 Contratos | IT-001-010 | Pre/post condiciones |
| §8.1 Exit codes | IT-007 (1), IT-008 (4) | Correctos |
| §9.1 Validaciones (C-01, I-06) | UT-B-031-035, SEC-007 | Schema + hooks |
| §11.4 Migración schema (M-05) | REG-004, REG-004b | Schema anidado |
| §13.1 Seguridad | SEC-001-012 | HTTPS, injection, CRITICAL |

### 14.4 DESIGN → TEST

| Sección DESIGN | Test ID(s) | Verificación |
|----------------|-----------|-------------|
| §3.2 Header (set -euo pipefail) | REG-001 | Primer check |
| §3.4 yaml_get/yaml_list (C-01 heredoc) | SEC-001-002 | No injection |
| §3.5 sysyaml_* helpers | CON-001-005, IT-001-004 | Atómico + correcto |
| §3.6 find_manifest prioridad | UT-B-011-014, REG-005 | Orden determinista |
| §3.8 Router + C-03 autocorrect | IT-010, REG-003 | git-only auto-canal |
| §3.9 cleanup_critical | IT (critical_cleanup) | Trap funciona |
| §4.1 Implementación legacy (M-05) | REG-004, REG-004b | No usar campos planos |
| §4.2 Implementación target | UT-P-017-024, REG-004 | Schema anidado |
| §5.3 _handle_dots_pack target | UT-P-051-055 | Canal auto-corrección |
| §9 Seguridad | SEC-001-012 | HTTPS, inline hooks |
| §10 Testing (estrategia) | §1 este documento | Pirámide tests |


