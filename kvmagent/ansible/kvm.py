#!/usr/bin/env python
# encoding=utf-8
import os
import sys
import argparse
from zstacklib import *

# set default value
file_root = "files/kvm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
is_init = 'false'
yum_repo = 'false'
post_url = ""

# get paramter from shell
parser = argparse.ArgumentParser(description='Deploy kvm to host')
parser.add_argument('-i',type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key',type=str,help='use this file to authenticate the connection')
parser.add_argument('-e',type=str, help='set additional variables as key=value or YAML/JSON')

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
zstacklib = ZstackLib(zstacklib_args)

# name: create root directories
command = 'mkdir -p %s %s' % (kvm_root, virtenv_path)
run_remote_command(command, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    if yum_repo != 'false':
        # name: install kvm related packages on RedHat based OS from user defined repo
        command = ('yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y qemu-kvm '
                   'bridge-utils wget qemu-img libvirt-python libvirt nfs-utils vconfig libvirt-client'
                   'net-tools iscsi-initiator-utils lighttpd dnsmasq iproute sshpass rsync') % yum_repo
        run_remote_command(command, host_post_info)
        if distro_version >= 7:
            # name: RHEL7 specific packages from user defined repos
            command = 'rpm -q iptables-services || yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y iptables-services' % yum_repo
            run_remote_command(command, host_post_info)
    else:
        # name: install kvm related packages on RedHat based OS from online
        for pkg in ['qemu-kvm', 'bridge-utils', 'wget', 'qemu-img', 'libvirt-python', 'libvirt', 'nfs-utils','vconfig',
                    'libvirt-client', 'net-tools', 'iscsi-initiator-utils', 'lighttpd', 'dnsmasq', 'iproute', 'sshpass',
                    'rsync']:
            yum_install_package(pkg, host_post_info)
        if distro_version >= 7:
            # name: RHEL7 specific packages from online
            yum_install_package("iptables-services", host_post_info)

    if distro_version < 7:
        # name: copy name space supported iproute for RHEL6
        copy_arg = CopyArg()
        copy_arg.src= iproute_pkg
        copy_arg.dest = iproute_local_pkg
        copy(copy_arg, host_post_info)
        # name: Update iproute for RHEL6
        command =  "rpm -q iproute-2.6.32-130.el6ost.netns.2.x86_64 || yum install -y %s" % iproute_local_pkg
        run_remote_command(command, host_post_info)
        # name: disable NetworkManager in RHEL6 and Centos6
        network_manager_installed = yum_check_pacakge("NetworkManager", host_post_info)
        if network_manager_installed == True:
            service_status("name=NetworkManager state=stopped enabled=no", host_post_info)

    else:
        # name: disable firewalld in RHEL7 and Centos7
        command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
        run_remote_command(command, host_post_info)
        # name: disable NetworkManager in RHEL7 and Centos7
        service_status("name=NetworkManager state=stopped enabled=no", host_post_info)

    if is_init == 'true':
        # name: copy iptables initial rules in RedHat
        copy_arg = CopyArg()
        copy_arg.src = "%s/iptables" % file_root
        copy_arg.dest = "/etc/sysconfig/iptables"
        copy(copy_arg, host_post_info)
        if chroot_env == 'false':
            # name: restart iptables
            service_status("name=iptables state=restarted enabled=yes", host_post_info)

    if chroot_env == 'false':
        # name: enable libvirt daemon on RedHat based OS
        service_status("name=libvirtd state=started enabled=yes", host_post_info)

    # name: copy updated dnsmasq for RHEL6 and RHEL7
    copy_arg = CopyArg()
    copy_arg.src = "%s" % dnsmasq_pkg
    copy_arg.dest = "%s" % dnsmasq_local_pkg
    copy(copy_arg, host_post_info)
    # name: Update dnsmasq for RHEL6 and RHEL7
    command =  "rpm -q dnsmasq-2.68-1 || yum install -y %s" % dnsmasq_local_pkg
    run_remote_command(command, host_post_info)
    # name: disable selinux on RedHat based OS
    set_selinux("state=permissive policy=targeted", host_post_info)
    # name :copy sysconfig libvirtd conf in RedHat
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirtd" % file_root
    copy_arg.dest = "/etc/sysconfig/libvirtd"
    libvirtd_status= copy(copy_arg, host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    # name: install kvm related packages on Debian based OS
    for pkg in ['qemu-kvm', 'bridge-utils', 'wget', 'qemu-utils', 'python-libvirt', 'libvirt-bin',
                'vlan', 'nfs-common', 'open-iscsi', 'lighttpd', 'dnsmasq', 'sshpass', 'rsync']:
       apt_install_packages(pkg, host_post_info)
    # name: copy default libvirtd conf in Debian
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirt-bin" % file_root
    copy_arg.dest='/etc/default/libvirt-bin'
    libvirt_bin_status = copy(copy_arg, host_post_info)
    # name: enable bridge forward on UBUNTU
    command = "modprobe br_netfilter; echo 1 > /proc/sys/net/bridge/bridge-nf-call-iptables ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
    run_remote_command(command, host_post_info)

    if libvirt_bin_status == "changed:true":
        # name: restart debian libvirtd
        service_status("name=libvirt-bin state=restarted enabled=yes", host_post_info)

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

# name: install virtualenv version 12.1.1
check_and_install_virtual_env("12.1.1", trusted_host, pip_url, host_post_info)
# name: create virtualenv
command = "rm -rf %s && rm -f %s/%s && rm -f %s/%s && virtualenv --system-site-packages %s" % \
          (virtenv_path, kvm_root, pkg_zstacklib, kvm_root, pkg_kvmagent, virtenv_path)
run_remote_command(command, host_post_info)
# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (kvm_root,pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
#if zstack_lib_copy == "changed:true":
pip_install_arg = PipInstallArg()
pip_install_arg.name = "%s/%s" % (kvm_root,pkg_zstacklib)
pip_install_arg.extra_args =  "\"--ignore-installed --trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv = virtenv_path
pip_install_arg.virtualenv_site_packages = "yes"
pip_install_package(pip_install_arg,host_post_info)
# name: copy kvmagent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root,pkg_kvmagent)
copy_arg.dest = "%s/%s" % (kvm_root,pkg_kvmagent)
kvmagent_copy = copy(copy_arg, host_post_info)
# only for os using init.d not systemd
# name: copy kvm service file
copy_arg = CopyArg()
copy_arg.src = "files/kvm/zstack-kvmagent"
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: install kvm agent
pip_install_arg = PipInstallArg()
pip_install_arg.name = "%s/%s" % (kvm_root,pkg_kvmagent)
pip_install_arg.extra_args =  "\"--ignore-installed --trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv = virtenv_path
pip_install_arg.virtualenv_site_packages = "yes"
pip_install_package(pip_install_arg,host_post_info)

# handlers
if chroot_env == 'false':
    if distro == "RedHat" or distro == "CentOS":
        if libvirtd_status == "changed:true" or libvirtd_conf_status == "changed:true" \
                or qemu_conf_status == "changed:true":
            # name: restart redhat libvirtd
            service_status("name=libvirtd state=restarted enabled=yes", host_post_info)
        #name: restart kvmagent
        service_status("name=zstack-kvmagent state=restarted enabled=yes",host_post_info)
    elif distro == "Debian" or distro == "Ubuntu":
        if libvirtd_conf_status == "changed:true" or qemu_conf_status == "changed:true":
            # name: restart debian libvirtd
            service_status("name=libvirt-bin state=restarted enabled=yes", host_post_info)
        # name: restart kvmagent
        service_status("name=zstack-kvmagent state=restarted enabled=yes",host_post_info)

sys.exit(0)
