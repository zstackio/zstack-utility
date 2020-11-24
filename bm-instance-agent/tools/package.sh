#!/bin/bash

bin_name='bm-instance-agent.tar.gz'

# Get the shell scirpt's dir
shell_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
pushd ${shell_dir}

# Get the git repo's root dir
project_dir=`git rev-parse --show-toplevel`/bm-instance-agent
pushd ${project_dir}

temp=`mktemp -d`
pex . -v \
    --disable-cache \
    --platform current \
    --console-script bm-instance-agent \
    --output-file ${temp}/bm-instance-agent.pex

cp ./tools/shellinaboxd-x86_64 ./tools/shellinaboxd-aarch64 ${temp}
tar -C ${temp} -czf ${temp}/${bin_name} ./shellinaboxd-x86_64 ./shellinaboxd-aarch64 ./bm-instance-agent.pex

pushd ${temp}
md5=`md5sum ${bin_name}`
popd

popd
popd

cat ./tools/install.sh ${temp}/${bin_name} > ./install.bin
sed -i "s/MD5_SUM/${md5}/g" ./install.bin
chmod +x ./install.bin
rm -rf ${temp}
