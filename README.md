# ouroborOS

ouroborOS is an ArchLinux-based Linux distribution focused on simplicity, modularity, and continuous self-improvement — much like the ouroboros symbol it takes its name from.

## About
- **Base:** ArchLinux
- **Philosophy:** Rolling release, minimal bloat, user-centric design
- **Status:** Phase 3 complete - Installer and basic system functionality working

## Key Features

### Installer
- **Finite State Machine (FSM)** based installer with state persistence
- **Checkpoint system** for resumable installations
- **Automated configuration** via embedded YAML
- **Progress tracking** with global installation progress bar
- **Secure password handling** with SHA-512 crypt hashing
- **Btrfs snapshot support** for system upgrades

### System Design
- **Immutable root filesystem** with read-only root subvolume
- **systemd-boot** bootloader (no GRUB)
- **systemd-networkd + iwd** for networking (no NetworkManager)
- **zram swap** for memory efficiency
- **UUID-based device addressing** (no hardcoded /dev/sdX paths)

## Recent Improvements

### Critical Fixes
- ✅ **fstab regeneration**: Proper fstab restoration after pacstrap
- ✅ **systemd-firstboot masking**: Prevents interactive firstboot prompts
- ✅ **machine-id setup**: Ensures clean first boot behavior
- ✅ **fstab copy optimization**: Temp mount strategy to avoid "target busy" errors
- ✅ **journal log access socket**: Resolved subvolumen @var issues

### Testing Infrastructure
- ✅ **115/115 unit tests passing**
- ✅ **Automated E2E test loop**: Build → Install → Boot verification
- ✅ **Docker-based CI testing**: Full test suite automation
- ✅ **Shell syntax validation**: All scripts pass shellcheck

## Getting Started

### Build the ISO
```bash
# Setup development environment (host Arch Linux)
bash src/scripts/setup-dev-env.sh

# Build the ISO
sudo bash src/scripts/build-iso.sh --clean
```

### Flash to USB
```bash
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso
```

### Test in QEMU
```bash
qemu-system-x86_64 -enable-kvm -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso -boot d
```

### Run Tests
```bash
# Unit tests
pytest src/installer/tests/ -v

# CI test suite (Docker)
docker-compose -f tests/docker-compose.yml run --rm full-suite
```

## Project Structure

```
ouroborOS/
├── src/
│   ├── installer/         # Python FSM installer + Bash ops
│   ├── scripts/           # Build, flash, dev-env scripts
│   └── ouroborOS-profile/ # archiso profile (airootfs, efiboot, packages)
├── docs/                  # Architecture, build, installer documentation
├── tests/                 # Docker-based test infrastructure
└── agents/                # Agent role definitions
```

## Contributing

Contributions are welcome. Please open an issue or pull request to get started.

## License

To be defined.