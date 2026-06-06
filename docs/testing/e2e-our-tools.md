# E2E Test Plan — our_* Tools

> VM: minimal profile, SSH on 2225, user `admin/changeme`
> Run all tests as root via SSH unless noted.

---

## Automated Test Results — v0.6.0 (2026-06-05)

**Script:** `/tmp/run-e2e-tests.sh` — SSH against installed QEMU VM (4 GB RAM, e1000 NIC, SLIRP)

| Section | Tests | Result |
|---------|-------|--------|
| 0. Setup | 9/9 | PASS |
| 1. ouroboros-health | 4/4 | PASS |
| 2. our-pac install/remove | 10/10 | PASS |
| 3. our-snapshot lifecycle | 11/11 | PASS |
| 4. our-rollback try/promote/undo | 10/10 | PASS |
| 5. our-wall firewalld | 10/10 | PASS |
| 6. our-flat Flatpak | 4/4 | PASS |
| 7. our-wifi error path | 4/4 | PASS |
| 8. our-container nspawn | 10/10 | PASS |
| **Total** | **72/72** | **ALL PASS** |

### Bugs fixed during this run

| Bug | File | Fix |
|-----|------|-----|
| `our-rollback undo` fails when `@.del` already exists | `our-rollback` | Clear stale `@.del` before `mv @→@.del` (same as promote clears `@.old`) |
| `our-rollback undo` `--force` flag silently ignored | `our-rollback` | Pass `"$@"` in dispatch: `undo) cmd_undo "$@" ;;` |
| `our-rollback` cleanup trap fires with `$toplevel` unbound | `our-rollback` | Use `${toplevel:-}` in `cleanup()` to survive `exit` from within function |
| `our-container enter -- cmd` fails with "Unknown command verb 'exec'" | `our-container` | Replace `machinectl exec` (removed in systemd 246+) with `nsenter -t <leader>` |
| `our-wifi connect --password` fails without WiFi hardware | `our-wifi` | Move PSK write before `_require_iwd` — credentials can be pre-configured without a device |
| `firewall-cmd` Python import fails on fresh install | `packages.x86_64` | Add `python-dbus` and `python-firewall` to ISO packages list |

### Known constraints

- `our-rollback undo` leaves `@.del` on disk (by design — it's the live running root, can't be deleted until reboot)
- `our-flat -S` install not tested (would take too long in CI — only error path + remote-add covered)
- `our-wifi` WiFi connect not tested in QEMU (no WiFi hardware) — PSK management tested only
- `our-container enter` uses `nsenter` which requires the container to expose a leader PID via machinectl

---

## Setup

- [ ] Boot fresh VM from latest ISO  
- [ ] Install with `/tmp/e2e-test-config.yaml` (minimal + openssh + flatpak + podman)  
- [ ] Reboot into installed system  
- [ ] Enable and start sshd  
- [ ] Confirm `btrfs property get / ro` → `ro=true`  
- [ ] Confirm `ouroboros-health --json` exits 0  

---

## 1. ouroboros-health

- [ ] `ouroboros-health` — all checks PASS, exit 0  
- [ ] `ouroboros-health --json` — valid JSON with `checks[]` and `summary`  
- [ ] `ouroboros-health --yaml` — valid YAML output  
- [ ] `ouroboros-health --doctor` — interactive fix mode launches without crash  
- [ ] Root mounted ro → `root_ro` PASS; manually `mount -o remount,rw /` → `root_ro` FAIL  

---

## 2. our-pac — install / remove / upgrade / rollback safety

- [ ] `our-pac -Ss htop` — search works (no snapshot)  
- [ ] `our-pac -S htop` — snapshot created before install; `htop` runs after  
- [ ] Snapshot count increased by 1 (`our-snapshot list`)  
- [ ] Root re-locked ro after install (`btrfs property get / ro`)  
- [ ] `/var/log/our-pac/` log written  
- [ ] `/etc/ouroboros/system.yaml` `user_packages` contains `htop`  
- [ ] `our-pac -R htop` — `htop` gone; snapshot created; yaml updated  
- [ ] `our-pac -Syu` — upgrade runs; yaml `user_packages` NOT modified  
- [ ] Simulate failure mid-install → root still relocked (trap test)  

---

## 3. our-snapshot — lifecycle

- [ ] `our-snapshot list` — shows install snapshot with `[protected]`  
- [ ] `our-snapshot create test-snap` — ro subvolume at `/.snapshots/test-snap`  
- [ ] `our-snapshot info test-snap` — shows metadata YAML  
- [ ] Boot entry created at `/boot/loader/entries/ouroboros-snapshot-test-snap.conf`  
- [ ] `our-snapshot diff install test-snap` — runs diff, exits 0  
- [ ] `our-snapshot delete test-snap` — subvolume and boot entry removed  
- [ ] `our-snapshot delete install` — REJECTED (protected)  
- [ ] `our-snapshot prune --keep 3` — leaves only 3 most recent  
- [ ] `our-snapshot sync-boot-entries` — idempotent, no orphans  

---

## 4. our-rollback — try / promote / undo

- [ ] `our-rollback list` — lists available snapshots  
- [ ] `our-rollback status` — no `@.old` → "no pending rollback"  
- [ ] `our-pac -S nano` — creates snapshot `snap-A`  
- [ ] `our-rollback try snap-A` — sets one-shot boot entry; `@` unchanged  
- [ ] `our-rollback promote snap-A` — safety snapshot created; `@.del` exists; `@` replaced  
- [ ] `our-rollback status` — shows `@.old` present  
- [ ] `our-rollback undo` — reverts to previous `@`; `@.old` gone  
- [ ] `our-rollback promote snap-A --force` — skips confirmation  
- [ ] `our-rollback undo` with no `@.old` → exits 1 with clear error  

---

## 5. our-aur — AUR sysext install / remove / update

- [ ] `our-aur -Ss yay` — AUR search returns results  
- [ ] `our-aur -Si yay` — shows package info  
- [ ] `our-aur -S yay` — builds and installs as sysext  
- [ ] `systemd-sysext list` — `our-aur-yay` extension visible  
- [ ] `/var/lib/extensions/our-aur-yay/` exists with `extension-release.our-aur-yay`  
- [ ] `yay --version` — runs from sysext  
- [ ] `our-aur -Q` — shows installed AUR packages  
- [ ] `our-aur -Qs yay` — finds it  
- [ ] `our-aur -R yay` — removes sysext dir and tracking JSON  
- [ ] `systemd-sysext list` — extension gone  
- [ ] `our-aur --clean` — no orphan build containers  

---

## 6. our-flat — Flatpak system install / remove

- [ ] `our-flat -S org.gnome.Calculator` without remote → fails with clear error  
- [ ] `our-flat remote-add flathub https://dl.flathub.org/repo/flathub.flatpakrepo`  
- [ ] `our-flat remote-list` — shows flathub  
- [ ] `our-flat -Ss Calculator` — search returns results  
- [ ] `our-flat -Si org.gnome.Calculator` — shows app info  
- [ ] `our-flat -S org.gnome.Calculator` — installs system-wide  
- [ ] `our-flat -Q` — shows installed apps  
- [ ] `our-flat -Qs Calculator` — finds it  
- [ ] `our-flat -Su` — upgrade runs without error  
- [ ] `our-flat -R org.gnome.Calculator` — removes app  
- [ ] `our-flat -Syu` — REJECTED with error (not allowed)  

---

## 7. our-app — AppImage install / remove / upgrade

> Uses a real small AppImage from GitHub for testing.

- [ ] `our-app -S <URL>` — downloads, extracts, installs to `/var/lib/ouroboros/appimages/`  
- [ ] AppImage file present and executable  
- [ ] `.desktop` symlink in `/usr/local/share/applications/`  
- [ ] `.app.yaml` metadata written  
- [ ] `our-app -Q` — shows installed apps  
- [ ] `our-app -Qs <name>` — finds it  
- [ ] `our-app -Si <name>` — shows metadata  
- [ ] `our-app -Su` — re-downloads URL-sourced app  
- [ ] `our-app -R <name>` — removes dir, symlinks, yaml entry  
- [ ] Local file install: `our-app -S /path/to/app.AppImage` — skipped in `-Su`  

---

## 8. our-wall — firewalld wrapper

- [ ] `our-wall status` — shows firewalld state  
- [ ] `our-wall enable` — starts and enables firewalld  
- [ ] `our-wall allow ssh` — ssh service allowed; `our-wall list` shows it  
- [ ] `our-wall allow 8080/tcp` — port rule added  
- [ ] `our-wall list` — shows both ssh and 8080/tcp  
- [ ] `our-wall deny 8080/tcp` — rule removed; `list` no longer shows it  
- [ ] `our-wall zone show` — shows current zone  
- [ ] `our-wall preset server` — applies server preset rules  
- [ ] `our-wall preset reset` — only ssh remains  
- [ ] `our-wall reload` — returns exit 0  
- [ ] Unknown subcommand → exits 1 with usage  

---

## 9. our-container — nspawn lifecycle

- [ ] `our-container list` — empty, no error  
- [ ] `our-container engine show` — shows default engine  
- [ ] `our-container create arch mybox` — creates Btrfs subvolume under `/var/lib/machines/mybox`  
- [ ] `our-container list` — shows `mybox`  
- [ ] `our-container start mybox` — container starts  
- [ ] `our-container enter mybox -- uname -a` — runs command inside  
- [ ] `our-container stats mybox` — shows resource usage  
- [ ] `our-container logs mybox` — returns output  
- [ ] `our-container stop mybox` — container stops  
- [ ] `our-container snapshot create mybox snap1` — snapshot at `/var/lib/machines/.snapshots/mybox/snap1`  
- [ ] `our-container snapshot list mybox` — shows snap1  
- [ ] `our-container snapshot restore mybox snap1` — safety backup created first  
- [ ] `our-container remove mybox` — removes container and all snapshots  
- [ ] `our-container disk-usage` — shows usage summary  

---

## 10. ouroboros-reinstall — reinstall from live ISO

> Run from the live ISO environment (reboot to ISO first).

- [ ] `ouroboros-reinstall --dry-run --disk /dev/sda` — exits 0 with no changes  
- [ ] `ouroboros-reinstall --disk /dev/sda` — prompted to type `reinstall`; abort with `n`  
- [ ] Full reinstall: type `reinstall` → `pre-reinstall-*` snapshot created; packages reinstalled; `post-reinstall-*` snapshot created  
- [ ] `@` is ro=true after completion  
- [ ] `@home` preserved (original user data intact)  
- [ ] `--no-home` flag: `@home` renamed to `@home.old-<ts>`  
- [ ] Non-ouroborOS disk → exits 1 with clear error  

---

## 11. our-wifi — iwd wrapper (error path in QEMU)

> QEMU has no WiFi hardware — test error handling.

- [ ] `our-wifi list` — triggers scan attempt; fails gracefully (no WiFi device)  
- [ ] `our-wifi status` — shows "no WiFi device" or equivalent  
- [ ] `our-wifi connect TestNet --password secret` → writes `/var/lib/iwd/TestNet.psk` with `Passphrase=secret`  
- [ ] `our-wifi show-password TestNet` → reads back `secret`  
- [ ] `our-wifi forget TestNet` → removes PSK file  
- [ ] SSID with spaces: `our-wifi connect "My Net" --password x` → hex-encoded filename used  

---

## Summary

| Tool              | Install | Remove | Upgrade | Rollback | Edge cases |
|-------------------|:-------:|:------:|:-------:|:--------:|:----------:|
| ouroboros-health  |   —     |   —    |   —     |    —     | ✓          |
| our-pac           | ✓       | ✓      | ✓       | ✓ (snap) | ✓          |
| our-snapshot      | ✓       | ✓      | —       | —        | ✓          |
| our-rollback      | —       | —      | —       | ✓        | ✓          |
| our-aur           | ✓       | ✓      | ✓       | —        | ✓          |
| our-flat          | ✓       | ✓      | ✓       | —        | ✓          |
| our-app           | ✓       | ✓      | ✓       | —        | ✓          |
| our-wall          | —       | —      | —       | —        | ✓          |
| our-container     | ✓       | ✓      | —       | ✓ (snap) | ✓          |
| ouroboros-reinstall | ✓     | —      | —       | —        | ✓          |
| our-wifi          | —       | —      | —       | —        | ✓ (errors) |
