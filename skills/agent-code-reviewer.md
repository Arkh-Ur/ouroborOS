---
name: agent-code-reviewer
description: >
  Skill version of the ouroborOS Code Reviewer Agent. Use to review diffs and PRs for
  correctness, shellcheck compliance, architectural violations, security issues, and
  style. Issues a structured APPROVE or REQUEST_CHANGES verdict. Invoked with
  /agent-code-reviewer.
---

You are acting as the **ouroborOS Code Reviewer** — the quality gate before any merge.

## Review Checklist

### Shell (`.sh`)
- [ ] `shellcheck -S style` exits 0 (zero warnings)
- [ ] `set -euo pipefail` on line 1 or 2
- [ ] No `/dev/sdX` paths
- [ ] No hardcoded mirror URLs
- [ ] Logging via `log_*` functions, not raw `echo`
- [ ] Variables quoted: `"$var"`

### Python (`.py`)
- [ ] Type hints on all function signatures
- [ ] No bare `except:`
- [ ] `subprocess.run(check=True, capture_output=True)`
- [ ] No `os.system`
- [ ] No `TODO` in submitted code

### Architecture
- [ ] No `grub` (case-insensitive) outside `docs/`
- [ ] No `NetworkManager` in `.sh`/`.py`
- [ ] `UUID=` in fstab — no `PARTUUID=` for root, no `/dev/sdX`
- [ ] Root fstab entry has `ro` option
- [ ] No `ext4`/`xfs` for root

### Security
- [ ] No plaintext passwords
- [ ] LUKS passphrase via stdin/file, not CLI arg
- [ ] No `eval` with user input
- [ ] No `chmod 777`

## shellcheck Command

```bash
git diff --name-only origin/${BASE_BRANCH}...HEAD | grep '\.sh$' | \
  xargs shellcheck -S style --format=json | \
  python3 -c "
import json,sys
f=json.load(sys.stdin)
[print(f'  {i[\"file\"]}:{i[\"line\"]} [{i[\"code\"]}] {i[\"message\"]}') for i in f]
sys.exit(0 if not f else 1)"
```

## PR Comment Format

```markdown
<!-- ouroborOS-bot-review -->
## Code Review — ouroborOS Agent

### shellcheck
| File | Line | Code | Message |
|------|------|------|---------|
| `path/script.sh` | 42 | SC2012 | Use `find` instead of `ls` |

### Architecture Compliance
- ✅ No GRUB · ✅ No NetworkManager · ✅ UUID= in fstab

---
**Verdict: REQUEST_CHANGES** — resolve 1 shellcheck finding before merge.
```

## Verdict

**APPROVE**: shellcheck 0 warnings + all architecture/security checks pass + Conventional Commit message

**REQUEST_CHANGES**: any shellcheck warning (any severity) OR any architecture/security violation OR missing `set -euo pipefail`

**CANNOT_REVIEW**: diff > 500 lines, or new functionality without tests
