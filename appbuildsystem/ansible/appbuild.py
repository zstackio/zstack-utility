#!/usr/bin/env python
# encoding: utf-8
import argparse
import datetime

from zstacklib import *


# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy app build system agent")
start_time = datetime.datetime.now()
# set default value
file_root = "files/appbuild"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
zstack_repo = 'false'
post_url = ""
chrony_servers = None
pkg_appbuildsystemagent = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None


# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy app build system to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/appbuildsystem/" % zstack_root
appbuild_root = "%s/appbuildsystem/package" % zstack_root
host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
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

zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = host_info.distro
zstacklib_args.distro_release = host_info.distro_release
zstacklib_args.distro_version = host_info.major_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.yum_server = yum_server
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.zstack_releasever = releasever
zstacklib = ZstackLib(zstacklib_args)

# name: judge this process is init install or upgrade
if file_dir_exist("path=" + appbuild_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (appbuild_root, virtenv_path)
    run_remote_command(command, host_post_info)


if host_info.distro in RPM_BASED_OS:
    dep_pkg = "wget qemu-img"
    py3_rpms = ' python3.11 python3.11-devel python3.11-pip libffi-devel openssl-devel'
    if releasever in ['h84']:
        dep_pkg += py3_rpms

    if zstack_repo != 'false':
        command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg"
                   " in $pkg_list; do yum --disablerepo=* --enablerepo=%s install -y $pkg; done;") % (dep_pkg, zstack_repo)
        run_remote_command(command, host_post_info)
        if host_info.major_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    else:
        for pkg in dep_pkg.split():
            yum_install_package(pkg, host_post_info)
        if host_info.major_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    set_selinux("state=disabled", host_post_info)

elif host_info.distro in DEB_BASED_OS:
    install_pkg_list = ["wget", "qemu-utils", "libvirt-bin", "libguestfs-tools"]
    apt_install_packages(install_pkg_list, host_post_info)
    command = "(chmod 0644 /boot/vmlinuz*) || true"
    run_remote_command(command, host_post_info)
else:
    error("unsupported OS!")

# name: install virtualenv
py_version = get_virtualenv_python_version(virtenv_path, host_post_info)
if py_version and not py_version.startswith("3.11"):
    command = "rm -rf %s" % virtenv_path
    run_remote_command(command, host_post_info)
    py_version = None

if not py_version:
    # name: make sure virtualenv has been setup
    command = "python3.11 -m venv %s --system-site-packages" % virtenv_path
    run_remote_command(command, host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/" % appbuild_root
copy_arg.args = "force=yes"
copy_zstacklib = copy(copy_arg, host_post_info)

if copy_zstacklib != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = appbuild_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy app buildsystem agent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_appbuildsystemagent)
copy_arg.dest = "%s/%s" % (appbuild_root, pkg_appbuildsystemagent)
copy_arg.args = "force=yes"
copy_appbuild = copy(copy_arg, host_post_info)

if copy_appbuild != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "appbuildsystem"
    agent_install_arg.agent_root = appbuild_root
    agent_install_arg.pkg_name = pkg_appbuildsystemagent
    agent_install(agent_install_arg, host_post_info)

# name: copy service file
# only support centos redhat debian and ubuntu
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-app-buildsystem" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755 force=yes"
copy(copy_arg, host_post_info)


# name: restart appbuildsystemagent
if host_info.distro in RPM_BASED_OS:
    command = "service zstack-app-buildsystem stop && service zstack-app-buildsystem start && chkconfig zstack-app-buildsystem on"
elif host_info.distro in DEB_BASED_OS:
    command = "update-rc.d zstack-app-buildsystem start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-app-buildsystem stop && service zstack-app-buildsystem start"
run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy appbuildsystem agent successful", host_post_info, "INFO")

sys.exit(0)
