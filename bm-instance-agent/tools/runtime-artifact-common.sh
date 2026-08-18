#!/bin/bash

RUNTIME_ROOT="${RUNTIME_ROOT:-/var/lib/zstack/baremetalv2/runtime}"
RUNTIME_RELEASES_DIR="${RUNTIME_ROOT}/releases"
RUNTIME_CURRENT_LINK="${RUNTIME_ROOT}/current"
RUNTIME_PREVIOUS_LINK="${RUNTIME_ROOT}/previous"
RUNTIME_BINARY_LINK="${RUNTIME_ROOT}/baremetal-runtime-agent"
RUNTIME_MOUNT_FACTS_DIR="${RUNTIME_ROOT}/mount-facts.d"
RUNTIME_SOCKET_PATH="${RUNTIME_ROOT}/runtime.sock"
RUNTIME_STATE_DIR="${RUNTIME_STATE_DIR:-/var/lib/zstack/baremetal-runtime/state}"
RUNTIME_MAX_REQUEST_BYTES="${RUNTIME_MAX_REQUEST_BYTES:-4194304}"
RUNTIME_MAX_RESPONSE_BYTES="${RUNTIME_MAX_RESPONSE_BYTES:-4194304}"

runtime_fail() {
    echo "runtime artifact error: $*" >&2
    return 1
}

runtime_normalize_arch() {
    case "$1" in
        x86_64|amd64)
            echo "x86_64"
            ;;
        aarch64|arm64)
            echo "aarch64"
            ;;
        *)
            runtime_fail "unsupported runtime artifact architecture [$1]"
            ;;
    esac
}

runtime_normalize_target() {
    case "$1" in
        x86_64-unknown-linux-musl|aarch64-unknown-linux-musl)
            echo "$1"
            ;;
        x86_64|amd64)
            echo "x86_64-unknown-linux-musl"
            ;;
        aarch64|arm64)
            echo "aarch64-unknown-linux-musl"
            ;;
        *)
            runtime_fail "unsupported runtime artifact target [$1]"
            ;;
    esac
}

runtime_detect_arch() {
    runtime_normalize_arch "${1:-$(uname -m)}"
}

runtime_detect_target() {
    runtime_normalize_target "${1:-$(uname -m)}"
}

runtime_target_arch() {
    case "$1" in
        x86_64-unknown-linux-musl)
            echo "x86_64"
            ;;
        aarch64-unknown-linux-musl)
            echo "aarch64"
            ;;
        *)
            runtime_fail "unsupported runtime artifact target [$1]"
            ;;
    esac
}

runtime_parse_artifact_metadata() {
    local artifact_name
    artifact_name="$(basename "$1")"
    if [[ ! "${artifact_name}" =~ ^baremetal-runtime-agent-linux-(x86_64-unknown-linux-musl|aarch64-unknown-linux-musl)-v([A-Za-z0-9][A-Za-z0-9._-]*)\.tar\.gz$ ]]; then
        runtime_fail "artifact name must match baremetal-runtime-agent-linux-<target>-v<version>.tar.gz"
        return 1
    fi

    RUNTIME_ARTIFACT_TARGET="${BASH_REMATCH[1]}"
    RUNTIME_ARTIFACT_ARCH="$(runtime_target_arch "${RUNTIME_ARTIFACT_TARGET}")"
    RUNTIME_ARTIFACT_VERSION="${BASH_REMATCH[2]}"
    return 0
}

runtime_read_sha256_sidecar() {
    local sidecar="$1"
    local first_line

    [ -f "${sidecar}" ] || {
        runtime_fail "missing checksum sidecar [${sidecar}]"
        return 1
    }

    first_line="$(head -n 1 "${sidecar}" | tr -d '\r')"
    case "${first_line}" in
        *"  "*|*" "*"*"*)
            awk '{print $1}' "${sidecar}" | head -n 1
            ;;
        *)
            echo "${first_line}" | tr -d '[:space:]'
            ;;
    esac
}

runtime_verify_artifact_contract() {
    local artifact_path="$1"
    local expected_target="${2:-}"
    local actual_sha256
    local expected_sha256
    local artifact_members

    [ -f "${artifact_path}" ] || {
        runtime_fail "runtime artifact [${artifact_path}] not found"
        return 1
    }

    runtime_parse_artifact_metadata "${artifact_path}" || return 1
    if [ -n "${expected_target}" ] && [ "${RUNTIME_ARTIFACT_TARGET}" != "${expected_target}" ]; then
        runtime_fail "artifact target [${RUNTIME_ARTIFACT_TARGET}] does not match host [${expected_target}]"
        return 1
    fi

    expected_sha256="$(runtime_read_sha256_sidecar "${artifact_path}.sha256")" || return 1
    actual_sha256="$(sha256sum "${artifact_path}" | awk '{print $1}')"
    if [ "${expected_sha256}" != "${actual_sha256}" ]; then
        runtime_fail "artifact checksum mismatch for [${artifact_path}]"
        return 1
    fi

    artifact_members="$(tar -tzf "${artifact_path}" 2>/dev/null)" || {
        runtime_fail "artifact [${artifact_path}] is not a readable gzip tar archive"
        return 1
    }
    case "${artifact_members}" in
        baremetal-runtime-agent|./baremetal-runtime-agent)
            ;;
        *)
            runtime_fail "artifact [${artifact_path}] must contain only baremetal-runtime-agent at archive root"
            return 1
            ;;
    esac

    RUNTIME_ARTIFACT_SHA256="${actual_sha256}"
    return 0
}

runtime_verify_input_binary() {
    local binary_path="$1"
    local expected_sha256="$2"
    local expected_target="$3"
    local actual_sha256
    local file_output
    local version_output

    [ -f "${binary_path}" ] || {
        runtime_fail "runtime binary [${binary_path}] not found"
        return 1
    }

    actual_sha256="$(sha256sum "${binary_path}" | awk '{print $1}')"
    if [ "${actual_sha256}" != "${expected_sha256}" ]; then
        runtime_fail "runtime binary checksum mismatch for [${binary_path}]"
        return 1
    fi

    file_output="$(file "${binary_path}")"
    echo "${file_output}" | grep -Eq 'static-pie linked|statically linked' || {
        runtime_fail "runtime binary must be statically linked musl material"
        return 1
    }

    case "${expected_target}" in
        x86_64-unknown-linux-musl)
            echo "${file_output}" | grep -q 'x86-64' || {
                runtime_fail "runtime binary file type does not match target [${expected_target}]"
                return 1
            }
            ;;
        aarch64-unknown-linux-musl)
            echo "${file_output}" | grep -Eiq 'aarch64|arm64' || {
                runtime_fail "runtime binary file type does not match target [${expected_target}]"
                return 1
            }
            ;;
    esac

    version_output="$("${binary_path}" --version 2>&1)" || {
        runtime_fail "runtime binary version smoke failed for [${binary_path}]"
        return 1
    }
    echo "${version_output}" | grep -Eq '^baremetal-runtime-agent [0-9]+\.[0-9]+\.[0-9]+$' || {
        runtime_fail "runtime binary returned malformed version output [${version_output}]"
        return 1
    }
}

runtime_prepare_directories() {
    mkdir -p "${RUNTIME_ROOT}" \
        "${RUNTIME_RELEASES_DIR}" \
        "${RUNTIME_MOUNT_FACTS_DIR}" \
        "${RUNTIME_STATE_DIR}"
    chown root:root "${RUNTIME_ROOT}" \
        "${RUNTIME_RELEASES_DIR}" \
        "${RUNTIME_MOUNT_FACTS_DIR}" \
        "${RUNTIME_STATE_DIR}"
    chmod 0755 "${RUNTIME_ROOT}" \
        "${RUNTIME_RELEASES_DIR}" \
        "${RUNTIME_MOUNT_FACTS_DIR}" \
        "${RUNTIME_STATE_DIR}"
}

runtime_install_artifact() {
    local artifact_path="$1"
    local expected_target="${2:-$(runtime_detect_target)}"
    local release_name
    local release_dir
    local staging_dir
    local previous_target
    local tmp_link
    local binary_sha256

    runtime_prepare_directories || return 1
    runtime_verify_artifact_contract "${artifact_path}" "${expected_target}" || return 1

    release_name="${RUNTIME_ARTIFACT_VERSION}-${RUNTIME_ARTIFACT_TARGET}-${RUNTIME_ARTIFACT_SHA256:0:12}"
    release_dir="${RUNTIME_RELEASES_DIR}/${release_name}"
    staging_dir="${RUNTIME_RELEASES_DIR}/.staging-${release_name}-$$"
    previous_target="$(readlink "${RUNTIME_CURRENT_LINK}" 2>/dev/null || true)"

    rm -rf "${staging_dir}"
    mkdir -p "${staging_dir}" || return 1
    tar -xzf "${artifact_path}" -C "${staging_dir}" || {
        rm -rf "${staging_dir}"
        return 1
    }
    [ -f "${staging_dir}/baremetal-runtime-agent" ] \
        && [ ! -L "${staging_dir}/baremetal-runtime-agent" ] || {
        rm -rf "${staging_dir}"
        runtime_fail "artifact payload is not a regular baremetal-runtime-agent binary"
        return 1
    }

    binary_sha256="$(sha256sum "${staging_dir}/baremetal-runtime-agent" | awk '{print $1}')"
    runtime_verify_input_binary \
        "${staging_dir}/baremetal-runtime-agent" \
        "${binary_sha256}" \
        "${RUNTIME_ARTIFACT_TARGET}" || {
        rm -rf "${staging_dir}"
        return 1
    }

    chmod 0755 "${staging_dir}/baremetal-runtime-agent"
    chown root:root "${staging_dir}/baremetal-runtime-agent"
    printf '%s\n' "${RUNTIME_ARTIFACT_VERSION}" > "${staging_dir}/.artifact-version"
    printf '%s\n' "${RUNTIME_ARTIFACT_TARGET}" > "${staging_dir}/.artifact-target"
    printf '%s\n' "${RUNTIME_ARTIFACT_ARCH}" > "${staging_dir}/.artifact-arch"
    printf '%s\n' "${RUNTIME_ARTIFACT_SHA256}" > "${staging_dir}/.artifact-sha256"
    chown root:root "${staging_dir}/.artifact-version" \
        "${staging_dir}/.artifact-target" \
        "${staging_dir}/.artifact-arch" \
        "${staging_dir}/.artifact-sha256"
    chmod 0644 "${staging_dir}/.artifact-version" \
        "${staging_dir}/.artifact-target" \
        "${staging_dir}/.artifact-arch" \
        "${staging_dir}/.artifact-sha256"

    if [ -e "${release_dir}" ]; then
        rm -rf "${staging_dir}"
        runtime_fail "release [${release_name}] already installed"
        return 1
    fi

    mv "${staging_dir}" "${release_dir}" || {
        rm -rf "${staging_dir}"
        return 1
    }

    tmp_link="${RUNTIME_CURRENT_LINK}.new"
    ln -sfn "${release_dir}" "${tmp_link}" && mv -Tf "${tmp_link}" "${RUNTIME_CURRENT_LINK}" || {
        [ -n "${previous_target}" ] && ln -sfn "${previous_target}" "${RUNTIME_CURRENT_LINK}"
        runtime_fail "failed to switch current runtime release"
        return 1
    }

    tmp_link="${RUNTIME_BINARY_LINK}.new"
    ln -sfn "${RUNTIME_CURRENT_LINK}/baremetal-runtime-agent" "${tmp_link}" && mv -Tf "${tmp_link}" "${RUNTIME_BINARY_LINK}" || {
        [ -n "${previous_target}" ] && ln -sfn "${previous_target}" "${RUNTIME_CURRENT_LINK}"
        runtime_fail "failed to switch runtime binary link"
        return 1
    }

    if [ -n "${previous_target}" ]; then
        tmp_link="${RUNTIME_PREVIOUS_LINK}.new"
        ln -sfn "${previous_target}" "${tmp_link}" && mv -Tf "${tmp_link}" "${RUNTIME_PREVIOUS_LINK}" || return 1
    fi

    echo "${release_dir}"
    return 0
}

runtime_rollback_artifact() {
    local current_target
    local previous_target
    local tmp_link

    current_target="$(readlink "${RUNTIME_CURRENT_LINK}" 2>/dev/null || true)"
    previous_target="$(readlink "${RUNTIME_PREVIOUS_LINK}" 2>/dev/null || true)"
    [ -n "${current_target}" ] && [ -n "${previous_target}" ] || {
        runtime_fail "current and previous runtime releases are required for rollback"
        return 1
    }
    [ "${current_target}" != "${previous_target}" ] || {
        runtime_fail "current and previous runtime releases are identical"
        return 1
    }
    case "${current_target}" in
        "${RUNTIME_RELEASES_DIR}"/*) ;;
        *) runtime_fail "current runtime release is outside the managed release directory"; return 1 ;;
    esac
    case "${previous_target}" in
        "${RUNTIME_RELEASES_DIR}"/*) ;;
        *) runtime_fail "previous runtime release is outside the managed release directory"; return 1 ;;
    esac
    [ -x "${current_target}/baremetal-runtime-agent" ] \
        && [ -x "${previous_target}/baremetal-runtime-agent" ] || {
        runtime_fail "rollback runtime release is incomplete"
        return 1
    }

    tmp_link="${RUNTIME_CURRENT_LINK}.rollback"
    ln -sfn "${previous_target}" "${tmp_link}" \
        && mv -Tf "${tmp_link}" "${RUNTIME_CURRENT_LINK}" || {
        runtime_fail "failed to switch current runtime release during rollback"
        return 1
    }

    tmp_link="${RUNTIME_PREVIOUS_LINK}.rollback"
    ln -sfn "${current_target}" "${tmp_link}" \
        && mv -Tf "${tmp_link}" "${RUNTIME_PREVIOUS_LINK}" || {
        ln -sfn "${current_target}" "${RUNTIME_CURRENT_LINK}"
        runtime_fail "failed to update previous runtime release during rollback"
        return 1
    }
    echo "${previous_target}"
}

runtime_find_packaged_artifact() {
    local search_dir="$1"
    local expected_target="${2:-$(runtime_detect_target)}"
    find "${search_dir}" -maxdepth 1 -type f \
        -name "baremetal-runtime-agent-linux-${expected_target}-v*.tar.gz" \
        | sort \
        | head -n 1
}
