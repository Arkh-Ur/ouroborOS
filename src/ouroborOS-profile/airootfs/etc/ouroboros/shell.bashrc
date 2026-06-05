# ouroborOS — interactive shell drop from the installer menu.
# Sourced via `bash --rcfile` by /usr/local/bin/ouroboros-install.
# This is an interactive rcfile, NOT a standalone script: no `set -euo pipefail`
# (it would make the live shell exit on the first non-zero command).

# Guard so /etc/profile.d/ouroboros-autostart.sh does not re-launch the menu.
export OUROBOROS_SHELL_SESSION=1

source /etc/profile 2>/dev/null || true
source ~/.bashrc 2>/dev/null || true

printf "\n  Type 'ouroboros-install' to return to the installer menu.\n\n"
