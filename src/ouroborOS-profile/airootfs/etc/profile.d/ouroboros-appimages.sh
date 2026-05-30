# ouroborOS — expose AppImage data dir (managed by our-app) to XDG.
# Sourced by /etc/profile at login. Adds /var/lib/ouroboros/appimages/share to
# XDG_DATA_DIRS so .desktop entries and icons for installed AppImages are picked
# up by application launchers without writing to the immutable /usr.
# NOTE: this is a sourced login snippet — it must NOT use `set -euo pipefail`.

case ":${XDG_DATA_DIRS:-}:" in
    *:/var/lib/ouroboros/appimages/share:*) ;;
    *) export XDG_DATA_DIRS="/var/lib/ouroboros/appimages/share${XDG_DATA_DIRS:+:${XDG_DATA_DIRS}}" ;;
esac
