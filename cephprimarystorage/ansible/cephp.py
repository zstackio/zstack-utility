#!/usr/bin/env python
# encoding: utf-8
import argparse
from zstacklib import *

start_time = datetime.now()
# set default value
file_root = "files/cephp"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
yum_repo = 'false'
post_url = ""
pkg_cephpagent = ""
virtualenv_version = "12.1.1"

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy ceph primary strorage to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/cephp/" % zstack_root
cephp_root = "%s/cephp" % zstack_root
# create log
logger_dir = zstack_root + "/deploy-log/"
create_log(logger_dir)
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


# name: judge this process is init install or upgrade
if file_dir_exist("path=" + cephp_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (cephp_root, virtenv_path)
    run_remote_command(command, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    if yum_repo != 'false':
        command = "yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y wget qemu-img" % yum_repo
        run_remote_command(command, host_post_info)
        if distro_version >= 7:
            command = "rpm -q iptables-services || yum --disablerepo=* --enablerepo=%s --nogpgcheck install" \
                      " -y iptables-services " % yum_repo
            run_remote_command(command, host_post_info)
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    else:
        for pkg in ["wget", "qemu-img"]:
            yum_install_package(pkg, host_post_info)
        if distro_version >= 7:
            command = "rpm -q iptables-services || yum --nogpgcheck install -y iptables-services "
            run_remote_command(command, host_post_info)
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    set_selinux("state=permissive policy=targeted", host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    for pkg in ["wget", "qemu-utils"]:
        apt_install_packages(pkg, host_post_info)
else:
    print "unsupported OS!"
    sys.exit(1)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, cephp_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv --system-site-packages %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: copy zstacklib and install
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (cephp_root, pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
if zstack_lib_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = cephp_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy ceph primarystorage agent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_cephpagent)
copy_arg.dest = "%s/%s" % (cephp_root, pkg_cephpagent)
cephpagent_copy = copy(copy_arg, host_post_info)
if cephpagent_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "ceph_primarystorage"
    agent_install_arg.agent_root = cephp_root
    agent_install_arg.pkg_name = pkg_cephpagent
    agent_install(agent_install_arg, host_post_info)

# name: copy service file
# only support centos redhat debian and ubuntu
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-ceph-primarystorage" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)
# name: restart cephpagent
service_status("zstack-ceph-primarystorage", "state=restarted enabled=yes", host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy ceph primary agent successful", host_post_info, "INFO")

sys.exit(0)
