#!/usr/bin/env python
# encoding: utf-8
import argparse
import datetime

from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy zbs primary agent")
start_time = datetime.datetime.now()


# set default value
file_root = "files/zbsp"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
zstack_repo = 'false'
post_url = ""
chrony_servers = None
pkg_zbspagent = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None


# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy zbs primary strorage to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)


# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/zbsp/" % zstack_root
zbsp_root = "%s/zbsp/package" % zstack_root
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

zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = host_info.distro
zstacklib_args.distro_release = host_info.distro_release
zstacklib_args.distro_version = host_info.major_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.zstack_releasever = releasever
if host_info.distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)


# name: judge this process is init install or upgrade
if file_dir_exist("path=" + zbsp_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (zbsp_root, virtenv_path)
    run_remote_command(command, host_post_info)


# name: install dependencies
if host_info.distro in RPM_BASED_OS:
    common_rpm_list = "wget nmap"
    ky10_rpm_list = "nettle qemu-block-rbd"

    if zstack_repo != 'false':
        command = """pkg_list=`rpm -q {} | grep "not installed" | awk '{{ print $2 }}'` && for pkg"""\
                """ in $pkg_list; do yum --disablerepo=* --enablerepo={} install -y $pkg; done;"""\
                .format(common_rpm_list, zstack_repo)
        run_remote_command(command, host_post_info)

        if releasever in kylin:
            command = ("for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg || true; done;") % (
                ky10_rpm_list, zstack_repo)
            run_remote_command(command, host_post_info)

        if host_info.major_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    else:
        for pkg in common_rpm_list.split():
            yum_install_package(pkg, host_post_info)
        if host_info.major_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    set_selinux("state=disabled", host_post_info)
elif host_info.major_version in DEB_BASED_OS:
    install_pkg_list = ["wget", "qemu-utils","libvirt-bin", "libguestfs-tools"]
    apt_install_packages(install_pkg_list, host_post_info)
    command = "(chmod 0644 /boot/vmlinuz*) || true"
    run_remote_command(command, host_post_info)
else:
    error("Unsupported OS!")


# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, zbsp_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)


# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv --system-site-packages %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)


# name: copy zstacklib and install
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/" % zbsp_root
copy_arg.args = "force=yes"
zstack_lib_copy = copy(copy_arg, host_post_info)
if zstack_lib_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = zbsp_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)


# name: copy zbs primarystorage agent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_zbspagent)
copy_arg.dest = "%s/%s" % (zbsp_root, pkg_zbspagent)
copy_arg.args = "force=yes"
zbspagent_copy = copy(copy_arg, host_post_info)
if zbspagent_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zbs_primarystorage"
    agent_install_arg.agent_root = zbsp_root
    agent_install_arg.pkg_name = pkg_zbspagent
    agent_install(agent_install_arg, host_post_info)


# name: copy service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-zbs-primarystorage" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)


# name: copy iptables file
copy_arg = CopyArg()
copy_arg.src = "%s/zbsps-iptables" % file_root
copy_arg.dest = "/var/lib/zstack/zbsp/package/zbsps-iptables"
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)


# name: restart zbspagent
if host_info.distro in RPM_BASED_OS:
    command = "service zstack-zbs-primarystorage stop && service zstack-zbs-primarystorage start" \
              " && chkconfig zstack-zbs-primarystorage on"
elif host_info.distro in DEB_BASED_OS:
    command = "update-rc.d zstack-zbs-primarystorage start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-zbs-primarystorage stop && service zstack-zbs-primarystorage start"
run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy zbs primary agent successful", host_post_info, "INFO")

sys.exit(0)
