#!/usr/bin/env python
# encoding: utf-8
import argparse
from zstacklib import *
from datetime import datetime

start_time = datetime.now()
# set default value
file_root = "files/imagestorebackupstorage"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
current_dir = os.path.dirname(os.path.realpath(__file__))
post_url = ""
fs_rootpath = ""
pkg_imagestorebackupstorage = ""
client = "false"
remote_user = "root"
remote_pass = None
remote_port = None
require_python_env = "false"

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy image backupstorage to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
imagestore_root = "%s/imagestorebackupstorage" % zstack_root

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.post_url = post_url
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

# include zstacklib.py
(distro, distro_version, distro_release) = get_remote_host_info(host_post_info)
zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = distro
zstacklib_args.distro_release = distro_release
zstacklib_args.distro_version = distro_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.yum_server = yum_server
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.require_python_env = require_python_env
zstacklib = ZstackLib(zstacklib_args)

if distro == "CentOS" or distro == "RedHat":
    if client == "true" :
        if distro_version < 7:
            error("Client only support distribution version newer than 7.0")
        else:
            if zstack_repo == 'false':
                yum_install_package("qemu-img-2.3.0", host_post_info)
            else:
                command = ("yum clean --enablerepo=alibase metadata && yum --disablerepo=* --enablerepo=%s install "
                           "-y qemu-img-ev-2.3.0") % zstack_repo
                run_remote_command(command, host_post_info)
    else:
        if zstack_repo == 'false':
            yum_install_package("qemu-img", host_post_info)
        else:
            command = ("yum clean --enablerepo=alibase metadata && yum --disablerepo=* --enablerepo=%s install "
                       "-y qemu-img") % zstack_repo

elif distro == "Debian" or distro == "Ubuntu":
    if client == "true" and distro_version < 16:
        error("Client only support distribution version newer than 16.04")
    apt_install_packages("qemu-img", host_post_info)

else:
    error("ERROR: Unsupported distribution")

command = 'mkdir -p %s' % (imagestore_root + "/certs")
run_remote_command(command, host_post_info)

# name: copy necessary certificates
copy_arg = CopyArg()
dest_pkg = "%s/%s" % (imagestore_root, pkg_imagestorebackupstorage)
copy_arg.src = "%s/%s" % (file_root, pkg_imagestorebackupstorage)
copy_arg.dest = dest_pkg
copy(copy_arg, host_post_info)

local_cert_dir = "/usr/local/zstack/imagestore/bin/certs"

# name: copy imagestore binary
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (local_cert_dir, "ca.pem")
copy_arg.dest = "%s/%s/%s" % (imagestore_root, "certs", "ca.pem")
copy_arg.args = "mode=644"
copy(copy_arg, host_post_info)

copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (local_cert_dir, "privkey.pem")
copy_arg.dest = "%s/%s/%s" % (imagestore_root, "certs", "privkey.pem")
copy_arg.args = "mode=400"
copy(copy_arg, host_post_info)

# name: install zstack-store
command = "bash %s %s " % (dest_pkg, fs_rootpath)
run_remote_command(command, host_post_info)

# name: restart image store server
if client != "true":
    command = "/usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage restart"
    run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy imagestore backupstore successful", host_post_info, "INFO")
sys.exit(0)
