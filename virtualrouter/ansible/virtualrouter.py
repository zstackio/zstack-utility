#!/usr/bin/env python
# encoding =  utf-8
import os,sys
import argparse
import ast
from zstacklib import *

start_time = datetime.now()
# set default value
file_root = "files/virtualrouter"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
yum_repo = 'false'
post_url = ""

# get paramter from shell
parser = argparse.ArgumentParser(description='Deploy virtual Router to host')
parser.add_argument('-i',type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key',type=str,help='use this file to authenticate the connection')
parser.add_argument('-e',type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = ast.literal_eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/virtualrouter/" % zstack_root
vr_root = "%s/virtualrouter" % zstack_root
host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.post_url = post_url
host_post_info.private_key = args.private_key

# tmp inject operation
command = "echo 'nameserver 114.114.114.114' > /etc/resolv.conf"
run_remote_command(command, host_post_info)

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

# name: create root directories
command = 'mkdir -p %s %s' % (vr_root,virtenv_path)
run_remote_command(command, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    if yum_repo != 'false':
        # name: install appliance vm related packages on RedHat based OS from user defined repo
        command = "yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y haproxy dnsmasq" % yum_repo
    else:
        # name: install virtual router related packages for RedHat
        for pkg in ["haproxy","dnsmasq"]:
            yum_install_package(pkg, host_post_info)
elif distro == "Debian" or distro == "Ubuntu":
    # name: install virtual router related packages for Debian
    apt_install_packages("dnsmasq", host_post_info)
else:
    print "unsupported OS!"
    sys.exit(1)

check_and_install_virtual_env("12.1.1", trusted_host, pip_url, host_post_info)

# name: create virtualenv
command = "rm -rf %s && rm -f %s/%s && rm -f %s/%s && virtualenv %s" % \
          (virtenv_path, vr_root, pkg_zstacklib, vr_root, pkg_virtualrouter, virtenv_path)
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
copy_arg.src="%s/sysctl.conf" % file_root
copy_arg.dest="/etc/sysctl.conf"
copy(copy_arg, host_post_info)

# name: copy dnsmasq conf file
copy_arg = CopyArg()
copy_arg.src="%s/dnsmasq.conf" % file_root
copy_arg.dest="/etc/dnsmasq.conf"
copy(copy_arg, host_post_info)

if chroot_env == 'false':
    # name: enable dnsmasq service
    service_status("name=dnsmasq enabled=yes state=started", host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src="files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest="%s/%s" % (vr_root,pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
#if zstack_lib_copy == "changed:true":
pip_install_arg = PipInstallArg()
pip_install_arg.name = "%s/%s" % (vr_root,pkg_zstacklib)
pip_install_arg.extra_args =  "\"--ignore-installed --trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv = virtenv_path
pip_install_arg.virtualenv_site_packages = "yes"
pip_install_package(pip_install_arg,host_post_info)

# name: copy virtual router
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root,pkg_virtualrouter)
copy_arg.dest = "%s/%s" % (vr_root,pkg_virtualrouter)
vragent_copy = copy(copy_arg, host_post_info)
pip_install_arg = PipInstallArg()
pip_install_arg.name="%s/%s" % (vr_root,pkg_virtualrouter)
pip_install_arg.extra_args="\"--ignore-installed --trusted-host %s -i %s\"" % (trusted_host,pip_url)
pip_install_arg.virtualenv="%s" % virtenv_path
pip_install_arg.virtualenv_site_packages="yes"
pip_install_package(pip_install_arg,host_post_info)

# name: copy virtual rourte service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-virtualrouter" % file_root
copy_arg.dest ="/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

if chroot_env == 'false':
    # name: restart vr
    service_status("name=zstack-virtualrouter enabled=yes state=restarted", host_post_info)
    # name: restart dnsmasq
    service_status("name=dnsmasq state=restarted enabled=yes", host_post_info)
else:
    if distro == "RedHat" or distro == "CentOS":
        service_status("name=zstack-virtualrouter enabled=yes state=stopped", host_post_info)
    else:
        command = "sed -i '/zstack-virtualrouter start/d' /etc/rc.local"
        run_remote_command(command, host_post_info)
        update_file("/etc/rc.local", regexp="exit 0", insertbefore="exit 0", line="/etc/init.d/zstack-virtualrouter start\n")

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy virtualrouter successful", host_post_info, "INFO")

sys.exit(0)
