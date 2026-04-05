# ISO Build Process and Test Automation

## Overview

This document describes the automated build and testing infrastructure for ouroborOS, including ISO generation, testing, and quality assurance processes.

## ISO Build Process

### Prerequisites

- Arch Linux host system
- Required dependencies (installed via `setup-dev-env.sh`)
- Docker for testing infrastructure
- QEMU for virtual machine testing

### Build Steps

1. **Setup Development Environment**
   ```bash
   bash src/scripts/setup-dev-env.sh
   ```

2. **Clean Build**
   ```bash
   sudo bash src/scripts/build-iso.sh --clean
   ```

3. **Build Output**
   - ISO file: `out/ouroborOS-0.1.0-x86_64.iso`
   - Build artifacts: `src/temp/` directory

### Build Scripts

#### `build-iso.sh`
Main build script that orchestrates the ISO creation process:
- Cleans previous builds
- Sets up the archiso environment
- Builds the ISO using `mkarchiso`
- Validates the output

#### `flash-usb.sh`
Secure USB flashing utility:
- Verifies target device
- Uses `dd` with progress monitoring
- Includes safety checks

## Test Automation

### Unit Testing

#### Python Tests
- Location: `src/installer/tests/`
- Framework: pytest
- Coverage: 115/115 tests passing
- Validation: Type checking with Ruff

#### Shell Script Testing
- Location: `tests/scripts/`
- Tool: shellcheck
- Validation: All scripts pass with zero warnings

### Integration Testing

#### Docker-based CI
- File: `tests/docker-compose.yml`
- Suites:
  - `shellcheck-suite`: Shell syntax validation
  - `pytest-suite`: Python unit tests
  - `smoke-test`: End-to-end installation test

#### E2E Test Loop
Automated test cycle that:
1. Builds the ISO
2. Creates a test disk image
3. Runs QEMU installation
4. Verifies system boot
5. Collects logs
6. Reports results

### Running Tests

```bash
# Run all tests
docker-compose -f tests/docker-compose.yml run --rm full-suite

# Individual test suites
docker-compose -f tests/docker-compose.yml run --rm shellcheck-suite
docker-compose -f tests/docker-compose.yml run --rm pytest-suite
docker-compose -f tests/docker-compose.yml run --rm smoke-test
```

## Quality Assurance

### Linting
- Python: Ruff (E,W,F,I,UP,ANN001,ANN201,E722)
- Shell: shellcheck (zero warnings required)

### Code Coverage
- Minimum 70% test coverage enforced
- Coverage reports generated during testing

### Build Verification
- ISO validation after each build
- Boot verification in QEMU
- System integrity checks

## Troubleshooting

### Common Issues

#### Build Failures
- Check dependencies: `setup-dev-env.sh`
- Verify archiso installation
- Check disk space and permissions

#### Test Failures
- Review test logs in `src/logs/`
- Check Docker container logs
- Verify test disk image integrity

#### Boot Issues
- Check QEMU parameters
- Verify ISO integrity
- Review system logs for errors

## Automation Workflow

### CI Pipeline (GitHub Actions)
- Linting and testing on every push
- Build verification
- Documentation updates

### Development Workflow
1. Make changes to source code
2. Run local tests
3. Build ISO
4. Test in QEMU
5. Commit and push
6. CI runs full test suite
7. Create pull request

## Best Practices

- Always run tests before committing
- Keep ISO build artifacts in `out/` directory
- Maintain test coverage above 70%
- Follow Conventional Commits for commits
- Document any changes to build/test processes

## Future Improvements

- Enhanced test coverage for edge cases
- Automated benchmarking
- Performance testing
- Security scanning
- Package validation

## Contact

For issues with the build process or testing infrastructure, please open an issue in the repository.