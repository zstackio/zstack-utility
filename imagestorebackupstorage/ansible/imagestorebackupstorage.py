#!/usr/bin/env python
# encoding: utf-8
import argparse
import datetime
from distutils.version import LooseVersion
import os.path
import re

from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy image store backup storage agent")
start_time = datetime.datetime.now()
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
new_add = "false"

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

# include zstacklib.py
host_info = get_remote_host_info_obj(host_post_info)
host_info = upgrade_to_helix(host_info, host_post_info)
releasever = get_host_releasever(host_info)
host_post_info.releasever = releasever

IS_AARCH64 = host_info.host_arch == 'aarch64'
IS_MIPS64EL = host_info.host_arch == 'mips64el'
IS_LOONGARCH64 = host_info.host_arch == 'loongarch64'

if host_info.host_arch == 'x86_64':
    src_pkg_imagestorebackupstorage = "zstack-store.bin"
    src_pkg_exporter = "collectd_exporter"
else:
    src_pkg_imagestorebackupstorage = "zstack-store.{}.bin".format(host_info.host_arch)
    src_pkg_exporter = "collectd_exporter_{}".format(host_info.host_arch)

if client != "true":
    dst_pkg_imagestorebackupstorage = "zstack-store.bin"
else:
    dst_pkg_imagestorebackupstorage = "zstack-store-client.bin"
dst_pkg_exporter = "collectd_exporter"

zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = host_info.distro
zstacklib_args.distro_release = host_info.distro_release
zstacklib_args.distro_version = host_info.major_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.require_python_env = require_python_env
zstacklib_args.zstack_releasever = releasever
if host_info.distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)

if host_info.distro in RPM_BASED_OS:
    qemu_pkg = "fuse-sshfs nmap collectd tar net-tools blktrace"

    releasever_mapping = {
        'h84r': ' collectd-disk pyparted',
        'h2203sp1o': ' collectd-disk',
    }

    for k in kylin:
        releasever_mapping[k] = ' python2-pyparted nettle'
    qemu_pkg += releasever_mapping.get(releasever, ' pyparted')

    if not remote_bin_installed(host_post_info, "qemu-img", return_status=True):
        qemu_pkg += ' qemu-img'

    # skip these packages
    _skip_list = re.split(r'[|;,\s]\s*', skip_packages)
    _qemu_pkg = [ pkg for pkg in qemu_pkg.split() if pkg not in _skip_list ]
    qemu_pkg = ' '.join(_qemu_pkg)
    svr_pkgs = 'ntfs-3g exfat-utils fuse-exfat btrfs-progs nmap-ncat lvm2 lvm2-libs'
    # common imagestorebackupstorage deps of ky10 that need to update
    ky10_update_list = "nettle collectd collectd-disk collectd-virt exfat-utils fuse-exfat"
    ky10sp3_update_list = "qemu-block-rbd"
    common_update_list = 'qemu-storage-daemon'

    if client == "true" :
        if host_info.major_version < 7:
            # change error to warning due to imagestore client will install after add kvm host
            Warning("Imagestore Client only support distribution version newer than 7.0")
        if zstack_repo == 'false':
            yum_install_package(qemu_pkg, host_post_info)
        else:
            command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                       "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % (qemu_pkg, zstack_repo)
            run_remote_command(command, host_post_info)

            if releasever in kylin:
                common_update_list = common_update_list + ' ' + ky10_update_list
            command = ("for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg || true; done;") % (
                common_update_list, zstack_repo)
            run_remote_command(command, host_post_info)
    else:
        if zstack_repo == 'false':
            yum_install_package(qemu_pkg, host_post_info)
        else:
            command = ("pkg_list=`rpm -q {0} | grep \"not installed\" | awk '{{ print $2 }}'` && for pkg in $pkg_list; do yum "
                       "--disablerepo=* --enablerepo={1} install -y $pkg; done;").format(qemu_pkg, zstack_repo)
            run_remote_command(command, host_post_info)

            if releasever in kylin:
                common_update_list = common_update_list + ' ' + ky10_update_list
                if IS_LOONGARCH64 and yum_check_package("qemu", host_post_info):
                    command = ("for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg || true; done;") % (
                        ky10sp3_update_list, zstack_repo)
                    run_remote_command(command, host_post_info)

            command = ("for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg || true; done;") % (
                common_update_list, zstack_repo)
            run_remote_command(command, host_post_info)

            if releasever not in ['c72', 'c74']:
                command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                           "--disablerepo=* --enablerepo=%s install -y $pkg || true; done;") % (svr_pkgs, zstack_repo)
                run_remote_command(command, host_post_info)

elif host_info.distro in DEB_BASED_OS:
    if client == "true" and host_info.major_version < 16:
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
    if LooseVersion(host_info.kernel_version) > LooseVersion('4.0.0'):
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

if client == "false" and new_add == "false":
    exp_dir = os.path.join(fs_rootpath, "export")
    reg_dir = os.path.join(fs_rootpath, "registry")
    if not file_dir_exist("path=" + exp_dir, host_post_info) and not file_dir_exist("path=" + reg_dir, host_post_info):
        error("ERROR: registry directory is missing, imagestore metadata may have been lost. Check it immediately!")

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
    if host_info.distro in RPM_BASED_OS:
        command = "/usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage stop && /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage start && chkconfig zstack-imagestorebackupstorage on"
    elif host_info.distro in DEB_BASED_OS:
        command = "update-rc.d zstack-imagestorebackupstorage start 97 3 4 5 . stop 3 0 1 2 6 . && /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage stop && /usr/local/zstack/imagestore/bin/zstack-imagestorebackupstorage start"
    run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy imagestore backupstore successful", host_post_info, "INFO")
sys.exit(0)
