#!/usr/bin/env python
# encoding =  utf-8
import argparse
import datetime

from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy virtual router agent")
start_time = datetime.datetime.now()
# set default value
file_root = "files/virtualrouter"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
post_url = ""
chrony_servers = None
pkg_virtualrouter = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy virtual Router to host')
parser.add_argument('-i', type=str,  help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/virtualrouter/" % zstack_root
vr_root = "%s/virtualrouter/package" % zstack_root
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
if file_dir_exist("path=" + vr_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (vr_root, virtenv_path)
    run_remote_command(command, host_post_info)

run_remote_command("rm -rf %s/*" % vr_root, host_post_info)

if host_info.distro in RPM_BASED_OS:
    if zstack_repo != 'false':
        # name: install vr related packages on RedHat based OS from user defined repo
        command = ("pkg_list=`rpm -q haproxy dnsmasq | grep \"not installed\" | awk '{ print $2 }'` && for pkg"
                   " in $pkg_list; do yum --disablerepo=* --enablerepo=%s install -y $pkg; done;") % (zstack_repo)
        run_remote_command(command, host_post_info)
    else:
        # name: install virtual router related packages for RedHat
        for pkg in ["haproxy", "dnsmasq"]:
            yum_install_package(pkg, host_post_info)
elif host_info.distro in DEB_BASED_OS:
    # name: install virtual router related packages for Debian
    apt_install_packages(["dnsmasq"], host_post_info)
else:
    error("unsupported OS!")

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, vr_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: create dnsmasq host dhcp file
command = "/bin/touch /etc/hosts.dhcp"
run_remote_command(command, host_post_info)

# name: create dnsmasq host option file
command = "/bin/touch /etc/hosts.option"
run_remote_command(command, host_post_info)

# name: create dnsmasq host dns file
command = "/bin/touch /etc/hosts.dns"
run_remote_command(command, host_post_info)

# name: copy sysctl.conf
copy_arg = CopyArg()
copy_arg.src = "%s/sysctl.conf" % file_root
copy_arg.dest = "/etc/sysctl.conf"
copy(copy_arg, host_post_info)

# name: copy dnsmasq conf file
copy_arg = CopyArg()
copy_arg.src = "%s/dnsmasq.conf" % file_root
copy_arg.dest = "/etc/dnsmasq.conf"
copy(copy_arg, host_post_info)

if chroot_env == 'false':
    # name: enable dnsmasq service
    service_status("dnsmasq", "enabled=yes state=started", host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (vr_root, pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
if zstack_lib_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = vr_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy virtual router
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_virtualrouter)
copy_arg.dest = "%s/%s" % (vr_root, pkg_virtualrouter)
vragent_copy = copy(copy_arg, host_post_info)

if vragent_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "virtualrouter"
    agent_install_arg.agent_root = vr_root
    agent_install_arg.pkg_name = pkg_virtualrouter
    agent_install(agent_install_arg, host_post_info)

# name: copy virtual router service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-virtualrouter" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

if chroot_env == 'false':
    # name: restart vr
    command = "service zstack-virtualrouter stop && service zstack-virtualrouter start"
    run_remote_command(command, host_post_info)
    # name: restart dnsmasq
    service_status("dnsmasq", "state=restarted enabled=yes", host_post_info)
else:
    if host_info.distro in RPM_BASED_OS:
        service_status("zstack-virtualrouter", "enabled=yes state=stopped", host_post_info)
    else:
        replace_content("/etc/rc.local",
                        "regexp='zstack-virtualrouter start'",
                        host_post_info)
        update_file("/etc/rc.local", regexp="exit 0", insertbefore="exit 0", line="/etc/init.d/zstack-virtualrouter start\n")

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy virtualrouter successful", host_post_info, "INFO")

sys.exit(0)
