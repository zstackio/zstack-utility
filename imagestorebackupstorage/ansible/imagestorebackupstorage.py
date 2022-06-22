#!/usr/bin/env python
# encoding: utf-8
import re
import argparse
import os.path
from zstacklib import *
from datetime import datetime
from distutils.version import LooseVersion

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
IS_LOONGARCH64 = host_arch == 'loongarch64'

if host_arch == 'x86_64':
    src_pkg_imagestorebackupstorage = "zstack-store.bin"
    src_pkg_exporter = "collectd_exporter"
else:
    src_pkg_imagestorebackupstorage = "zstack-store.{}.bin".format(host_arch)
    src_pkg_exporter = "collectd_exporter_{}".format(host_arch)

if client != "true":
    dst_pkg_imagestorebackupstorage = "zstack-store.bin"
else:
    dst_pkg_imagestorebackupstorage = "zstack-store-client.bin"
dst_pkg_exporter = "collectd_exporter"

# include zstacklib.py
(distro, major_version, distro_release, distro_version) = get_remote_host_info(host_post_info)
releasever = get_host_releasever([distro, distro_release, distro_version])
host_post_info.releasever = releasever

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
zstacklib_args.zstack_releasever = releasever
if distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)

if distro in RPM_BASED_OS:
    qemu_pkg = "fuse-sshfs nmap collectd tar"
    if releasever in ['c74', 'c76']:
        qemu_pkg = "qemu-img-ev {}".format(qemu_pkg)
    else:
        qemu_pkg = "qemu-img {}".format(qemu_pkg)
    # skip these packages
    _skip_list = re.split(r'[|;,\s]\s*', skip_packages)
    _qemu_pkg = [ pkg for pkg in qemu_pkg.split() if pkg not in _skip_list ]
    qemu_pkg = ' '.join(_qemu_pkg)
    svr_pkgs = 'ntfs-3g exfat-utils fuse-exfat btrfs-progs qemu-storage-daemon nmap-ncat'
    # common imagestorebackupstorage deps of ns10 that need to update
    ns10_update_list = "nettle"

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
            command = ("pkg_list=`rpm -q {0} | grep \"not installed\" | awk '{{ print $2 }}'` && for pkg in $pkg_list; do yum "
                       "--disablerepo=* --enablerepo={1} install -y $pkg; done;").format(qemu_pkg, zstack_repo)
            run_remote_command(command, host_post_info)

            if releasever in ['ns10']:
                command = ("for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg; done;") % (
                ns10_update_list, zstack_repo)
                run_remote_command(command, host_post_info)

            if releasever not in ['c72', 'c74']:
                command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                           "--disablerepo=* --enablerepo=%s install -y $pkg || true; done;") % (svr_pkgs, zstack_repo)
                run_remote_command(command, host_post_info)

elif distro in DEB_BASED_OS:
    if client == "true" and distro_version < 16:
        Warning("Client only support distribution version newer than 16.04")
    apt_install_packages(["qemu-utils", "qemu-system", "sshfs", "collectd"], host_post_info)
else:
    error("ERROR: Unsupported distribution")

# name: copy imagestore binary
command = 'rm -rf {};mkdir -p {}'.format(imagestore_root, imagestore_root + "/certs")
run_remote_command(command, host_post_info)
copy_arg = CopyArg()
dest_pkg = "%s/%s" % (imagestore_root, dst_pkg_imagestorebackupstorage)
copy_arg.src = "%s/%s" % (file_root, src_pkg_imagestorebackupstorage)
copy_arg.dest = dest_pkg
copy(copy_arg, host_post_info)

# name: copy exporter binary
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (kvm_file_root, src_pkg_exporter)
copy_arg.dest = "%s/%s" % (utils_root, dst_pkg_exporter)
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

def load_nbd():
    command = "modinfo nbd"
    status = run_remote_command(command, host_post_info, True, False)
    if status is False:
        return "nbd kernel module not found!"
    if LooseVersion(get_remote_host_kernel_version(host_post_info)) > LooseVersion('4.0.0'):
        command = "/sbin/modprobe nbd nbds_max=32 max_part=16"
    else:
        command = "/sbin/modprobe nbd nbds_max=128 max_part=16"
    status = run_remote_command(command, host_post_info, True, False)
    if status is False:
        return "failed to load nbd kernel module"
    command = "cat /sys/module/nbd/parameters/nbds_max"
    is_nbds_max = '128' in run_remote_command(command, host_post_info, False, True)
    if not is_nbds_max and not file_dir_exist("path=/etc/modprobe.d/nbd.conf", host_post_info):
        command = "echo 'nbd' > /etc/modules-load.d/nbd.conf; echo 'options nbd nbds_max=128 max_part=16' > /etc/modprobe.d/nbd.conf; dracut -f;"
        run_remote_command(command, host_post_info)

load_nbd()

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
if client != "true":
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
