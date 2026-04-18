# CI Dev-First Alignment — Plan de Implementación

**Versión:** 3.0 (final)
**Fecha:** 2026-04-17
**Branch de trabajo:** dev

---

## Flujo objetivo

```
1. PUSH a dev        →  Solo dev, nada más
2. CI corre          →  lint + test + build
3. Si todo verde ✅   →  Se puede taggear
4. Tag v* en dev     →  Release job: ISO + prerelease (privado) + merge a origin/main (privado)
5. origin/main       →  Mirror automático a repo público + GitHub Release
```

**Nada se mueve sin verde. Nada toca main sin tag. Nada es público sin pasar por privado primero.**

Ver skill `ci-dev-first` para diagramas Mermaid completos.

---

## Estado actual vs deseado

| # | Regla | Actual | Deseado | Archivo |
|---|-------|--------|---------|---------|
| 1 | CI solo desde dev | `build.yml` dispara en dev Y main | Solo dev | `build.yml` |
| 2 | PRs contra dev | `build.yml` PRs contra main | Solo dev | `build.yml` |
| 3 | lint solo dev | `lint.yml` en `["**"]` | Solo dev | `lint.yml` |
| 4 | Sin master | 3 workflows usan `master` | Solo dev | `lint/test/code-review.yml` |
| 5 | Prerelease privado primero | Va directo al público | Privado → público | `build.yml` |
| 6 | Merge tag → origin/main | No existe | Release job lo hace | `build.yml` |
| 7 | Mirror privado → público | Push directo | Mirror después de merge | `build.yml` |
| 8 | Protección local main | Hook instalado ✅ | — | `.git/hooks/pre-push` |

---

## Paso 1 — Fix lint.yml

**Antes:**
```yaml
on:
  push:
    branches: ["**"]
  pull_request:
    branches: [dev, master]
```

**Después:**
```yaml
on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev]
```

---

## Paso 2 — Fix test.yml

**Antes:**
```yaml
on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev, master]
```

**Después:**
```yaml
on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev]
```

---

## Paso 3 — Fix code-review.yml

**Antes:**
```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
    branches: [dev, master]
```

**Después:**
```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
    branches: [dev]
```

---

## Paso 4 — Fix build.yml (el más complejo)

### 4a. Triggers

**Antes:**
```yaml
on:
  push:
    branches: [dev, main]
    tags: ["v*"]
  pull_request:
    branches: [main]
```

**Después:**
```yaml
on:
  push:
    branches: [dev]
    tags: ["v*"]
  pull_request:
    branches: [dev]
```

### 4b. Release job — Nueva secuencia

El release job actual hace:
1. Build ISO
2. Push directo a ouroborOS (público)
3. GitHub Release en público

Debe hacer:
1. Build ISO
2. **Prerelease en ouroborOS-dev (privado)** — NUEVO
3. **Merge tag → origin/main (privado)** — NUEVO
4. **Mirror origin/main → ouroborOS (público)** — reemplaza push directo
5. GitHub Release en público

### 4c. Steps nuevos del release job

Agregar después de "Verify ISO size":

```yaml
      - name: Create prerelease in private repo
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          TAG="${{ github.ref_name }}"
          ISO=$(ls out/ouroborOS-*.iso | head -n 1)
          CHECKSUM="out/ouroborOS-SHA256SUMS.txt"
          if gh release view "$TAG" --repo Arkh-Ur/ouroborOS-dev >/dev/null 2>&1; then
            gh release delete "$TAG" --repo Arkh-Ur/ouroborOS-dev --yes --cleanup-tag 2>/dev/null || true
          fi
          gh release create "$TAG" \
            --repo Arkh-Ur/ouroborOS-dev \
            --title "ouroborOS ${TAG} (Alpha)" \
            --prerelease \
            --notes "Pre-release build from tag ${TAG}. Mirror to public repo follows." \
            "$ISO" \
            "$CHECKSUM"

      - name: Merge tag to origin/main (private)
        run: |
          git config --global --add safe.directory '*'
          git config --global user.name "ouroborOS CI"
          git config --global user.email "ci@ouroboros.dev"
          git checkout main
          git merge --ff-only "$GITHUB_SHA" || git merge --no-ff "$GITHUB_SHA" -m "release: merge tag ${{ github.ref_name }} to main"
          git push origin main
```

Los steps existentes de "Push main and tag to public repo" y "Create or update GitHub Release in public repo" se mantienen pero ahora ejecutan DESPUÉS del merge privado.

---

## Paso 5 — Fix CLAUDE.md

Ya aplicado. Cambios:
- `Status: v0.5.0 — Phase 5 in progress`
- Branch Strategy → dev-first con reglas claras
- Dual-Repo → flujo prerelease privado → mirror público
- Pre-push hook requirement

---

## Paso 6 — Verificar

```bash
# 1. Push a dev (debe disparar CI solo en dev)
git push origin dev

# 2. Verificar que NO hay workflows corriendo en main
gh run list --repo Arkh-Ur/ouroborOS-dev --limit 5

# 3. Verificar que el hook bloquea push a main
# (simular — no ejecutar realmente)
echo "refs/heads/main abc123 refs/heads/main abc123" | bash .git/hooks/pre-push

# 4. Cuando CI esté verde, probar release:
git tag v0.5.X
git push origin v0.5.X

# 5. Verificar prerelease en privado
gh release view v0.5.X --repo Arkh-Ur/ouroborOS-dev

# 6. Verificar mirror en público
gh release view v0.5.X --repo Arkh-Ur/ouroborOS
```

---

## Orden de ejecución

1. `lint.yml` → `test.yml` → `code-review.yml` → `build.yml` (en un solo commit)
2. `CLAUDE.md` (ya aplicado, incluir en el mismo commit)
3. Push a `dev`
4. Verificar CI verde
5. Probar release con tag
