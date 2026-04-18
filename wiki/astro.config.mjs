import starlight from '@astrojs/starlight'

export default {
  site: 'https://docs.ouroboros.la',
  base: '/',
  trailingSlash: 'never',
  build: {
    format: 'directory',
  },
  integrations: [
    starlight({
      title: 'Docs ouroborOS',
      tagline: 'Modern immutable Arch Linux',
      logo: {
        src: './src/assets/logo.svg',
        replacesTitle: true,
      },
      defaultLocale: 'root',
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'What is ouroborOS?', slug: 'getting-started/what-is-ouroboros' },
            { label: 'Why ouroborOS?', slug: 'getting-started/why-ouroboros' },
            { label: 'System Architecture', slug: 'getting-started/architecture' },
          ],
        },
        {
          label: 'Installation',
          items: [
            { label: 'Requirements', slug: 'installation/requirements' },
            { label: 'Interactive Install (TUI)', slug: 'installation/interactive' },
            { label: 'Unattended Install (YAML)', slug: 'installation/unattended' },
            { label: 'Configuration Reference', slug: 'installation/config-reference' },
          ],
        },
        {
          label: 'System Management',
          items: [
            { label: 'system.yaml Manifest', slug: 'system/manifest' },
            { label: 'our-pac — Package Manager', slug: 'system/our-pac' },
            { label: 'our-snapshot — Btrfs Snapshots', slug: 'system/our-snapshot' },
            { label: 'our-rollback — Rollback', slug: 'system/our-rollback' },
            { label: 'ouroboros-rebase — Rebase', slug: 'system/rebase' },
            { label: 'ouroboros-health — Health Check', slug: 'system/health' },
            { label: 'ouroboros-update — OTA Updates', slug: 'system/ota-updates' },
          ],
        },
        {
          label: 'Desktop & Wayland',
          items: [
            { label: 'Desktop Profiles', slug: 'desktop/profiles' },
            { label: 'Hyprland', slug: 'desktop/hyprland' },
            { label: 'Niri', slug: 'desktop/niri' },
            { label: 'UI Components & Ricing', slug: 'desktop/ricing' },
            { label: 'Themes & Appearance', slug: 'desktop/themes' },
            { label: 'GPU Detection & Drivers', slug: 'desktop/gpu' },
          ],
        },
        {
          label: 'Containers & Apps',
          items: [
            { label: 'our-container — systemd-nspawn', slug: 'apps/our-container' },
            { label: 'our-aur — AUR Helper', slug: 'apps/our-aur' },
            { label: 'our-flat — Flatpak Wrapper', slug: 'apps/our-flat' },
          ],
        },
        {
          label: 'Network & Connectivity',
          items: [
            { label: 'our-wifi — WiFi Setup', slug: 'network/our-wifi' },
            { label: 'our-bluetooth — Bluetooth & BLE', slug: 'network/our-bluetooth' },
            { label: 'systemd-networkd', slug: 'network/networkd' },
          ],
        },
        {
          label: 'Security',
          items: [
            { label: 'Secure Boot', slug: 'security/secure-boot' },
            { label: 'FIDO2 / WebAuthn / Passkeys', slug: 'security/fido2' },
            { label: 'Disk Encryption (LUKS + TPM2)', slug: 'security/luks-tpm2' },
            { label: 'systemd-homed', slug: 'security/homed' },
          ],
        },
        {
          label: 'Troubleshooting',
          items: [
            { label: 'System Rescue & Rollbacks', slug: 'troubleshooting/rescue' },
            { label: 'Logs & Debugging', slug: 'troubleshooting/logs' },
            { label: 'FAQ', slug: 'troubleshooting/faq' },
            { label: 'Known Limitations', slug: 'troubleshooting/limitations' },
          ],
        },
        {
          label: 'Vision & Roadmap',
          items: [
            { label: 'The Declarative Vision', slug: 'roadmap/declarative-vision' },
            { label: 'Phase 5 — system.yaml & OTA', slug: 'roadmap/phase5' },
            { label: 'Phase 6+ — What\'s Next', slug: 'roadmap/phase6' },
            { label: 'Contributing', slug: 'roadmap/contributing' },
          ],
        },
      ],
      locales: {
        root: {
          label: 'English',
          lang: 'en',
        },
        es: {
          label: 'Español',
          lang: 'es-CL',
          sidebar: [
            {
              label: 'Primeros Pasos',
              items: [
                { label: '¿Qué es ouroborOS?', slug: 'getting-started/what-is-ouroboros' },
                { label: '¿Por qué ouroborOS?', slug: 'getting-started/why-ouroboros' },
                { label: 'Arquitectura del Sistema', slug: 'getting-started/architecture' },
              ],
            },
            {
              label: 'Instalación',
              items: [
                { label: 'Requisitos', slug: 'installation/requirements' },
                { label: 'Instalación Interactiva (TUI)', slug: 'installation/interactive' },
                { label: 'Instalación Desatendida (YAML)', slug: 'installation/unattended' },
                { label: 'Referencia de Configuración', slug: 'installation/config-reference' },
              ],
            },
            {
              label: 'Gestión del Sistema',
              items: [
                { label: 'Manifiesto system.yaml', slug: 'system/manifest' },
                { label: 'our-pac — Gestor de Paquetes', slug: 'system/our-pac' },
                { label: 'our-snapshot — Snapshots Btrfs', slug: 'system/our-snapshot' },
                { label: 'our-rollback — Rollback', slug: 'system/our-rollback' },
                { label: 'ouroboros-rebase — Rebase', slug: 'system/rebase' },
                { label: 'ouroboros-health — Health Check', slug: 'system/health' },
                { label: 'ouroboros-update — OTA', slug: 'system/ota-updates' },
              ],
            },
            {
              label: 'Escritorio y Wayland',
              items: [
                { label: 'Perfiles de Escritorio', slug: 'desktop/profiles' },
                { label: 'Hyprland', slug: 'desktop/hyprland' },
                { label: 'Niri', slug: 'desktop/niri' },
                { label: 'UI Components y Ricing', slug: 'desktop/ricing' },
                { label: 'Temas y Apariencia', slug: 'desktop/themes' },
                { label: 'Detección de GPU', slug: 'desktop/gpu' },
              ],
            },
            {
              label: 'Contenedores y Apps',
              items: [
                { label: 'our-container — nspawn', slug: 'apps/our-container' },
                { label: 'our-aur — AUR Helper', slug: 'apps/our-aur' },
                { label: 'our-flat — Flatpak', slug: 'apps/our-flat' },
              ],
            },
            {
              label: 'Red y Conectividad',
              items: [
                { label: 'our-wifi — WiFi', slug: 'network/our-wifi' },
                { label: 'our-bluetooth — Bluetooth', slug: 'network/our-bluetooth' },
                { label: 'systemd-networkd', slug: 'network/networkd' },
              ],
            },
            {
              label: 'Seguridad',
              items: [
                { label: 'Secure Boot', slug: 'security/secure-boot' },
                { label: 'FIDO2 / WebAuthn / Passkeys', slug: 'security/fido2' },
                { label: 'Encriptación (LUKS + TPM2)', slug: 'security/luks-tpm2' },
                { label: 'systemd-homed', slug: 'security/homed' },
              ],
            },
            {
              label: 'Solución de Problemas',
              items: [
                { label: 'Rescate y Rollbacks', slug: 'troubleshooting/rescue' },
                { label: 'Logs y Depuración', slug: 'troubleshooting/logs' },
                { label: 'FAQ', slug: 'troubleshooting/faq' },
                { label: 'Limitaciones Conocidas', slug: 'troubleshooting/limitations' },
              ],
            },
            {
              label: 'Visión y Roadmap',
              items: [
                { label: 'La Visión Declarativa', slug: 'roadmap/declarative-vision' },
                { label: 'Phase 5 — system.yaml y OTA', slug: 'roadmap/phase5' },
                { label: 'Phase 6+ — Lo que viene', slug: 'roadmap/phase6' },
                { label: 'Contribuir', slug: 'roadmap/contributing' },
              ],
            },
          ],
        },
      },
      disable404Route: false,
      pagination: true,
      tableOfContents: {
        minHeadingLevel: 2,
        maxHeadingLevel: 4,
      },
      head: [
        {
          tag: 'link',
          rel: 'icon',
          type: 'image/svg+xml',
          href: '/logo-icon.svg',
        },
        {
          tag: 'script',
          attrs: { type: 'text/javascript' },
          content: `(function(){var k='ouroboros-lang';if(document.cookie.indexOf(k+'=')!==-1)return;var p=window.location.pathname;if(p.startsWith('/es'))return;var l=navigator.languages||[navigator.language||'en'];for(var i=0;i<l.length;i++){if(l[i].toLowerCase().startsWith('es')){document.cookie=k+'=es;path=/;max-age='+31536000;window.location.replace('/es'+p);return;}}document.cookie=k+'=en;path=/;max-age='+31536000;})();`,
        },
      ],
    }),
  ],
  vite: {
    server: {
      allowedHosts: ['asus-arch.emperor-betta.ts.net'],
    },
  },
}