# Set a Unicode-capable console font with full glyph coverage.
ouroborOS-unifont includes Latin, Cyrillic, Arabic, Hebrew, and Braille.
if [[ -t 0 ]] && command -v setfont &>/dev/null; then
    setfont ouroborOS-unifont 2>/dev/null || setfont LatArCyrHeb-16 2>/dev/null || true
fi

# Launch the ouroborOS installer menu on login in the live ISO.
# Runs on all ttys (including tty1) for root autologin.
# If the installer crashes or the user presses ESC/q, they get a shell.
# IMPORTANT: Do NOT use exec here. If the installer crashes, exec would
# replace the bash process, ending the session. The getty would then restart,
# autologin would trigger, and we would loop forever.
if [[ $EUID -eq 0 ]] && [[ "${OUROBOROS_AUTOSTART:-1}" == "1" ]]; then
    [[ -n "${OUROBOROS_SHELL_SESSION:-}" ]] && return 0
    /usr/local/bin/ouroboros-install
    # If the installer exited (crash or user quit), offer a shell.
    export OUROBOROS_SHELL_SESSION=1
    exec /bin/bash
fi
