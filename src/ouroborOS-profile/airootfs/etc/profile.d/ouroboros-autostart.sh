# Launch the ouroborOS installer menu on login in the live ISO.
# Runs on all ttys (including tty1) for root autologin.
# If the installer crashes or the user presses ESC/q, they get a shell.
if [[ $EUID -eq 0 ]] && [[ "${OUROBOROS_AUTOSTART:-1}" == "1" ]]; then
    [[ -n "${OUROBOROS_SHELL_SESSION:-}" ]] && return 0
    exec /usr/local/bin/ouroboros-install
fi
