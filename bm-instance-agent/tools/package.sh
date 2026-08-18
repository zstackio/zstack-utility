#!/bin/bash

version=`awk -F' = ' '{gsub(/"/,"",$2);print $2}' bm_instance_agent/__init__.py`
bin_name='bm-instance-agent.tar.gz'
agent_name=zstack-bm-agent-`uname -m`-${version}.bin

# Get the shell scirpt's dir
shell_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
pushd ${shell_dir}
. ${shell_dir}/runtime-artifact-common.sh

pushd ${shell_dir}/../

temp=`mktemp -d`
package_items=(
    ./shellinaboxd-x86_64
    ./shellinaboxd-aarch64
    ./shellinaboxd-aarch64-kylin
    ./shellinaboxd-x86_64-kylin
    ./bm-instance-agent.pex
    ./zwatch-vm-agent-x86_64
    ./zwatch-vm-agent-aarch64
    ./service.conf
    ./zstack-baremetal-runtime-agent.service
    ./package-runtime-artifact.sh
    ./runtime-artifact-common.sh
)
pex . -v \
    --disable-cache \
    --no-pypi -i http://mirrors.aliyun.com/pypi/simple \
    --platform current \
    --console-script bm-instance-agent \
    --output-file ${temp}/bm-instance-agent.pex

cp ./tools/shellinaboxd-x86_64 ./tools/shellinaboxd-aarch64 ./tools/shellinaboxd-aarch64-kylin ./tools/shellinaboxd-x86_64-kylin ./tools/zwatch-vm-agent-x86_64 ./tools/zwatch-vm-agent-aarch64 ./tools/service.conf ./tools/zstack-baremetal-runtime-agent.service ./tools/package-runtime-artifact.sh ./tools/runtime-artifact-common.sh ${temp}

if [ -n "${BM_RUNTIME_ARTIFACT_PATH}" ]; then
    expected_target="$(runtime_detect_target)"
    "${shell_dir}/validate-runtime-artifact.sh" "${BM_RUNTIME_ARTIFACT_PATH}" "${expected_target}"
    cp "${BM_RUNTIME_ARTIFACT_PATH}" "${BM_RUNTIME_ARTIFACT_PATH}.sha256" "${temp}"
    package_items+=(
        "./$(basename "${BM_RUNTIME_ARTIFACT_PATH}")"
        "./$(basename "${BM_RUNTIME_ARTIFACT_PATH}.sha256")"
    )
elif [ -n "${BM_RUNTIME_BINARY_PATH}" ]; then
    runtime_target="${BM_RUNTIME_ARTIFACT_TARGET:-$(runtime_detect_target)}"
    runtime_target="$(runtime_normalize_target "${runtime_target}")"
    runtime_version="${BM_RUNTIME_ARTIFACT_VERSION:-}"
    runtime_sha256="${BM_RUNTIME_BINARY_SHA256:-}"
    [ -n "${runtime_version}" ] || {
        echo "BM_RUNTIME_ARTIFACT_VERSION is required when BM_RUNTIME_BINARY_PATH is set" >&2
        exit 1
    }
    [ -n "${runtime_sha256}" ] || {
        echo "BM_RUNTIME_BINARY_SHA256 is required when BM_RUNTIME_BINARY_PATH is set" >&2
        exit 1
    }
    bash "${shell_dir}/package-runtime-artifact.sh" \
        "${BM_RUNTIME_BINARY_PATH}" \
        "${runtime_sha256}" \
        "${runtime_version}" \
        "${runtime_target}" \
        "${temp}" >/dev/null
    runtime_artifact_name="baremetal-runtime-agent-linux-${runtime_target}-v${runtime_version}.tar.gz"
    package_items+=(
        "./${runtime_artifact_name}"
        "./${runtime_artifact_name}.sha256"
    )
fi

tar -C ${temp} -czf ${temp}/${bin_name} "${package_items[@]}"

pushd ${temp}
md5=`md5sum ${bin_name}`
popd

popd
popd

cat ./tools/install.sh ${temp}/${bin_name} > ${agent_name}
sed -i "s/MD5_SUM/${md5}/g" ${agent_name}
chmod +x ${agent_name}
rm -rf ${temp}
