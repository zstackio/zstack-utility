#!/bin/bash
set -ex

# prepare_env.sh: Ztest uses this script to mock mn environment and install kvmagent.
# Usage: arch_os="aarch64:ky10sp2" version="4.6.31" bash prepare_env.sh
# Param arch_os : arch and os splited by ":"
# Param version : like 4.6.31


YUM_BASED_OS="c76 ky10sp2"
APT_BASED_OS=""

# /root/.zguest/zstack-utility is zstack-utility home of ztest.
SCRIPTS_HOME="/root/.zguest/zstack-utility/kvmagent/kvmagent/test/unittest_tools"


validate_necessary_parameters() {
    if [ -z "${arch_os}" ] || [ -z "${version}" ];then
        echo "Error: params needed is empty: arch_os:[${arch_os}] version:[${arch_os}]"
        exit 1
    fi
    arch=$(echo $arch_os | awk -F ':' '{print $1}')
    os=$(echo $arch_os | awk -F ':' '{print $2}')
}
validate_necessary_parameters


prepare_external_repo() {
    cd /root/
    if [[ ${YUM_BASED_OS} =~ ${os} ]];then
        if [ "$arch_os" == "x86_64:c76" ]; then
            wget -O /etc/yum.repos.d/epel.repo http://192.168.200.114:9001/download/prsystem/UtilityUT/epel-7.repo
            wget -O /etc/yum.repos.d/CentOS-Base.repo http://192.168.200.114:9001/download/prsystem/UtilityUT/Centos-7.repo
        fi
        if [ "$arch_os" == "aarch64:ky10sp2" ]; then
            echo later to add
        fi
        if [ -f "/etc/yum.repos.d/CentOS-Base.repo" ]; then
            sed -i '/mirrors\.aliyuncs\.com/d' /etc/yum.repos.d/CentOS-Base.repo
            sed -i '/mirrors\.cloud\.aliyuncs\.com/d' /etc/yum.repos.d/CentOS-Base.repo
        fi
    fi
    if [[ ${APT_BASED_OS} =~ ${os} ]]; then
        echo later to add
    fi
    echo "==>> prepare_external_repo"
}
prepare_external_repo


prepare_internal_repo() {
    cd /root/
    if [[ ${YUM_BASED_OS} =~ ${os} ]];then
        rm -f /etc/yum.repos.d/qemu-kvm-ev.repo || true
        cp ${SCRIPTS_HOME}/qemu-kvm-ev.repo /etc/yum.repos.d/
        # 172.20.197.206 mirrors.rpms.zstack.io
        if [ "$(curl -I -m 10 -o /dev/null -s -w \%{http_code} 172.20.197.206/${arch}/${os}/${version})" == "404" ]; then
            echo "======================WARNING======================"
            echo "Mirror of ZStack Version: ${version} does not exist. Use Version: 4.6.21 as YUM2"
            version="4.6.21"
        fi
        sed -i "s/__ARCH__/${arch}/g" /etc/yum.repos.d/qemu-kvm-ev.repo
        sed -i "s/__OS__/${os}/g" /etc/yum.repos.d/qemu-kvm-ev.repo
        sed -i "s/__VERSION__/${version}/g" /etc/yum.repos.d/qemu-kvm-ev.repo
    fi
    if [[ ${APT_BASED_OS} =~ ${os} ]]; then
        echo later to add
    fi
    echo "==>> prepare_internal_repo"
}
prepare_internal_repo


prepare_mn_mock() {
    cd /root/
    mkdir -p ~/.pip/
    wget -c http://minio.zstack.io:9001/download/prsystem/UtilityUT/pip.conf -O pip.conf || true
    mv pip.conf ~/.pip/ || true

    # wget -c http://minio.zstack.io:9001/download/prsystem/UtilityUT/get-pip.py -O get-pip.py
    cd /root/.zguest/zstack-utility/kvmagent/kvmagent/test/unittest_tools/unittest_pypi_source/
    pip install -r requirements/requirements1.txt -i file://`pwd`/pypi/simple
    pip install -r requirements/requirements2.txt -i file://`pwd`/pypi/simple
    virtualenv --version || pip install virtualenv==12.1.1
    cd /root
    python2_path=$(which python)
    rm -rf venv
    virtualenv -p "$python2_path" venv
    # in virtualenv
    source /root/venv/bin/activate
    cd /root/.zguest/zstack-utility/kvmagent/kvmagent/test/unittest_tools/unittest_pypi_source/
    pip install pip==20.3.4 -i file://`pwd`/pypi/simple
    pip install setuptools==44.1.1 -i file://`pwd`/pypi/simple
    # prepare_zstacklib 
    cd /root/.zguest/zstack-utility/zstacklib/
    bash install.sh -i file:///root/.zguest/zstack-utility/zstackbuild/pypi_source/pypi/simple
    ZSTACKLIB_TAR=$(basename dist/zstacklib-?*.tar.gz)
    \cp dist/zstacklib-?*.tar.gz ansible/
    mkdir -p /usr/local/zstack/ansible/files/zstacklib/
    \cp -r ansible/* /usr/local/zstack/ansible/files/zstacklib/
    # prepare_kvmagent
    cd /root/.zguest/zstack-utility/kvmagent/
    bash install.sh -i file:///root/.zguest/zstack-utility/zstackbuild/pypi_source/pypi/simple
    KVMAGENT_TAR=$(basename dist/kvmagent-?*.tar.gz)
    \cp dist/kvmagent-?*.tar.gz ansible/
    \cp zstack-kvmagent ansible/
    mkdir -p /usr/local/zstack/ansible/files/kvm/
    \cp -rL ansible/* /usr/local/zstack/ansible/files/kvm/
    deactivate
    # in system env
    cd /root
    # python get-pip.py
    yum --disablerepo=* --enablerepo=zstack-local,qemu-kvm-ev install -y openssl-devel openssl libffi libffi-devel
    umount /tmp
    mkdir -p /tmp
    cd /root/.zguest/zstack-utility/kvmagent/kvmagent/test/unittest_tools/unittest_pypi_source/
    pip install -r requirements/requirements3.txt -i file://`pwd`/pypi/simple
    pip2 install ansible==4.10.0 -i file:///root/.zguest/zstack-utility/zstackbuild/pypi_source/pypi/simple
    echo "==>> pass prepare_mn_mock"
}
prepare_mn_mock


install_kvm() {
    local ip
    # mark: grep law may change.
    ip="$(ip -4 a | grep inet | awk '{print $2}' | grep "192.168.100." | sed 's/\/.*//g')"
    if [ "${ip}" == "" ]; then
        echo "Ztest govirt error. No vm ip found."
    fi
    sed -i "s/__host_ip__/\"${ip}\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    sed -i "s/__pip_url__/\"file:\/\/\/root\/.zguest\/zstack-utility\/zstackbuild\/pypi_source\/pypi\/simple\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    sed -i "s/__trusted_host__/\"${ip}\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    sed -i "s/__zstack_repo__/\"qemu-kvm-ev\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    sed -i "s/__zstack_root__/\"\/var\/lib\/zstack\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    sed -i "s/__pkg_zstacklib__/\"${ZSTACKLIB_TAR}\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    sed -i "s/__pkg_kvmagent__/\"${KVMAGENT_TAR}\"/g" ${SCRIPTS_HOME}/install_kvm.sh
    bash ${SCRIPTS_HOME}/install_kvm.sh
    echo "==>> pass install_kvm"
    # "pip_url":"http://172.25.103.91:8686/simple/"
    # "trusted_host":"172.25.103.91"
    # markkkk + zstack_internal.repo
    # need to figure out the relationship between qemu-kvm-ev(-mn) and mirrors.rpms.zstack.io
    # qemu-kvm-ev-mn is a remote yum server like 
    # http://172.25.12.75:8080/zstack/static/zstack-repo/$basearch/$YUM0/Extra/qemu-kvm-ev/
    # qemu-kvm-ev is a local yum server like
    # file:///opt/zstack-dvd/$basearch/$YUM0/Extra/qemu-kvm-ev
    # "zstack_root":"/var/lib/zstack"
    # "pkg_zstacklib":"zstacklib-4.6.0.tar.gz"
    # "pkg_kvmagent":"kvmagent-4.6.0.tar.gz"
}
install_kvm
