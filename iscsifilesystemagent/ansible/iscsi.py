#!/usr/bin/env python
# encoding: utf-8

import argparse
from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy iscsi agent")
start_time = datetime.now()
# set default value
file_root = "files/iscsi"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
post_url = ""
pkg_iscsiagent = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy iscsi to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/iscsi/" % zstack_root
iscsi_root = "%s/iscsi/package" % zstack_root
host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.host_uuid = host_uuid
host_post_info.post_url = post_url
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
if distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
    zstacklib_args.zstack_releasever = get_mn_apt_release()
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)

# name: judge this process is init install or upgrade
if file_dir_exist("path=" + iscsi_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (iscsi_root, virtenv_path)
    run_remote_command(command, host_post_info)

force_remove_file("%s/" % iscsi_root, host_post_info)

if distro in RPM_BASED_OS:
    if zstack_repo != 'false':
        # name: install iscsi related packages on RedHat based OS from user defined repo
        command = "yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y wget " \
                  "qemu-img-ev scsi-target-utils"  % (zstack_repo)
        run_remote_command(command, host_post_info)

    else:
        # name: install isci related packages on RedHat based OS from online
        for pkg in ['wget', 'qemu-img-ev', 'scsi-target-utils']:
            yum_install_package(pkg, host_post_info)
    if distro_version >= 7:
        # name: disable firewalld in RHEL7 and Centos7
        command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
        run_remote_command(command, host_post_info)
    # name: disable selinux on RedHat based OS
    set_selinux("state=disabled", host_post_info)
    # name: enable tgtd daemon on RedHat
    service_status("tgtd", "state=started enabled=yes", host_post_info)

elif distro in DEB_BASED_OS:
    # name: install isci related packages on Debian based OS
    install_pkg_list = ['iscsitarget', 'iscsitarget-dkms', 'tgt', 'wget', 'qemu-utils']
    apt_install_packages(install_pkg_list, host_post_info)
    # name: enable tgtd daemon on Debian
    service_status("iscsitarget", "state=started enabled=yes", host_post_info)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, iscsi_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: copy zstacklib and install zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (iscsi_root, pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
if zstack_lib_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = iscsi_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy iscsi filesystem agent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_iscsiagent)
copy_arg.dest = "%s/%s" % (iscsi_root, pkg_iscsiagent)
iscsiagent_copy = copy(copy_arg, host_post_info)

# name: copy iscsi service file
copy_arg = CopyArg()
copy_arg.src = "files/iscsi/zstack-iscsi"
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

if iscsiagent_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "iscsi agent"
    agent_install_arg.agent_root = iscsi_root
    agent_install_arg.pkg_name = pkg_iscsiagent
    agent_install(agent_install_arg, host_post_info)


# name: restart iscsiagent
service_status("zstack-iscsi", "state=restarted enabled=yes", host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy isci agent successful", host_post_info, "INFO")

sys.exit(0)
