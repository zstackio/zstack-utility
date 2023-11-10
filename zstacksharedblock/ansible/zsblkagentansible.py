#!/usr/bin/env python
# encoding: utf-8
import argparse
import datetime
import os

from zstacklib import *


def add_true_in_command(cmd):
    return "%s || true" % cmd

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy zstack sharedblock agent")
start_time = datetime.datetime.now()
# set default value
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
current_dir = os.path.dirname(os.path.realpath(__file__))
file_root = "files/zsblkagentansible"
pkg_zsblk = ""
post_url = ""
chrony_servers = None
fs_rootpath = ""
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None
require_python_env = "false"
isZYJ = "false"
zyjDistribution = ""

free_spcae = 1073741824
increment = 1073741824
log_file = "/var/log/zstack/zsblk-agent/zsblk-agent.log"
qmp_socket_dir = "/var/lib/libvirt/qemu/zstack/"
utilization_percent = 85

maxLockButNotUsedTimes = 12
scanInterval = 300
verboseLog = "false"

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy zsblk-agent to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')
args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
zsblk_root = "%s/zsblk-agent/package" % zstack_root

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
if isZYJ == "true" and zyjDistribution != "":
    host_post_info.distribution = zyjDistribution

# include zstacklib.py
host_info = get_remote_host_info_obj(host_post_info)
releasever = get_host_releasever(host_info)
host_post_info.releasever = releasever

IS_AARCH64 = host_info.host_arch == 'aarch64'
if IS_AARCH64:
    src_pkg_zsblk = "zsblk-agent.aarch64.bin"
else:
    src_pkg_zsblk = "zsblk-agent.bin"
pkg_zsblk = "zsblk-agent.bin"

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


@skip_on_zyj(isZYJ)
def config_zsblk():
    run_remote_command(add_true_in_command("rm -rf %s/*" % zsblk_root), host_post_info)
    command = 'mkdir -p %s ' % (zsblk_root)
    run_remote_command(add_true_in_command(command), host_post_info)

    # name: copy zsblk binary
    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (file_root, src_pkg_zsblk)
    dest_pkg = "%s/%s" % (zsblk_root, pkg_zsblk)
    copy_arg.dest = dest_pkg
    copy(copy_arg, host_post_info)
    # name: install zstack-sharedblock
    command = "bash %s %s " % (dest_pkg, fs_rootpath)
    run_remote_command(add_true_in_command(command), host_post_info)

    # copy service
    run_remote_command(add_true_in_command("/bin/cp -f /usr/local/zstack/zsblk-agent/bin/zstack-sharedblock-agent.service /usr/lib/systemd/system/"), host_post_info)

    # replace service content
    service_env = "ZSBLKARGS=-free-space %s -increment %s -log-file %s -qmp-socket-dir %s -utilization-percent %s " \
                  "-lk-helper-max-times %s -lk-helper-scan-interval %s -verbose %s" \
                  % (int(free_spcae), int(increment), log_file, qmp_socket_dir, utilization_percent, maxLockButNotUsedTimes, scanInterval, verboseLog)
    replace_content("/usr/lib/systemd/system/zstack-sharedblock-agent.service", '''regexp='.*Environment=.*' replace="Environment='%s'"''' % service_env, host_post_info)


config_zsblk()


command = "systemctl daemon-reload && systemctl enable zstack-sharedblock-agent.service && systemctl restart zstack-sharedblock-agent.service"
run_remote_command(add_true_in_command(command), host_post_info, False, False, isZYJ)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy zstack sharedblock successful", host_post_info, "INFO")
sys.exit(0)

