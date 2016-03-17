#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import argparse
import ast
from zstacklib import *

# set default value
file_root = "files/appliancevm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
yum_repo = 'false'
post_url = ""

# get paramter from shell
parser = argparse.ArgumentParser(description='Deploy consoleproxy to management node')
parser.add_argument('-i',type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key',type=str,help='use this file to authenticate the connection')
parser.add_argument('-e',type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = ast.literal_eval(args.e)
locals().update(argument_dict)

# update the variable from shell arguments
virtenv_path = "%s/virtualenv/appliancevm/" % zstack_root
appliancevm_root  = "%s/appliancevm" % zstack_root
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
command = 'mkdir -p %s %s' % (appliancevm_root, virtenv_path)
run_remote_command(command, host_post_info)
check_and_install_virtual_env("12.1.1", trusted_host, pip_url, host_post_info)

# name: create virtualenv
command = "rm -rf %s && rm -f %s/%s && rm -f %s/%s && virtualenv --system-site-packages %s" % \
          (virtenv_path, appliancevm_root, pkg_zstacklib, appliancevm_root, pkg_appliancevm, virtenv_path)
run_remote_command(command, host_post_info)

# name: copy appliancevm service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-appliancevm" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)
if distro == "RedHat" or distro == "CentOS":
    if yum_repo != 'false':
        # name: install appliance vm related packages on RedHat based OS from user defined repo
        command = "yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y iputils tcpdump ethtool" % yum_repo
        run_remote_command(command, host_post_info)
    else:
        # name: install appliance vm related packages on RedHat based OS
        for pkg in ['iputils','tcpdump','ethtool']:
            yum_install_package("openssh-clients", host_post_info)
    if distro_version >= 7:
        # name: workaround RHEL7 iptables service issue
        command = 'mkdir -p /var/lock/subsys/'
        run_remote_command(command, host_post_info)
        # name: remove RHEL7 firewalld
        yum_remove_package("firewalld", host_post_info)
    # name: copy iptables initial rules in RedHat
    copy_arg = CopyArg()
    copy_arg.src="%s/iptables" % file_root
    copy_arg.dest="/etc/sysconfig/iptables"
    iptables_copy_result = copy(copy_arg, host_post_info)
    if chroot_env == 'false':
        if iptables_copy_result == "changed:true":
            service_status("name=iptables state=restarted enabled=yes", host_post_info)
    else:
        # name: enable appliancevm service for RedHat on chroot
        service_status("name=zstack-appliancevm enabled=yes state=stopped", host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    for pkg in ['iputils-arping','tcpdump','ethtool']:
        apt_install_packages("openssh-client", host_post_info)
    # name: copy iptables initial rules in Debian
    copy_arg = CopyArg()
    copy_arg.src="%s/iptables" % file_root
    copy_arg.dest="/etc/iptables"
    copy(copy_arg, host_post_info)
    # name: copy iptables initial start script in Debian
    copy_arg = CopyArg()
    copy_arg.src="%s/iptables.up" % file_root
    copy_arg.dest="/etc/network/if-pre-up.d/iptables.up"
    copy_arg.args = "mode=0777"
    iptables_script_result = copy(copy_arg, host_post_info)
    if iptables_script_result == "status:changed":
        command = "/etc/network/if-pre-up.d/iptables.up"
        run_remote_command(command, host_post_info)
    # name: enable appliancevm service for Debian -1
    command = "sed -i '/zstack-appliancevm start/d' /etc/rc.local"
    run_remote_command(command, host_post_info)
    # name: enable appliancevm service for Debian -2
   # command = "sed -i 's/^exit 0/\\\/etc\\\/init.d\\\/zstack-appliancevm start\nexit 0/' /etc/rc.local"
   # run_remote_command(command, host_post_info)
    update_arg = "insertbefore='^exit 0' line='/etc/init.d/zstack-appliancevm start\n'"
    update_file("/etc/rc.local",update_arg,host_post_info)
    # name: restore iptables
    command = '/etc/network/if-pre-up.d/iptables.up'
    run_remote_command(command, host_post_info)

else:
    print "unsupported OS!"
    sys.exit(1)

# name: copy bootstrap script
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-appliancevm-bootstrap.py" % file_root
copy_arg.dest = '/sbin/zstack-appliancevm-bootstrap.py'
copy_arg.args = "mode=0777"
copy(copy_arg, host_post_info)

# name: copy zstacklib and install
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest ="%s/%s" % (appliancevm_root, pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)

#if zstack_lib_copy == "changed:true":
pip_install_arg = PipInstallArg()
pip_install_arg.name="%s/%s" % (appliancevm_root,pkg_zstacklib)
pip_install_arg.extra_args="\"--trusted-host  %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv="%s" % virtenv_path
pip_install_arg.virtualenv_site_packages="yes"
pip_install_package(pip_install_arg,host_post_info)

# name: copy appliancevm and install
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root,pkg_appliancevm)
copy_arg.dest = "%s/%s" % (appliancevm_root,pkg_appliancevm)
appliancevm_copy_result = copy(copy_arg, host_post_info)
pip_install_arg = PipInstallArg()
pip_install_arg.name="%s/%s" % (appliancevm_root,pkg_appliancevm)
pip_install_arg.extra_args="\"--trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv="%s" % virtenv_path
pip_install_package(pip_install_arg,host_post_info)

if chroot_env == 'false':
    # name: restart appliancevm
    service_status("name=zstack-appliancevm enabled=yes state=restarted", host_post_info)
else:
    if distro == "RedHat" or distro == "CentOS":
        # name: restart iptables
        service_status("name=iptables state=restarted enabled=yes", host_post_info)
sys.exit(0)
