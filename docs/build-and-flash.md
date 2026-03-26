# ouroborOS — Build & Flash Guide

How to build the ouroborOS ISO from source and write it to a bootable USB drive.

---

## Requirements

### Host machine

`mkarchiso` — the tool used to build the ISO — only runs on **ArchLinux**.
You have three options:

| Option | Notes |
|--------|-------|
| ArchLinux nativo | Recommended. Fastest build times. |
| VM ArchLinux | VirtualBox, QEMU, VMware — any hypervisor works. Allocate ≥ 15 GB disk and 4 GB RAM. |
| Contenedor Docker (privilegiado) | Requires `--privileged` and loop device access. Useful for CI. |

### Required packages (install once)

```bash
sudo pacman -S --needed archiso squashfs-tools libisoburn dosfstools git
```

### Disk space

| Component | Approximate size |
|-----------|-----------------|
| Build working directory | ~6–8 GB |
| Output ISO | ~400–700 MB |
| Total free space needed | **10 GB minimum** |

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/Arkhur-Vo/ouroborOS.git
cd ouroborOS
git checkout dev
```

---

## Step 2 — Set up the development environment

Installs all build dependencies and validates the environment:

```bash
bash src/scripts/setup-dev-env.sh
```

What it does:
- Installs `archiso`, `mkarchiso`, `shellcheck`, QEMU, Python dependencies
- Adds your user to the `kvm` group (for hardware-accelerated QEMU)
- Validates all scripts with `shellcheck`

---

## Step 3 — Build the ISO

```bash
sudo bash src/scripts/build-iso.sh --clean
```

Options:

| Flag | Description |
|------|-------------|
| `--clean` | Remove previous build artifacts before starting (recommended) |
| `--output DIR` | Where to write the ISO (default: `./out/`) |
| `--workdir DIR` | Build working directory (default: `/tmp/ouroborOS-build`) |
| `--sign` | GPG-sign the ISO after build |

Expected output (last few lines):

```
── Build Summary ──────────────────────────────
  ISO:      /path/to/ouroborOS/out/ouroborOS-202601-x86_64.iso
  Size:     512M
  SHA256:   a1b2c3d4...
  Duration: 480s

[OK]    ouroborOS ISO ready.

Test with QEMU:
  qemu-system-x86_64 -enable-kvm -m 2048 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
    -cdrom "out/ouroborOS-202601-x86_64.iso" -boot d
```

The ISO and its SHA256 checksum appear in `out/`:

```
out/
├── ouroborOS-202601-x86_64.iso
└── ouroborOS-202601-x86_64.iso.sha256
```

---

## Step 4 — Verify the checksum

```bash
cd out/
sha256sum --check ouroborOS-*.iso.sha256
```

Expected output:

```
ouroborOS-202601-x86_64.iso: OK
```

---

## Step 5 — Test in QEMU (recommended before flashing)

Install UEFI firmware for QEMU:

```bash
sudo pacman -S edk2-ovmf
```

Boot the ISO in QEMU with UEFI:

```bash
qemu-system-x86_64 \
  -enable-kvm \
  -m 2048 \
  -cpu host \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso \
  -boot d \
  -vga virtio \
  -display gtk
```

What you should see:
1. systemd-boot menu with timeout (3 seconds)
2. ArchLinux boot messages
3. Auto-login as root on tty1
4. MOTD with ouroborOS branding
5. Shell prompt (or installer launching automatically)

To test the installer interactively in QEMU (with a virtual disk):

```bash
qemu-system-x86_64 \
  -enable-kvm \
  -m 4096 \
  -cpu host \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2-ovmf/x64/OVMF_CODE.fd \
  -cdrom out/ouroborOS-*.iso \
  -drive file=/tmp/ouroboros-test.img,format=raw,if=virtio \
  -boot d
```

Create the virtual disk first if it doesn't exist:

```bash
qemu-img create -f raw /tmp/ouroboros-test.img 20G
```

---

## Step 6 — Identify your USB drive

**Before plugging in the USB:**

```bash
lsblk -o NAME,SIZE,MODEL,TYPE,HOTPLUG,TRAN
```

**After plugging in the USB**, run the same command and note which new device appeared.
USB drives will have `HOTPLUG=1` and `TRAN=usb`.

Example output:

```
NAME   SIZE MODEL              TYPE HOTPLUG TRAN
sda    500G Samsung SSD 870    disk       0 sata   ← system disk, DO NOT USE
sdb     32G SanDisk Ultra      disk       1 usb    ← USB drive ✓
```

> **Never use the system disk (`sda`, `nvme0n1`, etc.).**
> The flash script protects against this, but double-check manually.

---

## Step 7 — Flash to USB

```bash
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso
```

The script will:
1. Verify the SHA256 checksum automatically
2. List available USB devices and ask you to pick one
3. Show device info and ask you to type `YES` to confirm
4. Write the ISO with `dd` (shows live progress)
5. Run `sync` to flush all buffers

To specify the device directly (non-interactive):

```bash
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso --device /dev/sdb
```

To skip the confirmation prompt (for scripting):

```bash
sudo bash src/scripts/flash-usb.sh --iso out/ouroborOS-*.iso --device /dev/sdb --yes
```

Expected output:

```
── Validating ISO ──────────────────────────────
[OK]    ISO: out/ouroborOS-202601-x86_64.iso (512M)
[OK]    SHA256 checksum verified.

── USB Device Selection ──────────────────────────────
Available USB devices:

  1) /dev/sdb       32G    SanDisk Ultra

Enter device number (1-1): 1

── Device Validation ──────────────────────────────
[INFO]  Target device: /dev/sdb

── Unmounting Partitions ──────────────────────────────
[OK]    No mounted partitions found on /dev/sdb.

── Final Confirmation ──────────────────────────────
WARNING: ALL DATA ON /dev/sdb WILL BE PERMANENTLY DESTROYED.

  ISO:     out/ouroborOS-202601-x86_64.iso (512M)
  Device:  /dev/sdb

Type YES (all caps) to confirm: YES

── Writing ISO to USB ──────────────────────────────
512+0 records in
512+0 records out
536870912 bytes (537 MB, 512 MiB) copied, 45.2 s, 11.9 MB/s

── Done ──────────────────────────────
[OK]    ISO successfully written to /dev/sdb in 46s.

  Next steps:
  1. Safely remove the USB drive.
  2. Plug it into the target machine.
  3. Boot from USB (select it in UEFI firmware boot menu, usually F12 or F2).
  4. Run 'ouroborOS-installer' from the live environment.
```

---

## Step 8 — Verify the USB (optional)

Mount the USB and check the contents:

```bash
# Mount the first partition of the USB
mount /dev/sdb1 /mnt

# Verify key files are present
ls /mnt/arch/boot/
ls /mnt/loader/entries/

# Unmount
umount /mnt
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `mkarchiso: command not found` | `sudo pacman -S archiso` |
| Build fails with "no space left" | Free ≥ 10 GB in `/tmp` or use `--workdir` to point to a larger partition |
| QEMU: "not a bootable disk" | Ensure you have the `edk2-ovmf` package and use the `-drive if=pflash` argument exactly as shown |
| USB not detected by flash script | Check `lsblk -o HOTPLUG` — only hotplug devices are listed; use `--device /dev/sdX` to override |
| `dd` very slow | Normal for USB 2.0 (~10 MB/s). USB 3.0 should be 40–80 MB/s |
| SHA256 mismatch | Delete the ISO and rebuild: `sudo bash src/scripts/build-iso.sh --clean` |
