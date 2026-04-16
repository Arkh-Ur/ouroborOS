# Análisis Comparativo: archiso · archinstall · ouroborOS

**Fecha:** 2026-04-12
**Versión analizada:** ouroborOS v0.4.0 · archiso master · archinstall master
**Autor:** Análisis automatizado con contexto del proyecto

---

## Resumen Ejecutivo

Este documento compara ouroborOS con dos proyectos upstream de Arch Linux:
**archiso** (framework de build de ISO) y **archinstall** (installer interactivo).
El objetivo es identificar mejoras, gaps y lecciones que ouroborOS puede adoptar
sin comprometer su filosofía de diseño inmutable, minimalista y systemd-native.

### Hallazgos clave

| Hallazgo | Severidad | Estado |
|----------|-----------|--------|
| `cryptsetup` ausente del ISO (requerido por `disk.sh` para LUKS) | 🔴 Crítico | Pendiente fix |
| Hyprland sin herramientas esenciales (screenshots, file manager) | 🟡 Gap funcional | Pendiente |
| Niri sin barra de estado, lock screen ni wallpaper setter | 🟡 Gap funcional | Pendiente |
| KDE con `kde-applications-meta` instala ~300 paquetes innecesarios | 🟡 Bloat | Pendiente optimizar |
| `os-release` desactualizado (0.1.0 vs 0.4.3) | 🟢 Menor | Pendiente fix |
| Perfiles correctamente minimalistas vs upstream | ✅ Correcto | — |
| Exclusión de X11/GRUB/NM consistente con antipatrones | ✅ Correcto | — |

---

## Parte 1: ouroborOS — Visión General del Proyecto

### 1.1 Qué es ouroborOS

ouroborOS es una distribución Linux inmutable basada en ArchLinux con las siguientes
características definitorias:

- **Root filesystem read-only** montado via Btrfs subvolumen `@` con opción `ro`
- **Updates atómicos** via snapshots Btrfs + `our-pac` wrapper
- **Rollback en un comando** via `our-rollback`
+- **Stack 100% systemd-native**: boot, red, DNS, swap, contenedores, home dirs
+- **UEFI-only**, systemd-boot exclusivo (sin GRUB, sin Legacy BIOS)
+- **AUR containerizado** via `our-aur` + systemd-sysext
+- **Flatpak opt-in** via `our-flat`

### 1.2 Arquitectura del sistema instalado

```mermaid
graph TB
    subgraph BOOT["⚡ Boot Layer"]
        UEFI["UEFI Firmware"]
        SDBOOT["systemd-boot"]
        KERNEL["linux-zen + initramfs<br/>btrfs hook"]
    end

    subgraph IMMUTABLE["🔒 Read-Only Root /"]
        ROOT["Btrfs @ subvolume<br/>ro,noatime,compress=zstd"]
    end

    subgraph MUTABLE["✏️ Writable Layer"]
        ETC["/etc<br/>@etc · rw · configs"]
        VAR["/var<br/>@var · rw · logs, cache, state"]
        HOME["/home<br/>@home · rw · user data"]
        TMP["/tmp<br/>tmpfs · cleared on reboot"]
    end

    subgraph SNAPSHOTS["📸 Snapshot Layer"]
        SNAP["/.snapshots<br/>@snapshots · rollback targets"]
        INSTALL["@snapshots/install<br/>🏆 golden baseline (never pruned)"]
        PRE["@snapshots/2026-04-12T143000<br/>pre-update snapshots"]
    end

    subgraph TOOLS["🔧 our-* Tooling"]
        OURPAC["our-pac<br/>atomic package manager"]
        OURSNAP["our-snapshot<br/>Btrfs snapshot manager"]
        OURROLL["our-rollback<br/>atomic rollback"]
        OURAUR["our-aur<br/>containerized AUR helper"]
        OURFLAT["our-flat<br/>Flatpak wrapper"]
        OURCONT["our-container<br/>nspawn container manager"]
        OURWIFI["our-wifi · our-bluetooth · our-fido2"]
    end

    UEFI --> SDBOOT --> KERNEL --> ROOT
    ROOT --> SNAP
    SNAP --> INSTALL
    SNAP --> PRE
    ROOT -.->|bind mounts| ETC
    ROOT -.->|bind mounts| VAR
    ROOT -.->|bind mounts| HOME
    ROOT -.->|tmpfs| TMP
    OURPAC --> ROOT
    OURSNAP --> SNAP
    OURROLL --> SNAP
```

### 1.3 Flujo de update atómico

```mermaid
sequenceDiagram
    actor User
    participant OurPac as our-pac
    participant Btrfs as Btrfs
    participant Boot as systemd-boot
    participant SB as Secure Boot

    User->>OurPac: sudo our-pac -Syu
    OurPac->>Btrfs: ① snapshot -r @ → @snapshots/TIMESTAMP
    OurPac->>Boot: ② write snapshot boot entry
    OurPac->>Btrfs: ③ mount subvolid=5 → set ro=false
    OurPac->>Btrfs: ④ remount / as rw
    OurPac->>OurPac: ⑤ pacman -Syu
    OurPac->>Btrfs: ⑥ set ro=true → remount / as ro
    OurPac->>SB: ⑦ sbctl sign-all (if active)
    OurPac->>Boot: ⑧ sync boot entries
    OurPac->>OurPac: ⑨ prune if >10 snapshots
    OurPac-->>User: done ✓

    Note over User,Boot: Rollback flow
    User->>Boot: select snapshot at boot menu
    Boot->>Btrfs: mount @snapshots/TIMESTAMP,ro
    User->>OurPac: sudo our-rollback promote TIMESTAMP
    OurPac->>Btrfs: mv @ → @.old
    OurPac->>Btrfs: mv @snapshots/TIMESTAMP → @
    OurPac-->>User: rollback permanente ✓
```

### 1.4 El Installer: FSM de 13 estados

```mermaid
flowchart TD
    INIT["🟢 INIT<br/>Load config / detect resume"]
    NET["📶 NETWORK_SETUP<br/>WiFi if no internet"]
    PRE["🔍 PREFLIGHT<br/>UEFI · RAM · disk · clock"]
    LOC["🌐 LOCALE<br/>Language · keymap · timezone"]
    USR["👤 USER<br/>Username · password · shell"]
    DESK["🖥️ DESKTOP<br/>Profile · DM selection"]
    SB["🔐 SECURE_BOOT<br/>sbctl setup (if enabled)"]
    PART["💾 PARTITION<br/>⚠️ POINT OF NO RETURN"]
    FMT["📦 FORMAT<br/>GPT · Btrfs · subvolumes"]
    INST["⚙️ INSTALL<br/>pacstrap 10 retries"]
    CONF["🔧 CONFIGURE<br/>Bootloader · network · users"]
    SNAP["📸 SNAPSHOT<br/>Golden baseline"]
    FIN["✅ FINISH<br/>Unmount · reboot"]

    INIT --> NET --> PRE
    PRE -->|pass| LOC
    PRE -->|fail| FATAL["💀 FATAL"]
    LOC --> USR --> DESK --> SB --> PART
    SB -.->|skip if disabled| PART
    PART --> FMT --> INST --> CONF --> SNAP --> FIN

    style INIT fill:#2d6a4f,color:#fff
    style FIN fill:#2d6a4f,color:#fff
    style PART fill:#d62828,color:#fff
    style FMT fill:#e76f51,color:#fff
    style INST fill:#e76f51,color:#fff
    style CONF fill:#e76f51,color:#fff
    style SNAP fill:#457b9d,color:#fff
    style FATAL fill:#6c757d,color:#fff
```

### 1.5 Métricas del proyecto

| Métrica | Valor |
|---------|-------|
| Código del installer | ~5,466 líneas (Python + Bash) |
| Ejecutables our-* | ~5,700+ líneas (13 scripts Bash) |
| Total estimado | ~11,000+ líneas |
| Tests unitarios | 347 tests, ≥93% coverage |
| Paquetes ISO | ~62 |
| Perfiles desktop | 5 (minimal, hyprland, niri, gnome, kde) |
| Workflows CI | 5 |
| Releases | 4 (v0.1.0 → v0.4.0) |
| Tiempo de desarrollo | ~6 días |

---

## Parte 2: archiso — Comparación del Framework de Build

### 2.1 ¿Qué es archiso?

archiso es el framework oficial de Arch Linux para construir imágenes ISO booteables.
Proporciona el comando `mkarchiso` que toma un **profile** (directorio con configuración)
y produce un ISO listo para flashear.

### 2.2 Estructura de un profile archiso

```mermaid
graph LR
    subgraph Profile["📁 archiso profile"]
        DEF["profiledef.sh<br/>Metadatos del ISO"]
        PKG["packages.x86_64<br/>Lista de paquetes"]
        PAC["pacman.conf<br/>Config pacman"]
        AIR["airootfs/<br/>Overlay de archivos"]
        EFI["efiboot/<br/>systemd-boot entries"]
    end

    DEF --> MK["mkarchiso"]
    PKG --> MK
    PAC --> MK
    AIR --> MK
    EFI --> MK

    MK --> ISO["ouroborOS-0.4.3-x86_64.iso<br/>+ SHA256 checksum"]
```

### 2.3 Comparación de profiles

| Aspecto | archiso `releng` | archiso `baseline` | ouroborOS |
|---------|------------------|--------------------|-----------|
| Propósito | ISO mensual de Arch | ISO mínima de Arch | Distro inmutable |
| Paquetes | ~130 | ~110 | ~62 |
| Boot modes | BIOS + UEFI | BIOS + UEFI (GRUB) | Solo UEFI |
| airootfs type | squashfs (xz) | **erofs** (lzma) | squashfs (zstd-15) |
| Kernel | linux | linux | linux-zen |
| Bootloader | systemd-boot + syslinux | GRUB | systemd-boot |

### 2.4 Novedades de upstream que ouroborOS no usa

```mermaid
graph TD
    subgraph UPSTREAM["archiso upstream features"]
        EROFS["erofs airootfs<br/>Más rápido que squashfs"]
        ARCH["architecture field<br/>En boot entries .conf"]
        UCOD["Microcode check<br/>Auto-detect en initramfs"]
        GPG["GPG rootfs signing<br/>Para netboot seguro"]
        SDE["SOURCE_DATE_EPOCH<br/>→ IMAGE_ID/VERSION<br/>En os-release"]
    end

    subgraph DECISION["Decisión"]
        YES["✅ ADOPTAR"]
        MAYBE["⚠️ EVALUAR"]
        NO["❌ NO"]
    end

    EROFS --> MAYBE
    ARCH --> YES
    UCOD --> MAYBE
    GPG --> NO
    SDE --> YES

    style YES fill:#2d6a4f,color:#fff
    style MAYBE fill:#f4a261,color:#000
    style NO fill:#e76f51,color:#fff
```

| Feature | Descripción | Conveniencia | Esfuerzo |
|---------|-------------|--------------|----------|
| `erofs` | Filesystem read-only nativo del kernel, montaje más rápido | ⚠️ Evaluar | 1 línea en profiledef.sh |
| `architecture` en entries | Campo para filtrar boot entries por arch | ✅ Adoptar | Agregar a .conf files |
| Microcode en initramfs | No copiar ucode separado si ya está en initramfs | ⚠️ Evaluar | Medio |
| GPG signing de rootfs | Firma del airootfs.sfs | ❌ No usa netboot | — |
| SOURCE_DATE_EPOCH → os-release | Inyectar IMAGE_ID/VERSION en os-release | ✅ Adoptar | Bajo |

### 2.5 Lo que ouroborOS hace mejor que archiso

| Feature | archiso | ouroborOS |
|---------|---------|-----------|
| Installer TUI/FSM | Ninguno | 13 estados con checkpoints |
| Desktop profiles | Ninguno | 5 perfiles con AUR lazy |
| Secure Boot | No | sbctl integrado |
| AUR helper | No | our-aur containerizado |
| SSH en live ISO | No | Servidor SSH activo |
| Serial console | No | ttyS0 configurado |
| Unattended YAML | No | Config discovery multi-source |

---

## Parte 3: Paquetes — Comparación Detallada

### 3.1 Bug crítico: `cryptsetup` ausente

```mermaid
flowchart LR
    subgraph BUG["🔴 BUG: cryptsetup ausente"]
        DISK["disk.sh<br/>encrypt_partition()"]
        CRYPT["cryptsetup luksFormat<br/>cryptsetup open"]
        ISO["packages.x86_64<br/>❌ NO incluye cryptsetup"]
    end

    DISK --> CRYPT
    CRYPT -->|command not found| FAIL["💥 Instalación LUKS falla"]
    ISO -.->|falta| CRYPT

    style FAIL fill:#d62828,color:#fff
```

**`disk.sh` invoca `cryptsetup` directamente en el live ISO**, pero `cryptsetup`
no está en `packages.x86_64`. Cualquier instalación con `use_luks: true` falla con
`command not found: cryptsetup`.

**Fix:** Agregar `cryptsetup` a `packages.x86_64`.

### 3.2 Paquetes recomendados para agregar

| Paquete | Peso | Justificación |
|---------|------|---------------|
| **`cryptsetup`** | ~2 MB | **BUG** — requerido por `disk.sh` para LUKS |
| **`pciutils`** | ~1 MB | `lspci` esencial para debug de hardware headless via SSH |
| **`usbutils`** | ~0.5 MB | `lsusb` para diagnóstico de FIDO2 tokens y Bluetooth |
| **`diffutils`** | ~0.3 MB | `diff` usado implícitamente por muchos scripts |

**Costo total:** ~4 MB. ISO pasa de ~800 MB a ~804 MB.

### 3.3 Paquetes cuestionables en ouroborOS (considerar quitar)

| Paquete | Peso | Problema | Veredicto |
|---------|------|----------|-----------|
| `linux-zen-headers` | ~30 MB | Solo sirve para DKMS en el sistema instalado. Ya se instala via pacstrap | **Quitar del ISO** |
| `flatpak` | ~15 MB | No funciona en el live ISO (sin persistencia). Se instala post-install on-demand | **Quitar del ISO** |

**Ahorro:** ~45 MB. ISO pasaría de ~800 MB a ~755 MB.

### 3.4 Paquetes de upstream correctamente rechazados

```mermaid
graph TD
    subgraph REJECTED["❌ Paquetes rechazados (correctamente)"]
        GRUB["grub<br/>Solo systemd-boot"]
        NM["networkmanager<br/>systemd-networkd exclusivo"]
        WPA["wpa_supplicant<br/>iwd exclusivo"]
        SYSLINUX["syslinux<br/>UEFI-only, sin BIOS"]
        RE["refind<br/>Redundante con systemd-boot"]
        MM["modemmanager<br/>Sin soporte de modems"]
        BW["broadcom-wl<br/>Driver propietario"]
        CLOUD["cloud-init<br/>No es distro cloud"]
        X11["bspwm · i3 · awesome<br/>X11-only"]
    end

    subgraph REASON["Razón"]
        ANTIPATRON["Antipatrón documentado"]
        FILOSOFIA["Contradice filosofía"]
        SCOPE["Fuera de scope"]
    end

    GRUB --> ANTIPATRON
    NM --> ANTIPATRON
    WPA --> ANTIPATRON
    SYSLINUX --> ANTIPATRON
    RE --> FILOSOFIA
    MM --> SCOPE
    BW --> FILOSOFIA
    CLOUD --> SCOPE
    X11 --> FILOSOFIA

    style ANTIPATRON fill:#d62828,color:#fff
    style FILOSOFIA fill:#e76f51,color:#fff
    style SCOPE fill:#f4a261,color:#000
```

### 3.5 Comparación visual de tamaño

```
archiso releng:     ~130 paquetes   ~1.8 GB ISO
archiso baseline:   ~110 paquetes   ~1.2 GB ISO (erofs)
ouroborOS actual:    ~62 paquetes   ~800 MB ISO
ouroborOS optimizado: ~61 paquetes  ~755 MB ISO (-headers, -flatpak, +4 nuevos)
```

---

## Parte 4: archinstall vs ouroborOS — Desktop Profiles

### 4.1 Enfoques arquitectónicos

```mermaid
graph TB
    subgraph ARCHINSTALL["archinstall"]
        direction TB
        AI_LIB["Librería Python reutilizable"]
        AI_CLASES["Clases Profile con herencia OOP"]
        AI_MENU["Menú jerárquico interactivo"]
        AI_JSON["Config JSON (2 archivos)"]
        AI_LIB --> AI_CLASES --> AI_MENU
    end

    subgraph OUROBOROS["ouroborOS"]
        direction TB
        OU_FSM["FSM de estados (13 estados)"]
        OU_DICT["Diccionario PROFILE_PACKAGES"]
        OU_YAML["Config YAML (1 archivo)"]
        OU_BASH["Bash ops (disk.sh, configure.sh)"]
        OU_FSM --> OU_DICT --> OU_BASH
    end

    style ARCHINSTALL fill:#2980b9,color:#fff
    style OUROBOROS fill:#2d6a4f,color:#fff
```

| Aspecto | archinstall | ouroborOS |
|---------|------------|-----------|
| Paradigma | Librería Python + OOP | FSM + diccionario estático |
| Configuración | JSON (config + credentials) | YAML (1 archivo) |
| Profiles | Clases Python con herencia | Dict `PROFILE_PACKAGES` |
| Extensibilidad | Nueva clase que hereda de `Profile` | Agregar entrada al dict |
| Interactividad | Menú jerárquico (DE → Greeter → GPU → Seat) | Menú plano (profile → DM auto) |
| Post-install hooks | `install()`, `post_install()`, `provision()` | `configure.sh` con branching |
| AUR packages | No gestiona | Lazy queue via `our-aur` |

### 4.2 Comparación perfil por perfil

#### 4.2.1 Hyprland

```mermaid
graph LR
    subgraph COMMON["✅ Compartido"]
        HYP["hyprland"]
        PORTAL["xdg-desktop-portal-hyprland"]
        WOFI["wofi"]
        QT5["qt5-wayland"]
        QT6["qt6-wayland"]
    end

    subgraph AI_ONLY["🔵 Solo archinstall"]
        KITTY["kitty (terminal GPU)"]
        DUNST["dunst (notificaciones)"]
        GRIM["grim + slurp (screenshots)"]
        DOLPHIN_A["dolphin (file manager)"]
        UWSM["uwsm (session manager)"]
        SEATD_A["seat access: seatd/polkit"]
    end

    subgraph OU_ONLY["🟢 Solo ouroborOS"]
        FOOT["foot (terminal ligero)"]
        WAYBAR["waybar (barra de estado)"]
        HPOLKIT["hyprpolkitagent (polkit)"]
        AUR["quickshell · hyprlock<br/>hypridle · hyprshot (AUR)"]
    end

    style COMMON fill:#2d6a4f,color:#fff
    style AI_ONLY fill:#2980b9,color:#fff
    style OU_ONLY fill:#e67e22,color:#fff
```

| Aspecto | archinstall | ouroborOS | Análisis |
|---------|------------|-----------|----------|
| Terminal | `kitty` (GPU) | `foot` (ligero) | Ambos válidos. `foot` más alineado con minimalismo |
| Notificaciones | `dunst` | **FALTA** | ⚠️ Gap — sin notificaciones |
| Screenshots | `grim` + `slurp` | **FALTA** | 🔴 Gap esencial |
| File manager | `dolphin` | **FALTA** | ⚠️ Gap — sin file manager |
| Polkit | `polkit-kde-agent` | `hyprpolkitagent` | ✅ ouroborOS usa nativo de Hyprland |
| Barra | — | `waybar` | ✅ ouroborOS la incluye |
| Session manager | `uwsm` | — | Menor — no crítico |
| AUR | — | 4 paquetes AUR lazy | ✅ Ventaja clara de ouroborOS |

**⚠️ Gaps del perfil Hyprland en ouroborOS:**
1. **`grim` + `slurp`** (screenshots) — ESENCIAL, sin esto no se pueden tomar capturas
2. **`dunst`** o **`swaync`** (notificaciones) — Necesario para un desktop funcional
3. **`dolphin`** o **`thunar`** (file manager) — El usuario necesita gestionar archivos

#### 4.2.2 Niri

```mermaid
graph LR
    subgraph COMMON["✅ Compartido"]
        NIRI["niri"]
        NPORTAL["xdg-desktop-portal-gnome"]
        FUZZEL["fuzzel"]
    end

    subgraph AI_ONLY["🔵 Solo archinstall"]
        ALACRITTY["alacritty (terminal)"]
        WAYBAR_A["waybar (barra)"]
        MAKO["mako (notificaciones)"]
        SWAYBG["swaybg (wallpaper)"]
        SWAYLOCK["swaylock (lock)"]
        SWAYIDLE["swayidle (idle)"]
        XWAY["xorg-xwayland"]
        SEATD_N["seat access"]
    end

    subgraph OU_ONLY["🟢 Solo ouroborOS"]
        FOOT_N["foot (terminal)"]
        POLKIT_N["polkit-gnome"]
        QT_N["qt5-wayland + qt6-wayland"]
    end

    style COMMON fill:#2d6a4f,color:#fff
    style AI_ONLY fill:#2980b9,color:#fff
    style OU_ONLY fill:#e67e22,color:#fff
```

| Aspecto | archinstall | ouroborOS | Análisis |
|---------|------------|-----------|----------|
| Terminal | `alacritty` | `foot` | Ambos válidos |
| Barra de estado | `waybar` | **FALTA** | 🔴 Gap crítico — WM sin barra es spartan |
| Notificaciones | `mako` | **FALTA** | 🔴 Gap — sin notificaciones |
| Wallpaper | `swaybg` | **FALTA** | ⚠️ Gap — sin wallpaper setter |
| Lock screen | `swaylock` | **FALTA** | 🔴 Gap — sin lock screen |
| Idle daemon | `swayidle` | **FALTA** | ⚠️ Gap — sin gestión de idle |
| XWayland | `xorg-xwayland` | No | Decisión válida (Wayland-native) |
| Polkit | — | `polkit-gnome` | ✅ ouroborOS lo incluye |
| Qt Wayland | — | `qt5-wayland` + `qt6-wayland` | ✅ ouroborOS los incluye |
| Greeter | `lightdm` | `sddm` | Diferente pero funcional |

**🔴 Gaps significativos del perfil Niri en ouroborOS:**
1. **`waybar`** (barra de estado) — Un tiling WM sin barra es frustrante
2. **`swaylock`** o alternativa (lock screen) — Seguridad básica
3. **`swaybg`** o `swww` (wallpaper) — Experiencia visual
4. **`mako`** o `swaync` (notificaciones) — Desktop funcional

#### 4.2.3 GNOME — Prácticamente idéntico

| Paquete | archinstall | ouroborOS | Notas |
|---------|:-----------:|:---------:|-------|
| `gnome` | ✅ | ✅ | Meta-paquete que incluye todo |
| `gnome-tweaks` | ✅ | ✅ | Herramientas de customización |
| `xdg-user-dirs` | — | ✅ | Crea ~/Documents, ~/Downloads etc. |
| Greeter | `gdm` | `gdm` (auto) | Igual |

**✅ Sin gaps.** Ambos perfiles son correctos y completos. GNOME como meta-paquete
ya incluye todo lo necesario.

#### 4.2.4 KDE Plasma — Diferencia de enfoque

```mermaid
graph TB
    subgraph ARCHINSTALL_KDE["archinstall"]
        AI_FLAVOR["3 flavors interactivos"]
        AI_META["plasma-meta (recomendado)"]
        AI_PLASMA["plasma (grupo completo)"]
        AI_DESK["plasma-desktop (mínimo)"]
        AI_FLAVOR --> AI_META
        AI_FLAVOR --> AI_PLASMA
        AI_FLAVOR --> AI_DESK
    end

    subgraph OUROBOROS_KDE["ouroborOS"]
        OU_FIXED["Un flavor fijo"]
        OU_PLASMA["plasma (grupo)"]
        OU_APPS["+ kde-applications-meta"]
        OU_WAY["+ plasma-wayland-session"]
        OU_FIXED --> OU_PLASMA
        OU_FIXED --> OU_APPS
        OU_FIXED --> OU_WAY
    end

    style ARCHINSTALL_KDE fill:#2980b9,color:#fff
    style OUROBOROS_KDE fill:#e76f51,color:#fff
```

| Aspecto | archinstall | ouroborOS | Análisis |
|---------|------------|-----------|----------|
| Flavor selector | Sí (3 opciones) | No | archinstall ofrece flexibilidad |
| Paquete base | `plasma-meta` (default) | `plasma` (grupo) | Grupo instala más que meta |
| Apps adicionales | Ninguna | `kde-applications-meta` | ⚠️ Instala ~300 paquetes, ~1.5 GB |
| Wayland | Incluido en plasma | `plasma-wayland-session` explícito | Ya es dependencia de plasma |
| Greeter | `plasma-login-manager` | `plasma-login-manager` (plm) | Igual |

**⚠️ Problema en ouroborOS:** `kde-applications-meta` instala TODAS las apps KDE
incluyendo juegos, educación, ofimática, multimedia. ~1.5 GB de paquetes.
La recomendación del PHASE_2_PLAN sigue pendiente:

> *"Consider replacing with: `plasma-desktop dolphin konsole kate gwenview ark ffmpegthumbs`.
> Reduce de ~1.5 GB a ~400 MB."*

#### 4.2.5 Perfiles que archinstall tiene y ouroborOS no

```mermaid
graph TD
    subgraph WAYLAND["Wayland-native<br/>⚠️ Podría considerar"]
        COSMIC["Cosmic<br/>System76 · Rust-based"]
        SWAY["Sway<br/>i3 de Wayland"]
    end

    subgraph X11["X11-only<br/>❌ Correctamente excluidos"]
        CINNAMON["Cinnamon"]
        XFCE["XFCE4"]
        MATE["Mate"]
        DEEPIN["Deepin"]
        LXQT["LXQt"]
        I3["i3-wm"]
        BSPWM["bspwm"]
        AWESOME["awesome"]
        ENLIGHT["Enlightenment"]
    end

    style WAYLAND fill:#2d6a4f,color:#fff
    style X11 fill:#6c757d,color:#fff
```

**Cosmic** (System76) es el único candidato real para un futuro perfil — es
Wayland-native, Rust-based, y está en activo desarrollo. Podría considerarse
para Phase 5+.

### 4.3 Comparación de features del installer

| Feature | archinstall | ouroborOS |
|---------|:-----------:|:---------:|
| GPU driver selection | ✅ | ❌ |
| Seat access (seatd/polkit) | ✅ | ❌ (implícito) |
| KDE flavor selector | ✅ | ❌ |
| Greeter selection | ✅ | ✅ |
| AUR support | ❌ | ✅ (lazy queue) |
| Flatpak support | ❌ | ✅ |
| Immutable root | ❌ | ✅ |
| Snapshots + Rollback | ❌ | ✅ |
| Container support | ❌ | ✅ |
| Secure Boot | ❌ | ✅ |
| WiFi/Bluetooth/FIDO2 | ❌ | ✅ |
| Unattended install | ✅ | ✅ |
| Resume/checkpoint | ❌ | ✅ |
| i18n (30+ idiomas) | ✅ | ❌ |
| X11 profiles | ✅ | ❌ (by design) |

---

## Parte 5: Veredicto y Recomendaciones

### 5.1 ¿Debería ouroborOS usar archinstall?

**No.** Razones fundamentales:

```mermaid
graph TD
    ARCH["archinstall"]
    OU["ouroborOS"]

    ARCH -->|Incompatible| R1["No soporta root inmutable"]
    ARCH -->|Incompatible| R2["No maneja Btrfs subvolumes<br/>(@, @var, @etc, @home, @snapshots)"]
    ARCH -->|Incompatible| R3["No tiene our-pac wrapper<br/>(snapshot → remount → upgrade)"]
    ARCH -->|Incompatible| R4["No gestiona systemd-boot<br/>con snapshot entries"]
    ARCH -->|Incompatible| R5["No integra our-* tooling"]

    OU -->|✅| R6["FSM con checkpoints<br/>más robusto para su caso"]
    OU -->|✅| R7["Segregación input/destructiva<br/>antes de tocar el disco"]
    OU -->|✅| R8["our-aur, our-flat, our-pac<br/>ecosistema propio"]

    style ARCH fill:#e76f51,color:#fff
    style OU fill:#2d6a4f,color:#fff
```

### 5.2 Acciones recomendadas (priorizadas)

```mermaid
gantt
    title Acciones Recomendadas — Prioridad
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section 🔴 Crítico
    Agregar cryptsetup al ISO        :a1, 2026-04-13, 1d

    section 🟡 Alta prioridad
    Agregar grim+slurp a Hyprland    :a2, 2026-04-14, 1d
    Agregar waybar+swaylock a Niri   :a3, 2026-04-14, 1d
    Optimizar KDE (quitar apps-meta)  :a4, 2026-04-15, 1d

    section 🟢 Media prioridad
    Agregar pciutils+usbutils        :a5, 2026-04-16, 1d
    Agregar seatd a WM profiles      :a6, 2026-04-16, 1d
    Quitar headers+flatpak del ISO    :a7, 2026-04-16, 1d
    Fix os-release version            :a8, 2026-04-16, 1d

    section 🔵 Baja prioridad
    Agregar Cosmic profile            :a9, 2026-05-01, 3d
    KDE flavor selector               :a10, 2026-05-01, 2d
    GPU driver selection               :a11, 2026-05-05, 3d
```

#### 🔴 Crítico (inmediato)

| # | Acción | Archivo | Detalle |
|---|--------|---------|---------|
| 1 | Agregar `cryptsetup` | `packages.x86_64` | Instalaciones con `use_luks: true` fallan sin esto |

#### 🟡 Alta prioridad (siguiente sprint)

| # | Acción | Archivo | Detalle |
|---|--------|---------|---------|
| 2 | Agregar `grim` + `slurp` | `desktop_profiles.py` | Hyprland: screenshots esenciales |
| 3 | Agregar `waybar` + `swaylock` + `swaybg` | `desktop_profiles.py` | Niri: WM sin barra/lock es spartan |
| 4 | Reemplazar `kde-applications-meta` | `desktop_profiles.py` | Usar `dolphin konsole kate gwenview ark ffmpegthumbs` (~400 MB vs ~1.5 GB) |

#### 🟢 Media prioridad

| # | Acción | Archivo | Detalle |
|---|--------|---------|---------|
| 5 | Agregar `pciutils` + `usbutils` + `diffutils` | `packages.x86_64` | Debug de hardware en live ISO |
| 6 | Agregar `seatd` a hyprland + niri | `desktop_profiles.py` | Seat access para WM |
| 7 | Quitar `linux-zen-headers` del ISO | `packages.x86_64` | Ya se instala via pacstrap (-30 MB) |
| 8 | Quitar `flatpak` del ISO | `packages.x86_64` | Se instala on-demand (-15 MB) |
| 9 | Fix `os-release` version | `airootfs/etc/os-release` | Usar SOURCE_DATE_EPOCH como upstream |

#### 🔵 Baja prioridad (Phase 5+)

| # | Acción | Detalle |
|---|--------|---------|
| 10 | Agregar Cosmic como 6to perfil | Wayland-native, Rust-based, en alza |
| 11 | KDE flavor selector | Opción meta/desktop como archinstall |
| 12 | GPU driver selection en installer | mesa/nvidia como opción del FSM |
| 13 | Evaluar `erofs` vs `squashfs` | 1 línea en profiledef.sh, más rápido |

### 5.3 Lecciones de archinstall para ouroborOS

| Lección | Aplicación |
|---------|-----------|
| Profiles más completos | Agregar screenshots, notificaciones, file manager a WM profiles |
| KDE flavor selector | Ofrecer meta vs desktop en vez del full apps-meta |
| Seat access explícito | Agregar `seatd` a perfiles de tiling WM |
| Custom profile hooks | El patrón `install()` + `post_install()` podría inspirar un mecanismo similar |
| i18n | El sistema gettext de archinstall es un buen modelo para Phase 4.3 |

### 5.4 Lecciones de archiso para ouroborOS

| Lección | Aplicación |
|---------|-----------|
| `erofs` como alternativa a squashfs | Evaluar — montaje más rápido, mejor ratio |
| `architecture` en boot entries | Agregar para futura compatibilidad aarch64 |
| `SOURCE_DATE_EPOCH` → os-release | Fix del bug de version desactualizado |
| Boot mode validation | Aprovechar la validación exhaustiva de mkarchiso |

---

## Apéndice A: Paquetes completos por perfil (comparación directa)

### Hyprland

| Paquete | archinstall | ouroborOS | Notas |
|---------|:-----------:|:---------:|-------|
| hyprland | ✅ | ✅ | Compositor |
| xdg-desktop-portal-hyprland | ✅ | ✅ | Portal |
| kitty | ✅ | — | Terminal GPU (arch: kitty, ouro: foot) |
| foot | — | ✅ | Terminal ligero |
| wofi | ✅ | ✅ | Launcher |
| waybar | — | ✅ | Barra de estado |
| dunst | ✅ | — | **⚠️ Falta en ouroborOS** |
| grim | ✅ | — | **🔴 Falta — screenshots** |
| slurp | ✅ | — | **🔴 Falta — screenshots** |
| dolphin | ✅ | — | **⚠️ Falta — file manager** |
| uwsm | ✅ | — | Session manager |
| polkit-kde-agent | ✅ | — | Polkit |
| hyprpolkitagent | — | ✅ | Polkit nativo de Hyprland |
| qt5-wayland | ✅ | ✅ | Qt5 Wayland |
| qt6-wayland | ✅ | ✅ | Qt6 Wayland |
| quickshell (AUR) | — | ✅ | Shell Qt6/QML |
| hyprlock (AUR) | — | ✅ | Screen locker |
| hypridle (AUR) | — | ✅ | Idle daemon |
| hyprshot (AUR) | — | ✅ | Screenshot tool |
| **Greeter** | sddm | sddm | Igual |

### Niri

| Paquete | archinstall | ouroborOS | Notas |
|---------|:-----------:|:---------:|-------|
| niri | ✅ | ✅ | Compositor |
| xdg-desktop-portal-gnome | ✅ | ✅ | Portal |
| alacritty | ✅ | — | Terminal (arch: alacritty, ouro: foot) |
| foot | — | ✅ | Terminal ligero |
| fuzzel | ✅ | ✅ | Launcher |
| waybar | ✅ | — | **🔴 Falta — barra** |
| mako | ✅ | — | **🔴 Falta — notificaciones** |
| swaybg | ✅ | — | **⚠️ Falta — wallpaper** |
| swaylock | ✅ | — | **🔴 Falta — lock screen** |
| swayidle | ✅ | — | **⚠️ Falta — idle** |
| xorg-xwayland | ✅ | — | XWayland (ouroborOS: Wayland-native) |
| polkit-gnome | — | ✅ | Polkit |
| qt5-wayland | — | ✅ | Qt5 Wayland |
| qt6-wayland | — | ✅ | Qt6 Wayland |
| **Greeter** | lightdm | sddm | Diferente |

### GNOME

| Paquete | archinstall | ouroborOS | Notas |
|---------|:-----------:|:---------:|-------|
| gnome | ✅ | ✅ | Meta-paquete |
| gnome-tweaks | ✅ | ✅ | Tweaks |
| xdg-user-dirs | — | ✅ | Crea directorios de usuario |
| **Greeter** | gdm | gdm | Igual |

### KDE Plasma

| Paquete | archinstall | ouroborOS | Notas |
|---------|:-----------:|:---------:|-------|
| plasma-meta (default) | ✅ | — | Meta curado (~1.5 GB) |
| plasma (grupo) | ✅ (opción) | ✅ | Grupo completo |
| plasma-desktop (mínimo) | ✅ (opción) | — | Solo el shell |
| kde-applications-meta | — | ✅ | **⚠️ ~300 apps, ~1.5 GB** |
| plasma-wayland-session | — | ✅ | Ya es dependencia de plasma |
| **Greeter** | plasma-login-manager | plasma-login-manager (plm) | Igual |
| **Flavor selector** | ✅ | ❌ | archinstall ofrece 3 opciones |

---

## Apéndice B: Tabla completa de paquetes ISO

### Paquetes en ouroborOS (~62)

| Categoría | Paquetes |
|-----------|----------|
| **Base** | base, linux-zen, linux-zen-headers, linux-firmware |
| **Filesystem** | btrfs-progs, dosfstools, util-linux, parted, gptfdisk |
| **Arch helpers** | arch-install-scripts, archiso, mkinitcpio-archiso, pacman-contrib, reflector |
| **Bootloader** | efibootmgr, edk2-shell, memtest86+-efi, intel-ucode, amd-ucode |
| **Red** | iwd, iw, wireless_tools, dhcpcd, openssh |
| **TUI** | dialog, libnewt |
| **Python** | python, python-yaml, python-rich, python-pyaml |
| **Texto** | less, nano, vim |
| **Shells** | zsh, fish |
| **System** | htop, rsync, wget, curl, git |
| **Dev/CI** | shellcheck, debootstrap |
| **Seguridad** | sbctl |
| **Apps** | flatpak |

### Paquetes recomendados a agregar

| Paquete | Justificación |
|---------|---------------|
| **cryptsetup** | BUG — requerido por disk.sh para LUKS |
| **pciutils** | `lspci` para debug de hardware |
| **usbutils** | `lsusb` para diagnóstico de dispositivos |
| **diffutils** | `diff` usado por scripts |

### Paquetes recomendados a quitar

| Paquete | Razón | Ahorro |
|---------|-------|--------|
| **linux-zen-headers** | Ya se instala via pacstrap | ~30 MB |
| **flatpak** | Se instala on-demand post-install | ~15 MB |

---

*Documento generado como parte del análisis comparativo ouroborOS v0.4.0.*