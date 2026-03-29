# tests/

## OVERVIEW
Docker-based test infrastructure. All CI tests run in Arch Linux container from tests/Dockerfile.

## STRUCTURE
```
tests/
├── scripts/           # Test runner scripts
├── Dockerfile         # Arch Linux test image
├── docker-compose.yml # Orchestrates test suites
├── run-local.sh       # Local entry point
└── README.md          # Test suite overview
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Shell validation | `scripts/test-shellcheck.sh` | `shellcheck -S style` + `set -euo pipefail` |
| Script validation | `scripts/validate-scripts.sh` | Executability, flags, `--help` |
| Build dry-run | `scripts/test-build-dry-run.sh` | Mocked `mkarchiso` |
| Python lint | `scripts/lint-python.sh` | Ruff: E,W,F,I,UP,ANN001,ANN201,E722 |
| Unit tests | `scripts/run-pytest.sh` | `src/installer/tests/`, 70% coverage gate |
| Profile smoke | `scripts/smoke-test.sh` | Profile structure, architecture compliance |

## TEST SUITES
- **shellcheck-suite**: Validates all `.sh` files.
- **validate-scripts**: Checks executability and `--help` output.
- **dry-run-build**: Tests `build-iso.sh` with mocked tools.
- **python-lint**: Runs Ruff on Python source.
- **pytest-suite**: Executes unit tests with coverage.
- **smoke-test**: Verifies profile and architecture.
- **full-suite**: Runs all tests sequentially.

## CONVENTIONS
- 70% coverage gate for Python tests.
- `shellcheck -S style` required for all scripts.
- All scripts must have `set -euo pipefail`.
- No `pyproject.toml`, `pytest.ini`, or `conftest.py`.
- Test configuration lives in `scripts/`.

## ANTI-PATTERNS
- No skipping `shellcheck`.
- No reducing coverage gate.
- No hardcoded paths in test scripts.
- No `root` user in `Dockerfile` (use `testrunner`).
