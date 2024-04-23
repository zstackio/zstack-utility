#!/bin/bash

# Usage: __Something__ will be replaced by script prepare_mn_mock()

host_ip=__host_ip__
pip_url=__pip_url__
trusted_host=__trusted_host__
zstack_repo=__zstack_repo__
zstack_root=__zstack_root__
pkg_zstacklib=__pkg_zstacklib__
pkg_kvmagent=__pkg_kvmagent__
unittest_flag="true"

cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys

cd /usr/local/zstack/ansible || true
echo ${host_ip} > /usr/local/zstack/ansible/hosts
source /root/venv2/bin/activate
PYTHONPATH=/root/.zguest/zstack-utility/zstacklib/ansible python /root/.zguest/zstack-utility/kvmagent/ansible/kvm.py -i /usr/local/zstack/ansible/hosts -e "{\"host\":\"${host_ip}\",\"pip_url\":\"${pip_url}\",\"trusted_host\":\"${trusted_host}\",\"zstack_repo\":\"${zstack_repo}\",\"zstack_root\":\"${zstack_root}\",\"pkg_zstacklib\":\"${pkg_zstacklib}\",\"pkg_kvmagent\":\"${pkg_kvmagent}\",\"unittest_flag\":\"${unittest_flag}\", \"init\":\"true\"}"
deactivate
