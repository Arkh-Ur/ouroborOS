# ouroborOS — Test Suite

All tests run inside an ArchLinux Docker container defined in `tests/Dockerfile`. This ensures the test environment matches the target platform (ArchLinux) and avoids host-specific differences in tool versions.

---

## Quick Start

```bash
# Run all suites
docker compose -f tests/docker-compose.yml run --rm full-suite

# Run a specific suite
docker compose -f tests/docker-compose.yml run --rm shellcheck-suite
docker compose -f tests/docker-compose.yml run --rm validate-scripts
docker compose -f tests/docker-compose.yml run --rm dry-run-build
docker compose -f tests/docker-compose.yml run --rm python-lint
docker compose -f tests/docker-compose.yml run --rm pytest-suite
docker compose -f tests/docker-compose.yml run --rm smoke-test
```

---

## Test Suites

| Suite | Script | What it validates |
|-------|--------|------------------|
| `shellcheck-suite` | `scripts/test-shellcheck.sh` | shellcheck -S style on all `.sh` + `set -euo pipefail` guard |
| `validate-scripts` | `scripts/validate-scripts.sh` | Script permissions, required flags, function definitions, `--help` |
| `dry-run-build` | `scripts/test-build-dry-run.sh` | `build-iso.sh` control flow with mocked `mkarchiso` |
| `python-lint` | `scripts/lint-python.sh` | ruff check on all `.py` files (no-op if none exist) |
| `pytest-suite` | `scripts/run-pytest.sh` | pytest + 70% coverage gate (no-op if `installer/` absent) |
| `smoke-test` | `scripts/smoke-test.sh` | archiso profile structure (no-op if `ouroborOS-profile/` absent) |

---

## Container Limitations

These tests **cannot** run inside Docker containers due to kernel/device requirements:

| Test | Reason | When available |
|------|--------|----------------|
| Full ISO build (`mkarchiso`) | Requires loop devices (`/dev/loop*`) | Phase 5 — QEMU integration |
| Btrfs subvolume creation | Requires Btrfs kernel module + block device | Phase 5 |
| LUKS encryption (`cryptsetup`) | Requires root + `/dev/mapper` | Phase 5 |
| QEMU boot test | Requires KVM module | Phase 5 |

---

## Debugging a Failed Test

```bash
# Drop into an interactive shell in the exact test container
docker run --rm -it \
  -v "$(pwd)":/workspace:ro \
  $(docker compose -f tests/docker-compose.yml config | grep image | head -1 | awk '{print $2}') \
  bash

# Or build and run manually
docker build -t ouroborOS-test tests/
docker run --rm -it -v "$(pwd)":/workspace:ro ouroborOS-test bash

# Inside the container:
bash /workspace/tests/scripts/test-shellcheck.sh
shellcheck -S style /workspace/docs/scripts/build-iso.sh
```

---

## CI Integration

Tests run automatically via GitHub Actions:

| Workflow | Trigger | What runs |
|----------|---------|-----------|
| `lint.yml` | Every push | shellcheck + python lint (fast, < 2 min) |
| `test.yml` | Push to `dev`, PRs | Full container test suite |
| `code-review.yml` | PRs to `dev`/`master` | shellcheck on changed files + architecture check |

---

## Phase Gating

Some suites exit 0 with an informational message when their subject does not exist yet:

| Suite | Condition for skip |
|-------|--------------------|
| `pytest-suite` | `installer/` directory does not exist |
| `smoke-test` | `ouroborOS-profile/` directory does not exist |
| `python-lint` | No `.py` files in repository |

This allows CI to stay green in Phase 1 while the relevant components are being built.
