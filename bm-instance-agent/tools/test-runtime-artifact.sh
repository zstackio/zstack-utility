#!/bin/bash

set -e

shell_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

test_root="$(mktemp -d)"
artifact_root="${test_root}/artifacts"
runtime_home="${test_root}/runtime-home"
mkdir -p "${artifact_root}" "${runtime_home}"
RUNTIME_ROOT="${runtime_home}"
RUNTIME_STATE_DIR="${test_root}/state"

chown() {
    return 0
}

. "${shell_dir}/runtime-artifact-common.sh"

cleanup() {
    rm -rf "${test_root}"
}
trap cleanup EXIT

make_artifact() {
    local target="$1"
    local version="$2"
    local content="$3"
    local build_dir="${test_root}/build-${target}-${version}"
    local artifact_path="${artifact_root}/baremetal-runtime-agent-linux-${target}-v${version}.tar.gz"

    rm -rf "${build_dir}"
    mkdir -p "${build_dir}"
    cat > "${build_dir}/baremetal-runtime-agent" <<EOF
#!/bin/sh
echo ${content}
EOF
    chmod 0755 "${build_dir}/baremetal-runtime-agent"
    tar -czf "${artifact_path}" -C "${build_dir}" baremetal-runtime-agent
    sha256sum "${artifact_path}" | awk '{print $1}' > "${artifact_path}.sha256"
    echo "${artifact_path}"
}

make_packaged_artifact() {
    local target="$1"
    local version="$2"
    local content="$3"
    local binary_path="${test_root}/real-${target}-${version}"
    local stub_dir="${test_root}/stub-${target}-${version}"
    local binary_sha256

    mkdir -p "${stub_dir}"
    cat > "${binary_path}" <<EOF
#!/bin/sh
echo ${content}
EOF
    chmod 0755 "${binary_path}"
    binary_sha256="$(sha256sum "${binary_path}" | awk '{print $1}')"
    cat > "${stub_dir}/file" <<EOF
#!/bin/sh
echo "\$1: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), static-pie linked"
EOF
    chmod 0755 "${stub_dir}/file"
    PATH="${stub_dir}:${PATH}" bash "${shell_dir}/package-runtime-artifact.sh" \
        "${binary_path}" "${binary_sha256}" "${version}" "${target}" "${artifact_root}" >/dev/null
    echo "${artifact_root}/baremetal-runtime-agent-linux-${target}-v${version}.tar.gz"
}

assert_equals() {
    local expected="$1"
    local actual="$2"
    local message="$3"
    if [ "${expected}" != "${actual}" ]; then
        echo "assert failed: ${message}: expected [${expected}] actual [${actual}]" >&2
        exit 1
    fi
}

unsafe_artifact="$(make_artifact x86_64-unknown-linux-musl 1.2.2 shell-script)"
if runtime_install_artifact "${unsafe_artifact}" x86_64-unknown-linux-musl; then
    echo "non-static runtime payload should fail install" >&2
    exit 1
fi
[ ! -e "${RUNTIME_CURRENT_LINK}" ] || {
    echo "failed initial install must not create current release" >&2
    exit 1
}

version_file_stub="${test_root}/version-file-stub"
mkdir -p "${version_file_stub}"
cat > "${version_file_stub}/file" <<'EOF'
#!/bin/sh
echo "$1: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), static-pie linked"
EOF
chmod 0755 "${version_file_stub}/file"
bad_version_binary="${test_root}/bad-version-binary"
printf '#!/bin/sh\necho malformed-version\n' > "${bad_version_binary}"
chmod 0755 "${bad_version_binary}"
bad_version_sha256="$(sha256sum "${bad_version_binary}" | awk '{print $1}')"
if PATH="${version_file_stub}:${PATH}" runtime_verify_input_binary \
    "${bad_version_binary}" "${bad_version_sha256}" x86_64-unknown-linux-musl; then
    echo "malformed runtime version output should fail validation" >&2
    exit 1
fi

good_version_binary="${test_root}/good-version-binary"
printf '#!/bin/sh\necho baremetal-runtime-agent 1.2.3\n' > "${good_version_binary}"
chmod 0755 "${good_version_binary}"
good_version_sha256="$(sha256sum "${good_version_binary}" | awk '{print $1}')"
PATH="${version_file_stub}:${PATH}" runtime_verify_input_binary \
    "${good_version_binary}" "${good_version_sha256}" x86_64-unknown-linux-musl

runtime_verify_input_binary() {
    return 0
}

artifact_v1="$(make_artifact x86_64-unknown-linux-musl 1.2.3 version-123)"
runtime_install_artifact "${artifact_v1}" x86_64-unknown-linux-musl >/dev/null
current_target_v1="$(readlink "${RUNTIME_CURRENT_LINK}")"
current_version_v1="$(cat "${RUNTIME_CURRENT_LINK}/.artifact-version")"
assert_equals "1.2.3" "${current_version_v1}" "current runtime version after first install"
[ -x "${RUNTIME_CURRENT_LINK}/baremetal-runtime-agent" ] || {
    echo "runtime binary missing after install" >&2
    exit 1
}

artifact_v2="$(make_artifact x86_64-unknown-linux-musl 1.2.4 version-124)"
runtime_install_artifact "${artifact_v2}" x86_64-unknown-linux-musl >/dev/null
assert_equals "${current_target_v1}" "$(readlink "${RUNTIME_PREVIOUS_LINK}")" "successful upgrade records previous release"
current_target_v2="$(readlink "${RUNTIME_CURRENT_LINK}")"
current_version_v2="$(cat "${RUNTIME_CURRENT_LINK}/.artifact-version")"
assert_equals "1.2.4" "${current_version_v2}" "current runtime version after upgrade"

runtime_rollback_artifact >/dev/null
assert_equals "${current_target_v1}" "$(readlink "${RUNTIME_CURRENT_LINK}")" "rollback restores previous release"
assert_equals "${current_target_v2}" "$(readlink "${RUNTIME_PREVIOUS_LINK}")" "rollback retains replaced release"
runtime_rollback_artifact >/dev/null
assert_equals "${current_target_v2}" "$(readlink "${RUNTIME_CURRENT_LINK}")" "second rollback swaps releases again"
assert_equals "${current_target_v1}" "$(readlink "${RUNTIME_PREVIOUS_LINK}")" "second rollback restores previous pointer"

artifact_v3="$(make_artifact x86_64-unknown-linux-musl 1.2.5 version-125)"
echo "badchecksum" > "${artifact_v3}.sha256"
if runtime_install_artifact "${artifact_v3}" x86_64-unknown-linux-musl; then
    echo "checksum mismatch should fail upgrade" >&2
    exit 1
fi
assert_equals "${current_target_v2}" "$(readlink "${RUNTIME_CURRENT_LINK}")" "failed upgrade keeps current release"
assert_equals "${current_target_v1}" "$(readlink "${RUNTIME_PREVIOUS_LINK}")" "failed upgrade keeps previous release pointer"

wrong_arch="$(make_artifact aarch64-unknown-linux-musl 1.2.6 version-126)"
if runtime_verify_artifact_contract "${wrong_arch}" x86_64-unknown-linux-musl; then
    echo "wrong architecture artifact should fail validation" >&2
    exit 1
fi

packaged_real="$(make_packaged_artifact x86_64-unknown-linux-musl 2.0.0 'baremetal-runtime-agent 2.0.0')"
runtime_verify_artifact_contract "${packaged_real}" x86_64-unknown-linux-musl >/dev/null

extra_build_dir="${test_root}/build-extra"
extra_artifact="${artifact_root}/baremetal-runtime-agent-linux-x86_64-unknown-linux-musl-v1.2.7.tar.gz"
mkdir -p "${extra_build_dir}"
printf '#!/bin/sh\n' > "${extra_build_dir}/baremetal-runtime-agent"
printf 'unexpected\n' > "${extra_build_dir}/extra-file"
tar -czf "${extra_artifact}" -C "${extra_build_dir}" baremetal-runtime-agent extra-file
sha256sum "${extra_artifact}" | awk '{print $1}' > "${extra_artifact}.sha256"
if runtime_verify_artifact_contract "${extra_artifact}" x86_64-unknown-linux-musl; then
    echo "artifact with extra archive members should fail validation" >&2
    exit 1
fi
