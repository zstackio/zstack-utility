#!/usr/bin/env python
# encoding: utf-8
import re
import argparse
import os.path
from zstacklib import *
from datetime import datetime

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy image store backup storage agent")
start_time = datetime.now()
# set default value
file_root = "files/imagestorebackupstorage"
kvm_file_root = "files/kvm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
current_dir = os.path.dirname(os.path.realpath(__file__))
post_url = ""
chrony_servers = None
fs_rootpath = ""
max_capacity = 0
client = "false"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None
require_python_env = "false"
skip_packages = ""

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
imagestore_root = "%s/imagestorebackupstorage/package" % zstack_root
utils_root = "%s/imagestorebackupstorage" % zstack_root

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

# get remote host arch
host_arch = get_remote_host_arch(host_post_info)
IS_AARCH64 = host_arch == 'aarch64'
IS_MIPS64EL = host_arch == 'mips64el'

if IS_AARCH64:
    src_pkg_imagestorebackupstorage = "zstack-store.aarch64.bin"
    src_pkg_exporter = "collectd_exporter_aarch64"
elif IS_MIPS64EL:
    src_pkg_imagestorebackupstorage = "zstack-store.mips64el.bin"
    src_pkg_exporter = "collectd_exporter_mips64el"
else:
    src_pkg_imagestorebackupstorage = "zstack-store.bin"
    src_pkg_exporter = "collectd_exporter"
dst_pkg_imagestorebackupstorage = "zstack-store.bin"
dst_pkg_exporter = "collectd_exporter"

# include zstacklib.py
(distro, distro_version, distro_release, _) = get_remote_host_info(host_post_info)
zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = distro
zstacklib_args.distro_release = distro_release
zstacklib_args.distro_version = distro_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.require_python_env = require_python_env
if distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
    zstacklib_args.zstack_releasever = get_mn_apt_release()
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)

if distro in RPM_BASED_OS:
    (status, output) = run_remote_command("rpm -q zstack-release >/dev/null && echo `awk '{print $3}' /etc/zstack-release`", host_post_info, True, True)
    if status:
        # c72 is no longer supported, force set c74
        releasever = 'c74' if output.strip() == 'c72' else output.strip()
    else:
        releasever = get_mn_yum_release()
    x86_64_c74 = "qemu-img-ev fuse-sshfs nmap collectd"
    x86_64_c76 = "qemu-img-ev fuse-sshfs nmap collectd"
    aarch64_ns10 = "qemu-img fuse-sshfs nmap collectd"
    mips64el_ns10 = "qemu-img-ev fuse-sshfs nmap collectd"
    x86_64_ns10 = "qemu-img fuse-sshfs nmap collectd"
    
    qemu_pkg = eval("%s_%s" % (host_arch, releasever))
    # skip these packages
    _skip_list = re.split(r'[|;,\s]\s*', skip_packages)
    _qemu_pkg = [ pkg for pkg in qemu_pkg.split() if pkg not in _skip_list ]
    qemu_pkg = ' '.join(_qemu_pkg)

    if client == "true" :
        if distro_version < 7:
            # change error to warning due to imagestore client will install after add kvm host
            Warning("Imagestore Client only support distribution version newer than 7.0")
        if zstack_repo == 'false':
            yum_install_package(qemu_pkg, host_post_info)
        else:
            command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                       "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % (qemu_pkg, zstack_repo)
            run_remote_command(command, host_post_info)
    else:
        if zstack_repo == 'false':
            yum_install_package(qemu_pkg, host_post_info)
        else:
            command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                       "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % (qemu_pkg, zstack_repo)
            run_remote_command(command, host_post_info)

elif distro in DEB_BASED_OS:
    if client == "true" and distro_version < 16:
        Warning("Client only support distribution version newer than 16.04")
    apt_install_packages(["qemu-utils", "qemu-system", "sshfs", "collectd"], host_post_info)
else:
    error("ERROR: Unsupported distribution")

# name: copy imagestore binary
copy_arg = CopyArg()
dest_pkg = "%s/%s" % (imagestore_root, dst_pkg_imagestorebackupstorage)
copy_arg.src = "%s/%s" % (file_root, src_pkg_imagestorebackupstorage)
copy_arg.dest = "%s/" % imagestore_root
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

# name: copy exporter binary
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (kvm_file_root, src_pkg_exporter)
copy_arg.dest = "%s/" % utils_root
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

# name: copy iptables-scrpit
copy_arg = CopyArg()
copy_arg.src = "%s/zstore-iptables" % file_root
copy_arg.dest = "%s/zstore-iptables" % imagestore_root
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

# name: copy necessary certificates
xs = current_dir.split('/')
local_install_dir = '/'.join(xs[:xs.index('ansible')])
local_cert_dir = os.path.join(local_install_dir, "imagestore", "bin", "certs")

copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (local_cert_dir, "ca.pem")
copy_arg.dest = "%s/%s/" % (imagestore_root, "certs")
copy_arg.args = "mode=644 force=yes"
copy(copy_arg, host_post_info)

copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (local_cert_dir, "privkey.pem")
copy_arg.dest = "%s/%s/" % (imagestore_root, "certs")
copy_arg.args = "mode=400 force=yes"
copy(copy_arg, host_post_info)

# name: install zstack-store
if client == "false":
    command = "bash %s %s %s" % (dest_pkg, fs_rootpath, max_capacity)
else:
    command = "bash " + dest_pkg
run_remote_command(command, host_post_info)

# if user is not root , Change the owner of the directory to ordinary user
if fs_rootpath != '' and remote_user != 'root':
    run_remote_command("sudo chown -R -H --dereference %s: %s" % (remote_user, fs_rootpath), host_post_info)

# name: restart image store server
server = client != "true" or run_remote_command("pkill -0 zstore", host_post_info, return_status=True, return_output=False)
if server:
    # integrate zstack-store with init.d
    run_remote_command("/bin/cp -f /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage /etc/init.d/", host_post_info)
    if distro in RPM_BASED_OS:
        command = "/usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage stop && /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage start && chkconfig zstack-imagestorebackupstorage on"
    elif distro in DEB_BASED_OS:
        command = "update-rc.d zstack-imagestorebackupstorage start 97 3 4 5 . stop 3 0 1 2 6 . && /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage stop && /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage start"
    run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy imagestore backupstore successful", host_post_info, "INFO")
sys.exit(0)
