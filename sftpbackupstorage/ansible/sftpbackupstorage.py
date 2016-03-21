#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import argparse
from zstacklib import *
from datetime import datetime

start_time = datetime.now()
# set default value
file_root = "files/sftpbackupstorage"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
yum_repo = 'false'
current_dir = os.path.dirname(os.path.realpath(__file__))
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
virtenv_path = "%s/virtualenv/sftpbackupstorage/" % zstack_root
sftp_root = "%s/sftpbackupstorage" % zstack_root
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
command = 'mkdir -p %s %s' % (sftp_root,virtenv_path)
run_remote_command(command, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    if yum_repo != 'false':
        # name: install sftp backup storage related packages on RedHat based OS from local
        command = 'yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y openssh-clients' % yum_repo
        run_remote_command(command, host_post_info)
    else:
        # name: install sftp backup storage related packages on RedHat based OS from online
        yum_install_package("openssh-clients", host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    apt_install_packages("openssh-client", host_post_info)

else:
    print "unsupported OS!"
    sys.exit(1)

check_and_install_virtual_env("12.1.1", trusted_host, pip_url, host_post_info)
# name: create virtualenv
command = "rm -rf %s && rm -f %s/%s && rm -f %s/%s && virtualenv --system-site-packages %s" % \
          (virtenv_path, sftp_root, pkg_sftpbackupstorage, sftp_root, pkg_zstacklib, virtenv_path)
run_remote_command(command, host_post_info)
# name: add public key
authorized_key("root", current_dir +  "/id_rsa.sftp.pub", host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src="files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest="%s/%s" % (sftp_root, pkg_zstacklib)
zstacklib_copy_result = copy(copy_arg, host_post_info)
# name: install zstacklib
# if zstacklib_copy_result == "changed:true":
pip_install_arg = PipInstallArg()
pip_install_arg.name="%s/%s" % (sftp_root, pkg_zstacklib)
pip_install_arg.host=host
pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (trusted_host, pip_url)
pip_install_arg.virtualenv="%s" % virtenv_path
pip_install_package(pip_install_arg, host_post_info)

# name: copy sftp
copy_arg = CopyArg()
copy_arg.src="%s/%s" % (file_root, pkg_sftpbackupstorage)
copy_arg.dest="%s/%s" % (sftp_root, pkg_sftpbackupstorage)
sftp_copy_result = copy(copy_arg, host_post_info)

# name: copy sftp backup storage service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-sftpbackupstorage" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# if sftp_copy_result == "changed:true":
# name: install sftp
pip_install_arg = PipInstallArg()
pip_install_arg.name="%s/%s" % (sftp_root, pkg_sftpbackupstorage)
pip_install_arg.host=host
pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (trusted_host, pip_url)
pip_install_arg.virtualenv="%s" % virtenv_path
pip_install_package(pip_install_arg, host_post_info)

# name: restart sftp
if chroot_env == 'false':
    service_status("name=zstack-sftpbackupstorage state=restarted enabled=yes", host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploysftpbackupstorage agent successful", host_post_info, "INFO")

sys.exit(0)
