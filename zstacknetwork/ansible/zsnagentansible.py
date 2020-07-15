#!/usr/bin/env python
# encoding: utf-8
import argparse
import commands
import os.path
from zstacklib import *
try:
    from zstacklib.ansible.zstacklib import *
except Exception as e:
    print e.message
from datetime import datetime

def add_true_in_command(cmd):
    return "%s || true" % cmd

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
src_pkg_zsn = ""
dest_pkg_zsn = "zsn-agent.bin"
post_url = ""
chrony_servers = None
fs_rootpath = ""
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None
require_python_env = "false"
tmout = None


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
    if zstack_repo == 'false':
        yum_install_package("libpcap", host_post_info)
    else:
        command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                   "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % ("libpcap", zstack_repo)
        run_remote_command(command, host_post_info)

elif distro in DEB_BASED_OS:
    apt_install_packages(["libpcap-dev"], host_post_info)

else:
    error("ERROR: Unsupported distribution")

run_remote_command(add_true_in_command("rm -rf %s/*" % zsn_root), host_post_info)
command = 'mkdir -p %s ' % (zsn_root)
run_remote_command(add_true_in_command(command), host_post_info)

# name: copy zsn binary
HOST_ARCH = get_remote_host_arch(host_post_info)
if HOST_ARCH == 'aarch64':
    src_pkg_zsn = 'zsn-agent.aarch64.bin'
elif HOST_ARCH == 'mips64el':
    src_pkg_zsn = 'zsn-agent.mips64el.bin'
else:
    src_pkg_zsn = 'zsn-agent.bin'

copy_arg = CopyArg()
dest_pkg = "%s/%s" % (zsn_root, dest_pkg_zsn)
copy_arg.src = "%s/%s" % (file_root, src_pkg_zsn)
copy_arg.dest = dest_pkg
copy(copy_arg, host_post_info)

command = "/bin/cp /usr/local/zstack/zsn-agent/bin/zsn-agent /usr/local/zstack/zsn-agent/bin/zsn-agent.bak || touch /usr/local/zstack/zsn-agent/bin/zsn-agent.bak"
run_remote_command(add_true_in_command(command), host_post_info)

# name: install zstack-network
command = "bash %s %s " % (dest_pkg, fs_rootpath)
run_remote_command(add_true_in_command(command), host_post_info)

# integrate zstack-network with systemd
run_remote_command(add_true_in_command("/bin/cp -f /usr/local/zstack/zsn-agent/bin/zstack-network-agent.service /usr/lib/systemd/system/"), host_post_info)

if tmout is None:
    tmout = 960

successTmout, stdoutTmout = run_remote_command("grep -- '-tmout %s' /usr/lib/systemd/system/zstack-network-agent.service" % int(tmout), host_post_info, True, True)
successMd5, stdoutMd5 = run_remote_command(add_true_in_command("md5sum /usr/local/zstack/zsn-agent/bin/zsn-agent"), host_post_info, True, True)
successOldMd5, oldMd5 = run_remote_command(add_true_in_command("md5sum /usr/local/zstack/zsn-agent/bin/zsn-agent.bak"), host_post_info, True, True)

msg = Msg()
post_url = host_post_info.post_url
msg.details = "zsn agent deploying %s, %s, %s, %s, %s, %s" % (successTmout, stdoutTmout, successMd5, stdoutMd5, successOldMd5, oldMd5)
msg.label = "ansible.zsn"
msg.parameters = host_post_info.post_label_param
msg.level = "WARNING"
post_msg(msg, post_url)

if successTmout is True and len(stdoutMd5.strip()) != 0 and stdoutMd5.split(" ")[0] == oldMd5.split(" ")[0]:
    host_post_info.start_time = start_time
    command = "systemctl daemon-reload && systemctl enable zstack-network-agent.service && systemctl start zstack-network-agent.service"
    run_remote_command(add_true_in_command(command), host_post_info)
    handle_ansible_info("SUCC: Deploy zstack network agent successful(only enable and start)", host_post_info, "INFO")
    sys.exit(0)

run_remote_command(add_true_in_command("pkill zsn-agent; /bin/rm /etc/init.d/zstack-network-agent"), host_post_info)

service_env = "ZSNARGS=-log-file /var/log/zstack/zsn-agent/zsn-agent.log -tmout %s" % int(tmout)
replace_content("/usr/lib/systemd/system/zstack-network-agent.service", '''regexp='.*Environment=.*' replace="Environment='%s'"''' % service_env, host_post_info)

command = "systemctl daemon-reload && systemctl enable zstack-network-agent.service && systemctl restart zstack-network-agent.service"
run_remote_command(add_true_in_command(command), host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy zstack network agent successful(killed old one and restart)", host_post_info, "INFO")

sys.exit(0)

