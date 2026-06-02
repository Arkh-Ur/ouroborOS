# Launch the ouroborOS installer menu on login in the live ISO.
# TTY1: handled by ouroborOS-installer.service (skip to avoid double-launch).
# SSH / other TTYs: auto-launch the menu for root.
if [[ $EUID -eq 0 ]] && [[ "${OUROBOROS_AUTOSTART:-1}" == "1" ]]; then
    [[ -n "${OUROBOROS_SHELL_SESSION:-}" ]] && return 0
    [[ "$(tty)" == "/dev/tty1" ]]          && return 0
    exec /usr/local/bin/ouroboros-install
fi
