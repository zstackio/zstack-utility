#!/bin/bash

bin_name='bm-instance-agent.tar.gz'
agent_name=zstack-bm-agent-`uname -m`.bin

# Get the shell scirpt's dir
shell_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
pushd ${shell_dir}

pushd ${shell_dir}/../

temp=`mktemp -d`
pex . -v \
    --disable-cache \
    --no-pypi -i http://mirrors.aliyun.com/pypi/simple \
    --platform current \
    --console-script bm-instance-agent \
    --output-file ${temp}/bm-instance-agent.pex

cp ./tools/shellinaboxd-x86_64 ./tools/shellinaboxd-aarch64 ./tools/shellinaboxd-aarch64-kylin ./tools/shellinaboxd-x86_64-kylin ./tools/zwatch-vm-agent-x86_64 ./tools/zwatch-vm-agent-aarch64 ${temp}
tar -C ${temp} -czf ${temp}/${bin_name} ./shellinaboxd-x86_64 ./shellinaboxd-aarch64 ./shellinaboxd-aarch64-kylin ./shellinaboxd-x86_64-kylin ./bm-instance-agent.pex ./zwatch-vm-agent-x86_64 ./zwatch-vm-agent-aarch64

pushd ${temp}
md5=`md5sum ${bin_name}`
popd

popd
popd

cat ./tools/install.sh ${temp}/${bin_name} > ${agent_name}
sed -i "s/MD5_SUM/${md5}/g" ${agent_name}
chmod +x ${agent_name}
rm -rf ${temp}
