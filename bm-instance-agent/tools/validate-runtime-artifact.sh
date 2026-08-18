#!/bin/bash

set -e

shell_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
. "${shell_dir}/runtime-artifact-common.sh"

[ $# -ge 1 ] || {
    echo "usage: $0 <artifact.tar.gz> [expected-target]" >&2
    exit 1
}

expected_target=""
if [ $# -ge 2 ]; then
    expected_target="$(runtime_normalize_target "$2")"
fi

runtime_verify_artifact_contract "$1" "${expected_target}"
echo "artifact=${1}"
echo "target=${RUNTIME_ARTIFACT_TARGET}"
echo "arch=${RUNTIME_ARTIFACT_ARCH}"
echo "version=${RUNTIME_ARTIFACT_VERSION}"
echo "sha256=${RUNTIME_ARTIFACT_SHA256}"
