#!/usr/bin/env python
# encoding: utf-8
import argparse
import datetime

from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy console proxy agent")
start_time = datetime.datetime.now()
# set default value
file_root = "files/consoleproxy"
pip_url = 'https://pypi.python.org/simple/'
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
post_url = ""
chrony_servers = None
pkg_consoleproxy = ""
http_console_proxy_port = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy consoleproxy to management node')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)
locals().update(argument_dict)
# update the variable from shell arguments
virtenv_path = "%s/virtualenv/consoleproxy/" % zstack_root
consoleproxy_root = "%s/console/package" % zstack_root
host_post_info = HostPostInfo()
host_post_info.host = host
host_post_info.host_uuid = host_uuid
host_post_info.host_inventory = args.i

host_post_info.post_url = post_url
host_post_info.chrony_servers = chrony_servers
host_post_info.transport = 'local'


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
if file_dir_exist("path=" + consoleproxy_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (consoleproxy_root, virtenv_path)
    run_remote_command(command, host_post_info)

# name: create zstack-baremetal-nginx.service
command = """
mkdir -p /var/log/zstack/zstack-baremetal-nginx
touch /var/log/zstack/zstack-baremetal-nginx/error.log
touch /var/log/zstack/zstack-baremetal-nginx/access.log
mkdir -p /var/lib/zstack/nginx/baremetal/v1/pxeserver/conf.d/
mkdir -p /var/lib/zstack/nginx/baremetal/v1/management_node/
mkdir -p /var/lib/zstack/nginx/baremetal/v2/gateway/conf.d/
mkdir -p /var/lib/zstack/nginx/baremetal/v2/management_node/

iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport {PORT} -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport {PORT} -j ACCEPT

echo -e "[Unit]
Description=ZStack BareMetal Nginx Service
After=network.target remote-fs.target nss-lookup.target

[Service]
Type=forking
Restart=always
RestartSec=3
PIDFile=/var/run/zstack/zstack-baremetal-nginx.pid
ExecStartPre=/usr/bin/rm -f /var/run/zstack/zstack-baremetal-nginx.pid
ExecStartPre=/usr/sbin/nginx -t -c /var/lib/zstack/nginx/baremetal/zstack-baremetal-nginx.conf
ExecStart=/usr/sbin/nginx -c /var/lib/zstack/nginx/baremetal/zstack-baremetal-nginx.conf
ExecReload=/bin/kill -s HUP \$MAINPID
KillSignal=SIGQUIT
TimeoutStopSec=5
KillMode=process
PrivateTmp=true

[Install]
WantedBy=multi-user.target" > /usr/lib/systemd/system/zstack-baremetal-nginx.service

systemctl disable zstack-baremetal-nginx.service

echo -e "user nginx;
worker_processes auto;
include /usr/share/nginx/modules/*.conf;
pid /var/run/zstack/zstack-baremetal-nginx.pid;
error_log /var/log/zstack/zstack-baremetal-nginx/error.log;

events {{
    worker_connections 1024;
}}

http {{
    access_log          /var/log/zstack/zstack-baremetal-nginx/access.log;
    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;
    keepalive_timeout   1000;
    types_hash_max_size 2048;
    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    map \$http_upgrade \$connection_upgrade {{
        default upgrade;
        ''      close;
    }}

    server {{
        listen  {PORT};

        # baremetal v1 proxy conf on pxeserver, e.g. sendcommand / instance terminal
        include /var/lib/zstack/nginx/baremetal/v1/pxeserver/*.conf;

        # baremetal v1 proxy conf on management node, e.g. instance terminal
        include /var/lib/zstack/nginx/baremetal/v1/management_node/*.conf;

        # baremetal v2 proxy conf on gateway, e.g. instance agent path / send hardware info / callback
        include /var/lib/zstack/nginx/baremetal/v2/gateway/*.conf;

        # baremetal v2 proxy conf on management node, e.g. instance terminal
        include /var/lib/zstack/nginx/baremetal/v2/management_node/*.conf;
    }}
}}

stream {{
    # baremetal v1 proxy conf on pxeserver, e.g. instance vnc
    include /var/lib/zstack/nginx/baremetal/v1/pxeserver/conf.d/*.tcp;

    # baremetal v2 proxy conf on gateway, e.g. instance vnc/rdp/terminal
    include /var/lib/zstack/nginx/baremetal/v2/gateway/conf.d/*.tcp;
}}" > /var/lib/zstack/nginx/baremetal/zstack-baremetal-nginx.conf
"""
run_remote_command(command.format(PORT=http_console_proxy_port), host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/" % consoleproxy_root
copy_arg.args = "force=yes"
copy_zstacklib = copy(copy_arg, host_post_info)
# name: copy consoleproxy
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_consoleproxy)
copy_arg.dest = "%s/%s" % (consoleproxy_root, pkg_consoleproxy)
copy_arg.args = "force=yes"
copy_consoleproxy = copy(copy_arg, host_post_info)
# only for os using init.d not systemd
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-consoleproxy" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, consoleproxy_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: install zstacklib
agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
agent_install_arg.agent_name = "zstacklib"
agent_install_arg.agent_root = consoleproxy_root
agent_install_arg.pkg_name = pkg_zstacklib
agent_install(agent_install_arg, host_post_info)

# name: install consoleproxy
agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
agent_install_arg.agent_name = "consoleproxy"
agent_install_arg.agent_root = consoleproxy_root
agent_install_arg.pkg_name = pkg_consoleproxy
agent_install(agent_install_arg, host_post_info)

# name: restart consoleproxy
if chroot_env == 'false':
    if host_info.distro in RPM_BASED_OS:
        command = "service zstack-consoleproxy stop && service zstack-consoleproxy start && chkconfig zstack-consoleproxy on"
    elif host_info.distro in DEB_BASED_OS:
        command = "update-rc.d zstack-consoleproxy start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-consoleproxy stop && service zstack-consoleproxy start"
    run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy consoleproxy agent successful", host_post_info, "INFO")

sys.exit(0)

