#!/usr/bin/env python
# encoding=utf-8
import argparse
from zstacklib import *

start_time = datetime.now()
# set default value
file_root = "files/kvm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
init = 'false'
yum_repo = 'false'
post_url = ""
pkg_kvmagent = ""
libvirtd_status = ""
virtualenv_version = "12.1.1"

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
kvm_root = "%s/kvm" % zstack_root
iproute_pkg = "%s/iproute-2.6.32-130.el6ost.netns.2.x86_64.rpm" % file_root
iproute_local_pkg = "%s/iproute-2.6.32-130.el6ost.netns.2.x86_64.rpm" % kvm_root
dnsmasq_pkg = "%s/dnsmasq-2.68-1.x86_64.rpm" % file_root
dnsmasq_local_pkg = "%s/dnsmasq-2.68-1.x86_64.rpm" % kvm_root

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)

host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.post_url = post_url
host_post_info.private_key = args.private_key

# include zstacklib.py
(distro, distro_version) = get_remote_host_info(host_post_info)
zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = distro
zstacklib_args.distro_version = distro_version
zstacklib_args.yum_repo = yum_repo
zstacklib_args.yum_server = yum_server
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib = ZstackLib(zstacklib_args)

# name: judge this process is init install or upgrade
if file_dir_exist("path=" + kvm_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (kvm_root, virtenv_path)
    run_remote_command(command, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    # handle yum_repo
    if yum_repo != 'false':
        # name: install kvm related packages on RedHat based OS from user defined repo
        command = ("pkg_list=`rpm -q openssh-clients qemu-kvm bridge-utils wget qemu-img libvirt-python libvirt nfs-utils "
                   "vconfig libvirt-client net-tools iscsi-initiator-utils lighttpd dnsmasq iproute sshpass "
                   "rsync nmap | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                   "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % yum_repo
        run_remote_command(command, host_post_info)
        if distro_version >= 7:
            # name: RHEL7 specific packages from user defined repos
            command = ("pkg_list=`rpm -q iptables-services | grep \"not installed\" | awk '{ print $2 }'` && for pkg "
                       "in $pkg_list; do yum --disablerepo=* --enablerepo=%s "
                       "--nogpgcheck install -y $pkg; done;") % yum_repo
            run_remote_command(command, host_post_info)
    else:
        # name: install kvm related packages on RedHat based OS from online
        for pkg in ['openssh-clients', 'qemu-kvm', 'bridge-utils', 'wget', 'qemu-img', 'libvirt-python', 'libvirt', 'nfs-utils', 'vconfig',
                    'libvirt-client', 'net-tools', 'iscsi-initiator-utils', 'lighttpd', 'dnsmasq', 'iproute', 'sshpass',
                    'rsync', 'nmap']:
            yum_install_package(pkg, host_post_info)
        if distro_version >= 7:
            # name: RHEL7 specific packages from online
            yum_install_package("iptables-services", host_post_info)

    # handle distro version specific task
    if distro_version < 7:
        # name: copy name space supported iproute for RHEL6
        copy_arg = CopyArg()
        copy_arg.src = iproute_pkg
        copy_arg.dest = iproute_local_pkg
        copy(copy_arg, host_post_info)
        # name: Update iproute for RHEL6
        command = "rpm -q iproute-2.6.32-130.el6ost.netns.2.x86_64 || yum install -y %s" % iproute_local_pkg
        run_remote_command(command, host_post_info)
        # name: disable NetworkManager in RHEL6 and Centos6
        network_manager_installed = yum_check_package("NetworkManager", host_post_info)
        if network_manager_installed is True:
            service_status("NetworkManager", "state=stopped enabled=no", host_post_info)

    else:
        # name: disable firewalld in RHEL7 and Centos7
        command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
        run_remote_command(command, host_post_info)
        # name: disable NetworkManager in RHEL7 and Centos7
        service_status("NetworkManager", "state=stopped enabled=no", host_post_info)

    if init == 'true':
        # name: copy iptables initial rules in RedHat
        copy_arg = CopyArg()
        copy_arg.src = "%s/iptables" % file_root
        copy_arg.dest = "/etc/sysconfig/iptables"
        copy(copy_arg, host_post_info)
        if chroot_env == 'false':
            # name: restart iptables
            service_status("iptables", "state=restarted enabled=yes", host_post_info)

    if chroot_env == 'false':
        # name: enable libvirt daemon on RedHat based OS
        service_status("libvirtd", "state=started enabled=yes", host_post_info)
        if distro_version >= 7:
            # name: enable virtlockd daemon on RedHat based OS
            service_status("virtlockd", "state=started enabled=yes", host_post_info)

    # name: copy updated dnsmasq for RHEL6 and RHEL7
    copy_arg = CopyArg()
    copy_arg.src = "%s" % dnsmasq_pkg
    copy_arg.dest = "%s" % dnsmasq_local_pkg
    copy(copy_arg, host_post_info)
    # name: Update dnsmasq for RHEL6 and RHEL7
    command = "rpm -q dnsmasq-2.68-1 || yum install -y %s" % dnsmasq_local_pkg
    run_remote_command(command, host_post_info)
    # name: disable selinux on RedHat based OS
    set_selinux("state=permissive policy=targeted", host_post_info)
    # name: copy sysconfig libvirtd conf in RedHat
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirtd" % file_root
    copy_arg.dest = "/etc/sysconfig/libvirtd"
    libvirtd_status = copy(copy_arg, host_post_info)
    # name: flush forwarding chain reject rule avoid block VR packet and keep sg rule
    command = "iptables -C FORWARD -j REJECT --reject-with icmp-host-prohibited > /dev/null 2>&1 && iptables -D " \
              "FORWARD -j REJECT --reject-with icmp-host-prohibited  > /dev/null 2>&1 || iptables-save"
    run_remote_command(command, host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    # name: install kvm related packages on Debian based OS
    for pkg in ['qemu-kvm', 'bridge-utils', 'wget', 'qemu-utils', 'python-libvirt', 'libvirt-bin',
                'vlan', 'nfs-common', 'open-iscsi', 'lighttpd', 'dnsmasq', 'sshpass', 'rsync']:
        apt_install_packages(pkg, host_post_info)
    # name: copy default libvirtd conf in Debian
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirt-bin" % file_root
    copy_arg.dest = '/etc/default/libvirt-bin'
    libvirt_bin_status = copy(copy_arg, host_post_info)
    # name: enable bridge forward on UBUNTU
    command = "modprobe br_netfilter; echo 1 > /proc/sys/net/bridge/bridge-nf-call-iptables ; " \
              "echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
    run_remote_command(command, host_post_info)

    if libvirt_bin_status != "changed:False":
        # name: restart debian libvirtd
        service_status("libvirt-bin", "state=restarted enabled=yes", host_post_info)

else:
    print "unsupported OS!"
    sys.exit(1)

# name: remove libvirt default bridge
command = '(ifconfig virbr0 &> /dev/null && virsh net-destroy default > ' \
          '/dev/null && virsh net-undefine default > /dev/null) || true'
run_remote_command(command, host_post_info)

# name: copy libvirtd conf
copy_arg = CopyArg()
copy_arg.src = "%s/libvirtd.conf" % file_root
copy_arg.dest = "/etc/libvirt/libvirtd.conf"
libvirtd_conf_status = copy(copy_arg, host_post_info)

# name: copy qemu conf
copy_arg = CopyArg()
copy_arg.src = "%s/qemu.conf" % file_root
copy_arg.dest = "/etc/libvirt/qemu.conf"
qemu_conf_status = copy(copy_arg, host_post_info)

# name: delete A2 qemu hook
command = "rm -f /etc/libvirt/hooks/qemu"
run_remote_command(command, host_post_info)

# name: enable bridge forward
command = "echo 1 > /proc/sys/net/bridge/bridge-nf-call-iptables ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
run_remote_command(command, host_post_info)


# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (kvm_root, pkg_zstacklib)
copy_zstacklib = copy(copy_arg, host_post_info)

# name: copy kvmagent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_kvmagent)
copy_arg.dest = "%s/%s" % (kvm_root, pkg_kvmagent)
copy_kvmagent = copy(copy_arg, host_post_info)

# only for os using init.d not systemd
# name: copy kvm service file
copy_arg = CopyArg()
copy_arg.src = "files/kvm/zstack-kvmagent"
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, kvm_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)
# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv --system-site-packages %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: install zstacklib
if copy_zstacklib != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = kvm_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install_arg.virtualenv_site_packages = "yes"
    agent_install(agent_install_arg, host_post_info)

# name: install kvm agent
if copy_kvmagent != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "kvm agent"
    agent_install_arg.agent_root = kvm_root
    agent_install_arg.pkg_name = pkg_kvmagent
    agent_install_arg.virtualenv_site_packages = "yes"
    agent_install(agent_install_arg, host_post_info)

# handlers
if chroot_env == 'false':
    if distro == "RedHat" or distro == "CentOS":
        if libvirtd_status != "changed:False" or libvirtd_conf_status != "changed:False" \
                or qemu_conf_status != "changed:False":
            # name: restart redhat libvirtd
            service_status("libvirtd", "state=restarted enabled=yes", host_post_info)
        # name: restart kvmagent
        service_status("zstack-kvmagent", "state=restarted enabled=yes", host_post_info)
    elif distro == "Debian" or distro == "Ubuntu":
        if libvirtd_conf_status != "changed:False" or qemu_conf_status != "changed:False":
            # name: restart debian libvirtd
            service_status("libvirt-bin", "state=restarted enabled=yes", host_post_info)
        # name: restart kvmagent
        service_status("zstack-kvmagent", "state=restarted enabled=yes", host_post_info)


host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy kvm agent successful", host_post_info, "INFO")

sys.exit(0)
