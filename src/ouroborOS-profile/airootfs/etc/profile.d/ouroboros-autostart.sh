# Launch the ouroborOS installer menu on TTY1 login in the live ISO.
# Other TTYs (tty2..tty6) drop straight to a bash shell.
if [[ "$(tty)" == "/dev/tty1" ]] && [[ "${OUROBOROS_AUTOSTART:-1}" == "1" ]]; then
    exec /usr/local/bin/ouroboros-install
fi
