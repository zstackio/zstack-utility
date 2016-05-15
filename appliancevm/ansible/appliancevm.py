#!/usr/bin/env python
# encoding: utf-8

import argparse
from zstacklib import *

start_time = datetime.now()
# set default value
file_root = "files/appliancevm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
post_url = ""
pkg_appliancevm = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy appliancevm to management node')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)
locals().update(argument_dict)
# if use offline image, we will use mn node as http server
if zstack_repo == 'zstack-local':
    zstack_repo = 'zstack-mn'

# update the variable from shell arguments
virtenv_path = "%s/virtualenv/appliancevm/" % zstack_root
appliancevm_root = "%s/appliancevm" % zstack_root
host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.post_url = post_url
host_post_info.private_key = args.private_key

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
zstacklib = ZstackLib(zstacklib_args)

# name: judge this process is init install or upgrade
if file_dir_exist("path=" + appliancevm_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (appliancevm_root, virtenv_path)
    run_remote_command(command, host_post_info)

# name: copy zstacklib and install
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (appliancevm_root, pkg_zstacklib)
copy_zstacklib = copy(copy_arg, host_post_info)

# name: copy appliancevm and install
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_appliancevm)
copy_arg.dest = "%s/%s" % (appliancevm_root, pkg_appliancevm)
copy_appliancevm = copy(copy_arg, host_post_info)

# name: copy bootstrap script
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-appliancevm-bootstrap.py" % file_root
copy_arg.dest = '/sbin/zstack-appliancevm-bootstrap.py'
copy_arg.args = "mode=0777"
copy(copy_arg, host_post_info)

# name: copy appliancevm service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-appliancevm" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, appliancevm_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)


if distro == "RedHat" or distro == "CentOS":
    if zstack_repo != 'false':
        # name: install appliance vm related packages on RedHat based OS from user defined repo
        command = "yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y iputils tcpdump ethtool" % zstack_repo
        run_remote_command(command, host_post_info)
    else:
        # name: install appliance vm related packages on RedHat based OS
        for pkg in ['iputils', 'tcpdump', 'ethtool']:
            yum_install_package("openssh-clients", host_post_info)
    if distro_version >= 7:
        # name: workaround RHEL7 iptables service issue
        command = 'mkdir -p /var/lock/subsys/'
        run_remote_command(command, host_post_info)
        # name: remove RHEL7 firewalld
        yum_remove_package("firewalld", host_post_info)
    # name: copy iptables initial rules in RedHat
    copy_arg = CopyArg()
    copy_arg.src = "%s/iptables" % file_root
    copy_arg.dest = "/etc/sysconfig/iptables"
    iptables_copy_result = copy(copy_arg, host_post_info)
    if chroot_env == 'false':
        if iptables_copy_result != "changed:False":
            service_status("iptables", "state=restarted enabled=yes", host_post_info)
    else:
        # name: enable appliancevm service for RedHat on chroot
        service_status("zstack-appliancevm", "enabled=yes state=stopped", host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    install_pkg_list = ['iputils-arping', 'tcpdump', 'ethtool']
    apt_install_packages(install_pkg_list, host_post_info)
    # name: copy iptables initial rules in Debian
    copy_arg = CopyArg()
    copy_arg.src = "%s/iptables" % file_root
    copy_arg.dest = "/etc/iptables"
    copy(copy_arg, host_post_info)
    # name: copy iptables initial start script in Debian
    copy_arg = CopyArg()
    copy_arg.src = "%s/iptables.up" % file_root
    copy_arg.dest = "/etc/network/if-pre-up.d/iptables.up"
    copy_arg.args = "mode=0777"
    iptables_script_result = copy(copy_arg, host_post_info)
    if iptables_script_result == "status:changed":
        command = "/etc/network/if-pre-up.d/iptables.up"
        run_remote_command(command, host_post_info)
    # name: enable appliancevm service for Debian -1
    command = "sed -i '/zstack-appliancevm start/d' /etc/rc.local"
    run_remote_command(command, host_post_info)
    # name: enable appliancevm service for Debian -2
    update_arg = "insertbefore='^exit 0' line='/etc/init.d/zstack-appliancevm start\n'"
    update_file("/etc/rc.local", update_arg, host_post_info)
    # name: restore iptables
    command = '/etc/network/if-pre-up.d/iptables.up'
    run_remote_command(command, host_post_info)

else:
    print "unsupported OS!"
    sys.exit(1)


# name: install zstacklib
if copy_zstacklib != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "appliancevm"
    agent_install_arg.agent_root = appliancevm_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: install appliancevm
if copy_appliancevm != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "appliancevm"
    agent_install_arg.agent_root = appliancevm_root
    agent_install_arg.pkg_name = pkg_appliancevm
    agent_install(agent_install_arg, host_post_info)

if chroot_env == 'false':
    # name: restart appliancevm
    service_status("zstack-appliancevm", "enabled=yes state=restarted", host_post_info)
else:
    if distro == "RedHat" or distro == "CentOS":
        # name: restart iptables
        service_status("iptables", "state=restarted enabled=yes", host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy appliancevm successful", host_post_info, "INFO")

sys.exit(0)
