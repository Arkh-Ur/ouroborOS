# Creating a new our-tool repo

## Prerequisites

- `gh` CLI authenticated as Arkh-Ur
- The tool binary exists in `src/ouroborOS-profile/airootfs/usr/local/bin/`
- `MIRROR_TOKEN` secret: a GitHub PAT with `repo` scope on the public org

---

## Variables to set before running

```bash
TOOL=our-pac                    # exact binary name
DESC="Safe package manager for ouroborOS (immutable root wrapper)"
VERSION=0.1.0                   # initial version
DEPS="'btrfs-progs' 'systemd'"  # pacman depends= array entries
OPTDEPS=""                      # leave empty if none
```

---

## Steps

### 1. Create private dev repo

```bash
gh repo create "Arkh-Ur/${TOOL}-dev" \
  --private \
  --description "${DESC} [dev]" \
  --clone
cd "${TOOL}-dev"
```

### 2. Scaffold directory structure

```bash
mkdir -p bin lib completions man tests/bats tests/e2e .github/workflows

# Copy main binary from monorepo
cp "${OLDPWD}/src/ouroborOS-profile/airootfs/usr/local/bin/${TOOL}" bin/

# Copy shared lib if needed (our-pac, our-snapshot, our-rollback)
# cp "${OLDPWD}/src/ouroborOS-profile/airootfs/usr/local/lib/ouroboros/snapshot.sh" lib/

# Copy CI templates
cp "${OLDPWD}/docs/our-tools-template/.github/workflows/test.yml"    .github/workflows/
cp "${OLDPWD}/docs/our-tools-template/.github/workflows/release.yml" .github/workflows/
cp "${OLDPWD}/docs/our-tools-template/PKGBUILD" .
```

### 3. Fill in PKGBUILD placeholders

```bash
sed -i \
  -e "s/OUR_TOOL_NAME/${TOOL}/g" \
  -e "s/OUR_TOOL_DESC/${DESC}/" \
  -e "s/OUR_TOOL_DEPS/${DEPS}/" \
  -e "s/OUR_TOOL_OPTDEPS/${OPTDEPS}/" \
  PKGBUILD
```

### 4. Create public mirror repo (empty, no README)

```bash
gh repo create "Arkh-Ur/${TOOL}" \
  --public \
  --description "${DESC}"
```

### 5. Add MIRROR_TOKEN secret to dev repo

```bash
gh secret set MIRROR_TOKEN \
  --repo "Arkh-Ur/${TOOL}-dev" \
  --body "<your-PAT-here>"
```

### 6. Initial commit and push

```bash
git add .
git commit -m "feat(${TOOL}): initial standalone repo"
git push -u origin main
```

### 7. Tag v0.1.0 to trigger first release

```bash
git tag v${VERSION}
git push origin v${VERSION}
```

---

## Consuming the tool in ouroborOS-dev

Option A — **git submodule** (source always in sync):
```bash
# In ouroborOS-dev root:
git submodule add "https://github.com/Arkh-Ur/${TOOL}-dev" \
  "tools/${TOOL}"
```

Option B — **pacman package** (ISO build installs the .pkg.tar.zst):
```bash
# In build-iso.sh, add to the package cache step:
curl -L "https://github.com/Arkh-Ur/${TOOL}-dev/releases/latest/download/${TOOL}-*.pkg.tar.zst" \
  -o "out/cache/${TOOL}.pkg.tar.zst"
```

---

## Dependency order (always create dependencies first)

```
ouroboros-libs  ← snapshot.sh (shared lib)
    │
    ├── our-snapshot
    ├── our-pac       ← our-rollback, our-aur, our-flat, our-dots, our-container
    └── our-rollback
```
