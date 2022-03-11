#!/usr/bin/env python
# encoding=utf-8
import argparse
import os.path
import os
import re
from zstacklib import *
from distutils.version import LooseVersion
from uuid import uuid4

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy kvm agent")
start_time = datetime.now()
# set default value
file_root = "files/kvm"
package_root = "/opt/zstack-dvd/Packages"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
init = 'false'
zstack_repo = 'false'
zstack_apt_source = 'false'
chrony_servers = None
post_url = ""
pkg_kvmagent = ""
libvirtd_status = ""
libvirtd_conf_status = ""
qemu_conf_status = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None
libvirtd_conf_file = "/etc/libvirt/libvirtd.conf"
skip_packages = ""
update_packages = 'false'
zstack_lib_dir = "/var/lib/zstack"
zstack_libvirt_nwfilter_dir = "%s/nwfilter" % zstack_lib_dir
skipIpv6 = 'false'
bridgeDisableIptables = 'false'
isMini = 'false'
isBareMetal2Gateway='false'
releasever = ''


# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy kvm to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')
args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/kvm/" % zstack_root
workplace = "%s/kvm" % zstack_root
kvm_root = "%s/package" % workplace
iproute_pkg = "%s/iproute-2.6.32-130.el6ost.netns.2.x86_64.rpm" % file_root
iproute_local_pkg = "%s/iproute-2.6.32-130.el6ost.netns.2.x86_64.rpm" % kvm_root

host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.host_uuid = host_uuid
host_post_info.post_url = post_url
host_post_info.chrony_servers = chrony_servers
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

(distro, major_version, distro_release, distro_version) = get_remote_host_info(host_post_info)
releasever = get_host_releasever([distro, distro_release, distro_version])
host_post_info.releasever = releasever

# get remote host arch
host_arch = get_remote_host_arch(host_post_info)
IS_AARCH64 = host_arch == 'aarch64'
IS_MIPS64 = host_arch == 'mips64el'

repo_dir = "/opt/zstack-dvd/{}".format(host_arch)
if not os.path.isdir(repo_dir):
    error("Missing directory '{}', please try 'zstack-upgrade -a {}_iso'".format(repo_dir, host_arch))



def update_libvirtd_config(host_post_info):
    # name: copy libvirtd conf to keep environment consistent,only update host_uuid
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirtd.conf" % file_root
    copy_arg.dest =  libvirtd_conf_file
    file_changed_flag = copy(copy_arg, host_post_info)
    replace_content(libvirtd_conf_file, "regexp='#host_uuid.*' replace='host_uuid=\"%s\"'" % uuid4(), host_post_info)

    return file_changed_flag

@with_arch(todo_list=['x86_64'], host_arch=host_arch)
def check_nested_kvm(host_post_info):
    """aarch64 does not need to modprobe kvm"""
    enabled_nested_flag = False
    # enable nested kvm
    command = "cat /sys/module/kvm_intel/parameters/nested"
    (status, stdout) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
    if "Y" in stdout or "1" in stdout:
        enabled_nested_flag = True

    #add kvm module and tun module
    modprobe_arg = ModProbeArg()
    modprobe_arg.name = 'kvm'
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)

    modprobe_arg = ModProbeArg()
    cpu_info = get_remote_host_cpu(host_post_info).lower()
    if 'intel' in cpu_info or 'zhaoxin' in cpu_info:
        # reload kvm_intel for enable nested kvm
        if enabled_nested_flag is False:
            command = "mkdir -p /etc/modprobe.d/ && echo 'options kvm_intel nested=1' >  /etc/modprobe.d/kvm-nested.conf"
            run_remote_command(command, host_post_info)
            command = "modprobe -r kvm_intel"
            run_remote_command(command, host_post_info, return_status=True)
        modprobe_arg.name = 'kvm_intel'
    elif 'amd' in cpu_info or 'hygon' in cpu_info:
        if enabled_nested_flag is False:
            command = "mkdir -p /etc/modprobe.d/ && echo 'options kvm_amd nested=1' >  /etc/modprobe.d/kvm-nested.conf"
            run_remote_command(command, host_post_info)
            command = "modprobe -r kvm_amd"
            run_remote_command(command, host_post_info, return_status=True)
        modprobe_arg.name = 'kvm_amd'
    else:
        handle_ansible_info("Unknown CPU type detected when modprobe kvm", host_post_info, "WARNING")
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)

    modprobe_arg = ModProbeArg()
    modprobe_arg.name = 'tun'
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)

def install_release_on_host(is_rpm):
    # copy and install zstack-release
    if is_rpm:
        src_pkg = '/opt/zstack-dvd/{0}/{1}/Packages/zstack-release-{1}-1.el7.zstack.noarch.rpm'.format(host_arch, releasever)
        install_cmd = "rpm -q zstack-release || rpm -i /opt/zstack-release-{}-1.el7.zstack.noarch.rpm".format(releasever)
    else:
        src_pkg = '/opt/zstack-dvd/{0}/{1}/Packages/zstack-release_{1}_all.deb'.format(host_arch, releasever)
        install_cmd = "dpkg -l zstack-release || dpkg -i /opt/zstack-release_{}_all.deb".format(releasever)
    copy_arg = CopyArg()
    copy_arg.src = src_pkg
    copy_arg.dest = '/opt'
    copy(copy_arg, host_post_info)
    run_remote_command(install_cmd, host_post_info)


def load_zstacklib():
    """include zstacklib.py"""
    zstacklib_args = ZstackLibArgs()
    zstacklib_args.distro = distro
    zstacklib_args.distro_release = distro_release
    zstacklib_args.distro_version = major_version
    zstacklib_args.zstack_root = zstack_root
    zstacklib_args.zstack_repo = zstack_repo
    zstacklib_args.host_post_info = host_post_info
    zstacklib_args.pip_url = pip_url
    zstacklib_args.zstack_releasever = releasever
    zstacklib_args.trusted_host = trusted_host
    if distro in DEB_BASED_OS:
        zstacklib_args.apt_server = yum_server
        zstacklib_args.zstack_apt_source = zstack_repo
    else :
        zstacklib_args.yum_server = yum_server
    zstacklib = ZstackLib(zstacklib_args)

if distro in RPM_BASED_OS:
    install_release_on_host(True)
elif distro in DEB_BASED_OS:
    install_release_on_host(False)
else:
    error("Unsupported OS: {}".format(distro))

load_zstacklib()


# name: judge this process is init install or upgrade
if file_dir_exist("path=" + kvm_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (kvm_root, virtenv_path)
    host_post_info.post_label = "ansible.shell.mkdir"
    host_post_info.post_label_param = "%s, %s" % (kvm_root, virtenv_path)
    run_remote_command(command, host_post_info)

run_remote_command("rm -rf {}/*; mkdir -p /usr/local/zstack/ || true".format(kvm_root), host_post_info)


def install_kvm_pkg():
    def rpm_based_install():
        mlnx_ofed = " python3 unbound libnl3-devel lsof \
                        libibverbs ibacm librdmacm mlnx-ethtool libibumad ofed-scripts mlnx-dpdk infiniband-diags \
                        mlnx-dpdk-tools rdma-core mlnx-ofa_kernel kmod-mlnx-ofa_kernel kmod-iser mlnx-ofa_kernel-devel \
                        rdma-core-devel mstflint kmod-isert mlnx-iproute2 mlnx-dpdk-doc libibverbs-utils librdmacm-utils \
                        mlnx-dpdk-devel openvswitch kmod-srp mlnx-ofed-dpdk-upstream-libs"

        x86_64_c74 = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                      usbredir-server iputils iscsi-initiator-utils libvirt libvirt-client libvirt-python lighttpd lsof \
                      net-tools nfs-utils nmap openssh-clients OpenIPMI-modalias pciutils pv rsync sed \
                      smartmontools sshpass usbutils vconfig wget audit dnsmasq \
                      qemu-kvm-ev collectd-virt OVMF edk2-ovmf mcelog MegaCli storcli Arcconf python-pyudev i40e auxiliary"

        x86_64_c76 = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                      usbredir-server iputils iscsi-initiator-utils libvirt libvirt-client libvirt-python libvirt-admin lighttpd lsof \
                      net-tools nfs-utils nmap openssh-clients OpenIPMI-modalias pciutils pv rsync sed \
                      smartmontools sshpass usbutils vconfig wget audit dnsmasq \
                      qemu-kvm-ev collectd-virt OVMF edk2-ovmf mcelog MegaCli storcli Arcconf python-pyudev seabios-bin nping i40e auxiliary"

        aarch64_ns10 = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                        usbredir-server iputils iscsi-initiator-utils libvirt libvirt-client libvirt-python lighttpd lsof \
                        net-tools nfs-utils nmap openssh-clients OpenIPMI pciutils pv rsync sed nettle \
                        smartmontools sshpass usbutils vconfig wget audit dnsmasq tar \
                        qemu collectd-virt storcli edk2-aarch64 python2-pyudev collectd-disk"

        aarch64_euler20 = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                        usbredir-server iputils iscsi-initiator-utils libvirt libvirt-client libvirt-python lighttpd lsof \
                        net-tools nfs-utils nmap openssh-clients OpenIPMI-modalias pciutils pv rsync sed \
                        smartmontools sshpass usbutils vconfig wget audit dnsmasq \
                        qemu collectd-virt storcli edk2-aarch64 python2-pyudev collectd-disk"

        mips64el_ns10 = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                         usbredir-server iputils iscsi-initiator-utils libvirt libvirt-client libvirt-python lighttpd lsof mcelog \
                         net-tools nfs-utils nmap openssh-clients OpenIPMI-modalias pciutils python2-pyudev pv rsync sed \
                         qemu smartmontools sshpass usbutils vconfig wget audit dnsmasq tuned collectd-virt collectd-disk"

        x86_64_ns10 = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                        usbredir-server iputils iscsi-initiator-utils libvirt libvirt-client libvirt-python lighttpd lsof \
                        net-tools nfs-utils nmap openssh-clients OpenIPMI pciutils pv rsync sed nettle \
                        smartmontools sshpass usbutils vconfig wget audit dnsmasq tar \
                        qemu collectd-virt storcli edk2-ovmf python2-pyudev collectd-disk"

        # handle zstack_repo
        if zstack_repo != 'false':
            common_dep_list = eval("%s_%s" % (host_arch, releasever))
            # common kvmagent deps of x86 and arm that need to update
            common_update_list = "sanlock sysfsutils hwdata sg3_utils lvm2 lvm2-libs lvm2-lockd systemd openssh glusterfs"
            common_no_update_list = "librbd1"
            # common kvmagent deps of x86 and arm that no need to update
            common_dep_list = "%s %s" % (common_dep_list, common_update_list)

            # zstack mini needs higher version kernel etc.
            C76_KERNEL_OR_HIGHER = '3.10.0-957' in get_remote_host_kernel_version(host_post_info)
            if isMini == 'true':
                mini_dep_list = " drbd84-utils kmod-drbd84" if C76_KERNEL_OR_HIGHER and not IS_AARCH64 else ""
                common_dep_list += mini_dep_list

            dep_list = common_dep_list
            update_list = common_update_list
            no_update_list = common_no_update_list

            command = "which virsh"
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "libvirt"
            (status, output) = run_remote_command(command, host_post_info, True, True)

            versions = distro_version.split('.')
            if output and len(versions) > 2 and versions[0] == '7' and versions[1] == '2':
                dep_list = dep_list.replace('libvirt libvirt-client libvirt-python ', '')

            # skip these packages when connect host
            _skip_list = re.split(r'[|;,\s]\s*', skip_packages)
            _dep_list = [ pkg for pkg in dep_list.split() if pkg not in _skip_list ]
            dep_list = ' '.join(_dep_list)

            # name: install/update kvm related packages on RedHat based OS from user defined repo
            command = ("echo {1} >/var/lib/zstack/dependencies && yum --disablerepo=* --enablerepo={0} clean metadata >/dev/null && \
                    pkg_list=`rpm -q {1} | grep \"not installed\" | awk '{{ print $2 }}'`' {2}' && \
                    for pkg in {4}; do yum --disablerepo=* --enablerepo={0} install -y $pkg >/dev/null || exit 1; done; \
                    pkg_list=`rpm -q {3} | grep \"not installed\" | awk '{{ print $2 }}'` && \
                    for pkg in $pkg_list; do yum --disablerepo=* --enablerepo={0} install -y $pkg >/dev/null || exit 1; done; \
                    ").format(zstack_repo, dep_list, update_list, no_update_list, dep_list if update_packages == 'true' else '$pkg_list')
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = dep_list
            run_remote_command(command, host_post_info)
        else:
            # name: install kvm related packages on RedHat based OS from online
            for pkg in ['zstack-release', 'openssh-clients', 'bridge-utils', 'wget', 'chrony', 'sed', 'libvirt-python', 'libvirt', 'nfs-utils', 'vconfig',
                        'libvirt-client', 'net-tools', 'iscsi-initiator-utils', 'lighttpd', 'iproute', 'sshpass',
                        'libguestfs-winsupport', 'libguestfs-tools', 'pv', 'rsync', 'nmap', 'ipset', 'usbutils', 'pciutils', 'expect',
                        'lvm2', 'lvm2-lockd', 'sanlock', 'sysfsutils', 'smartmontools', 'device-mapper-multipath', 'hwdata', 'sg3_utils']:
                yum_install_package(pkg, host_post_info)
            if major_version >= 7:
                # name: RHEL7 specific packages from online
                for pkg in ['qemu-kvm-ev', 'qemu-img-ev', 'collectd-virt']:
                    yum_install_package(pkg, host_post_info)
            else:
                for pkg in ['qemu-kvm', 'qemu-img']:
                    yum_install_package(pkg, host_post_info)

        # handle distro version specific task
        if major_version < 7:
            # name: copy name space supported iproute for RHEL6
            copy_arg = CopyArg()
            copy_arg.src = iproute_pkg
            copy_arg.dest = iproute_local_pkg
            copy(copy_arg, host_post_info)
            # name: Update iproute for RHEL6
            command = "rpm -q iproute-2.6.32-130.el6ost.netns.2.x86_64 || yum install --nogpgcheck -y %s" % iproute_local_pkg
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "iproute-2.6.32-130.el6ost.netns.2.x86_64"
            run_remote_command(command, host_post_info)
            # name: disable NetworkManager in RHEL6 and Centos6
            network_manager_installed = yum_check_package("NetworkManager", host_post_info)
            if network_manager_installed is True:
                service_status("NetworkManager", "state=stopped enabled=no", host_post_info)

        else:
            # name: disable firewalld in RHEL7 and Centos7
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            host_post_info.post_label = "ansible.shell.disable.service"
            host_post_info.post_label_param = "firewalld"
            run_remote_command(command, host_post_info)
            if releasever in enable_networkmanager_list:
                # name: enable NetworkManager in euler20, arm and x86 ns10
                service_status("NetworkManager", "state=started enabled=yes", host_post_info, ignore_error=True)
            else:
                # name: disable NetworkManager in RHEL7 and Centos7
                service_status("NetworkManager", "state=stopped enabled=no", host_post_info, ignore_error=True)

        if init == 'true':
            # name: copy iptables initial rules in RedHat
            copy_arg = CopyArg()
            copy_arg.src = "%s/iptables" % file_root
            copy_arg.dest = "/etc/sysconfig/iptables"
            copy(copy_arg, host_post_info)
            if chroot_env == 'false':
                # name: restart iptables
                # name: workaround RHEL7 iptables service issue
                command = 'mkdir -p /var/lock/subsys/'
                run_remote_command(command, host_post_info)
                service_status("iptables", "state=restarted enabled=yes", host_post_info)

        #we should check libvirtd config file status before restart the service
        libvirtd_conf_status = update_libvirtd_config(host_post_info)
        # in the libvirtd 5.6.0 and later, the libvirtd daemon now prefers to uses systemd socket activation
        command = "libvirtd --version | grep 'libvirtd (libvirt) ' | cut -d ' ' -f 3 | cut -d '(' -f 1"
        (status, libvirtd_version) = run_remote_command(command, host_post_info, False, True)
        if LooseVersion(libvirtd_version) >= LooseVersion('5.6.0'):
            command = 'systemctl mask libvirtd.socket libvirtd-ro.socket libvirtd-admin.socket libvirtd-tls.socket libvirtd-tcp.socket'
            run_remote_command(command, host_post_info)
        if chroot_env == 'false':
            # name: enable libvirt daemon on RedHat based OS
            service_status("libvirtd", "state=started enabled=yes", host_post_info)
            if major_version >= 7:
                # name: enable virtlockd daemon on RedHat based OS
                service_status("virtlockd", "state=stopped enabled=no", host_post_info)
                service_status("virtlogd", "state=started enabled=yes", host_post_info, True)

        #run_remote_command(command, host_post_info)
        # name: disable selinux on RedHat based OS
        set_selinux("state=disabled", host_post_info)
        run_remote_command("setenforce 0 || true", host_post_info)
        # name: copy sysconfig libvirtd conf in RedHat
        copy_arg = CopyArg()
        copy_arg.src = "%s/libvirtd" % file_root
        copy_arg.dest = "/etc/sysconfig/libvirtd"
        libvirtd_status = copy(copy_arg, host_post_info)

        # replace qemu-img binary if qemu-img-ev before 2.12.0 is installed, to fix zstack-11004 / zstack-13594 / zstack-20983
        command = "qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1"
        (status, qemu_img_version) = run_remote_command(command, host_post_info, False, True)
        if qemu_img_version is None or qemu_img_version == '':
            error('cannot get qemu-img version!')
        if LooseVersion(qemu_img_version) < LooseVersion('2.12.0'):
            qemu_img_src = '{}/{}'.format(file_root, "qemu-img" if host_arch == 'x86_64' else "qemu-img_"+host_arch )
            qemu_img_dst = '{}/{}'.format(kvm_root, 'qemu-img')
            copy_to_remote(qemu_img_src, qemu_img_dst, None, host_post_info)

            command = "for i in {1..3}; do /bin/cp %s `which qemu-img` && break || sleep 2; done; sync" % qemu_img_dst
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "qemu-img"
            run_remote_command(command, host_post_info)

    def deb_based_install():
        # name: install kvm related packages on Debian based OS
        install_pkg_list = ['curl', 'qemu', 'qemu-system', 'bridge-utils', 'wget', 'qemu-utils', 'python-libvirt', 
                            'libvirt-daemon-system', 'libfdt-dev', 'libvirt-dev', 'libvirt-clients', 'chrony','vlan', 
                            'libguestfs-tools', 'sed', 'nfs-common', 'open-iscsi','ebtables', 'pv', 'usbutils', 
                            'pciutils', 'expect', 'lighttpd', 'sshpass', 'rsync', 'iputils-arping', 'nmap', 'collectd', 
                            'iptables', 'python-pip', 'dmidecode', 'ovmf', 'dnsmasq', 'auditd', 'ipset',
                            'multipath-tools', 'uuid-runtime', 'lvm2', 'lvm2-lockd', 'udev', 'sanlock', 'usbredirserver', 'python-pyudev']
        apt_install_packages(install_pkg_list, host_post_info)
        if zstack_repo == 'false':
            command_deb_list = "echo %s >/var/lib/zstack/dependencies".format(' '.join(install_pkg_list))
            run_remote_command(command_deb_list, host_post_info)
        # name: copy default libvirtd conf in Debian
        copy_arg = CopyArg()
        copy_arg.src = "%s/libvirt-bin" % file_root
        copy_arg.dest = '/etc/default/libvirt-bin'
        libvirt_bin_status = copy(copy_arg, host_post_info)
        # name: enable bridge forward on UBUNTU
        command = "modprobe br_netfilter"
        host_post_info.post_label = "ansible.shell.enable.module"
        host_post_info.post_label_param = "br_netfilter"
        run_remote_command(command, host_post_info)
        update_pkg_list = ['ebtables', 'python-libvirt', 'qemu-system-arm']
        apt_update_packages(update_pkg_list, host_post_info)
        libvirtd_conf_status = update_libvirtd_config(host_post_info)
        if chroot_env == 'false':
            # name: enable libvirt daemon on RedHat based OS
            service_status("libvirtd", "state=started enabled=yes", host_post_info)
        # name: copy default libvirtd conf in Debian
        copy_arg = CopyArg()
        copy_arg.src = "%s/libvirtd_debian" % file_root
        copy_arg.dest = "/etc/default/libvirtd"
        libvirtd_status = copy(copy_arg, host_post_info)

    if distro in RPM_BASED_OS:
        rpm_based_install()
    elif distro in DEB_BASED_OS:
        deb_based_install()
    else:
        error("unsupported OS!")

def copy_tools():
    """copy binary tools"""
    tool_list = ['collectd_exporter', 'node_exporter', 'dnsmasq', 'zwatch-vm-agent', 'zwatch-vm-agent-freebsd', 'pushgateway', 'sas3ircu', 'zs-raid-heartbeat']
    for tool in tool_list:
        arch_lable = '' if host_arch == 'x86_64' else '_' + host_arch
        real_name = tool + arch_lable
        pkg_path = os.path.join(file_root, real_name)
        if tool == "dnsmasq":
            pkg_dest_path = "/usr/local/zstack/dnsmasq"
        elif tool == "sas3ircu":
            pkg_dest_path = "/usr/bin/sas3ircu"
        else:
            pkg_dest_path = os.path.join(workplace, tool)
        if os.path.exists(pkg_path):
            copy_to_remote(pkg_path, pkg_dest_path, "mode=755", host_post_info)

def copy_kvm_files():
    """copy kvmagent files and packages"""
    global qemu_conf_status, copy_zstacklib_status, copy_kvmagent_status, copy_smart_nics_status

    # copy agent files
    file_list = ["vm-tools.sh", "agent_version", "kvmagent-iptables"]
    for file in file_list:
        _src = os.path.join(file_root, file)
        _dst = os.path.join(workplace, file)
        copy_to_remote(_src, _dst, None, host_post_info)

    # copy qemu configration file
    qemu_conf_src = os.path.join(file_root, "qemu.conf")
    qemu_conf_dst = "/etc/libvirt/qemu.conf"
    qemu_conf_status = copy_to_remote(qemu_conf_src, qemu_conf_dst, None, host_post_info)

    # copy zstacklib pkg
    zslib_src = os.path.join("files/zstacklib", pkg_zstacklib)
    zslib_dst = os.path.join(kvm_root, pkg_zstacklib)
    copy_zstacklib_status = copy_to_remote(zslib_src, zslib_dst, None, host_post_info)

    # copy smart-nics file
    command = 'mkdir -p /usr/local/etc/zstack-ovs/'
    run_remote_command(command, host_post_info)
    smart_nics_src = os.path.join(file_root, "smart-nics.yaml")
    smart_nics_dst = "/usr/local/etc/zstack-ovs/smart-nics.yaml"
    copy_smart_nics_status = copy_to_remote(smart_nics_src, smart_nics_dst, None, host_post_info)

    # copy kvmagent pkg
    kvmagt_src = os.path.join(file_root, pkg_kvmagent)
    kvmagt_dst = os.path.join(kvm_root, pkg_kvmagent)
    copy_kvmagent_status = copy_to_remote(kvmagt_src, kvmagt_dst, None, host_post_info)

    # copy kvmagent service
    kvmagt_svc_src = "files/kvm/zstack-kvmagent"
    kvmagt_svc_dst = "/etc/init.d/"
    args = "mode=755"
    copy_to_remote(kvmagt_svc_src, kvmagt_svc_dst, args, host_post_info)

def copy_gpudriver():
    """copy mxgpu driver"""
    _src = "{}/mxgpu_driver.tar.gz".format(file_root)
    _dst = "/var/lib/zstack/mxgpu_driver.tar.gz"
    copy_to_remote(_src, _dst, None, host_post_info)

def create_virtio_driver_directory():
    _dst_path = "/var/lib/zstack/virtio-drivers/"
    run_remote_command("mkdir -p %s" % _dst_path, host_post_info)

@on_debian_based(distro)
def copy_ovmf_tools():
    _src = "/opt/zstack-dvd/{}/{}/ovmf_tools/".format(host_arch, releasever)
    _dst = "/usr/share/OVMF/"
    copy_to_remote(_src, _dst, None, host_post_info)

@on_debian_based(distro)
def copy_lsusb_scripts():
    _src = os.path.join(file_root, "lsusb.py")
    _dst = "/usr/local/bin/"
    copy_to_remote(_src, _dst, "mode=755", host_post_info)

@on_redhat_based(distro)
def copy_zs_scripts():
    """copy zs-xxx from mn_node to host_node"""
    _src = '/opt/zstack-dvd/{}/{}/scripts/'.format(host_arch, releasever)
    _dst = '/usr/local/bin/'
    copy_to_remote(_src, _dst, None, host_post_info)

@on_redhat_based(distro)
def copy_grubaa64_efi():
    """copy grubaa64.efi from mn_node to bm2 gateway"""
    _src = os.path.join(file_root, "grubaa64.efi")
    _dst = "/tmp/"
    copy_to_remote(_src, _dst, "mode=755", host_post_info)


@on_redhat_based(distro, exclude=['alibaba'])
def set_max_performance():
    # AliOS 7u2 does not support tuned-adm
    command = "tuned-adm profile virtual-host; echo virtual-host > /etc/tuned/active_profile"
    host_post_info.post_label = "ansible.shell.set.tuned.profile"
    host_post_info.post_label_param = "set profile as virtual-host"
    run_remote_command(command, host_post_info)

@on_redhat_based(distro)
def copy_bond_conf():
    """copy bond.conf from mn_node to host_node"""
    _src = os.path.join(file_root, "bond.conf")
    _dst = "/etc/modprobe.d/"
    copy_to_remote(_src, _dst, "mode=644", host_post_info)

def do_libvirt_qemu_config():
    """special configration"""

    # remove libvirt default bridge
    command = '(ip addr show dev virbr0 &> /dev/null && virsh net-destroy default > ' \
              '/dev/null && virsh net-undefine default > /dev/null) || true'
    host_post_info.post_label = "ansible.shell.virsh.destroy.bridge"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

    # delete A2 qemu hook
    command = "rm -f /etc/libvirt/hooks/qemu"
    host_post_info.post_label = "ansible.shell.remove.file"
    host_post_info.post_label_param = "/etc/libvirt/hooks/qemu"
    run_remote_command(command, host_post_info)


def do_network_config():
    """config NetworkManager(fix 40371)"""
    NETWORKMANAGER_CONF_FILE = '/etc/NetworkManager/NetworkManager.conf'
    replace_content(NETWORKMANAGER_CONF_FILE, "regexp='.*no-auto-default=.*' replace='no-auto-default=*'", host_post_info)

    # name: enable bridge forward
    if bridgeDisableIptables == "true":
        command = " [ `sysctl -n net.bridge.bridge-nf-call-iptables` -eq 1 ] && sysctl -w net.bridge.bridge-nf-call-iptables=0 >> /etc/sysctl.conf ; echo 1 > /proc/sys/net/bridge/bridge-nf-filter-vlan-tagged ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
        host_post_info.post_label = "ansible.shell.enable.service"
        host_post_info.post_label_param = "bridge forward"
        run_remote_command(command, host_post_info)
    else:
        command = " [ `sysctl -n net.bridge.bridge-nf-call-iptables` -eq 0 ] && sysctl -w net.bridge.bridge-nf-call-iptables=1 >> /etc/sysctl.conf ; echo 1 > /proc/sys/net/bridge/bridge-nf-filter-vlan-tagged ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
        host_post_info.post_label = "ansible.shell.enable.service"
        host_post_info.post_label_param = "bridge forward"
        run_remote_command(command, host_post_info)

    if skipIpv6 != 'true':
        if distro in RPM_BASED_OS:
            # name: copy ip6tables initial rules in RedHat
            IP6TABLE_SERVICE_FILE = '/usr/lib/systemd/system/ip6tables.service'
            copy_arg = CopyArg()
            copy_arg.src = "%s/ip6tables" % file_root
            copy_arg.dest = "/etc/sysconfig/ip6tables"
            copy(copy_arg, host_post_info)
            replace_content(IP6TABLE_SERVICE_FILE, "regexp='syslog.target,iptables.service' replace='syslog.target iptables.service'", host_post_info)
            service_status("ip6tables", "state=restarted enabled=yes", host_post_info)
        elif distro in DEB_BASED_OS:
            copy_arg = CopyArg()
            copy_arg.src = "%s/ip6tables" % file_root
            copy_arg.dest = "/etc/iptables/rules.v6"
            copy(copy_arg, host_post_info)
            command = "ip6tables-save"
            run_remote_command(command, host_post_info)

        # name: copy libvirt nw-filter
        copy_arg = CopyArg()
        copy_arg.src = "%s/zstack-libvirt-nwfilter/" % file_root
        copy_arg.dest = "%s/" % zstack_libvirt_nwfilter_dir
        copy(copy_arg, host_post_info)
        command = ("(virsh nwfilter-undefine zstack-allow-incoming-ipv6; \
                    virsh nwfilter-define %s/zstack-allow-incoming-ipv6;  \
                    virsh nwfilter-undefine zstack-no-dhcpv6-server;  \
                    virsh nwfilter-define %s/zstack-no-dhcpv6-server;  \
                    virsh nwfilter-undefine zstack-no-ipv6-router-advertisement;  \
                    virsh nwfilter-define %s/zstack-no-ipv6-router-advertisement;  \
                    virsh nwfilter-undefine zstack-no-ipv6-spoofing; \
                    virsh nwfilter-define %s/zstack-no-ipv6-spoofing; \
                    virsh nwfilter-undefine zstack-clean-traffic-ipv6; \
                    virsh nwfilter-define %s/zstack-clean-traffic-ipv6; \
                    virsh nwfilter-undefine zstack-clean-traffic-ip46; \
                    virsh nwfilter-define %s/zstack-clean-traffic-ip46) || true") \
                    % (zstack_libvirt_nwfilter_dir, zstack_libvirt_nwfilter_dir, zstack_libvirt_nwfilter_dir,
                        zstack_libvirt_nwfilter_dir, zstack_libvirt_nwfilter_dir, zstack_libvirt_nwfilter_dir)
        run_remote_command(command, host_post_info)

        # name: enable bridge forward
        command = "echo 1 > /proc/sys/net/bridge/bridge-nf-call-ip6tables ; echo 1 > /proc/sys/net/ipv6/conf/default/forwarding"
        host_post_info.post_label = "ansible.shell.enable.service"
        host_post_info.post_label_param = "bridge forward"
        run_remote_command(command, host_post_info)


def copy_spice_certificates_to_host():
    """copy spice certificates"""

    spice_certificates_path = os.path.join(file_root, "spice-certs")
    if not os.path.isdir(spice_certificates_path):
        return

    if kvm_root is not None:
        run_remote_command("rm -rf %s/%s && mkdir -p %s/%s " % (kvm_root, "spice-certs", kvm_root, "spice-certs"),
                           host_post_info)

    local_cert_dir = os.path.join(file_root, "spice-certs")
    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "ca-cert.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "ca-cert.pem")
    copy_arg.args = "mode=644"
    copy(copy_arg, host_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "ca-key.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "ca-key.pem")
    copy_arg.args = "mode=400"
    copy(copy_arg, host_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "server-cert.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "server-cert.pem")
    copy_arg.args = "mode=644"
    copy(copy_arg, host_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "server-key.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "server-key.pem")
    copy_arg.args = "mode=400"
    copy(copy_arg, host_post_info)

def install_virtualenv():
    """install virtualenv"""

    virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
    if virtual_env_status is False:
        command = "rm -rf %s && rm -rf %s" % (virtenv_path, kvm_root)
        host_post_info.post_label = "ansible.shell.remove.file"
        host_post_info.post_label_param = "%s, %s" % (virtenv_path, kvm_root)
        run_remote_command(command, host_post_info)
        sys.exit(1)
    # name: make sure virtualenv has been setup
    command = "[ -f %s/bin/python ] || virtualenv --system-site-packages %s " % (virtenv_path, virtenv_path)
    host_post_info.post_label = "ansible.shell.check.virtualenv"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

def install_python_pkg():
    extra_args = "\"--trusted-host %s -i %s \"" % (trusted_host, pip_url)
    pip_install_arg = PipInstallArg()
    pip_install_arg.extra_args = extra_args
    pip_install_arg.name = "python-cephlibs"
    pip_install_arg.virtualenv = virtenv_path
    pip_install_package(pip_install_arg, host_post_info)

def install_agent_pkg():
    """install zstacklib and kvmagent on host"""

    if copy_zstacklib_status != "changed:False":
        agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
        agent_install_arg.agent_name = "zstacklib"
        agent_install_arg.agent_root = kvm_root
        agent_install_arg.pkg_name = pkg_zstacklib
        agent_install_arg.virtualenv_site_packages = "yes"
        agent_install(agent_install_arg, host_post_info)

    if copy_kvmagent_status != "changed:False":
        agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
        agent_install_arg.agent_name = "kvm agent"
        agent_install_arg.agent_root = kvm_root
        agent_install_arg.pkg_name = pkg_kvmagent
        agent_install_arg.virtualenv_site_packages = "yes"
        agent_install(agent_install_arg, host_post_info)

@on_debian_based(distro, exclude=['Kylin'])
def set_legacy_iptables_ebtables():
    """set legacy mode if needed"""
    command = "update-alternatives --set iptables /usr/sbin/iptables-legacy;" \
              "update-alternatives --set ebtables /usr/sbin/ebtables-legacy"
    host_post_info.post_label = "ansible.shell.switch.legacy-version"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

 
def do_auditd_config():
    """add audit rules for signals"""
    AUDIT_CONF_FILE = '/etc/audit/auditd.conf'
    AUDIT_NUM_LOG = 50
    replace_content(AUDIT_CONF_FILE, "regexp='num_logs = .*' replace='num_logs = %d'" % AUDIT_NUM_LOG, host_post_info)
    command = "systemctl enable auditd; systemctl restart auditd || true; " \
              "auditctl -D -k zstack_log_kill || true; " \
              "auditctl -a always,exit -F arch=b64 -F a1=9 -S kill -k zstack_log_kill || true; " \
              "auditctl -a always,exit -F arch=b64 -F a1=15 -S kill -k zstack_log_kill || true"
    host_post_info.post_label = "ansible.shell.audit.signal"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

def start_kvmagent():
    if chroot_env != 'false':
        return

    if any(status != "changed:False" for status in [libvirtd_status, libvirtd_conf_status, qemu_conf_status, copy_smart_nics_status]):
        # name: restart libvirtd if status is stop or cfg changed
        service_status("libvirtd", "state=restarted enabled=yes", host_post_info)
    # name: restart kvmagent, do not use ansible systemctl due to kvmagent can start by itself, so systemctl will not know
    # the kvm agent status when we want to restart it to use the latest kvm agent code
    if distro in RPM_BASED_OS and major_version >= 7:
        # NOTE(weiw): dump threads and wait 1 second for dumping
        command = "pkill -USR2 -P 1 -ef 'kvmagent import kdaemon' || true && sleep 1"
        host_post_info.post_label = "ansible.shell.dump.service"
        host_post_info.post_label_param = "zstack-kvmagent"
        run_remote_command(command, host_post_info)
        command = "service zstack-kvmagent stop && service zstack-kvmagent start && chkconfig zstack-kvmagent on"
    elif distro in RPM_BASED_OS:
        command = "service zstack-kvmagent stop && service zstack-kvmagent start && chkconfig zstack-kvmagent on"
    elif distro in DEB_BASED_OS:
        command = "update-rc.d zstack-kvmagent start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-kvmagent stop && service zstack-kvmagent start"
    host_post_info.post_label = "ansible.shell.restart.service"
    host_post_info.post_label_param = "zstack-kvmagent"
    run_remote_command(command, host_post_info)

def modprobe_usb_module():
    command = "modprobe usb-storage; modprobe uas || true"
    host_post_info.post_label = "ansible.shell.modprobe.usb"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

check_nested_kvm(host_post_info)
install_kvm_pkg()
copy_tools()
copy_kvm_files()
copy_gpudriver()
copy_ovmf_tools()
copy_lsusb_scripts()
copy_zs_scripts()
copy_grubaa64_efi()
copy_bond_conf()
create_virtio_driver_directory()
set_max_performance()
do_libvirt_qemu_config()
do_network_config()
copy_spice_certificates_to_host()
install_virtualenv()
install_python_pkg()
set_legacy_iptables_ebtables()
install_agent_pkg()
do_auditd_config()
modprobe_usb_module()
start_kvmagent()

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy kvm agent successful", host_post_info, "INFO")

sys.exit(0)
