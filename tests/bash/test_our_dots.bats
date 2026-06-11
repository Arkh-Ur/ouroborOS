#!/usr/bin/env bats
# test_our_dots.bats — Unit tests for our-dots helpers and subcommands (UT-B-001 to UT-B-038).
# Requires: bats-core 1.10+, bats-assert, bats-support
#
# Install:
#   git clone https://github.com/bats-core/bats-core.git /opt/bats
#   git clone https://github.com/bats-core/bats-assert.git /opt/bats-assert
#   git clone https://github.com/bats-core/bats-support.git /opt/bats-support
#
# Run:
#   bats tests/bash/test_our_dots.bats

load 'helpers/setup_our_dots'

# Try common bats helper locations
for dir in /opt/bats-support /usr/lib/bats-support /usr/local/lib/bats-support; do
    [[ -f "$dir/load.bash" ]] && { load "$dir/load.bash"; break; }
done
for dir in /opt/bats-assert /usr/lib/bats-assert /usr/local/lib/bats-assert; do
    [[ -f "$dir/load.bash" ]] && { load "$dir/load.bash"; break; }
done

SCRIPT="${BATS_TEST_DIRNAME}/../../src/ouroborOS-profile/airootfs/usr/local/bin/our-dots"

setup() {
    setup_our_dots_env
    create_manifest "testpack" "low" "hyprland"
}

teardown() {
    teardown_our_dots_env
}

# Helper: source script functions with overridden env vars
_source_funcs() {
    # shellcheck disable=SC1090
    MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
    REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
    source "${SCRIPT}"
}

# ── UT-B-001 to UT-B-010: yaml_get / yaml_list ────────────────────────────────

@test "UT-B-001: yaml_get returns root-level scalar field" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_get '${mf}' 'id'
    ")
    assert_equal "$result" "testpack"
}

@test "UT-B-002: yaml_get returns nested field compatibility.immutable" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_get '${mf}' 'compatibility.immutable'
    ")
    assert_equal "$result" "low"
}

@test "UT-B-003: yaml_get exits non-zero for non-existent field" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_get '${mf}' 'nonexistent.field'
    "
    assert_failure
}

@test "UT-B-004: yaml_list returns compatibility.profiles as lines" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_list '${mf}' 'compatibility.profiles'
    ")
    assert_equal "$result" "hyprland"
}

@test "UT-B-005: yaml_list returns empty output without error for empty list" {
    cat > "${MANIFEST_DIR}/empty_list.yaml" <<'YAML'
id: empty
name: Empty
description: d
credits:
  author: a
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: []
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_list '${MANIFEST_DIR}/empty_list.yaml' 'compatibility.profiles'
    "
    assert_success
    assert_output ""
}

@test "UT-B-006: yaml_get returns credits.author nested value" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_get '${mf}' 'credits.author'
    ")
    assert_equal "$result" "Test Author"
}

@test "UT-B-007: yaml_get returns variants.stable.version_hint" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_get '${mf}' 'variants.stable.version_hint'
    ")
    assert_equal "$result" "v1.0"
}

@test "UT-B-008: yaml_list returns packages list items" {
    local mf="${MANIFEST_DIR}/testpack.yaml"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        yaml_list '${mf}' 'variants.stable.packages'
    ")
    assert_equal "$result" "pkg-testpack"
}

# ── UT-B-011 to UT-B-017: find_manifest / derive_channels ────────────────────

@test "UT-B-011: find_manifest returns path to built-in manifest" {
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        find_manifest 'testpack'
    ")
    assert_equal "$result" "${MANIFEST_DIR}/testpack.yaml"
}

@test "UT-B-012: find_manifest exits non-zero when pack not found" {
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        find_manifest 'nonexistent-pack'
    "
    assert_failure
}

@test "UT-B-013: find_manifest prefers built-in over external repo" {
    mkdir -p "${REPOS_DIR}/my-repo"
    cat > "${REPOS_DIR}/my-repo/testpack.yaml" <<YAML
id: testpack
name: External TestPack
description: External version.
credits:
  author: External
  homepage: https://external.example.com
compatibility:
  immutable: medium
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "external"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    cat > "${REPOS_INDEX}" <<YAML
repos:
  - name: my-repo
    url: https://example.com/my-repo.git
YAML
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        find_manifest 'testpack'
    ")
    assert_equal "$result" "${MANIFEST_DIR}/testpack.yaml"
}

@test "UT-B-014: find_manifest finds pack in external repo if not built-in" {
    mkdir -p "${REPOS_DIR}/community-repo"
    cat > "${REPOS_DIR}/community-repo/community-pack.yaml" <<YAML
id: community-pack
name: Community Pack
description: From external repo.
credits:
  author: Community
  homepage: https://community.example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    cat > "${REPOS_INDEX}" <<YAML
repos:
  - name: community-repo
    url: https://example.com/community-repo.git
YAML
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        find_manifest 'community-pack'
    ")
    assert_equal "$result" "${REPOS_DIR}/community-repo/community-pack.yaml"
}

@test "UT-B-015: derive_channels returns 'stable' for stable-only pack" {
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        derive_channels '${MANIFEST_DIR}/testpack.yaml'
    ")
    assert_equal "$result" "stable"
}

@test "UT-B-016: derive_channels returns 'git' for git-only pack" {
    create_git_only_manifest "gitpack"
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        derive_channels '${MANIFEST_DIR}/gitpack.yaml'
    ")
    assert_equal "$result" "git"
}

@test "UT-B-017: derive_channels returns 'stable/git' for pack with both channels" {
    cat > "${MANIFEST_DIR}/both.yaml" <<'YAML'
id: both
name: Both Channels
description: d
credits:
  author: a
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
  git:
    packages: []
    aur: []
    version_hint: "rolling"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    result=$(bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        derive_channels '${MANIFEST_DIR}/both.yaml'
    ")
    assert_equal "$result" "stable/git"
}

# ── UT-B-021 to UT-B-030: CLI subcommands ────────────────────────────────────

@test "UT-B-021: --version prints 'our-dots 0.6.1' and exits 0" {
    run bash "${SCRIPT}" --version
    assert_success
    assert_output "our-dots 0.6.1"
}

@test "UT-B-022: --help exits 0" {
    run bash "${SCRIPT}" --help
    assert_success
}

@test "UT-B-023: unknown subcommand exits 1" {
    run bash "${SCRIPT}" --invalid-command-xyz
    assert_failure
    [ "$status" -eq 1 ]
}

@test "UT-B-024: -Q with empty system.yaml shows '(no packs installed)'" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Q
    assert_success
    assert_output --partial "no packs installed"
}

@test "UT-B-025: -Q with missing system.yaml exits 0 without error" {
    rm -f "${SYSYAML}"
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Q
    assert_success
    assert_output --partial "no packs installed"
}

@test "UT-B-026: -Qs without pattern lists catalog and exits 0" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Qs
    assert_success
    assert_output --partial "testpack"
}

@test "UT-B-027: -Qs with non-matching pattern exits 0 (no error)" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        bash "${SCRIPT}" -Qs "xyznonexistentpattern123"
    assert_success
}

@test "UT-B-028: CRITICAL + --noconfirm without OUROBOROS_ALLOW_CRITICAL exits 1" {
    create_critical_manifest "critpack"
    create_stub_our_pac
    create_stub_our_aur
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        EUID=0 \
        bash "${SCRIPT}" -S critpack --noconfirm
    assert_failure
    assert_output --partial "OUROBOROS_ALLOW_CRITICAL"
}

@test "UT-B-029: CRITICAL + OUROBOROS_ALLOW_CRITICAL=1 skips confirmation panel" {
    create_critical_manifest "critpack"
    create_stub_our_pac
    create_stub_our_aur
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        OUROBOROS_ALLOW_CRITICAL=1 EUID=0 \
        bash "${SCRIPT}" -S critpack --noconfirm
    refute_output --partial "Type 'yes'"
}

@test "UT-B-030: -S without root produces descriptive error" {
    run env \
        MANIFEST_DIR="${MANIFEST_DIR}" REPOS_DIR="${REPOS_DIR}" \
        REPOS_INDEX="${REPOS_INDEX}" SYSYAML="${SYSYAML}" LOG_DIR="${LOG_DIR}" \
        EUID=1000 \
        bash "${SCRIPT}" -S testpack
    assert_failure
    assert_output --partial "root"
}

# ── UT-B-031 to UT-B-038: validate_manifest_schema ──────────────────────────

@test "UT-B-031: validate_manifest_schema returns 0 for valid manifest" {
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${MANIFEST_DIR}/testpack.yaml'
    "
    assert_success
}

@test "UT-B-032: validate_manifest_schema fails when 'id' field is missing" {
    cat > "${TEST_DIR}/no_id.yaml" <<'YAML'
name: No ID Pack
description: Missing id field.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${TEST_DIR}/no_id.yaml'
    "
    assert_failure
    assert_output --partial "missing required field"
}

@test "UT-B-033: validate_manifest_schema fails when compatibility.immutable is missing" {
    cat > "${TEST_DIR}/no_compat.yaml" <<'YAML'
id: no-compat
name: No Compat
description: Missing compatibility.immutable.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${TEST_DIR}/no_compat.yaml'
    "
    assert_failure
    assert_output --partial "compatibility.immutable"
}

@test "UT-B-034: validate_manifest_schema fails when compatibility.immutable has invalid value" {
    cat > "${TEST_DIR}/bad_immutable.yaml" <<'YAML'
id: bad-immutable
name: Bad Immutable
description: d.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: extreme
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${TEST_DIR}/bad_immutable.yaml'
    "
    assert_failure
}

@test "UT-B-035: validate_manifest_schema fails when no variants defined" {
    cat > "${TEST_DIR}/no_variants.yaml" <<'YAML'
id: no-variants
name: No Variants
description: d.
credits:
  author: Test
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants: {}
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${TEST_DIR}/no_variants.yaml'
    "
    assert_failure
    assert_output --partial "variants"
}

@test "UT-B-036: validate_manifest_schema accepts git-only pack as valid" {
    create_git_only_manifest "gitpack"
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${MANIFEST_DIR}/gitpack.yaml'
    "
    assert_success
}

@test "UT-B-037: validate_manifest_schema accepts CRITICAL pack as valid" {
    create_critical_manifest "critpack"
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${MANIFEST_DIR}/critpack.yaml'
    "
    assert_success
}

@test "UT-B-038: validate_manifest_schema fails when credits.author is missing" {
    cat > "${TEST_DIR}/no_author.yaml" <<'YAML'
id: no-author
name: No Author
description: d.
credits:
  homepage: https://example.com
compatibility:
  immutable: low
  profiles: [hyprland]
variants:
  stable:
    packages: []
    aur: []
    version_hint: "v1"
uninstall:
  packages: []
  aur: []
  post_remove: null
  remove_config: false
signature: null
YAML
    run bash -c "
        MANIFEST_DIR='${MANIFEST_DIR}' REPOS_DIR='${REPOS_DIR}'
        REPOS_INDEX='${REPOS_INDEX}' SYSYAML='${SYSYAML}'
        source '${SCRIPT}'
        validate_manifest_schema '${TEST_DIR}/no_author.yaml'
    "
    assert_failure
    assert_output --partial "credits.author"
}
