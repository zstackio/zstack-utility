#!/usr/bin/env python
# encoding: utf-8
import argparse
import os.path
from zstacklib import *
from datetime import datetime

logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to transfer files from mn to host")

src_paths_in_mn = None
dst_paths_in_host = None

post_url = ""
remote_user = "root"
remote_pass = None
remote_port = None
require_python_env = "false"

# get parameter from shell
parser = argparse.ArgumentParser(description='Transfer files from MN to host')
parser.add_argument('-i', type=str, help="""specify inventory host file default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

# update the variable from shell arguments
args = parser.parse_args()
argument_dict = eval(args.e)
locals().update(argument_dict)

if src_paths_in_mn is None or dst_paths_in_host is None:
    handle_ansible_info("FAIL: source path or destination path is empty", host_post_info, "ERROR")
    sys.exit(1)
src_path_in_mn_list = src_paths_in_mn.split(',')
dst_path_in_host_list = dst_paths_in_host.split(',')
if len(src_path_in_mn_list) != len(dst_path_in_host_list):
    handle_ansible_info("FAIL: length of source path and destination path is not equal: src=%s dst=%s" % (src_paths_in_mn, dst_paths_in_host), host_post_info, "ERROR")
    sys.exit(1)

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

for index, src_path in enumerate(src_path_in_mn_list):
    dst_path = os.path.dirname(dst_path_in_host_list[index]) + '/'
    copy_arg = CopyArg()
    copy_arg.src = src_path
    copy_arg.dest = dst_path
    copy_arg.args = "mode=0644 force=yes"
    copy(copy_arg, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Transfer files to host successful: src=%s dst=%s" % (src_paths_in_mn, dst_paths_in_host), host_post_info, "INFO")
sys.exit(0)
