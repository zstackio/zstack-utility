#!/usr/bin/env python
# encoding: utf-8
import os
import sys
import argparse
import ast
from deploylib import *
from zstacklib import *

# set default value
file_root = "files/consoleproxy"
pypi_url = 'https://pypi.python.org/simple/'
proxy = ""
sproxy = ""
chroot_env = 'false'
yum_repo = 'false'
post_url = ""

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy consoleproxy to management node')
parser.add_argument('-i',type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key',type=str,help='use this file to authenticate the connection')
parser.add_argument('-e',type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = ast.literal_eval(args.e)
locals().update(argument_dict)

#update the variable from shell arguments
virtenv_path = "%svirtualenv/consoleproxy/" % zstack_root
consoleproxy_root = "%sconsole" % zstack_root
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

# name: create root directories
command = 'mkdir -p %s %s' % (consoleproxy_root, virtenv_path)
run_remote_command(command, host_post_info)

# name: install virtualenv
check_and_install_virtual_env("12.1.1", trusted_host, pip_url, host_post_info)

# name: create virtualenv
command = "rm -rf %s && rm -f %s/%s && rm -f %s/%s && virtualenv %s" % (virtenv_path, consoleproxy_root,
                                                                        pkg_zstacklib, consoleproxy_root,
                                                                        pkg_consoleproxy, virtenv_path)
run_remote_command(command, host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (consoleproxy_root, pkg_zstacklib)
result = copy(copy_arg, host_post_info)

# name: install zstacklib
#if result == "changed:true":
pip_install_arg = PipInstallArg()
pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (trusted_host, pip_url)
pip_install_arg.name = "%s/%s" % (consoleproxy_root, pkg_zstacklib)
pip_install_arg.virtualenv = virtenv_path
pip_install_arg.virtualenv_site_packages = "yes"
pip_install_package(pip_install_arg, host_post_info)

# only for os using init.d not systemd
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-consoleproxy" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: copy consoleproxy
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_consoleproxy)
copy_arg.dest = "%s/%s" % (consoleproxy_root, pkg_consoleproxy)
result = copy(copy_arg, host_post_info)
# name: install consoleproxy
pip_install_arg = PipInstallArg()
pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (trusted_host, pip_url)
pip_install_arg.name = "%s/%s" % (consoleproxy_root, pkg_consoleproxy)
pip_install_arg.virtualenv = virtenv_path
pip_install_package(pip_install_arg, host_post_info)

# name: restart consoleproxy
if chroot_env == 'false':
    service_status("name=zstack-consoleproxy state=restarted enabled=yes", host_post_info)
sys.exit(0)
