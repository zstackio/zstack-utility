#!/bin/bash
set -eu

cd "$(dirname "$0")/.."
if [ "$(getconf GNU_LIBC_VERSION)" != "glibc 2.17" ]; then
    echo "Build on manylinux2014 for compatibility with EL7." >&2
    exit 1
fi
arch=$(uname -m)
version=$(awk -F'"' '/^__version__ = / {print $2}' bm_instance_agent/__init__.py)
agent_name="zstack-bm-agent-${arch}-${version}.bin"
temp=$(mktemp -d ./.bm-package-XXXXXX)
trap 'rm -rf "$temp"' EXIT

# Oslo requires a newer netaddr than the shared zstacklib pin.
python3.11 -m pex . ../zstacklib --exclude xms-client \
    --python "$(command -v python3.11)" --scie eager \
    --scie-python-version 3.11.18 --scie-pbs-release 20261110 --scie-pbs-stripped \
    --pip-version 24.0 --resolver-version pip-2020-resolver \
    --override 'netaddr==0.8.0' --console-script bm-instance-agent -o "$temp/bm-instance-agent"
mv "$temp/bm-instance-agent" "$temp/bm-instance-agent.pex"

tar -czf "$temp/bm-instance-agent.tar.gz" -C "$temp" bm-instance-agent.pex \
    -C "$PWD/tools" "shellinaboxd-$arch" "shellinaboxd-$arch-kylin" \
    "zwatch-vm-agent-$arch" service.conf
checksum=$(cd "$temp" && md5sum bm-instance-agent.tar.gz)
sed "s/MD5_SUM/$checksum/" tools/install.sh > "$temp/$agent_name"
cat "$temp/bm-instance-agent.tar.gz" >> "$temp/$agent_name"
chmod +x "$temp/$agent_name"
ln "$temp/$agent_name" "$agent_name"
