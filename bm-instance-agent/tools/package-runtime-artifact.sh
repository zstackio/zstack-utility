#!/bin/bash

set -e

shell_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
. "${shell_dir}/runtime-artifact-common.sh"

[ $# -ge 3 ] || {
    echo "usage: $0 <binary-path> <binary-sha256> <version> [target] [output-dir]" >&2
    exit 1
}

runtime_binary_path="$1"
runtime_sha256="$2"
runtime_version="$3"
runtime_target="${4:-$(runtime_detect_target)}"
runtime_output_dir="${5:-$(pwd)}"
runtime_target="$(runtime_normalize_target "${runtime_target}")"
runtime_verify_input_binary "${runtime_binary_path}" "${runtime_sha256}" "${runtime_target}"

artifact_name="baremetal-runtime-agent-linux-${runtime_target}-v${runtime_version}.tar.gz"
artifact_path="${runtime_output_dir}/${artifact_name}"
work_dir="$(mktemp -d)"

cleanup() {
    rm -rf "${work_dir}"
}
trap cleanup EXIT

mkdir -p "${runtime_output_dir}"
cp "${runtime_binary_path}" "${work_dir}/baremetal-runtime-agent"
chmod 0755 "${work_dir}/baremetal-runtime-agent"
tar -czf "${artifact_path}" -C "${work_dir}" baremetal-runtime-agent
sha256sum "${artifact_path}" | awk '{print $1}' > "${artifact_path}.sha256"

echo "artifact=${artifact_path}"
echo "sha256=$(cat "${artifact_path}.sha256")"
