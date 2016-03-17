#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import argparse
import ast
from zstacklib import *

# set default value
file_root = "files/iscsi"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
yum_repo = 'false'
post_url = ""

# get paramter from shell
parser = argparse.ArgumentParser(description='Deploy iscsi to host')
parser.add_argument('-i',type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key',type=str,help='use this file to authenticate the connection')
parser.add_argument('-e',type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = ast.literal_eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/iscsi/" % zstack_root
iscsi_root = "%s/iscsi" % zstack_root
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
command = 'mkdir -p %s %s' % (iscsi_root,virtenv_path)
run_remote_command(command, host_post_info)
if distro == "RedHat" or distro == "CentOS":
    if yum_repo != 'false':
        # name: install iscsi related packages on RedHat based OS from user defined repo
        command = "yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y wget qemu-img scsi-target-utils"  % yum_repo
        run_remote_command(command, host_post_info)
        # name: RHEL7 specific packages from user defined repos
        command = "rpm -q iptables-services || yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y iptables-services " % yum_repo
        run_remote_command(command, host_post_info)

    else:
        # name: install isci related packages on RedHat based OS from online
        for pkg in ['wget','qemu-img','scsi-target-utils']:
            yum_install_package(pkg, host_post_info)
            # name: RHEL7 specific packages from online
            yum_install_package("iptables-services", host_post_info)
    if distro_version >= 7:
        # name: disable firewalld in RHEL7 and Centos7
        command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
        run_remote_command(command, host_post_info)
    # name: disable selinux on RedHat based OS
    set_selinux("state=permissive policy=targeted", host_post_info)
    # name: enable tgtd daemon on RedHat
    service_status("name=tgtd state=started enabled=yes", host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    # name: install isci related packages on Debian based OS
    for pkg in ['iscsitarget','iscsitarget-dkms','tgt','wget','qemu-utils']:
       apt_install_packages(pkg, host_post_info)
    # name: enable tgtd daemon on Debian
    service_status("name=iscsitarget state=started enabled=yes", host_post_info)

check_and_install_virtual_env("12.1.1", trusted_host, pip_url, host_post_info)
# name: create virtualenv
command = "rm -rf %s && rm -f %s/%s && rm -f %s/%s && virtualenv --system-site-packages %s" % \
          (virtenv_path, iscsi_root, pkg_zstacklib, iscsi_root, pkg_iscsiagent, virtenv_path)
run_remote_command(command, host_post_info)

# name: copy zstacklib and install zstacklib
copy_arg = CopyArg()
copy_arg.src="files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest="%s/%s" % (iscsi_root,pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
#if zstack_lib_copy == "changed:true":
pip_install_arg = PipInstallArg()
pip_install_arg.name = "%s/%s" % (iscsi_root,pkg_zstacklib)
pip_install_arg.extra_args =  "\"--ignore-installed --trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv = virtenv_path
pip_install_arg.virtualenv_site_packages = "yes"
pip_install_package(pip_install_arg,host_post_info)
# name: copy iscsi filesystem agent
copy_arg = CopyArg()
copy_arg.src="%s/%s" % (file_root,pkg_iscsiagent)
copy_arg.dest="%s/%s" % (iscsi_root,pkg_iscsiagent)
iscsiagent_copy = copy(copy_arg, host_post_info)

# name: copy iscsi service file
copy_arg = CopyArg()
copy_arg.src="files/iscsi/zstack-iscsi"
copy_arg.dest="/etc/init.d/"
copy_arg.args="mode=755"
copy(copy_arg, host_post_info)

# name: install iscsiagent
# meilei: to do - http_proxy https_proxy
pip_install_arg = PipInstallArg()
pip_install_arg.name="%s/%s" % (iscsi_root,pkg_iscsiagent)
pip_install_arg.extra_args="\"--ignore-installed --trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv="%s" % virtenv_path
pip_install_arg.virtualenv_site_packages="yes"
pip_install_package(pip_install_arg,host_post_info)
# name: restart iscsiagent
service_status("name=zstack-iscsi state=restarted enabled=yes", host_post_info)
sys.exit(0)
