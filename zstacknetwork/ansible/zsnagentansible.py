#!/usr/bin/env python
# encoding: utf-8
import argparse
import os.path
from zstacklib import *
from datetime import datetime

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy zstack network agent")
start_time = datetime.now()
# set default value
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
current_dir = os.path.dirname(os.path.realpath(__file__))
file_root = "files/zsnagentansible"
pkg_zsn = ""
post_url = ""
fs_rootpath = ""
remote_user = "root"
remote_pass = None
remote_port = None
require_python_env = "false"


# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy zsn-agent to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')
args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
zsn_root = "%s/zsn-agent/package" % zstack_root

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy zsn-agent to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')
args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)

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
    if zstack_repo == 'false':
        yum_install_package("libpcap", host_post_info)
    else:
        command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                   "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % ("libpcap", zstack_repo)
        run_remote_command(command, host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    apt_install_packages(["libpcap"], host_post_info)

else:
    error("ERROR: Unsupported distribution")

run_remote_command("rm -rf %s/*" % zsn_root, host_post_info)
command = 'mkdir -p %s ' % (zsn_root)
run_remote_command(command, host_post_info)

# name: copy zsn binary
copy_arg = CopyArg()
dest_pkg = "%s/%s" % (zsn_root, pkg_zsn)
copy_arg.src = "%s/%s" % (file_root, pkg_zsn)
copy_arg.dest = dest_pkg
copy(copy_arg, host_post_info)


# name: install zstack-network
command = "bash %s %s " % (dest_pkg, fs_rootpath)
run_remote_command(command, host_post_info)


# integrate zstack-store with init.d
run_remote_command("/bin/cp -f /usr/local/zstack/zsn-agent/bin/zstack-network-agent /etc/init.d/", host_post_info)
if distro == "CentOS" or distro == "RedHat":
    command = "/usr/local/zstack/zsn-agent/bin/zstack-network-agent stop && /usr/local/zstack/zsn-agent/bin/zstack-network-agent start && chkconfig zstack-network-agent on"
elif distro == "Debian" or distro == "Ubuntu":
    command = "update-rc.d zstack-network-agent start 97 3 4 5 . stop 3 0 1 2 6 . && /usr/local/zstack/zsn-agent/bin/zstack-network-agent stop && /usr/local/zstack/zsn-agent/bin/zstack-network-agent start"
run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy zstack network successful", host_post_info, "INFO")
sys.exit(0)
