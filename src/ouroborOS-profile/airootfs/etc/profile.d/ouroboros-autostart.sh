# Set a Unicode-capable console font (Latin/Cyrillic/Arabic/Hebrew).
if [[ -t 0 ]] && command -v setfont &>/dev/null; then
    setfont LatArCyrHeb-16 2>/dev/null || true
fi

# Launch the ouroborOS installer menu on login in the live ISO.
# Runs on all ttys (including tty1) for root autologin.
# If the installer crashes or the user presses ESC/q, they get a shell.
if [[ $EUID -eq 0 ]] && [[ "${OUROBOROS_AUTOSTART:-1}" == "1" ]]; then
    [[ -n "${OUROBOROS_SHELL_SESSION:-}" ]] && return 0
    exec /usr/local/bin/ouroboros-install
fi
