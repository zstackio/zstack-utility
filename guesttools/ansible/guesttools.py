#!/usr/bin/env python
# encoding: utf-8
import argparse
import os.path
from zstacklib import *
from datetime import datetime

logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to download guest tools iso to host")

src_guest_tools_iso = None
dst_guest_tools_iso = None

post_url = ""
remote_user = "root"
remote_pass = None
remote_port = None
require_python_env = "false"

# get parameter from shell
parser = argparse.ArgumentParser(description='Download guest tools iso to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

# update the variable from shell arguments
args = parser.parse_args()
argument_dict = eval(args.e)
locals().update(argument_dict)

host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
host_post_info.post_url = post_url

if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

remote_create_dir(os.path.dirname(dst_guest_tools_iso), None, host_post_info)

copy_arg = CopyArg()
copy_arg.src = src_guest_tools_iso
copy_arg.dest = dst_guest_tools_iso
copy_arg.args = "mode=644"
copy(copy_arg, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Download guest tools iso to host successful", host_post_info, "INFO")
sys.exit(0)
