# Creating a new our-tool repo

## Prerequisites

- `gh` CLI authenticated as Arkh-Ur
- The tool binary exists in `src/ouroborOS-profile/airootfs/usr/local/bin/`
- Secrets configured on the private dev repo (see Secrets table below)

### Required secrets

| Secret | Minimum scope | Where to set |
|--------|---------------|--------------|
| `MIRROR_TOKEN` | Fine-grained PAT — `Contents: Read and write` on `Arkh-Ur/<tool>` ONLY | Private dev repo (`<tool>-dev`) |
| `MONOREPO_DISPATCH_TOKEN` | Fine-grained PAT — `Contents: Read and write` on `Arkh-Ur/ouroborOS-dev` ONLY | Private dev repo (`<tool>-dev`) |
| `TOOLS_READ_TOKEN` | Fine-grained PAT — `Contents: Read` on each `Arkh-Ur/<tool>-dev` repo | `ouroborOS-dev` monorepo |

> **Do NOT use classic PATs with `repo` scope.** Fine-grained PATs with the minimum listed
> permissions above are required to limit blast radius if a token is compromised.

> **S3 note:** The monorepo's `tools-sync.yml` MUST create its PR using
> `MONOREPO_DISPATCH_TOKEN` (a PAT), NOT `GITHUB_TOKEN`. GitHub does not trigger CI
> checks on PRs opened by `GITHUB_TOKEN`.

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

> **sed delimiter warning:** `DESC` must not contain `/` or `&` — those characters
> break the `s/…/…/` substitution. If your description contains slashes, use a
> different delimiter: `s|OUR_TOOL_DESC|${DESC}|` (pipe) or escape manually.

### 4. Create public mirror repo (empty, no README)

```bash
gh repo create "Arkh-Ur/${TOOL}" \
  --public \
  --description "${DESC}"
```

### 5. Add secrets to dev repo

```bash
gh secret set MIRROR_TOKEN \
  --repo "Arkh-Ur/${TOOL}-dev" \
  --body "<fine-grained PAT — Contents R/W on Arkh-Ur/${TOOL} only>"

gh secret set MONOREPO_DISPATCH_TOKEN \
  --repo "Arkh-Ur/${TOOL}-dev" \
  --body "<fine-grained PAT — Contents R/W on Arkh-Ur/ouroborOS-dev only>"
```

### 6. Initial commit and push

Before the first push, ensure `bin/${TOOL}` handles `--version` and outputs a
`MAJOR.MINOR` version string. The smoke test in `test.yml` requires this.

```bash
git add .
git commit -m "feat(${TOOL}): initial standalone repo"
git push -u origin main
```

### 7. Tag v0.1.0 to trigger first release

```bash
git tag "v${VERSION}"
git push origin "v${VERSION}"
```

---

## How the release pipeline works

The release pipeline (`release.yml`) has 4 jobs:

```
test → release-private → mirror-public → notify-monorepo
```

1. **test** — runs the full test suite (lint + bats + smoke).
2. **release-private** — attaches the raw binary (`bin/${TOOL}`) and a sha256sum
   file as GitHub Release artifacts on the private repo. No `.pkg.tar.zst` is built —
   the ouroborOS ISO pipeline does not use pacman packages.
3. **mirror-public** — pushes ONLY the tag ref (NOT branch history) to the public
   repo and creates a matching release there.
4. **notify-monorepo** — sends a `repository_dispatch` event to `ouroborOS-dev`
   with the tool name and commit SHA.

> **PKGBUILD note:** The PKGBUILD is provided for users who install the tool on a
> standard Arch system. It is NOT used by the ouroborOS ISO build pipeline.

---

## Consuming the tool in ouroborOS-dev

The monorepo uses a **raw binary sync model** via `sync-tools.sh`. When the monorepo
receives the `tool-updated` dispatch, `tools-sync.yml`:

1. Receives `tool` name and `commit_sha` from the dispatch payload.
2. Fetches the binary by commit SHA using the GitHub Contents API (not raw URL —
   `raw.githubusercontent.com` returns 404 for private repos):

```bash
# TOOLS_READ_TOKEN: fine-grained PAT with Contents:Read on Arkh-Ur/<tool>-dev.
# Do NOT use GITHUB_TOKEN here — it is scoped to ouroborOS-dev only and will
# receive 403 when fetching a different private repo.
curl -fsSL \
  -H "Authorization: Bearer ${TOOLS_READ_TOKEN}" \
  -H "Accept: application/vnd.github.raw+json" \
  "https://api.github.com/repos/Arkh-Ur/${TOOL}-dev/contents/bin/${TOOL}?ref=${COMMIT_SHA}"
```

> **Contents API size limit:** This API returns raw content only for files ≤ 1 MB.
> Tool binaries are Bash scripts and will never hit this limit, but use the Git
> Blobs API for larger assets.

3. **Computes sha256 locally** — never trusts a hash received in a dispatch payload.
4. Updates `src/ouroborOS-profile/airootfs/usr/local/bin/${TOOL}` with the fetched binary.
5. Records the pinned commit SHA in the manifest (immutable pointer — not a mutable tag).
6. Opens a PR using `MONOREPO_DISPATCH_TOKEN` so that CI checks are triggered.

> **Supply-chain integrity:** The monorepo always pins by commit SHA
> (`${{ github.sha }}`), not by tag name. Git tags are mutable and can be
> force-pushed. Pinning by SHA guarantees the exact binary version.

> **git identity in tools-sync.yml:** The monorepo workflow must configure git
> identity before committing:
> ```bash
> git config user.email "ci@ouroborOS.dev"
> git config user.name "ouroborOS CI"
> ```

---

## Dependency order (always create dependencies first)

```
ouroboros-libs-dev  ← snapshot.sh, other shared lib files
    │
    ├── our-snapshot-dev
    ├── our-pac-dev       ← our-rollback, our-aur, our-flat, our-dots, our-container
    └── our-rollback-dev
```

> **ouroboros-libs-dev dispatch:** `ouroboros-libs-dev` must include a
> `notify-monorepo` job in its own `release.yml`, dispatching
> `event_type: lib-updated` with `lib_path: lib/snapshot.sh` (or whichever lib
> changed) and `commit_sha`. The monorepo manifest has separate entries for lib
> files under `libs.*` and tool files under `tools.*` — `tools-sync.yml` must
> handle both dispatch event types.

> **src/scripts/ path:** Helper scripts referenced in the monorepo (e.g., the
> manifest updater) live at `src/scripts/update-manifest.py`, not `scripts/`.
