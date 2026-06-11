#!/usr/bin/env bash
# setup_our_dots.bash — Shared setup helpers for our-dots bats tests.

setup_our_dots_env() {
    export TEST_DIR
    TEST_DIR="$(mktemp -d)"
    export MANIFEST_DIR="${TEST_DIR}/packs"
    export REPOS_DIR="${TEST_DIR}/repos"
    export REPOS_INDEX="${TEST_DIR}/dots-repos.yaml"
    export SYSYAML="${TEST_DIR}/system.yaml"
    export LOG_DIR="${TEST_DIR}/logs"
    mkdir -p "$MANIFEST_DIR" "$REPOS_DIR" "$LOG_DIR"
    echo "dots_packs: []" > "$SYSYAML"

    export STUB_DIR="${TEST_DIR}/stubs"
    mkdir -p "$STUB_DIR"
    # Save PATH before prepending stubs so teardown can fully restore it.
    export _OUR_DOTS_SAVED_PATH="${PATH}"
    export PATH="${STUB_DIR}:${PATH}"
}

teardown_our_dots_env() {
    [[ -n "${_OUR_DOTS_SAVED_PATH:-}" ]] && export PATH="${_OUR_DOTS_SAVED_PATH}"
    unset _OUR_DOTS_SAVED_PATH
    rm -rf "${TEST_DIR:-/nonexistent_test_dir_safe}"
}

create_manifest() {
    local id="$1" level="${2:-low}" profile="${3:-hyprland}"
    cat > "${MANIFEST_DIR}/${id}.yaml" <<YAML
id: ${id}
name: Test Pack ${id}
description: Test pack for ${id}.
credits:
  author: Test Author
  homepage: https://example.com/${id}
compatibility:
  immutable: ${level}
  profiles: [${profile}]
variants:
  stable:
    packages: [pkg-${id}]
    aur: []
    post_deploy: null
    version_hint: "v1.0"
uninstall:
  packages: [pkg-${id}]
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
}

create_git_only_manifest() {
    local id="$1" level="${2:-medium}"
    cat > "${MANIFEST_DIR}/${id}.yaml" <<YAML
id: ${id}
name: GitOnly ${id}
description: Git-only test pack.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: ${level}
  profiles: [hyprland]
variants:
  git:
    packages: []
    aur: []
    post_deploy: null
    version_hint: "rolling"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
}

create_critical_manifest() {
    local id="$1"
    cat > "${MANIFEST_DIR}/${id}.yaml" <<YAML
id: ${id}
name: Critical ${id}
description: Critical test pack.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: critical
  profiles: [hyprland]
  warning: |
    This pack makes critical changes.
  critical_actions:
    - "Remount / as read-write"
    - "Edit /etc/pacman.conf"
variants:
  git:
    packages: []
    aur: []
    post_deploy: null
    version_hint: "rolling"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
}

create_stub_our_pac() {
    cat > "${STUB_DIR}/our-pac" <<'BASH'
#!/usr/bin/env bash
echo "[stub our-pac] called with: $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/our-pac"
}

create_stub_our_pac_fail() {
    cat > "${STUB_DIR}/our-pac" <<'BASH'
#!/usr/bin/env bash
echo "[stub our-pac] SIMULATED FAILURE" >&2
exit 1
BASH
    chmod +x "${STUB_DIR}/our-pac"
}

create_stub_our_aur() {
    cat > "${STUB_DIR}/our-aur" <<'BASH'
#!/usr/bin/env bash
echo "[stub our-aur] called with: $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/our-aur"
}

create_stub_git() {
    cat > "${STUB_DIR}/git" <<'BASH'
#!/usr/bin/env bash
echo "[stub git] called with: $*"
exit 0
BASH
    chmod +x "${STUB_DIR}/git"
}
