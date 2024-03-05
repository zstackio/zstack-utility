#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import hashlib
import sys
import os
import subprocess
import signal
import getpass
import urlparse

import gzip
import simplejson
from termcolor import colored
import ConfigParser
import StringIO
import functools
import time
import random
import string
from configobj import ConfigObj
import tempfile
import pwd, grp
import traceback
import uuid
import yaml
import re
import OpenSSL
import glob
from shutil import copyfile
from shutil import rmtree

from utils import linux, lock
from zstacklib import *
import log_collector
import jinja2
import socket
import struct
import fcntl
import commands
import threading
import itertools
import platform
from  datetime import datetime, timedelta
import multiprocessing
import base64
from Crypto.Cipher import AES
from Crypto.Util.py3compat import *
from hashlib import md5
from string import Template
from timeline import TaskTimeline, __doc__ as timeline_doc

mysql_db_config_script='''
#!/bin/bash
echo "modify my.cnf"
if [ -f /etc/mysql/mariadb.conf.d/50-server.cnf ]; then
    #ubuntu 16.04
    mysql_conf=/etc/mysql/mariadb.conf.d/50-server.cnf
elif [ -f /etc/mysql/my.cnf ]; then
    # Ubuntu 14.04
    mysql_conf=/etc/mysql/my.cnf
elif [ -f /etc/my.cnf.d/mariadb-server.cnf ]; then
    # MariaDB 10.3.9 CentOS.8/Kylin.V10
    mysql_conf=/etc/my.cnf.d/mariadb-server.cnf
elif [ -f /etc/my.cnf ]; then
    # centos
    mysql_conf=/etc/my.cnf
fi

if [ -z $mysql_conf ]; then
    echo "failed to find my.cnf" >&2
    exit 1
fi

sed -i 's/^bind-address/#bind-address/' $mysql_conf
sed -i 's/^skip-networking/#skip-networking/' $mysql_conf
sed -i 's/^bind-address/#bind-address/' $mysql_conf

grep 'binlog_format=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "binlog_format=mixed"
    sed -i '/\[mysqld\]/a binlog_format=mixed\' $mysql_conf
fi

grep 'log_bin_trust_function_creators=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "log_bin_trust_function_creators=1"
    sed -i '/\[mysqld\]/a log_bin_trust_function_creators=1\' $mysql_conf
fi

grep 'expire_logs=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "expire_logs=30"
    sed -i '/\[mysqld\]/a expire_logs=30\' $mysql_conf
fi

grep 'max_binlog_size=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "max_binlog_size=500m"
    sed -i '/\[mysqld\]/a max_binlog_size=500m\' $mysql_conf
fi

grep 'log-bin=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "log-bin=mysql-binlog"
    sed -i '/\[mysqld\]/a log-bin=mysql-binlog\' $mysql_conf
fi

# Fixes ZSTAC-24460
# if max_allowed_packet is not configured, then update from default value 1M to 4M
grep 'max_allowed_packet' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "max_allowed_packet=4M"
    sed -i '/\[mysqld\]/a max_allowed_packet=4M\' $mysql_conf
fi

# wanted_files = 10+max_connections+table_open_cache*2
# 'table_open_cache' is default to 400 as of 5.5.x
grep 'max_connections' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "max_connections=400"
    sed -i '/\[mysqld\]/a max_connections=400\' $mysql_conf
else
    echo "max_connections=400"
    sed -i 's/max_connections.*/max_connections=400/g' $mysql_conf
fi

grep 'interactive_timeout' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "interactive_timeout=600"
    sed -i '/\[mysqld\]/a interactive_timeout=600\' $mysql_conf
fi

grep 'wait_timeout' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "wait_timeout=600"
    sed -i '/\[mysqld\]/a wait_timeout=600\' $mysql_conf
fi

grep 'log-error' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "log-error=/var/log/mariadb/mariadb.log"
    sed -i '/\[mysqld\]/a log-error=/var/log/mariadb/mariadb.log\' $mysql_conf
fi

grep 'slave_net_timeout=' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "slave_net_timeout=60"
    sed -i '/\[mysqld\]/a slave_net_timeout=60\' $mysql_conf
fi

sed -i '/\[Service\]/a TimeoutStartSec=300' /usr/lib/systemd/system/mariadb.service

mkdir -p /etc/systemd/system/mariadb.service.d/
echo -e "[Service]\nLimitNOFILE=2048" > /etc/systemd/system/mariadb.service.d/limits.conf
systemctl daemon-reload || true

grep '^character-set-server' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "binlog_format=mixed"
    sed -i '/\[mysqld\]/a character-set-server=utf8\' $mysql_conf
fi
grep '^skip-name-resolve' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    sed -i '/\[mysqld\]/a skip-name-resolve\' $mysql_conf
fi

grep 'tmpdir' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    mysql_tmp_path="/var/lib/zstack-mysql-tmp"
    if [ ! -x "$mysql_tmp_path" ]; then
        mkdir "$mysql_tmp_path"
        chown mysql:mysql "$mysql_tmp_path"
        chmod 1777 "$mysql_tmp_path"
    fi
    echo "tmpdir=$mysql_tmp_path"
    sed -i "/\[mysqld\]/a tmpdir=$mysql_tmp_path" $mysql_conf
fi

if [ `systemctl is-active mariadb` != "unknown" ]; then 
    systemctl restart mariadb
fi
'''

mysqldump_skip_tables = "--ignore-table=zstack.VmUsageHistoryVO --ignore-table=zstack.RootVolumeUsageHistoryVO " \
                        "--ignore-table=zstack.NotificationVO --ignore-table=zstack.PubIpVmNicBandwidthUsageHistoryVO " \
                        "--ignore-table=zstack.DataVolumeUsageHistoryVO " \
                        "--ignore-table=zstack.ResourceUsageVO --ignore-table=zstack.PciDeviceUsageHistoryVO " \
                        "--ignore-table=zstack.PubIpVipBandwidthUsageHistoryVO"

zstone_db_dump_skip_tables = ""

# pre install scripts
# prepare yum configurations
configure_yum_repo_script = '''
if [ -f /etc/redhat-release ]; then
    os_release=`cat /etc/redhat-release`
    if [[ $os_release =~ ' 7' ]]; then
        [ -d /etc/yum.repos.d/ ] &&  [ ! -f /etc/yum.repos.d/epel.repo ] && cat << 'EOF' > /etc/yum.repos.d/epel.repo
[epel]
name=Extra Packages for Enterprise Linux $releasever - $basearce - mirrors.aliyun.com
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0
EOF
    elif [[ $os_release =~ ' 8' ]]; then
        [ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && cat << 'EOF' > /etc/yum.repos.d/epel.repo
[epel]
name=Extra Packages for Enterprise Linux $releasever - $basearce - mirrors.aliyun.com
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-8&arch=$basearch
enabled=0
gpgcheck=0
EOF
    else
        [ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && cat << 'EOF' > /etc/yum.repos.d/epel.repo
[epel]
name=Extra Packages for Enterprise Linux $releasever - $basearce - mirrors.aliyun.com
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0
EOF
    fi

    if [[ $os_release =~ ' 8' ]]; then
        [ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/zstack-aliyun-yum.repo ] && cat << 'EOF' > /etc/yum.repos.d/zstack-aliyun-yum.repo
#aliyun base
[alibase]
name=Rocky-$releasever - Base - mirrors.aliyun.com
baseurl=https://mirrors.aliyun.com/rockylinux/$releasever/BaseOS/$basearch/os/
gpgcheck=0
enabled=0
module_hotfixes=true

#released updates
[aliupdates]
name=Rocky-$releasever - Updates - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/rockylinux/$releasever/AppStream/$basearch/os/
enabled=0
gpgcheck=0
module_hotfixes=true

[aliextras]
name=Rocky-$releasever - Extras - mirrors.aliyun.com
baseurl=https://mirrors.aliyun.com/rockylinux/$releasever/extras/$basearch/os/
enabled=0
gpgcheck=0
module_hotfixes=true

[aliepel]
name=Extra Packages for Enterprise Linux $releasever - $basearce - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/epel/$releasever/Everything/$basearch
enabled=0
gpgcheck=0
module_hotfixes=true

[aliepel-modular]
name=Extra Packages for Enterprise Linux Modular $releasever - $basearce - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/epel/$releasever/Modular/$basearch
enabled=0
gpgcheck=0
module_hotfixes=true
EOF
        [ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/zstack-163-yum.repo ] && cat << 'EOF' > /etc/yum.repos.d/zstack-163-yum.repo
#163 base
[163base]
name=Rocky-$releasever - Base - mirrors.163.com
baseurl=http://mirrors.163.com/rocky/$releasever/BaseOS/$basearch/os/
gpgcheck=0
enabled=0
module_hotfixes=true

#released updates
[163updates]
name=Rocky-$releasever - Updates - mirrors.163.com
baseurl=http://mirrors.163.com/rocky/$releasever/AppStream/$basearch/os/
enabled=0
gpgcheck=0
module_hotfixes=true

#additional packages that may be useful
[163extras]
name=Rocky-$releasever - Extras - mirrors.163.com
baseurl=http://mirrors.163.com/rocky/$releasever/extras/$basearch/os/
enabled=0
gpgcheck=0
module_hotfixes=true

[ustcepel]
name=Extra Packages for Enterprise Linux $releasever - $basearch - ustc
baseurl=http://mirrors.ustc.edu.cn/epel/$releasever/Everything/$basearch
enabled=0
gpgcheck=0
module_hotfixes=true

[ustcepel-modular]
name=Extra Packages for Enterprise Linux Modular $releasever - $basearch - ustc
baseurl=http://mirrors.ustc.edu.cn/epel/$releasever/Modular/$basearch
enabled=0
gpgcheck=0
module_hotfixes=true
EOF
    else
        [ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/zstack-aliyun-yum.repo ] && cat << 'EOF' > /etc/yum.repos.d/zstack-aliyun-yum.repo
#aliyun base
[alibase]
name=CentOS-$releasever - Base - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/$releasever/os/$basearch/
gpgcheck=0
enabled=0
#released updates
[aliupdates]
name=CentOS-$releasever - Updates -mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/$releasever/updates/$basearch/
enabled=0
gpgcheck=0
[aliextras]
name=CentOS-$releasever - Extras - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/$releasever/extras/$basearch/
enabled=0
gpgcheck=0
[aliepel]
name=Extra Packages for Enterprise Linux $releasever - $basearce - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/epel/$releasever/$basearch
failovermethod=priority
enabled=0
gpgcheck=0
EOF
        [ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/zstack-163-yum.repo ] && cat << 'EOF' > /etc/yum.repos.d/zstack-163-yum.repo
#163 base
[163base]
name=CentOS-$releasever - Base - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/$releasever/os/$basearch/
gpgcheck=0
enabled=0
#released updates
[163updates]
name=CentOS-$releasever - Updates - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/$releasever/updates/$basearch/
enabled=0
gpgcheck=0
#additional packages that may be useful
[163extras]
name=CentOS-$releasever - Extras - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/$releasever/extras/$basearch/
enabled=0
gpgcheck=0
[ustcepel]
name=Extra Packages for Enterprise Linux $releasever - $basearch - ustc
baseurl=http://mirrors.ustc.edu.cn/epel/$releasever/$basearch
failovermethod=priority
enabled=0
gpgcheck=0
EOF
    fi
fi
'''

def signal_handler(signal, frame):
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def loop_until_timeout(timeout, interval=1):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            current_time = time.time()
            expired = current_time + timeout
            while current_time < expired:
                if f(*args, **kwargs):
                    return True
                time.sleep(interval)
                current_time = time.time()
            return False
        return inner
    return wrap

def find_process_by_cmdline(cmdlines):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            with open(os.path.join('/proc', pid, 'cmdline'), 'r') as fd:
                cmdline = fd.read()

            is_find = True
            for c in cmdlines:
                if c not in cmdline:
                    is_find = False
                    break

            if not is_find:
                continue

            return pid
        except IOError:
            continue

    return None

def ssh_run_full(ip, cmd, params=[], pipe=True):
    remote_path = '/tmp/%s.sh' % uuid.uuid4()
    script = '''/bin/bash << EOF
cat << EOF1 > %s
%s
EOF1
/bin/bash %s %s
ret=\$?
rm -f %s
exit \$ret
EOF''' % (remote_path, cmd, remote_path, ' '.join(params), remote_path)

    scmd = ShellCmd("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s \"%s\"" % (ip, script), pipe=pipe)
    scmd(False)
    return scmd

def ssh_run(ip, cmd, params=[]):
    scmd = ssh_run_full(ip, cmd, params)
    if scmd.return_code != 0:
        scmd.raise_error()
    return scmd.stdout

def ssh_run_no_pipe(ip, cmd, params=[]):
    scmd = ssh_run_full(ip, cmd, params, False)
    if scmd.return_code != 0:
        scmd.raise_error()
    return scmd.stdout

def kill_process(pid, sig=signal.SIGTERM):
    try:
        os.kill(int(pid), sig)
    except OSError:
        pass

class CtlError(Exception):
    pass

def warn(msg):
    sys.stdout.write(colored('WARNING: %s\n' % msg, 'yellow'))

def error(msg):
    sys.stderr.write(colored('ERROR: %s\n' % msg, 'red'))
    sys.exit(1)

def error_not_exit(msg):
    sys.stderr.write(colored('ERROR: %s\n' % msg, 'red'))

def info_verbose(*msg):
    if len(msg) == 1:
        out = '%s\n' % ''.join(msg)
    else:
        out = ''.join(msg)
    now = datetime.now()
    out = "%s " % str(now) + out
    sys.stdout.write(out)

def info(*msg):
    if len(msg) == 1:
        out = '%s\n' % ''.join(msg)
    else:
        out = ''.join(msg)
    sys.stdout.write(out)

def info_and_debug(*msg):
    if len(msg) == 1:
        out = '%s\n' % ''.join(msg)
    else:
        out = ''.join(msg)
    sys.stdout.write(out)
    logger.debug(out)

def get_detail_version():
    detailed_version_file = os.path.join(ctl.zstack_home, "VERSION")
    if os.path.exists(detailed_version_file):
        with open(detailed_version_file, 'r') as fd:
            detailed_version = fd.read().strip()
            return detailed_version
    else:
        return None

def check_ip_port(host, port):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, int(port)))
    return result == 0

def compare_version(version1, version2):
    def normalize(v):
        return [int(x) for x in re.sub(r'(\.0+)*$','', v).split(".")]
    return cmp(normalize(version2), normalize(version1))

def get_zstack_version(db_hostname, db_port, db_user, db_password):
    query = MySqlCommandLineQuery()
    query.host = db_hostname
    query.port = db_port
    query.user = db_user
    query.password = db_password
    query.table = 'zstack'
    query.sql = "select version from schema_version order by version desc"
    ret = query.query()

    versions = [r['version'] for r in ret]
    versions.sort(cmp=compare_version)

    version = versions[0]
    return version

def get_zstack_installed_on(db_hostname, db_port, db_user, db_password):
    query = MySqlCommandLineQuery()
    query.host = db_hostname
    query.port = db_port
    query.user = db_user
    query.password = db_password
    query.table = 'zstack'
    query.sql = "select installed_on from schema_version order by installed_on desc"
    ret = query.query()
    installed_ons = [r['installed_on'] for r in ret]

    installed_on = installed_ons[0]
    return installed_on

def get_default_gateway_ip():
    '''This function will return default route gateway ip address'''
    with open("/proc/net/route") as gateway:
        try:
            for item in gateway:
                fields = item.strip().split()
                if fields[1] != '00000000' or not int(fields[3], 16) & 2:
                    continue
                if fields[7] == '00000000':
                    return socket.inet_ntoa(struct.pack("=L", int(fields[2], 16)))
        except ValueError:
            return None

def get_default_ip():
    cmd = ShellCmd("""dev=`ip route|grep default|head -n 1|awk -F "dev" '{print $2}' | awk -F " " '{print $1}'`; ip addr show $dev |grep "inet "|awk '{print $2}'|head -n 1 |awk -F '/' '{print $1}'""")
    cmd(False)
    return cmd.stdout.strip()

def get_all_ips():
    script = ShellCmd('''ip addr | awk -F '[/| ]+'  '/inet\s+/{sub(/^\s*/,"");print $2}' ''')
    script(True)
    return script.stdout.splitlines()

def get_ui_address():
    ui_addr = ctl.read_ui_property("ui_address")
    return ui_addr if ui_addr else get_default_ip()

def get_yum_repo_from_property():
    yum_repo = ctl.read_property('Ansible.var.zstack_repo')
    if not yum_repo:
        return yum_repo

    # avoid http server didn't start when install package
    if 'zstack-mn' in yum_repo:
        yum_repo = yum_repo.replace("zstack-mn","zstack-local")
    if 'qemu-kvm-ev-mn' in yum_repo:
        yum_repo = yum_repo.replace("qemu-kvm-ev-mn","qemu-kvm-ev")
    if 'mlnx-ofed-mn' in yum_repo:
        yum_repo = yum_repo.replace("mlnx-ofed-mn","mlnx-ofed")
    return yum_repo


def get_host_list(table_name):
    db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
    query = MySqlCommandLineQuery()
    query.host = db_hostname
    query.port = db_port
    query.user = db_user
    query.password = db_password
    query.table = 'zstack'
    query.sql = "select * from %s" % table_name
    host_vo = query.query()
    return host_vo

def get_mn_list():
    return get_host_list("ManagementNodeVO")

def get_vrouter_list():
    ip_list = []
    db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
    query = MySqlCommandLineQuery()
    query.host = db_hostname
    query.port = db_port
    query.user = db_user
    query.password = db_password
    query.table = 'zstack'
    query.sql = "select ip from VmNicVO where deviceId = 0 and vmInstanceUuid in (select uuid from VirtualRouterVmVO)"
    vrouter_ip_list = query.query()
    for ip in vrouter_ip_list:
        ip_list.append(ip['ip'])
    return ip_list

def get_ha_mn_list(conf_file):
    with open(conf_file, 'r') as fd:
        ha_conf_content = yaml.load(fd.read())
        mn_list = ha_conf_content['host_list'].split(',')
    return mn_list

def stop_mevoco(host_post_info):
    command = "zstack-ctl stop_node && zstack-ctl stop_ui"
    logger.debug("[ HOST: %s ] INFO: starting run shell command: '%s' " % (host_post_info.host, command))
    (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                               (host_post_info.private_key, host_post_info.host, command))
    if status != 0:
        logger.error("[ HOST: %s ] INFO: shell command: '%s' failed" % (host_post_info.host, command))
        error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
    else:
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))

def start_mevoco(host_post_info):
    command = "zstack-ctl start_node && zstack-ctl start_ui"
    logger.debug("[ HOST: %s ] INFO: starting run shell command: '%s' " % (host_post_info.host, command))
    (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                               (host_post_info.private_key, host_post_info.host, command))
    if status != 0:
        logger.error("[ HOST: %s ] FAIL: shell command: '%s' failed" % (host_post_info.host, command))
        error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
    else:
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))

class ExceptionWrapper(object):
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if globals().get('verbose', False) and exc_type and exc_val and exc_tb:
            error_not_exit(''.join(traceback.format_exception(exc_type, exc_val, exc_tb)))

        if exc_type == CtlError:
            return

        if exc_val:
            error('%s\n%s' % (str(exc_val), self.msg))

def on_error(msg):
    return ExceptionWrapper(msg)

def error_if_tool_is_missing(tool):
    if shell_return('which %s' % tool) != 0:
        raise CtlError('cannot find tool "%s", please install it and re-run' % tool)

def check_gunzip_file(path):
    r, _, e = shell_return_stdout_stderr("gunzip -t " + path)
    if r != 0:
        raise CtlError(e)

def expand_path(path):
    if path.startswith('~'):
        return os.path.expanduser(path)
    else:
        return os.path.abspath(path)

def validate_ip(s):
    a = s.split('.')
    if len(a) != 4:
        return False
    for x in a:
        if not x.isdigit():
            return False
        i = int(x)
        if i < 0 or i > 255:
            return False
    return True


def check_host_info_format(host_info, with_public_key=False):
    '''check install ha and install multi mn node info format'''
    if '@' not in host_info:
        if with_public_key is False:
            error("Host connect info: '%s' is wrong, should follow format: 'root:password@host_ip', please check your input!" % host_info)
        if with_public_key is True:
            error("Host connect info: '%s' is wrong, should follow format: 'root@host_ip', please check your input!" % host_info)
    else:
        # get user and password
        if ':' not in host_info.split('@')[0]:
            if with_public_key is False:
                error("Host connect information should follow format: 'root:password@host_ip', please check your input!")
            else:
                user = host_info.split('@')[0]
                password = ""

        else:
            if with_public_key is False:
                user = host_info.split('@')[0].split(':')[0]
                password = host_info.split('@')[0].split(':')[1]
                if user != "root":
                    error("Only root user can be supported, please change user to root")
        # get ip and port
        if ':' not in host_info.split('@')[1]:
            ip = host_info.split('@')[1]
            port = '22'
        else:
            ip = host_info.split('@')[1].split(':')[0]
            port = host_info.split('@')[1].split(':')[1]

        if validate_ip(ip) is False:
            error("Ip : %s is invalid" % ip)
        return (user, password, ip, port)

def check_host_password(password, ip):
    command ='timeout 10 sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o PubkeyAuthentication=no -o ' \
             'StrictHostKeyChecking=no root@%s echo ""' % (shell_quote(password), ip)
    (status, output) = commands.getstatusoutput(command)
    if status != 0:
        error("Connect to host: '%s' with password '%s' failed! Please check password firstly and make sure you have "
              "disabled UseDNS in '/etc/ssh/sshd_config' on %s" % (ip, password, ip))

def check_host_connection_with_key(ip, user="root", private_key="", remote_host_port='22'):
    command ='timeout 5 sshpass ssh -o StrictHostKeyChecking=no -p %s %s@%s echo ""' % (remote_host_port, user, ip)
    (status, stdout, stderr) = shell_return_stdout_stderr(command)
    if status != 0:
        error("Connect to host: '%s' with private key: '%s' failed, please transfer your public key "
              "to remote host firstly then make sure the host address is valid" % (ip, private_key))

def get_ip_by_interface(device_name):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,
        struct.pack('256s', device_name[:15])
    )[20:24])


def start_remote_mn( host_post_info):
    command = "zstack-ctl start_node && zstack-ctl start_ui"
    (status, output) = commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                                (UpgradeHACmd.private_key_name, host_post_info.host, command))
    if status != 0:
        error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
    logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))

def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"

class SpinnerInfo(object):
    spinner_status = {}
    def __init__(self):
        self.output = ""
        self.name = ""

class ZstackSpinner(object):

    def __init__(self, spinner_info):
        self.output = spinner_info.output
        self.name = spinner_info.name
        self.spinner = itertools.cycle("|/~\\")

        self.thread = threading.Thread(target=self.run, args=())
        self.thread.daemon = True
        self.thread.start()

    def run(self):
        time.sleep(.2)
        while SpinnerInfo.spinner_status[self.name]:
                sys.stdout.write("\r %s: ... %s " % (self.output, next(self.spinner)))
                sys.stdout.flush()
                time.sleep(.1)
        print "\r %s: ... %s" % (self.output, colored("PASS","green"))


class Ansible(object):
    def __init__(self, yaml, host='localhost', debug=False, ssh_key='none'):
        self.yaml = yaml
        self.host = host
        self.debug = debug
        self.ssh_key = ssh_key

    def __call__(self, *args, **kwargs):
        error_if_tool_is_missing('ansible-playbook')

        cmd = '''
#!/bin/bash
yaml_file=`mktemp`
cat <<EOF >> $$yaml_file
$yaml
EOF

ansible_cmd="ansible-playbook $$yaml_file -i '$host,'"

if [ $debug -eq 1 ]; then
   ansible_cmd="$$ansible_cmd -vvvv"
fi

if [ "$ssh_key" != "none" ]; then
   ansible_cmd="$$ansible_cmd --private-key=$ssh_key"
   ssh -oPasswordAuthentication=no -oStrictHostKeyChecking=no -i $ssh_key $host 'echo hi > /dev/null'
else
   ssh -oPasswordAuthentication=no -oStrictHostKeyChecking=no $host 'echo hi > /dev/null'
fi

if [ $$? -ne 0 ]; then
   ansible_cmd="$$ansible_cmd --ask-pass"
fi

eval $$ansible_cmd
ret=$$?
rm -f $$yaml_file
exit $$ret
'''
        t = string.Template(cmd)
        cmd = t.substitute({
            'yaml': self.yaml,
            'host': self.host,
            'debug': int(self.debug),
            'ssh_key': self.ssh_key
        })

        with on_error('Ansible failure'):
            try:
                shell_no_pipe(cmd)
            except CtlError:
                raise Exception('see prior Ansible log for detailed information')

def ansible(yaml, host='localhost', debug=False, ssh_key=None):
    Ansible(yaml, host, debug, ssh_key or 'none')()

def reset_dict_value(dict_name, value):
    return dict.fromkeys(dict_name, value)

def check_zstack_user():
    try:
        pwd.getpwnam('zstack')
    except KeyError:
        raise CtlError('cannot find user account "zstack", your installation seems incomplete')

    try:
        grp.getgrnam('zstack')
    except KeyError:
        raise CtlError('cannot find user account "zstack", your installation seems incomplete')

def check_special_root(s):
    if re.match(r"[^a-z0-9A-Z\\\_]", s):
        s = "\\" + s
    elif re.match(r"[\\]", s):
        s = r"\\"
    return s

def check_special_new(s):
    if re.match(r"[^a-z0-9A-Z\\\%\_]", s):
        s = "\\" + s
    elif re.match(r"[\\]", s):
        s = r"\\\\"
    return s

def check_java_version():
    try:
        ver = shell('java -version 2>&1 | grep -w version')
    except CtlError:
        raise CtlError('Java 8 have not been installed yet. Please install Java 8 first.')
    if '1.8' not in ver:
        raise CtlError('Management node requires Java 8, your current version is %s\n'
                'please run "update-alternatives --config java" to set Java to Java 8' % ver)

class UseUserZstack(object):
    def __init__(self):
        self.root_uid = None
        self.root_gid = None
        check_zstack_user()

    def __enter__(self):
        self.root_uid = os.getuid()
        self.root_gid = os.getgid()
        self.root_home = os.environ.get('HOME') if os.environ.get('HOME') else "/root"

        os.setegid(grp.getgrnam('zstack').gr_gid)
        os.seteuid(pwd.getpwnam('zstack').pw_uid)
        os.environ['HOME'] = os.path.expanduser('~zstack')

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.seteuid(self.root_uid)
        os.setegid(self.root_gid)
        os.environ['HOME'] = self.root_home

def use_user_zstack():
    return UseUserZstack()

class ConfigObjEx(ConfigObj):
    def __init__(self, filename):
        super(ConfigObjEx, self).__init__(filename, write_empty_values=True)

    def write(self):
        with open(self.filename, 'wb') as f:
            super(ConfigObjEx, self).write(f)
            f.flush()
            os.fsync(f.fileno())

class PropertyFile(object):
    @lock.file_lock('/run/zstack.properties.lock')
    def __init__(self, path, use_zstack=True):
        self.path = path
        self.use_zstack = use_zstack
        if not os.path.isfile(self.path):
            raise CtlError('cannot find property file at %s' % self.path)
        if not os.access(self.path, os.W_OK|os.R_OK):
            raise CtlError('%s: permission denied' % self.path)

        with on_error("errors on reading %s" % self.path):
            self.config = ConfigObjEx(self.path)

    def read_all_properties(self):
        with on_error("errors on reading %s" % self.path):
            return self.config.items()

    @lock.file_lock('/run/zstack.properties.lock')
    def delete_properties(self, keys):
        for k in keys:
            if k in self.config:
                del self.config[k]

        with use_user_zstack():
            self.config.write()

    def read_property(self, key):
        with on_error("errors on reading %s" % self.path):
            return self.config.get(key, None)

    @lock.file_lock('/run/zstack.properties.lock')
    def write_property(self, key, value):
        with on_error("errors on writing (%s=%s) to %s" % (key, value, self.path)):
            if self.use_zstack:
                with use_user_zstack():
                    self.config[key] = value
                    self.config.write()
            else:
                self.config[key] = value
                self.config.write()

    @lock.file_lock('/run/zstack.properties.lock')
    def write_properties(self, lst):
        with on_error("errors on writing list of key-value%s to %s" % (lst, self.path)):
            if self.use_zstack:
                with use_user_zstack():
                    for key, value in lst:
                        self.config[key] = value
                        self.config.write()
            else:
                for key, value in lst:
                    self.config[key] = value
                    self.config.write()

class CtlParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error:%s\n' % message)
        self.print_help()
        sys.exit(1)


def check_ha():
    _, output, _ = shell_return_stdout_stderr("systemctl is-enabled zstack-ha")
    if output and output.strip() == "enabled":
        return True
    return False


class Ctl(object):
    IS_AARCH64 = platform.machine() == 'aarch64'
    DEFAULT_ZSTACK_HOME = '/usr/local/zstack/apache-tomcat/webapps/zstack/'
    USER_ZSTACK_HOME_DIR = os.path.expanduser('~zstack')
    ZSTACK_TOOLS_DIR = os.path.join(USER_ZSTACK_HOME_DIR, 'apache-tomcat/webapps/zstack/WEB-INF/classes/tools/')
    LAST_ALIVE_MYSQL_IP = "MYSQL_LATEST_IP"
    LAST_ALIVE_MYSQL_PORT = "MYSQL_LATEST_PORT"
    LOGGER_DIR = "/var/log/zstack/"
    LOGGER_FILE = "zstack-ctl.log"
    # always install zstack-ui inside zstack_install_root
    ZSTACK_UI_HOME = os.path.join(USER_ZSTACK_HOME_DIR, 'zstack-ui/')
    ZSTACK_UI_DB = os.path.join(ZSTACK_UI_HOME, 'scripts/deployuidb.sh')
    ZSTACK_UI_DB_MIGRATE = os.path.join(ZSTACK_UI_HOME, 'db')
    ZSTACK_UI_DB_MIGRATE_SH = os.path.join(ZSTACK_UI_HOME, 'scripts/migrateforupdate.sh')
    ZSTACK_UI_KEYSTORE = ZSTACK_UI_HOME + 'ui.keystore.p12'
    ZSTACK_UI_KEYSTORE_CP = ZSTACK_UI_KEYSTORE + '.cp'
    # for console proxy https
    ZSTACK_UI_KEYSTORE_PEM = ZSTACK_UI_HOME + 'ui.keystore.pem'
    ZSTACK_UI_KEYSTORE_PEM_OLD = ZSTACK_UI_HOME + 'ui.keystore.pem.old'
    # to set CATALINA_OPTS of zstack-ui.war
    ZSTACK_UI_CATALINA_OPTS = '-Xmx4096m'
    # always install zstack-mini-server inside zstack_install_root
    MINI_DIR = os.path.join(USER_ZSTACK_HOME_DIR, 'zstack-mini')
    NEED_ENCRYPT_PROPERTIES = ['DB.password']

    NEED_ENCRYPT_PROPERTIES_UI = ['db_password','redis_password']
    # get basharch and zstack-release
    BASEARCH = platform.machine()
    ZS_RELEASE = os.popen("awk '{print $3}' /etc/zstack-release").read().strip()

    def __init__(self):
        versionFile = os.path.join(self.ZSTACK_UI_HOME,'VERSION')
        if os.path.exists(versionFile):
            with open(versionFile, 'r') as fd2:
                self.uiVersion = fd2.readline()
                self.uiVersion = self.uiVersion.strip(' \t\n\r')
                self.uiPrimaryVersion = self.uiVersion[0]
        self.commands = {}
        self.command_list = []
        self.main_parser = CtlParser(prog='zstack-ctl', description="ZStack management tool", formatter_class=argparse.RawTextHelpFormatter)
        self.main_parser.add_argument('-v', help="verbose, print execution details", dest="verbose", action="store_true", default=False)
        self.zstack_home = None
        self.properties_file_path = None
        self.ui_properties_file_path = None
        self.tomcat_xml_file_path = None
        self.verbose = False
        self.extra_arguments = None
        self.http_call_cmd = 'curl -X POST -H "Content-Type:application/json" -H "commandpath:%s" -d \'%s\' --retry 5 http://%s:%s/zstack/asyncrest/sendcommand'

    def register_command(self, cmd):
        assert cmd.name, "command name cannot be None"
        assert cmd.description, "command description cannot be None"
        self.commands[cmd.name] = cmd
        self.command_list.append(cmd)

    def locate_zstack_home(self):
        env_path = os.path.expanduser(SetEnvironmentVariableCmd.PATH)
        if os.path.isfile(env_path):
            env = PropertyFile(env_path)
            self.zstack_home = env.read_property('ZSTACK_HOME')

        if not self.zstack_home:
            self.zstack_home = os.environ.get('ZSTACK_HOME', None)

        if not self.zstack_home:
            warn('ZSTACK_HOME is not set, default to %s' % self.DEFAULT_ZSTACK_HOME)
            self.zstack_home = self.DEFAULT_ZSTACK_HOME

        if not os.path.isdir(self.zstack_home):
            raise CtlError('cannot find ZSTACK_HOME at %s, please set it in .bashrc or use zstack-ctl setenv ZSTACK_HOME=path' % self.zstack_home)

        os.environ['ZSTACK_HOME'] = self.zstack_home
        self.properties_file_path = os.path.join(self.zstack_home, 'WEB-INF/classes/zstack.properties')
        self.tomcat_xml_file_path = os.path.join(self.USER_ZSTACK_HOME_DIR, 'apache-tomcat/conf/server.xml')
        self.ui_properties_file_path = os.path.join(Ctl.ZSTACK_UI_HOME, 'zstack.ui.properties')
        self.ssh_private_key = os.path.join(self.zstack_home, 'WEB-INF/classes/ansible/rsaKeys/id_rsa')
        self.ssh_public_key = os.path.join(self.zstack_home, 'WEB-INF/classes/ansible/rsaKeys/id_rsa.pub')
        if not os.path.isfile(self.properties_file_path):
            warn('cannot find %s, your ZStack installation may have crashed' % self.properties_file_path)
        if os.path.getsize(self.properties_file_path) == 0:
            warn('%s: file empty' % self.properties_file_path)

    def get_env(self, name):
        env = PropertyFile(SetEnvironmentVariableCmd.PATH)
        return env.read_property(name)

    def delete_env(self, name):
        env = PropertyFile(SetEnvironmentVariableCmd.PATH)
        env.delete_properties([name])

    def put_envs(self, vs):
        if not os.path.exists(SetEnvironmentVariableCmd.PATH):
            shell('su - zstack -c "mkdir -p %s"' % os.path.dirname(SetEnvironmentVariableCmd.PATH))
            shell('su - zstack -c "touch %s"' % SetEnvironmentVariableCmd.PATH)
        env = PropertyFile(SetEnvironmentVariableCmd.PATH)
        env.write_properties(vs)

    def run(self):
        create_log(Ctl.LOGGER_DIR, Ctl.LOGGER_FILE)
        if os.getuid() != 0:
            raise CtlError('zstack-ctl needs root privilege, please run with sudo')

        if os.path.exists(Ctl.ZSTACK_UI_HOME) and not os.path.exists(self.ui_properties_file_path):
            os.mknod(self.ui_properties_file_path)
            os.chmod(self.ui_properties_file_path, 438)

        metavar_list = []
        for n,cmd in enumerate(self.command_list):
            if cmd.hide is False:
                metavar_list.append(cmd.name)
            else:
                self.command_list[n].description = None

        metavar_string = '{' + ','.join(metavar_list) + '}'
        subparsers = self.main_parser.add_subparsers(help="All sub-commands", dest="sub_command_name", metavar=metavar_string)
        for cmd in self.command_list:
            if cmd.description is not None:
                cmd.install_argparse_arguments(subparsers.add_parser(cmd.name, help=cmd.description + '\n\n'))
            else:
                cmd.install_argparse_arguments(subparsers.add_parser(cmd.name))
        args, self.extra_arguments = self.main_parser.parse_known_args(sys.argv[1:])

        # check the ip address
        cmd_name = args.sub_command_name
        if cmd_name == "status" or cmd_name == "start" or cmd_name == "start_node" or cmd_name == "restart_node":
            ip_info = shell("ip a | grep 'inet ' | grep -v 127.0.0.1", False).strip()
            if ip_info is None or ip_info == '':
                if cmd_name == "status":
                    error_not_exit("Please configure the IP address of this management server correctly.")
                else:
                    error("Please configure the IP address of this management server correctly.")

        self.verbose = args.verbose
        globals()['verbose'] = self.verbose

        cmd = self.commands[args.sub_command_name]

        if cmd.need_zstack_home():
            self.locate_zstack_home()

        if cmd.need_zstack_user():
            check_zstack_user()

        cmd(args)

    def internal_run(self, cmd_name, args=''):
        cmd = self.commands[cmd_name]
        assert cmd, 'cannot find command %s' % cmd_name

        params = [cmd_name]
        params.extend(args.split())
        args_obj, _ = self.main_parser.parse_known_args(params)

        if cmd.need_zstack_home():
            self.locate_zstack_home()

        if cmd.need_zstack_user():
            check_zstack_user()

        cmd(args_obj)

    def read_property_list(self, key):
        prop = PropertyFile(self.properties_file_path)
        ret = []
        for name, value in prop.read_all_properties():
            if name.startswith(key):
                ret.append((name, value))
        return ret

    def read_all_properties(self):
        prop = PropertyFile(self.properties_file_path)
        return prop.read_all_properties()

    def read_property(self, key):
        prop = PropertyFile(self.properties_file_path)
        val = prop.read_property(key)
        # our code assume all values are strings
        if isinstance(val, list):
            return ','.join(val)
        else:
            return val

    def write_properties(self, properties):
        prop = PropertyFile(self.properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.write_properties(properties)

    def delete_properties(self, properties):
        prop = PropertyFile(self.properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.delete_properties(properties)

    def write_property(self, key, value):
        prop = PropertyFile(self.properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.write_property(key, value)

    # for zstack ui properties
    def read_all_ui_properties(self):
        prop = PropertyFile(self.ui_properties_file_path)
        return prop.read_all_properties()

    def read_ui_property(self, key):
        prop = PropertyFile(self.ui_properties_file_path)
        val = prop.read_property(key)
        # our code assume all values are strings
        if isinstance(val, list):
            return ','.join(val)
        else:
            return val

    def write_ui_properties(self, properties):
        prop = PropertyFile(self.ui_properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.write_properties(properties)

    def write_ui_property(self, key, value):
        prop = PropertyFile(self.ui_properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.write_property(key, value)

    def clear_ui_properties(self):
        prop = PropertyFile(self.ui_properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            props = prop.read_all_properties()
            keys = []
            for k, v in props:
                keys.append(k)
            prop.delete_properties(keys)

    def get_db_url(self):
        db_url = self.read_property("DB.url")
        regex = "^jdbc:mysql://.*"
        if not db_url:
            db_url = self.read_property('DbFacadeDataSource.jdbcUrl')
        if not re.match(regex, db_url):
            raise CtlError("invalid value DB url %s. please check again " % db_url)
        if not db_url:
            raise CtlError("cannot find DB url in %s. please set DB.url" % self.properties_file_path)
        return db_url

    def get_ui_db_url(self):
        db_url = self.read_ui_property("db_url")
        if not db_url:
            raise CtlError("cannot find zstack_ui db url in %s. please set db_url" % self.ui_properties_file_path)
        return db_url

    def get_live_mysql_portal(self, ui=False):
        if ui:
            hostname_ports, user, password = self.get_ui_database_portal()
        else:
            hostname_ports, user, password = self.get_database_portal()

        last_ip = ctl.get_env(self.LAST_ALIVE_MYSQL_IP)
        last_port = ctl.get_env(self.LAST_ALIVE_MYSQL_PORT)
        if last_ip and last_port and (last_ip, last_port) in hostname_ports:
            first = (last_ip, last_port)
            lst = [first]
            for it in hostname_ports:
                if it != first:
                    lst.append(it)

            hostname_ports = lst

        errors = []
        for hostname, port in hostname_ports:
            if password:
                sql = 'mysql --host=%s --port=%s --user=%s --password=%s -e "select 1"' % (hostname, port, user, shell_quote(password))
            else:
                sql = 'mysql --host=%s --port=%s --user=%s -e "select 1"' % (hostname, port, user)

            cmd = ShellCmd(sql)
            cmd(False)
            if cmd.return_code != 0:
                errors.append(
                    'connect MySQL server[hostname:%s, port:%s, user:%s]: %s %s' % (
                        hostname, port, user, cmd.stderr, cmd.stdout
                    ))
                continue

            # record the IP and port, so next time we will try them first
            if hostname != last_ip or port != last_port:
                ctl.put_envs([
                    (self.LAST_ALIVE_MYSQL_IP, hostname),
                    (self.LAST_ALIVE_MYSQL_PORT, port)
                ])
            return hostname, port, user, password

        raise CtlError('\n'.join(errors))

    def get_database_portal(self):
        db_user = self.read_property("DB.user")
        if not db_user:
            db_user = self.read_property('DbFacadeDataSource.user')
        if not db_user:
            raise CtlError("cannot find DB user in %s. please set DB.user" % self.properties_file_path)

        db_password = self.read_property("DB.password")
        if db_password is None:
            db_password = self.read_property('DbFacadeDataSource.password')

        if db_password is None:
            raise CtlError("cannot find DB password in %s. please set DB.password" % self.properties_file_path)

        cipher = AESCipher()
        if cipher.is_encrypted(db_password):
            db_password = cipher.decrypt(db_password)

        db_url = self.get_db_url()
        host_name_ports = []

        def parse_hostname_ports(prefix):
            ips = db_url.lstrip(prefix).lstrip('/').split('/')[0]
            ips = ips.split(',')
            for ip in ips:
                if ":" in ip:
                    hostname, port = ip.split(':')
                    host_name_ports.append((hostname, port))
                else:
                    host_name_ports.append((ip, '3306'))

        if db_url.startswith('jdbc:mysql:loadbalance:'):
            parse_hostname_ports('jdbc:mysql:loadbalance:')
        elif db_url.startswith('jdbc:mysql:'):
            parse_hostname_ports('jdbc:mysql:')

        return host_name_ports, db_user, db_password

    def get_ui_database_portal(self):
        db_user = self.read_ui_property("db_username")
        if not db_user:
            raise CtlError("cannot find zstack_ui db username in %s. please set db_username" % self.ui_properties_file_path)

        db_password = self.read_ui_property("db_password")
        if db_password is None:
            raise CtlError("cannot find zstack_ui db password in %s. please set db_password" % self.ui_properties_file_path)

        cipher = AESCipher()
        if cipher.is_encrypted(db_password):
            db_password = cipher.decrypt(db_password)

        db_url = self.get_ui_db_url()
        host_name_ports = []

        def parse_hostname_ports(prefix):
            ips = db_url.lstrip(prefix).lstrip('/').split('/')[0]
            ips = ips.split(',')
            for ip in ips:
                if ":" in ip:
                    hostname, port = ip.split(':')
                    host_name_ports.append((hostname, port))
                else:
                    host_name_ports.append((ip, '3306'))

        if db_url.startswith('jdbc:mysql:loadbalance:'):
            parse_hostname_ports('jdbc:mysql:loadbalance:')
        elif db_url.startswith('jdbc:mysql:'):
            parse_hostname_ports('jdbc:mysql:')

        return host_name_ports, db_user, db_password

    def check_if_management_node_has_stopped(self, force=False):
        db_hostname, db_port, db_user, db_password = self.get_live_mysql_portal()

        def get_nodes():
            query = MySqlCommandLineQuery()
            query.user = db_user
            query.password = db_password
            query.host = db_hostname
            query.port = db_port
            query.table = 'zstack'
            query.sql = 'select hostname,heartBeat from ManagementNodeVO'

            return query.query()

        def check():
            nodes = get_nodes()
            if nodes:
                node_ips = [n['hostname'] for n in nodes]
                raise CtlError('there are some management nodes%s are still running. Please stop all of them before performing the database upgrade.'
                               'If you are sure they have stopped, use option --force and run this command again.\n'
                               'If you are upgrade by all in on installer, use option -F and run all in one installer again.\n'
                               'WARNING: the database may crash if you run this command with --force but without stopping management nodes' % node_ips)

        def bypass_check():
            nodes = get_nodes()
            if nodes:
                node_ips = [n['hostname'] for n in nodes]
                info("it seems some nodes%s are still running. As you have specified option --force, let's wait for 10s to make sure those are stale records. Please be patient." % node_ips)
                time.sleep(10)
                new_nodes = get_nodes()

                for n in new_nodes:
                    for o in nodes:
                        if o['hostname'] == n['hostname'] and o['heartBeat'] != n['heartBeat']:
                            raise CtlError("node[%s] is still Running! Its heart-beat changed from %s to %s in last 10s. Please make sure you really stop it" %
                                           (n['hostname'], o['heartBeat'], n['heartBeat']))

        if force:
            bypass_check()
        else:
            check()


ctl = Ctl()


def file_hex_digest(algorithm, file_path):
    with open(file_path, 'rb') as data:
        try:
            return hashlib.new(algorithm, data.read()).hexdigest()
        except IOError as err:
            raise CtlError('can not open file %s because IOError: %s' % (file_path, str(err)))


def script(cmd, args=None, no_pipe=False):
    if args:
        t = string.Template(cmd)
        cmd = t.substitute(args)

    fd, script_path = tempfile.mkstemp(suffix='.sh')
    os.fdopen(fd, 'w').write(cmd)
    try:
        if ctl.verbose:
            info('execute script:\n%s\n' % cmd)
        if no_pipe:
            shell_no_pipe('bash %s' % script_path)
        else:
            shell('bash %s' % script_path)
    finally:
        os.remove(script_path)

@lock.lock("subprocess.popen")
def get_process(cmd, workdir, pipe):
    if pipe:
        return subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, cwd=workdir)
    else:
        return subprocess.Popen(cmd, shell=True, cwd=workdir)

class ShellCmd(object):
    def __init__(self, cmd, workdir=None, pipe=True):
        self.cmd = cmd
        self.process = get_process(cmd, workdir, pipe)
        self.return_code = None
        self.stdout = None
        self.stderr = None

    def raise_error(self):
        err = []
        err.append('failed to execute shell command: %s' % self.cmd)
        err.append('return code: %s' % self.process.returncode)
        err.append('stdout: %s' % self.stdout)
        err.append('stderr: %s' % self.stderr)
        raise CtlError('\n'.join(err))

    def __call__(self, is_exception=True):
        if ctl.verbose:
            info('executing shell command[%s]:' % self.cmd)

        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            self.raise_error()

        self.return_code = self.process.returncode

        if ctl.verbose:
            info(simplejson.dumps({
                "shell" : self.cmd,
                "return_code" : self.return_code,
                "stdout": self.stdout,
                "stderr": self.stderr
            }, ensure_ascii=True, sort_keys=True, indent=4))

        return self.stdout

def shell(cmd, is_exception=True):
    return ShellCmd(cmd)(is_exception)

def shell_no_pipe(cmd, is_exception=True):
    return ShellCmd(cmd, pipe=False)(is_exception)

def shell_return(cmd):
    scmd = ShellCmd(cmd)
    scmd(False)
    return scmd.return_code

def shell_return_stdout_stderr(cmd):
    scmd = ShellCmd(cmd)
    scmd(False)
    return (scmd.return_code, scmd.stdout, scmd.stderr)


class UpdateSNSGlobalPropertyCmd(object):
    def __init__(self):
        self.ticketTopicHttpURL = None
        self.systemTopicHttpEndpointURL = None

    def _asdict(self):
        return self.__dict__


class UpdatePropertyCmd(object):
    def __init__(self):
        self.propertiesDigestValue = None
        self.mnIp = None

    def _asdict(self):
        return self.__dict__


class Command(object):
    def __init__(self):
        self.name = None
        self.description = None
        self.hide = False
        self.cleanup_routines = []
        self.quiet = False
        self.sensitive_args = []

    def install_argparse_arguments(self, parser):
        pass

    def install_cleanup_routine(self, func):
        self.cleanup_routines.append(func)

    def need_zstack_home(self):
        return True

    def need_zstack_user(self):
        return True

    def mask_sensitive_args(self, args):
        arguments = [args[0]]
        next_mask = False
        for arg in args[1:]:
            if next_mask:
                arg = "*****"
                next_mask = False
            elif arg in self.sensitive_args:
                next_mask = True
            elif '=' in arg:
                key = arg.split('=', 1)[0]
                if key in self.sensitive_args:
                    arg = key + '=*****'

            arguments.append(arg)
        return arguments

    def __call__(self, *args, **kwargs):
        try:
            self.run(*args)
            if not self.quiet:
                if not self.sensitive_args:
                    logger.info('Start running command [ zstack-ctl %s ]' % ' '.join(sys.argv[1:]))
                else:
                    logger.info('Start running command [ zstack-ctl %s ]' % ' '.join(self.mask_sensitive_args(sys.argv[1:])))
        finally:
            for c in self.cleanup_routines:
                c()

    def run(self, args):
        raise CtlError('the command is not implemented')

def create_check_ui_status_command(timeout=10, ui_ip='127.0.0.1', ui_port='5000', if_https=False):
    protocol = 'https' if if_https else 'http'
    if shell_return('which wget') == 0:
        return ShellCmd(
            '''wget --no-proxy -O- --tries=%s --no-check-certificate --timeout=1 %s://%s:%s/health''' % (timeout, protocol, ui_ip, ui_port))
    elif shell_return('which curl') == 0:
            return ShellCmd(
                '''curl -k --noproxy --connect-timeout=1 --retry %s --retry-delay 0 --retry-max-time %s --max-time %s %s://%s:%s/health''' % (
                    timeout, timeout, timeout, protocol, ui_ip, ui_port))
    else:
        return None

def get_mn_port():
    mn_port = ctl.read_property('RESTFacade.port')
    if not mn_port:
        return 8080
    return mn_port

def get_mgmt_node_state_from_result(cmd):
    if cmd.return_code != 0:
        return None

    try:
        result = str(json.loads(cmd.stdout)["result"])
        if string.find(result, "success\":true") != -1:
            return True
        if string.find(result, "success\":false") != -1:
            return False
        return None
    except:
        return None

def create_check_mgmt_node_command(timeout=10, mn_node='127.0.0.1'):
    USE_CURL = 0
    USE_WGET = 1
    NO_TOOL = 2

    def use_tool():
        cmd = ShellCmd('which wget')
        cmd(False)
        if cmd.return_code == 0:
            return USE_WGET
        else:
            cmd = ShellCmd('which curl')
            cmd(False)
            if cmd.return_code == 0:
                return USE_CURL
            else:
                return NO_TOOL

    # make sure localhost as 127.0.0.1
    def check_hosts():
        cmd = ShellCmd("grep '^\s*127.0.0.1\s' /etc/hosts | grep -q '\slocalhost\s'")
        cmd(False)
        if cmd.return_code != 0:
            ShellCmd("sed -i '1i127.0.0.1   localhost ' /etc/hosts")

    check_hosts()
    what_tool = use_tool()
    mn_port = get_mn_port()
    # tag::get_zstack_status[]
    if what_tool == USE_CURL:
        return ShellCmd('''curl --noproxy --connect-timeout=1 --retry %s --retry-delay 0 --retry-max-time %s --max-time %s -H "Content-Type: application/json" -d '{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://%s:%s/zstack/api''' % (timeout, timeout, timeout, mn_node, mn_port))
    elif what_tool == USE_WGET:
        return ShellCmd('''wget --no-proxy -O- --tries=%s --timeout=1  --header=Content-Type:application/json --post-data='{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://%s:%s/zstack/api''' % (timeout, mn_node, mn_port))
        # end::get_zstack_status[]
    else:
        return None

def find_process_by_cmdline(keyword):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            with open(os.path.join('/proc', pid, 'cmdline'), 'r') as fd:
                cmdline = fd.read()

            if keyword not in cmdline:
                continue

            return pid
        except IOError:
            continue

    return None

class Zsha2Utils(object):
    def __init__(self):
        r, _, e = shell_return_stdout_stderr("sudo -i /usr/local/bin/zsha2 status")
        if r != 0:
            error('cannot get zsha2 status, %s' % e)

        r, o, e = shell_return_stdout_stderr("/usr/local/bin/zsha2 show-config")
        if r != 0:
            error('cannot get zsha2 config, maybe need upgrade zsha2 first: %s' % e)

        self.config = simplejson.loads(o)
        self.master = shell_return("ip addr show %s | grep -q '[^0-9]%s[^0-9]'"
                                   % (self.config['nic'], self.config['dbvip'])) == 0
        try:
            ssh_run(self.config['peerip'], "echo 1 > /dev/null")
        except:
            error('cannot ssh peer node with sshkey')

    def excute_on_peer(self, cmd):
        ssh_run_no_pipe(self.config['peerip'], cmd)


    def scp_to_peer(self, src_path, dst_path):
        shell("scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s %s:%s" % (
            src_path, self.config['peerip'], dst_path))



class MySqlCommandLineQuery(object):
    def __init__(self):
        self.user = None
        self.password = None
        self.host = 'localhost'
        self.port = 3306
        self.sql = None
        self.table = None

    def query(self):
        assert self.user, 'user cannot be None'
        assert self.sql, 'sql cannot be None'
        assert self.table, 'table cannot be None'

        sql = "%s\G" % self.sql
        if self.password:
            cmd = '''mysql -u %s -p%s --host %s --port %s -t %s -e "%s"''' % (self.user, shell_quote(self.password), self.host,
                                                                               self.port, self.table, sql)
        else:
            cmd = '''mysql -u %s --host %s --port %s -t %s -e "%s"''' % (self.user, self.host, self.port, self.table, sql)

        output = shell(cmd)
        output = output.strip(' \t\n\r')
        ret = []
        if not output:
            return ret

        current = None
        for l in output.split('\n'):
            if current is None and not l.startswith('*********'):
                raise CtlError('cannot parse mysql output generated by the sql "%s", output:\n%s' % (self.sql, output))

            if l.startswith('*********'):
                if current:
                    ret.append(current)
                current = {}
            else:
                l = l.strip()
                if ":" in l:
                    key, value = l.split(':', 1)
                    current[key.strip()] = value[1:]

        if current:
            ret.append(current)

        return ret

class ShowStatusCmd(Command):
    def __init__(self):
        super(ShowStatusCmd, self).__init__()
        self.name = 'status'
        self.description = 'show ZStack status and information.'
        ctl.register_command(self)
    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to show the management node status on a remote machine')
        parser.add_argument('--quiet', '-q', help='Do not log this action.', action='store_true', default=False)

    def _stop_remote(self, args):
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl status"' % args.host)

    def run(self, args):
        self.quiet = args.quiet
        if args.host:
            self._stop_remote(args)
            return

        log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
        log_path = os.path.normpath(log_path)

        info_list = [
            "ZSTACK_HOME: %s" % ctl.zstack_home,
            "zstack.properties: %s" % ctl.properties_file_path,
            "log4j2.xml: %s" % os.path.join(os.path.dirname(ctl.properties_file_path), 'log4j2.xml'),
            "PID file: %s" % os.path.join(os.path.expanduser('~zstack'), "management-server.pid"),
            "log file: %s" % log_path
        ]

        def check_zstack_status():
            cmd = create_check_mgmt_node_command()

            def dump_mn():
                if pid:
                    kill_process(pid, signal.SIGQUIT)

                shell_return("echo 'management node became Unknown on %s, you can check status in catalina.out' >> %s"
                             % (datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), log_path))

            def write_status(status):
                info_and_debug('MN status: %s' % status)

            if not cmd:
                write_status('cannot detect status, no wget and curl installed')
                return

            cmd(False)
            pid = get_management_node_pid()
            if cmd.return_code != 0:
                if pid:
                    write_status('%s, the management node seems to become zombie as it stops responding APIs but the '
                                 'process(PID: %s) is still running. Please stop the node using zstack-ctl stop_node' %
                                 (colored('Unknown', 'yellow'), pid))
                    dump_mn()
                else:
                    write_status(colored('Stopped', 'red'))
                return False

            state = get_mgmt_node_state_from_result(cmd)
            if state is None:
                write_status('Unknown')
                dump_mn()
                return False

            if state:
                write_status(colored('Running', 'green') + ' [PID:%s]' % pid)
            else:
                write_status('Starting, should be ready in a few seconds')

        def show_version():
            try:
                db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
            except CtlError as e:
                info('version: %s' % colored('unknown, %s' % e.message.strip(), 'yellow'))
                return

            if db_password:
                cmd = ShellCmd('''mysql -u %s -p%s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, shell_quote(db_password), db_hostname, db_port))
            else:
                cmd = ShellCmd('''mysql -u %s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_hostname, db_port))

            cmd(False)
            if cmd.return_code != 0:
                msg = 'unknown, %s %s' % (cmd.stderr, cmd.stdout)
                info('version: %s' % colored(msg.strip(), 'yellow'))
                return

            out = cmd.stdout
            if 'schema_version' not in out:
                version = '0.6'
            else:
                version = get_zstack_version(db_hostname, db_port, db_user, db_password)
                if len(version.split('.')) >= 4:
                    version = '.'.join(version.split('.')[:3])

            detailed_version = get_detail_version()
            if detailed_version is not None:
                info('version: %s (%s)' % (version, detailed_version))
            else:
                info('version: %s' % version)
        def show_hci_version():
            full_version = get_hci_full_version()
            if not full_version:
                return
            version = full_version.strip(' \t\n\r')
            if version is not None:
                if version[0].isdigit():
                    info('Cube version: %s (Cube %s)' % (version.split('-')[0], version))
                else:
                    list = version.split('-')
                    hci_version = list[-3]
                    hci_name = version.split("-%s-" % hci_version)
                    info(hci_name[0] + ' version: %s (%s)' % (hci_version, version))

        def show_zsv_version():
            zsv_version = get_zsv_version()
            if zsv_version:
                info('ZSphere version: %s' % zsv_version)
            else:
                info(colored('ZSphere version: Unknown', 'yellow'))

        info('\n'.join(info_list))
        show_version()
        if is_hyper_converged_host():
            show_hci_version()
        elif is_zsv_env():
            show_zsv_version()

        s = check_zstack_status()
        if s is not None and not s:
            boot_error_log = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'bootError.log')
            if os.path.exists(boot_error_log):
                info(colored('Management server met an error as below:', 'yellow'))
                with open(boot_error_log, 'r') as fd:
                    error_msg = fd.read()
                    try:
                        # strip unimportant messages for json.loads
                        error_msg = json.loads(error_msg)
                        error_msg['details'] = json.loads(error_msg['details'].replace('org.zstack.header.errorcode.OperationFailureException: ', ''))
                    except (KeyError, ValueError, TypeError):
                        pass

                    if 'Prometheus boot error' in error_msg:
                        filtered_msg = [x for x in json.dumps(error_msg).split('\\n') if 'error' in x]
                        info(colored('\r\n'.join(filtered_msg), 'red'))
                    else:
                        info(colored(json.dumps(error_msg, indent=4), 'red'))

        ctl.internal_run('ui_status', args='-q')


class ManagementNodeStatusCollector(Command):

    # safety-reinforcing
    def get_safe(self):
        code, stdout, stderr = shell_return_stdout_stderr("ipset list")
        if code == 0 and stdout.strip("\n") != "":
            status = "enabled"
        else:
            status = "disabled"
        return status

    def get_systemd_service_status(self, service_name):
        #systemctl status ${targetService}, example: systemctl status mariadb
        code, status, stderr = shell_return_stdout_stderr(
            "systemctl status %s | grep 'Active' | awk -F \"(\" 'NR==1{print $2}' | awk -F \")\" 'NR==1{print $1}' " % service_name)
        if code == 0 and status.strip('\n') == "running":
            return "running"
        elif status == "dead":
            return "stopped"
        else:
            return "unknown"

    def get_mn_ui_status(self):
        code, stdout, stderr = shell_return_stdout_stderr("zstack-ctl status | grep \"status\" | sed -r \"s/\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]//g\" | awk -F \":\" '{print $2}'| awk -F \"[\" '{print $1}'")
        if code == 0:
            try:
                mn_status = stdout.split('\n')[0].strip().lower()
                ui_status = stdout.split('\n')[1].strip().lower()
                return mn_status, ui_status
            except:
                return "unknown", "unknown"
        else:
            return "unknown", "unknown"

class ShowStatus2Cmd(Command):
    colors = ["green", "yellow", "red"]
    service_names = ["mysql", "prometheus2", "zops-ui", "port restriction", "MN", "MN-UI"]

    def __init__(self):
        super(ShowStatus2Cmd, self).__init__()
        self.name = 'status2'
        self.description = 'show ZStack main components status information.'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to show the management node status on a remote machine')
        parser.add_argument('--quiet', '-q', help='Do not log this action.', action='store_true', default=False)

    def _stop_remote(self, args):
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl status"' % args.host)

    def _format_str_color(self, service_name, status):
        if status in ["running", "enabled", "disabled"]:
            status_color = self.colors[0]
        elif status == "stopped" or status == "False":
            status_color = self.colors[2]
        else:
            status_color = self.colors[1]

        index = self.service_names.index(service_name)
        format_str = "[{}]{}[{}]".format(("%d" % (index + 1)),
                                         service_name.ljust(50, ".").replace(".","·"), colored(status, status_color))
        info_and_debug(format_str)

    def run(self, args):
        self.quiet = args.quiet
        if args.host:
            self._stop_remote(args)
            return

        collector = ManagementNodeStatusCollector()

        # mariadb
        mysql_status = collector.get_systemd_service_status("mariadb")
        self._format_str_color("mysql", mysql_status)

        # prometheus2
        prometheus_status = collector.get_systemd_service_status("prometheus2")
        self._format_str_color("prometheus2", prometheus_status)

        # zops ui status
        zops_ui_status = collector.get_systemd_service_status("zops-ui")
        self._format_str_color("zops-ui", zops_ui_status)

        # safety-reinforcing
        safe_reinforcing_status = collector.get_safe()
        self._format_str_color("port restriction", safe_reinforcing_status)

        # mn, ui status
        mn_status, ui_status = collector.get_mn_ui_status()
        self._format_str_color("MN", mn_status)
        self._format_str_color("MN-UI", ui_status)

class ShowStatus3Cmd(Command):
    def __init__(self):
        super(ShowStatus3Cmd, self).__init__()
        self.name = 'status3'
        self.description = 'show project num(PJNUM) and version installed_on info'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host',
                            help='SSH URL, for example, root@192.168.0.10, to show the management node status on a remote machine')
        parser.add_argument('--quiet', '-q', help='Do not log this action.', action='store_true', default=False)

    def _stop_remote(self, args):
        shell_no_pipe(
            'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl status"' % args.host)

    def run(self, args):
        self.quiet = args.quiet
        if args.host:
            self._stop_remote(args)
            return

        try:
            db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        except CtlError as e:
            info('version: %s' % colored('unknown, %s' % e.message.strip(), 'yellow'))
            return

        def get_pjnum():
            pjnum_path = ctl.zstack_home + "/PJNUM"
            if not os.path.exists(pjnum_path):
                return 'unknown'
            with open(pjnum_path, 'r') as fd:
                line = fd.readline()
                if line.startswith('PJNUM='):
                    num = line.strip('\t\n\r').split('=')[1]
                    if num == '001':
                        return 'universal'
                    else:
                        return 'particular'
                else:
                    return 'unknown'

        pjnum = get_pjnum()
        info('project num(PJNUM): %s' % pjnum)
        installed_on = get_zstack_installed_on(db_hostname, db_port, db_user, db_password)
        info('installed on: %s' % installed_on)

class DeployDBCmd(Command):
    DEPLOY_DB_SCRIPT_PATH = "WEB-INF/classes/deploydb.sh"
    ZSTACK_PROPERTY_FILE = "WEB-INF/classes/zstack.properties"

    def __init__(self):
        super(DeployDBCmd, self).__init__()
        self.name = "deploydb"
        self.description = (
            "deploy a new ZStack database, create a user 'zstack' with password specified in '--zstack-password',\n"
            "and update zstack.properties if --no-update is not set.\n"
            "\nDANGER: this will erase the existing ZStack database.\n"
            "NOTE: If the database is running on a remote host, please make sure you have granted privileges to the root user by:\n"
            "\n\tGRANT ALL PRIVILEGES ON *.* TO 'root'@'%%' IDENTIFIED BY 'your_root_password' WITH GRANT OPTION;\n"
            "\tFLUSH PRIVILEGES;\n"
        )
        self.sensitive_args = ['--root-password', '--zstack-password']
        ctl.register_command(self)

    def update_db_config(self):
        update_db_config_script = mysql_db_config_script

        fd, update_db_config_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(update_db_config_script)
        info('update_db_config_script_path is: %s' % update_db_config_script_path)
        ShellCmd('bash %s' % update_db_config_script_path)()
        os.remove(update_db_config_script_path)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--root-password', help='root user password of MySQL. [DEFAULT] empty password')
        parser.add_argument('--zstack-password', help='password of user "zstack". [DEFAULT] empty password')
        parser.add_argument('--host', help='IP or DNS name of MySQL host; default is localhost', default='localhost')
        parser.add_argument('--port', help='port of MySQL host; default is 3306', type=int, default=3306)
        parser.add_argument('--no-update', help='do NOT update database information to zstack.properties; if you do not know what this means, do not use it', action='store_true', default=False)
        parser.add_argument('--drop', help='drop existing zstack database', action='store_true', default=False)
        parser.add_argument('--keep-db', help='keep existing zstack database and not raise error.', action='store_true', default=False)

    def run(self, args):
        error_if_tool_is_missing('mysql')

        script_path = os.path.join(ctl.zstack_home, self.DEPLOY_DB_SCRIPT_PATH)
        if not os.path.exists(script_path):
            error('cannot find %s, your ZStack installation may have been corrupted, please reinstall it' % script_path)

        property_file_path = os.path.join(ctl.zstack_home, self.ZSTACK_PROPERTY_FILE)
        if not os.path.exists(property_file_path):
            error('cannot find %s, your ZStack installation may have been corrupted, please reinstall it' % property_file_path)

        if args.root_password:
            check_existing_db = 'mysql --user=root --password=%s --host=%s --port=%s -e "use zstack"' % (args.root_password, args.host, args.port)
        else:
            check_existing_db = 'mysql --user=root --host=%s --port=%s -e "use zstack"' % (args.host, args.port)

        self.update_db_config()
        cmd = ShellCmd(check_existing_db)
        cmd(False)
        if not args.root_password:
            args.root_password = "''"
        if not args.zstack_password:
            args.zstack_password = "''"

        if cmd.return_code == 0 and not args.drop:
            if args.keep_db:
                info('detected existing zstack database and keep it; if you want to drop it, please append parameter --drop, instead of --keep-db\n')
            else:
                raise CtlError('detected existing zstack database; if you are sure to drop it, please append parameter --drop or use --keep-db to keep the database')
        else:
            cmd = ShellCmd('bash %s root %s %s %s %s' % (script_path, args.root_password, args.host, args.port, args.zstack_password))
            cmd(False)
            if cmd.return_code != 0:
                if ('ERROR 1044' in cmd.stdout or 'ERROR 1044' in cmd.stderr) or ('Access denied' in cmd.stdout or 'Access denied' in cmd.stderr):
                    raise CtlError(
                        "failed to deploy database, access denied; if your root password is correct and you use IP rather than localhost,"
                        "it's probably caused by the privileges are not granted to root user for remote access; please see instructions in 'zstack-ctl -h'."
                        "error details: %s, %s\n" % (cmd.stdout, cmd.stderr)
                    )
                else:
                    cmd.raise_error()

        if not args.no_update:
            if args.zstack_password == "''":
                args.zstack_password = ''

            properties = [
                ("DB.user", "zstack"),
                ("DB.password", args.zstack_password),
                ("DB.url", 'jdbc:mysql://%s:%s' % (args.host, args.port)),
            ]

            ctl.write_properties(properties)

        info('Successfully deployed ZStack database and updated corresponding DB information in %s' % property_file_path)

class DeployUIDBCmd(Command):
    DEPLOY_UI_DB_SCRIPT_PATH = Ctl.ZSTACK_UI_DB
    ZSTACK_UI_PROPERTY_FILE = "zstack.ui.properties"

    def __init__(self):
        super(DeployUIDBCmd, self).__init__()
        self.name = "deploy_ui_db"
        self.description = (
            "Deploy a new zstack_ui database.\n"
            "\nDANGER: this will erase the existing zstack_ui database.\n"
            "NOTE: If the database is running on a remote host, please make sure you have granted privileges to the root user by:\n"
            "\n\tGRANT ALL PRIVILEGES ON *.* TO 'root'@'%%' IDENTIFIED BY 'your_root_password' WITH GRANT OPTION;\n"
            "\tFLUSH PRIVILEGES;\n"
        )
        self.sensitive_args = ['--root-password', '--zstack-ui-password']
        ctl.register_command(self)

    def update_db_config(self):
        update_db_config_script = mysql_db_config_script
        fd, update_db_config_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(update_db_config_script)
        info('update_db_config_script_path is: %s' % update_db_config_script_path)
        ShellCmd('bash %s' % update_db_config_script_path)()
        os.remove(update_db_config_script_path)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--root-password', help='root user password of MySQL. [DEFAULT] empty password')
        parser.add_argument('--zstack-ui-password', help='password of user "zstack_ui". [DEFAULT] empty password')
        parser.add_argument('--host', help='IP or DNS name of MySQL host; default is localhost', default='localhost')
        parser.add_argument('--port', help='port of MySQL host; default is 3306', type=int, default=3306)
        parser.add_argument('--drop', help='drop existing zstack ui database', action='store_true', default=False)
        parser.add_argument('--no-update', help='do NOT update database information to zstack.ui.properties; if you do not know what this means, do not use it', action='store_true', default=False)
        parser.add_argument('--keep-db', help='keep existing zstack ui database and not raise error.', action='store_true', default=False)

    def run(self, args):
        error_if_tool_is_missing('mysql')

        script_path = os.path.join(ctl.zstack_home, self.DEPLOY_UI_DB_SCRIPT_PATH)
        if not os.path.exists(script_path):
            error('cannot find %s, your zstack installation may have been corrupted, please reinstall it' % script_path)

        if args.root_password:
            check_existing_db = 'mysql --user=root --password=%s --host=%s --port=%s -e "use zstack_ui"' % (args.root_password, args.host, args.port)
            drop_mini_db = 'mysql --user=root --password=%s --host=%s --port=%s -e "DROP DATABASE IF EXISTS zstack_mini;"' % (args.root_password, args.host, args.port)
        else:
            check_existing_db = 'mysql --user=root --host=%s --port=%s -e "use zstack_ui"' % (args.host, args.port)
            drop_mini_db = 'mysql --user=root --host=%s --port=%s -e "DROP DATABASE IF EXISTS zstack_mini;"' % (args.host, args.port)

        self.update_db_config()
        cmd = ShellCmd(check_existing_db)
        cmd(False)
        if not args.root_password:
            args.root_password = "''"
        if not args.zstack_ui_password:
            args.zstack_ui_password = "''"

        if cmd.return_code == 0 and not args.drop:
            if args.keep_db:
                info('detected existing zstack_ui database and keep it; if you want to drop it, please append parameter --drop, instead of --keep-db\n')
            else:
                raise CtlError('detected existing zstack_ui database; if you are sure to drop it, please append parameter --drop or use --keep-db to keep the database')
        else:
            cmd = ShellCmd('bash %s root %s %s %s %s' % (script_path, args.root_password, args.host, args.port, args.zstack_ui_password))
            cmd(False)
            if cmd.return_code != 0:
                if ('ERROR 1044' in cmd.stdout or 'ERROR 1044' in cmd.stderr) or ('Access denied' in cmd.stdout or 'Access denied' in cmd.stderr):
                    raise CtlError(
                        "failed to deploy zstack_ui database, access denied; if your root password is correct and you use IP rather than localhost,"
                        "it's probably caused by the privileges are not granted to root user for remote access; please see instructions in 'zstack-ctl -h'."
                        "error details: %s, %s\n" % (cmd.stdout, cmd.stderr)
                    )
                else:
                    cmd.raise_error()

        if not args.no_update:
            if args.zstack_ui_password == "''":
                args.zstack_ui_password = ''

            properties = [
                    ("db_url", 'jdbc:mysql://%s:%s' % (args.host, args.port)),
                    ("db_username", "zstack_ui"),
                    ("db_password", args.zstack_ui_password),
            ]
            ctl.write_ui_properties(properties)
        if args.drop:
            drop_mini_db_cmd = ShellCmd(drop_mini_db)
            drop_mini_db_cmd(True)
        info_and_debug('Successfully deployed zstack_ui database')

class TailLogCmd(Command):
    WS_NAME = 'websocketd' if platform.machine() == 'x86_64' else 'websocketd_%s' % platform.machine()
    WS_PATH = os.path.join(Ctl.ZSTACK_TOOLS_DIR, WS_NAME)

    def __init__(self):
        super(TailLogCmd, self).__init__()
        self.name = 'taillog'
        self.description = "shortcut to print management node log to stdout"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--listen-port', help='if set, web browser can get log via designated protocol.', default=None)
        parser.add_argument('--protocol', help='the protocol web tail log use.', default='http', choices=['http', 'websocket'])
        parser.add_argument('--timeout', help='when tail log via websocket, survival time of server in seconds.'
                                              ' keep alive if not set.', default=None, type=int)

    def run(self, args):
        websocket_path = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/websocketd")
        if not os.path.isfile(websocket_path):
            raise CtlError('cannot find %s' % websocket_path)
        if not os.access(websocket_path, os.X_OK):
            ShellCmd('chmod +x %s' % websocket_path)

        log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
        log_path = os.path.normpath(log_path)
        if not os.path.isfile(log_path):
            raise CtlError('cannot find %s' % log_path)

        if not args.listen_port:
            script = ShellCmd('tail -f %s' % log_path, pipe=False)
            script()
            return

        if args.protocol == 'http':
            cmd = '''(echo -e 'HTTP/1.1 200 OK\\nAccess-Control-Allow-Origin: *\\nContent-type: text/event-stream\\n' \
                   && tail -f %s | sed -u -e 's/^/data: /;s/$/\\n/') | nc -lp %s''' % (
            log_path, args.listen_port)
            shell(cmd)
            return


        def get_running_ui_ssl_args():
            pid = get_ui_pid()
            if pid:
                with open('/proc/%s/cmdline' % pid, 'r') as fd:
                    cmdline = fd.read()
                    if 'ssl.enabled=true' in cmdline:
                        return "--ssl --sslkey " + ctl.ZSTACK_UI_KEYSTORE_PEM + " --sslcert " + ctl.ZSTACK_UI_KEYSTORE_PEM
            return ""

        timeoutcmd = "" if not args.timeout else "timeout " + str(args.timeout)
        cmd = '''%s %s --maxforks 1 %s --port %s tail -f %s''' % (timeoutcmd, self.WS_PATH, get_running_ui_ssl_args(), args.listen_port, log_path)

        ret = ShellCmd(cmd)
        ret(False)
        if ret.return_code == 124:
            info("websocketd exit.")
        elif ret.return_code != 0:
            ret.raise_error()

class ConfigureCmd(Command):
    def __init__(self):
        super(ConfigureCmd, self).__init__()
        self.name = 'configure'
        self.description = "configure zstack.properties"
        self.reportPath = "/progress/configure/properties"
        self.properties_algorithm = "sha256"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to set properties in zstack.properties on the remote machine')
        parser.add_argument('--duplicate-to-remote', help='SSH URL, for example, root@192.168.0.10, to copy zstack.properties on this machine to the remote machine')
        parser.add_argument('--use-file', help='path to a file that will be used to as zstack.properties')

    def _configure_remote_node(self, args):
        shell_no_pipe('ssh %s "/usr/bin/zstack-ctl configure %s"' % (args.host, ' '.join(ctl.extra_arguments)))

    def _duplicate_remote_node(self, args):
        tmp_file_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        tmp_file_name = os.path.join('/tmp/', tmp_file_name)
        with open(ctl.properties_file_path, 'r') as fd:
            txt = fd.read()
            cmd = '''ssh -T %s << EOF
cat <<EOT > %s
%s
EOT

if [ $? != 0 ]; then
    print "cannot create temporary properties file"
    exit 1
fi

/usr/bin/zstack-ctl configure --use-file %s
ret=$?
rm -f %s
exit $ret
EOF
'''
            shell_no_pipe(cmd % (args.duplicate_to_remote, tmp_file_name, txt, tmp_file_name, tmp_file_name))
            info("successfully copied %s to remote machine %s" % (ctl.properties_file_path, args.duplicate_to_remote))

    def _use_file(self, args):
        path = os.path.expanduser(args.use_file)
        if not os.path.isfile(path):
            raise CtlError('cannot find file %s' % path)

        shell('cp -f %s %s' % (path, ctl.properties_file_path))

    def _report_property_updated(self):
        config_cmd = UpdatePropertyCmd()
        config_cmd.propertiesDigestValue = file_hex_digest(self.properties_algorithm, ctl.properties_file_path)
        config_cmd.mnIp = ctl.read_property('management.server.ip')
        if not config_cmd.mnIp:
            config_cmd.mnIp = "127.0.0.1"
        mn_port = ctl.read_property('RESTFacade.port')
        if not mn_port:
            mn_port = 8080
        ShellCmd(ctl.http_call_cmd % (self.reportPath, simplejson.dumps(config_cmd), config_cmd.mnIp, mn_port))
        logger.debug('report properties updated, propertiesDigestValue: %s, mnIp: %s' % (config_cmd.propertiesDigestValue, config_cmd.mnIp))

    def run(self, args):
        if args.use_file:
            self._use_file(args)
            return

        if args.duplicate_to_remote:
            self._duplicate_remote_node(args)
            return

        if not ctl.extra_arguments:
            raise CtlError('please input properties that are in format of "key=value" split by space')

        if args.host:
            self._configure_remote_node(args)
            return

        properties = [l.split('=', 1) for l in ctl.extra_arguments]
        ctl.write_properties(properties)

        self._report_property_updated()

def get_management_node_pid():
    DEFAULT_PID_FILE_PATH = os.path.join(os.path.expanduser('~zstack'), "management-server.pid")

    pid = find_process_by_cmdline('appName=zstack')
    if pid:
        return pid

    pid_file_path = ctl.read_property('pidFilePath')
    if not pid_file_path:
        pid_file_path = DEFAULT_PID_FILE_PATH

    if not os.path.exists(pid_file_path):
        return None

    def is_zstack_process(pid):
        cmdline = os.path.join('/proc/%s/cmdline' % pid)
        with open(cmdline, 'r') as fd:
            content = fd.read()
            return 'appName=zstack' in content

    with open(pid_file_path, 'r') as fd:
        pid = fd.read()
        try:
            pid = int(pid)
            proc_pid = '/proc/%s' % pid
            if os.path.exists(proc_pid):
                if is_zstack_process(pid):
                    return pid
                else:
                    return None
        except Exception:
            return None

    return None

def release_mysql_lock(lock_name, mn_ip):
    access_db_hostname = None
    if is_ha_installed():
        access_db_hostname = ctl.read_property('management.server.vip')

    result = mysql("select IS_USED_LOCK('%s')" % lock_name, db_hostname=access_db_hostname)
    result = result.strip().splitlines()

    connection_id = result[1].strip()
    if connection_id == 'NULL' or connection_id == '-1' or connection_id == '0':
        return

    default_ip = get_default_ip()
    if default_ip and default_ip != mn_ip:
        result = mysql("SELECT count(*) FROM INFORMATION_SCHEMA.PROCESSLIST WHERE ID = %s and (HOST like '%s%%' or HOST like '%s%%')" % (
                connection_id, mn_ip, default_ip), db_hostname=access_db_hostname)
    else:
        result = mysql("SELECT count(*) FROM INFORMATION_SCHEMA.PROCESSLIST WHERE ID = %s and HOST like '%s%%'" % (
            connection_id, mn_ip), db_hostname=access_db_hostname)
    
    result = result.strip().splitlines()[1]
    if result == '0':
        return

    info("kill connection %s to release lock %s held by management node %s" % (connection_id, lock_name, mn_ip))
    mysql("KILL %s" % connection_id, db_hostname=access_db_hostname)

def clear_management_node_leftovers():
    pid = get_management_node_pid()
    if pid:
        info("management node (pid=%s) is still running, skip cleaning heartbeat" % pid)
        return

    mn_ip = ctl.read_property('management.server.ip')
    if not mn_ip:
        warn("management.server.ip not configured")
        return

    try:
        mysql("DELETE FROM ManagementNodeVO WHERE hostName = '%s'" % mn_ip)
        info("cleared management node heartbeat for %s" % mn_ip)
        release_mysql_lock('GlobalFacade.lock', mn_ip)
        release_mysql_lock('ManagementNodeManager.inventory_lock', mn_ip)
    except:
        pass

def is_ha_installed():
    _, output, _ = shell_return_stdout_stderr("systemctl is-enabled zstack-ha")
    status, _, _ = shell_return_stdout_stderr("pgrep -x zstack-hamon")
    if output and output.strip() == "enabled" and status != 0:
        return True
    else:
        return False

class StopAllCmd(Command):
    def __init__(self):
        super(StopAllCmd, self).__init__()
        self.name = 'stop'
        self.description = 'stop all ZStack related services including zstack management node, web UI' \
                           ' if those services are installed'
        ctl.register_command(self)

    def run(self, args):
        def stop_mgmt_node():
            info_and_debug(colored('Stopping ZStack management node, it may take a few minutes...', 'blue'))
            ctl.internal_run('stop_node')

        def stop_ui():
            virtualenv = '/var/lib/zstack/virtualenv/zstack-dashboard'
            if not os.path.exists(virtualenv) and not os.path.exists(ctl.ZSTACK_UI_HOME) and not os.path.exists(ctl.MINI_DIR):
                info_and_debug('skip stopping web UI, it is not installed')
                return

            info_and_debug(colored('Stopping ZStack web UI, it may take a few minutes...', 'blue'))
            ctl.internal_run('stop_ui')

        stop_ui()
        stop_mgmt_node()

class StartAllCmd(Command):

    def __init__(self):
        super(StartAllCmd, self).__init__()
        self.name = 'start'
        self.description = 'start all ZStack related services including zstack management node, web UI' \
                           ' if those services are installed'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--daemon', help='Start ZStack in daemon mode. Only used with systemd.', action='store_true', default=True)

    def run(self, args):
        def start_mgmt_node():
            info_and_debug(colored('Starting ZStack management node, it may take a few minutes...', 'blue'))
            if args.daemon:
                ctl.internal_run('start_node', '--daemon')
            else:
                ctl.internal_run('start_node')

        def start_ui():
            virtualenv = '/var/lib/zstack/virtualenv/zstack-dashboard'
            if not os.path.exists(virtualenv) and not os.path.exists(ctl.ZSTACK_UI_HOME) and not os.path.exists(ctl.MINI_DIR):
                info('skip starting web UI, it is not installed')
                return

            info(colored('Starting ZStack web UI, it may take a few minutes...', 'blue'))
            ctl.internal_run('start_ui')

        start_mgmt_node()
        start_ui()

class AESCipher:
    """
    Usage:
        c = AESCipher('password').encrypt('message')
        m = AESCipher('password').decrypt(c)
    """

    def __init__(self, key='ZStack open source'):
        self.key = md5(key).hexdigest()
        self.cipher = AES.new(self.key, AES.MODE_ECB)
        self.prefix = "crypt_key_for_v1::"
        self.BLOCK_SIZE = 16

    # PKCS#7
    def _pad(self, data_to_pad, block_size):
        padding_len = block_size - len(data_to_pad) % block_size
        padding = bchr(padding_len) * padding_len
        return data_to_pad + padding

    # PKCS#7
    def _unpad(self, padded_data, block_size):
        pdata_len = len(padded_data)
        if pdata_len % block_size:
            raise ValueError("Input data is not padded")
        padding_len = bord(padded_data[-1])
        if padding_len < 1 or padding_len > min(block_size, pdata_len):
            raise ValueError("Padding is incorrect.")
        if padded_data[-padding_len:] != bchr(padding_len) * padding_len:
            raise ValueError("PKCS#7 padding is incorrect.")
        return padded_data[:-padding_len]

    def encrypt(self, raw):
        raw = self._pad(self.prefix + raw, self.BLOCK_SIZE)
        return base64.b64encode(self.cipher.encrypt(raw))

    def decrypt(self, enc):
        denc = base64.b64decode(enc)
        ret = self._unpad(self.cipher.decrypt(denc), self.BLOCK_SIZE).decode('utf8')
        return ret[len(self.prefix):] if ret.startswith(self.prefix) else enc

    def is_encrypted(self, enc):
        try:
            raw = self.decrypt(enc)
            return raw != enc
        except:
            return False

class StartCmd(Command):
    START_SCRIPT = '../../bin/startup.sh'
    SET_ENV_SCRIPT = '../../bin/setenv.sh'
    BEAN_CONTEXT_REF_XML = "WEB-INF/classes/beanRefContext.xml"
    HEAP_DUMP_DIR = '../../logs/heap.hprof'
    MINIMAL_CPU_NUMBER = 4
    #MINIMAL_MEM_SIZE unit is KB, here is 8GB, in linxu, 8GB is 8388608 KB
    #Save some memory for kdump etc. 7GB = 7340032KB
    MINIMAL_MEM_SIZE = 7300000
    SIMULATORS_ON = 'SIMULATOR'
    # keep simulatorsOn, but --mode=simulator is recommanded
    START_MODE = 'START_MODE'
    SIMULATOR = 'simulator'
    MINIMAL = 'minimal'
    SUPPORTED_START_MODE_LIST = [MINIMAL, SIMULATOR]

    def __init__(self):
        super(StartCmd, self).__init__()
        self.name = 'start_node'
        self.description = 'start the ZStack management node on this machine'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to start the management node on a remote machine')
        parser.add_argument('--timeout', help='Wait for ZStack Server startup timeout, default is 1000 seconds.', default=1000)
        parser.add_argument('--daemon', help='Start ZStack in daemon mode. Only used with systemd.', action='store_true', default=False)
        parser.add_argument('--simulator', help='Start Zstack in simulator mode.', action='store_true', default=False)
        parser.add_argument('--mode', help='Start Zstack in specified mode. supported modes include %s' % self.SUPPORTED_START_MODE_LIST)
        parser.add_argument('--mysql_process_list', help='Check mysql wait timeout connection', action='store_true', default=False)

    def _start_remote(self, args):
        info('it may take a while because zstack-ctl will wait for management node ready to serve API')
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl start_node --timeout=%s"' % (args.host, args.timeout))

    def check_cpu_mem(self):
        if multiprocessing.cpu_count() < StartCmd.MINIMAL_CPU_NUMBER:
            error("CPU number should not less than %d" % StartCmd.MINIMAL_CPU_NUMBER)
        status, output = commands.getstatusoutput("cat /proc/meminfo | grep MemTotal |   awk -F \":\" '{print $2}' | awk -F \" \" '{print $1}'")
        if status == 0:
            if int(output) < StartCmd.MINIMAL_MEM_SIZE:
                error("Memory size should not less than %d KB" % StartCmd.MINIMAL_MEM_SIZE)
        else:
            warn("Can't get system memory size from /proc/meminfo")

    def run(self, args):
        self.check_cpu_mem()
        if args.host:
            self._start_remote(args)
            return
        # clean the error log before booting
        boot_error_log = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'bootError.log')
        linux.rm_file_force(boot_error_log)
        pid = get_management_node_pid()
        if pid:
            info('the management node[pid:%s] is already running' % pid)
            return
        else:
            linux.rm_file_force(os.path.join(os.path.expanduser('~zstack'), "management-server.pid"))

        def check_mn_port():
            mn_port = get_mn_port()
            (code, out, _) = shell_return_stdout_stderr('netstat -nap | grep :%s[[:space:]] | grep LISTEN | awk \'{printf $NF "\\n"}\'' % mn_port)
            if code == 0:
                occupied_process_set = set(out.split())
                if '-' in occupied_process_set:
                    occupied_process_set.remove('-')
                if occupied_process_set:
                    raise CtlError('Port %s is occupied by [%s]. Please stop it and retry.' % (mn_port, ', '.join(occupied_process_set)))

        def check_prometheus_port():
            port = ctl.read_property('Prometheus.port')
            if not port:
                port = 9090
            (code, out, _) = shell_return_stdout_stderr('netstat -nap | grep :%s[[:space:]] | grep LISTEN | grep -v prometheus | awk \'{printf $NF "\\n"}\'' % port)
            if code == 0:
                occupied_process_set = set(out.split())
                if '-' in occupied_process_set:
                    occupied_process_set.remove('-')
                if occupied_process_set:
                    raise CtlError('Port %s is occupied by [%s]. Please stop it and retry.' % (port, ', '.join(occupied_process_set)))

        def check_msyql():
            db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()

            if not check_ip_port(db_hostname, db_port):
                raise CtlError('unable to connect to %s:%s, please check if the MySQL is running and the firewall rules' % (db_hostname, db_port))

            with on_error('unable to connect to MySQL'):
                shell('mysql --host=%s --user=%s --password=%s --port=%s -e "select 1"' % (db_hostname, db_user, shell_quote(db_password), db_port))

            if args.mysql_process_list:
                ctl.internal_run('mysql_process_list', '--check')

        def open_iptables_port(protocol, port_list):
            distro = platform.dist()[0]
            if type(port_list) is not list:
                error("port list should be list")
            for port in port_list:
                if distro in RPM_BASED_OS:
                    shell('iptables-save | grep -- "-A INPUT -p %s -m %s --dport %s -j ACCEPT" > /dev/null || '
                          '(iptables -I INPUT -p %s -m %s --dport %s -j ACCEPT && service iptables save)' % (protocol, protocol, port, protocol, protocol, port))
                elif distro in DEB_BASED_OS:
                    shell('iptables-save | grep -- "-A INPUT -p %s -m %s --dport %s -j ACCEPT" > /dev/null || '
                          '(iptables -I INPUT -p %s -m %s --dport %s -j ACCEPT && /etc/init.d/iptables-persistent save)' % (protocol, protocol, port, protocol, protocol, port))
                else:
                    shell('iptables-save | grep -- "-A INPUT -p %s -m %s --dport %s -j ACCEPT" > /dev/null || '
                          'iptables -I INPUT -p %s -m %s --dport %s -j ACCEPT ' % (protocol, protocol, port, protocol, protocol, port))

        def restart_console_proxy():
            cmd = ShellCmd("service zstack-consoleproxy restart")
            cmd(False)
        def check_mn_ip():
            mn_ip = ctl.read_property('management.server.ip')
            if not mn_ip:
                error("management.server.ip not configured")
            if 0 != shell_return("ip a | grep 'inet ' | grep -w '%s'" % mn_ip):
                error("management.server.ip[%s] is not found on any device" % mn_ip)

        def check_ha():
            if is_ha_installed():
                error("please use 'zsha2 start-node'")

        def check_chrony():
            if ctl.read_property('syncNodeTime') == "false":
                return

            source_ips = [v for k, v in ctl.read_property_list('chrony.serverIp.')]
            if not source_ips:
                error("chrony.serverIp not configured")

            mn_ip = ctl.read_property('management.server.ip')
            chrony_running = shell_return("systemctl status chronyd | grep 'active[[:space:]]*(running)'")

            # mn is chrony server
            if set(get_all_ips() + [mn_ip]) & set(source_ips):
                if chrony_running != 0:
                    warn("chrony source is set to management node, but server is not running, try to restart it now...")
                    shell("systemctl disable ntpd || true; systemctl enable chronyd ; systemctl restart chronyd")
                return

            # mn is chrony client
            old_source_ips = shell("chronyc sources | grep '^\^' | awk '{print $2}'").splitlines()
            if set(source_ips) == set(old_source_ips):
                return

            shell('''sed -i /"^[[:space:]#]*server"/d /etc/chrony.conf''')
            with open('/etc/chrony.conf', 'a') as fd:
                fd.writelines('\n'.join(["server %s iburst" % ip for ip in source_ips]))

            shell("systemctl disable ntpd || true; systemctl enable chronyd || true; systemctl restart chronyd || true")
            info("chronyd restarted")

        def prepare_qemu_kvm_repo():
            DEFAULT_QEMU_KVM_PATH = '/opt/zstack-dvd/{}/{}/qemu-kvm-ev'.format(ctl.BASEARCH, ctl.ZS_RELEASE)
            EXPERIMENTAL_QEMU_KVM_PATH = '/opt/zstack-dvd/{}/{}/zstack-experimental'.format(ctl.BASEARCH, ctl.ZS_RELEASE)
            qemu_version = ctl.read_property('KvmHost.qemu_kvm.version')
            if qemu_version == 'zstack-experimental':
                cmd = ShellCmd("umount %s; mount --bind %s %s" % (DEFAULT_QEMU_KVM_PATH, EXPERIMENTAL_QEMU_KVM_PATH, DEFAULT_QEMU_KVM_PATH))
            else:
                cmd = ShellCmd("umount %s" % DEFAULT_QEMU_KVM_PATH)
            cmd(False)

        def prepare_setenv():
            setenv_path = os.path.join(ctl.zstack_home, self.SET_ENV_SCRIPT)
            catalina_opts = [
                '-Djdk.tls.trustNameService=true',
                '-Djava.net.preferIPv4Stack=true',
                '-Dcom.sun.management.jmxremote=true',
                '-Djava.security.egd=file:/dev/./urandom',
                '-XX:-OmitStackTraceInFastThrow',
                '-XX:MaxMetaspaceSize=512m',
                '-XX:+HeapDumpOnOutOfMemoryError',
                '-XX:HeapDumpPath=%s' % os.path.join(ctl.zstack_home, self.HEAP_DUMP_DIR),
                '-XX:+UseAltSigs',
                '-Dlog4j2.formatMsgNoLookups=true'
            ]

            if ctl.extra_arguments:
                catalina_opts.extend(ctl.extra_arguments)

            upgrade_params = ctl.get_env('ZSTACK_UPGRADE_PARAMS')
            if upgrade_params:
                catalina_opts.extend(upgrade_params.split(' '))

            co = ctl.get_env('CATALINA_OPTS')
            if co:
                info('use CATALINA_OPTS[%s] set in environment zstack environment variables; check out them by "zstack-ctl getenv"' % co)
                catalina_opts.extend(co.split(' '))

            def has_opt(prefix):
                for opt in catalina_opts:
                    if opt.startswith(prefix):
                        return True
                return False

            if not has_opt('-Xms'):
                catalina_opts.append('-Xms512M')
            if not has_opt('-Xmx'):
                catalina_opts.append('-Xmx12288M')

            with open(setenv_path, 'w') as fd:
                fd.write('export CATALINA_OPTS=" %s"' % ' '.join(catalina_opts))

        def start_mgmt_node():
            log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
            shell('chown zstack:zstack %s || true; sudo -u zstack sh %s -DappName=zstack' % (log_path, os.path.join(ctl.zstack_home, self.START_SCRIPT)))

            info_and_debug("successfully started Tomcat container; now it's waiting for the management node ready for serving APIs, which may take a few seconds")

        def wait_mgmt_node_start():
            log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
            timeout = int(args.timeout)
            @loop_until_timeout(timeout)
            def check():
                if os.path.exists(boot_error_log):
                    with open(boot_error_log, 'r') as fd:
                        error_msg = fd.read()
                        try:
                            # strip unimportant messages for json.loads
                            error_msg = json.loads(error_msg)
                            error_msg['details'] = json.loads(error_msg['details'].replace('org.zstack.header.errorcode.OperationFailureException: ', ''))
                        except (KeyError, ValueError, TypeError):
                            pass
                        raise CtlError('The management server fails to boot, details can be found in [%s].\n'
                                       'Here is a brief description of the error:\n%s' % \
                                       (log_path, json.dumps(error_msg, indent=4)))

                cmd = create_check_mgmt_node_command(1, 'localhost')
                cmd(False)
                return cmd.return_code == 0

            if not check():
                mgmt_ip = ctl.read_property('management.server.ip')
                if mgmt_ip:
                    mgmt_ip = '[ management.server.ip = %s ]' % mgmt_ip
                else:
                    mgmt_ip = ''
                raise CtlError('no management-node-ready message received within %s seconds%s, please check error in log file %s' % (timeout, mgmt_ip, log_path))

        def prepare_env():
            if args.mode:
                check_start_mode(args.mode)
                ctl.put_envs([(self.START_MODE, args.mode)])
            if args.simulator:
                ctl.put_envs([(self.SIMULATORS_ON, 'True')])

        def is_simulator_on():
            return ctl.get_env(self.SIMULATORS_ON) == 'True'

        def get_start_mode():
            return ctl.get_env(self.START_MODE)

        def encrypt_properties_if_need():
            cipher = AESCipher()
            for key in Ctl.NEED_ENCRYPT_PROPERTIES:
                value = ctl.read_property(key)
                if value and not cipher.is_encrypted(value):
                    ctl.write_properties([(key, cipher.encrypt(value))])

        def prepare_bean_ref_context_xml():
            if get_start_mode() == self.SIMULATOR or is_simulator_on():
                beanXml = "simulator/zstack-simulator2.xml"
                info_and_debug("%s=simulator is set, ZStack will start in simulator mode" % self.START_MODE)
            elif get_start_mode() == self.MINIMAL:
                beanXml = "zstack-minimal.xml"
                info_and_debug("%s=minimal is set, ZStack will start in minimal mode" % self.START_MODE)
            else:
                beanXml = "zstack.xml"

            commands.getstatusoutput("zstack-ctl configure beanConf=%s" % beanXml)

        def check_start_mode(mode):
            if mode and mode != '':
                if mode not in self.SUPPORTED_START_MODE_LIST:
                    error('unsupported start mode, following modes are supported: %s' % self.SUPPORTED_START_MODE_LIST)
                ctl.write_properties([('startMode', mode)])
            else:
                ctl.delete_env(self.START_MODE)
                ctl.delete_properties(['startMode'])

        def check_simulator():
            if get_start_mode() and get_start_mode() != self.SIMULATOR and is_simulator_on():
                error("duplicate start mode configurations, --simulator is deprecated, please use `zstack-ctl setenv %s=` to delete old configuration" % self.SIMULATORS_ON)
            if is_simulator_on():
                info_and_debug("--simulator is set, ZStack will start in simulator mode")
                ctl.write_properties(['simulatorsOn=true'.split('=', 1)])
            else:
                ctl.delete_properties(['simulatorsOn'])

        if os.getuid() != 0:
            raise CtlError('please use sudo or root user')

        prepare_env()
        check_java_version()
        check_mn_port()
        check_prometheus_port()
        check_msyql()
        check_ha()
        check_mn_ip()
        check_chrony()
        restart_console_proxy()
        prepare_qemu_kvm_repo()
        prepare_setenv()
        open_iptables_port('udp',['123'])
        encrypt_properties_if_need()
        check_start_mode(get_start_mode())
        check_simulator()
        prepare_bean_ref_context_xml()

        linux.sync_file(ctl.properties_file_path)
        start_mgmt_node()
        #sleep a while, since zstack won't start up so quickly
        time.sleep(5)

        try:
            wait_mgmt_node_start()
        except CtlError as e:
            try:
                info_and_debug("the management node failed to start, stop it now ...")
                ctl.internal_run('stop_node')
            except:
                pass

            raise e

        if not args.daemon:
            shell('which systemctl >/dev/null 2>&1; [ $? -eq 0 ] && systemctl start zstack', is_exception = False)
        info_and_debug('successfully started management node')

        ctl.delete_env('ZSTACK_UPGRADE_PARAMS')

class StopCmd(Command):
    STOP_SCRIPT = "../../bin/shutdown.sh"

    def __init__(self):
        super(StopCmd, self).__init__()
        self.name = 'stop_node'
        self.description = 'stop the ZStack management node on this machine'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to stop the management node on a remote machine')
        parser.add_argument('--force', '-f', help='force kill the java process, without waiting.', action="store_true", default=False)

    def _stop_remote(self, args):
        if args.force:
            shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl stop_node --force"' % args.host)
        else:
            shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl stop_node"' % args.host)

    def run(self, args):
        if args.host:
            self._stop_remote(args)
            return

        check_java_version()

        # for zstack-local repo upgrade
        DEFAULT_QEMU_KVM_PATH = '/opt/zstack-dvd/{}/{}/qemu-kvm-ev'.format(ctl.BASEARCH, ctl.ZS_RELEASE)
        cmd = ShellCmd("umount %s" % DEFAULT_QEMU_KVM_PATH)
        cmd(False)

        pid = get_management_node_pid()
        if not pid:
            info('the management node has been stopped')
            clear_management_node_leftovers()
            return

        timeout = 30
        if not args.force:
            @loop_until_timeout(timeout)
            def wait_stop():
                return get_management_node_pid() is None

            shell('bash %s' % os.path.join(ctl.zstack_home, self.STOP_SCRIPT))
            if wait_stop():
                info_and_debug('successfully stopped management node')
                return

        pid = get_management_node_pid()
        if pid:
            if not args.force:
                info_and_debug('unable to stop management node within %s seconds, kill it' % timeout)
            with on_error('unable to kill -9 %s' % pid):
                logger.info('graceful shutdown failed, try to kill management node process:%s' % pid)
                kill_process(pid, signal.SIGTERM)
                time.sleep(1)
                kill_process(pid, signal.SIGKILL)
                clear_management_node_leftovers()

                if get_management_node_pid():
                    raise CtlError('failed to kill management node, pid = %s' % pid)

class RefreshAuditCmd(Command):
    audit_rule_file = "/etc/audit/rules.d/audit.rules"

    def __init__(self):
        super(RefreshAuditCmd, self).__init__()
        self.name = 'refresh_audit'
        self.description = 'refresh audit list'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--add', '-a', help='Add audit rule at file')
        parser.add_argument('--delete', '-d', help='Delete audit rule at file')
        parser.add_argument('--search', '-s', help='Search file change history')
        parser.add_argument('--list', '-l', help='Show audit rule list', action="store_true", default=False)
        parser.add_argument('--refresh', '-r', help='Refresh audit rule from audit.list', action="store_true", default=False)

    def run(self, args):
        if not os.path.isfile(RefreshAuditCmd.audit_rule_file):
            info('ERROR: %s not exist' % RefreshAuditCmd.audit_rule_file)
            return

        if args.add:
            (status, output, stderr) = shell_return_stdout_stderr('auditctl -w %s -p wa -k zstack' % args.add)
            if status == 0:
                info('Successfully add rule at %s' % args.add)
                with open(RefreshAuditCmd.audit_rule_file, "a") as f:
                    f.write('-w %s -p wa -k zstack\n' % args.add)
            else:
                info('ERROR: %s' % stderr.strip('\n'))

        if args.delete:
            (status, output, stderr) = shell_return_stdout_stderr('auditctl -W %s -p wa -k zstack' % args.delete)
            if status == 0:
                info('Successfully delete rule at %s' % args.delete.strip('\n'))
                with open(RefreshAuditCmd.audit_rule_file, "r") as f:
                    lines = f.readlines()
                with open(RefreshAuditCmd.audit_rule_file, "w") as f_w:
                    for line in lines:
                        if args.delete in line:
                            continue
                        f_w.write(line)
            else:
                info('ERROR: %s' % stderr.strip('\n'))

        if args.search:
            cmd = ShellCmd('ausearch -i -f %s' % args.search.strip('\n'), pipe=False)
            cmd(False)
            return

        if args.list:
            (status, output, stderr) = shell_return_stdout_stderr('auditctl -l')
            info(output.strip('\n'))
            return

        if args.refresh:
            with open(RefreshAuditCmd.audit_rule_file, 'r') as fd:
                all_lines = fd.readlines()
                maxlength = max(len(line.strip('\n')) for line in all_lines) + 1
                info('Rule'.ljust(maxlength) + 'Result')
            for line in all_lines:
                (status, output, stderr) = shell_return_stdout_stderr('auditctl %s' % line)
                if ("rule exists" not in stderr.lower()) and (status != 0) and ("-k zstack" in line):
                    info(line.strip('\n').ljust(maxlength) + stderr.strip('\n'))
                elif ("-k zstack" in line):
                    info(line.strip('\n').ljust(maxlength) + 'success')

        info("\nCurrent rule list")
        (status, output, stderr) = shell_return_stdout_stderr('auditctl -l')
        info(output.strip('\n'))

class MysqlProcessList(Command):

    def __init__(self):
        super(MysqlProcessList, self).__init__()
        self.name = 'mysql_process_list'
        self.description = 'show mysql processlist'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--check', help='check mysql wait timeout connection for zstack start_node', action="store_true")
        parser.add_argument('--time', help='the time of wait timeout, must >= 1')
        parser.add_argument('--kill', help='kill wait timeout connection', action="store_true")
        parser.add_argument('--detail', help='show the detail of mysql wait timeout connection', action="store_true")
        parser.add_argument('--desc', help='order by time desc, used with detail', action="store_true")
        parser.add_argument('--asc', help='order by time asc, used with detail', action="store_true")
        parser.add_argument('--host', help='the connected host')

    def get_wait_timeout(self):
        (db_hostname, db_port, db_user, db_password) = ctl.get_live_mysql_portal()
        sql = '''mysql -u %s -p%s --host %s -P %s -e "show variables where variable_name='wait_timeout'"| grep wait_timeout| awk '{print $2}' ''' % (db_user, db_password, db_hostname, db_port)
        (status, output, stderr) = shell_return_stdout_stderr(sql)
        if status != 0:
            error("get mysql wait timeout error")
        return output.strip('\n')

    def check_argument(self, args):
        if args.time:
            try:
                time = int(args.time)
                if time < 1:
                    error("time must >= 1")
                    return
            except:
                error("time must be positive integer")

        if args.desc & args.asc:
            error("asc and desc cannot be used at the same time")

    def run(self, args):
        (db_hostname, db_port, db_user, db_password) = ctl.get_live_mysql_portal()
        self.check_argument(args)

        if args.check:
            sql = '''mysql -u %s -p%s --host %s -P %s -e "select count(*) from information_schema.processlist where command = 'Sleep' and time > (%s * 2)" |awk 'NR>1' ''' % (db_user, db_password, db_hostname, db_port, self.get_wait_timeout())
            (status, output, stderr) = shell_return_stdout_stderr(sql)
            if status != 0:
                error(stderr)
            if int(output.strip("\n")) > 0:
                error("mysql wait timeout connection[%s]" % output.strip("\n"))
            return

        if args.detail:
            if args.time:
                sql = '''mysql -u %s -p%s --host %s -P %s -e "select * from information_schema.processlist where command = 'Sleep' and time > %s''' % (db_user, db_password, db_hostname, db_port, args.time)
            else:
                sql = '''mysql -u %s -p%s --host %s -P %s -e "select * from information_schema.processlist where command = 'Sleep' and time > (%s * 2)''' % (db_user, db_password, db_hostname, db_port, self.get_wait_timeout())
            if args.host:
                sql = sql + " and host like'%" + args.host + "%'"
            if args.asc:
                sql = sql + " order by time asc"
            if args.desc:
                sql = sql + " order by time desc"
            sql = sql + "\""
            (status, output, stderr) = shell_return_stdout_stderr(sql)
            if status != 0:
                error(stderr)
            if output == "":
                print("no wait timeout connection")
                return
            info(output)
            count = output.count('\n') - 1
            info("%d wait timeout connection" % count)
            return

        if args.kill:
            if args.time:
                sql = '''mysql -u %s -p%s --host %s -P %s -e "select id from information_schema.processlist where command = 'Sleep' and time > %s ''' % (db_user, db_password, db_hostname, db_port, args.time)
            else:
                sql = '''mysql -u %s -p%s --host %s -P %s -e "select id from information_schema.processlist where command = 'Sleep' and time > (%s * 2) ''' % (db_user, db_password, db_hostname, db_port, self.get_wait_timeout())
            if args.host:
                sql = sql + " and host like'%" + args.host + "%'"
            sql = sql + "\"" + "|awk 'NR>1'"
            (status, output, stderr) = shell_return_stdout_stderr(sql)
            if status != 0:
                error(stderr)
            if output == "":
                info("no wait timeout connection")
                return
            ids = output.split("\n")
            info("kill such id")
            count = 0
            for id in ids:
                if id == "":
                    if count > 0:
                        info("kill %d wait timeout connection" % count)
                    return
                info(id)
                sql = '''mysql -u %s -p%s --host %s -P %s -e "kill %s" ''' % (db_user, db_password, db_hostname, db_port, id)
                (status, output, stderr) = shell_return_stdout_stderr(sql)
                if status != 0:
                    error("kill mysql connection id[%s] error, because: %s" % (id, stderr))
                count = count + 1
            return

        else:
            if args.time:
                sql = '''mysql -u %s -p%s --host %s -P %s -e "select count(*) as count from information_schema.processlist where command = 'Sleep' and time > %s" ''' % (db_user, db_password, db_hostname, db_port, args.time)
            else:
                sql = '''mysql -u %s -p%s --host %s -P %s -e "select count(*) as count from information_schema.processlist where command = 'Sleep' and time > (%s * 2)" ''' % (db_user, db_password, db_hostname, db_port, self.get_wait_timeout())
            (status, output, stderr) = shell_return_stdout_stderr(sql)
            if status != 0:
                error(stderr)
            info(output)

class RestartNodeCmd(Command):

    def __init__(self):
        super(RestartNodeCmd, self).__init__()
        self.name = 'restart_node'
        self.description = 'restart the management node'
        ctl.register_command(self)

    def run(self, args):
        ctl.internal_run('stop_node')
        ctl.internal_run('start_node')

class SaveConfigCmd(Command):
    DEFAULT_PATH = '~/.zstack/'

    def __init__(self):
        super(SaveConfigCmd, self).__init__()
        self.name = 'save_config'
        self.description = 'save ZStack configuration from ZSTACK_HOME to specified folder'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--save-to', help='the folder where ZStack configurations should be saved')

    def run(self, args):
        path = args.save_to
        if not path:
            path = self.DEFAULT_PATH

        path = os.path.expanduser(path)
        if not os.path.exists(path):
            os.makedirs(path)

        properties_file_path = os.path.join(path, 'zstack.properties')
        shell('yes | cp %s %s' % (ctl.properties_file_path, properties_file_path))
        ssh_private_key_path = os.path.join(path, 'id_rsa')
        ssh_public_key_path = os.path.join(path, 'id_rsa.pub')
        shell('yes | cp %s %s' % (ctl.ssh_private_key, ssh_private_key_path))
        shell('yes | cp %s %s' % (ctl.ssh_public_key, ssh_public_key_path))

        info('successfully saved %s to %s' % (ctl.properties_file_path, properties_file_path))

class RestoreConfigCmd(Command):
    DEFAULT_PATH = '~/.zstack/'

    def __init__(self):
        super(RestoreConfigCmd, self).__init__()
        self.name = "restore_config"
        self.description = 'restore ZStack configuration from specified folder to ZSTACK_HOME'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--restore-from', help='the folder where ZStack configurations should be found')

    def run(self, args):
        path = args.restore_from
        if not path:
            path = self.DEFAULT_PATH

        path = os.path.expanduser(path)
        if os.path.isdir(path):
            properties_file_path = os.path.join(path, 'zstack.properties')
        elif os.path.isfile(path):
            properties_file_path = path
        else:
            raise CtlError('cannot find zstack.properties at %s' % path)

        shell('yes | cp %s %s' % (properties_file_path, ctl.properties_file_path))
        ssh_private_key_path = os.path.join(path, 'id_rsa')
        ssh_public_key_path = os.path.join(path, 'id_rsa.pub')
        shell('yes | cp %s %s' % (ssh_private_key_path, ctl.ssh_private_key))
        shell('yes | cp %s %s' % (ssh_public_key_path, ctl.ssh_public_key))

        info('successfully restored zstack.properties and ssh identity keys from %s to %s' % (properties_file_path, ctl.properties_file_path))

class InstallDbCmd(Command):
    def __init__(self):
        super(InstallDbCmd, self).__init__()
        self.name = "install_db"
        self.description = (
            "install MySQL database on a target machine which can be a remote machine or the local machine."
            "\nNOTE: you may need to set --login-password to password of previous MySQL root user, if the machine used to have MySQL installed and removed."
            "\nNOTE: if you hasn't setup public key for ROOT user on the remote machine, this command will prompt you for password of SSH ROOT user for the remote machine."
        )
        self.sensitive_args = ['--root-password', '--login-password']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='host IP, for example, 192.168.0.212, please specify the real IP rather than "localhost" or "127.0.0.1" when installing on local machine; otherwise management nodes on other machines cannot access the DB.', required=True)
        parser.add_argument('--root-password', help="new password of MySQL root user; an empty password is used if both this option and --login-password option are omitted")
        parser.add_argument('--login-password', help="login password of MySQL root user; an empty password is used if this option is omitted."
                            "\n[NOTE] this option is needed only when the machine has MySQL previously installed and removed; the old MySQL root password will be left in the system,"
                            "you need to input it in order to reset root password for the new installed MySQL.", default=None)
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--yum', help="Use ZStack predefined yum repositories. The valid options include: alibase,aliepel,163base,ustcepel,zstack-local. NOTE: only use it when you know exactly what it does.", default=None)
        parser.add_argument('--no-backup', help='do NOT backup the database. If the database is very large and you have manually backup it, using this option will fast the upgrade process. [DEFAULT] false', default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def run(self, args):
        current_host_ips = get_all_ips()
        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      root_password: $root_password
      login_password: $login_password
      yum_repo: "$yum_repo"
      ansible_python_interpreter: /usr/bin/python2

  tasks:
    - name: set ansible_distribution_major_version
      set_fact:
        ansible_distribution_major_version: "{{ansible_distribution_major_version | int }}"

    - name: pre-install script
      script: $pre_install_script

    - name: install MySQL for RedHat 6 through user defined repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_major_version < 7 and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y mysql mysql-server
      register: install_result

    - name: install MySQL for RedHat 6 through system defined repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_major_version < 7 and yum_repo == 'false'
      shell: "yum clean metadata; yum --nogpgcheck install -y mysql mysql-server "
      register: install_result

    - name: install MySQL for RedHat 7/Kylin10/openEuler/UnionTech kongzi/Nfs from local
      when: (ansible_os_family == 'RedHat' and ansible_distribution_major_version >= 7 and yum_repo != 'false') or ansible_os_family == 'Kylin' \
            or ansible_os_family == 'Openeuler' or ansible_os_family == 'Nfs' or (ansible_os_family == 'UnionTech' and ansible_distribution_release == 'kongzi')
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y  mariadb mariadb-server iptables-services
      register: install_result

    - name: install MySQL for RedHat 7/Kylin10 or from local
      when: (ansible_os_family == 'RedHat' and ansible_distribution_major_version >= 7 and yum_repo == 'false') or (ansible_os_family == 'Kylin' and ansible_distribution_major_version == '10' and yum_repo == 'false')
      shell: yum clean metadata; yum --nogpgcheck install -y  mariadb mariadb-server iptables-services
      register: install_result

    - name: install MySQL for AliOS 7 from local
      when: ansible_os_family == 'Alibaba' and ansible_distribution_major_version >= 7 and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y  mariadb mariadb-server iptables-services
      register: install_result

    - name: install MySQL for AliOS 7 from local
      when: ansible_os_family == 'Alibaba' and ansible_distribution_major_version >= 7 and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y  mariadb mariadb-server iptables-services
      register: install_result

    - name: install MySQL for Ubuntu/Debain
      when: ansible_os_family == 'Debian'
      shell: apt-get -y install --allow-unauthenticated mariadb-server mariadb-client netfilter-persistent
      register: install_result

    - name: install MySQL for Kylin402/UOS
      when: (ansible_os_family == 'Kylin' and ansible_distribution_version == '4.0.2')  or ansible_os_family == 'Uos' or ansible_os_family == 'Uniontech os server 20 enterprise'
      shell: apt-get -y install --allow-unauthenticated mariadb-server mariadb-client netfilter-persistent
      register: install_result

    - name: open 3306 port on RedHat 7/Alibaba/Kyliin10/openEuler/UnionTech kongzi/Nfs
      when: ansible_os_family == 'RedHat' or ansible_os_family == 'Alibaba' or (ansible_os_family == 'Kylin' and ansible_distribution_version == '10')
            or ansible_os_family == 'Nfs' or (ansible_os_family == 'UnionTech' and ansible_distribution_release == 'kongzi')
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 3306 -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 3306 -j ACCEPT && service iptables save)

    - name: open 3306 port
      when: ansible_os_family != 'RedHat' and ansible_os_family != 'Alibaba' and (ansible_os_family == 'Kylin' and ansible_distribution_version == '4.0.2')
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 3306 -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 3306 -j ACCEPT && /etc/init.d/netfilter-persistent save)

    - name: run post-install script
      script: $post_install_script

    - name: enable MySQL daemon on RedHat 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_major_version < 7
      service: name=mysqld state=restarted enabled=yes

    - name: enable MySQL daemon on RedHat 7/Kyliin10/openEuler/UnionTech kongzi/Nfs
      when: (ansible_os_family == 'RedHat' and ansible_distribution_major_version >= 7) or ansible_os_family == 'Kylin' or ansible_os_family == 'Openeuler'
            or ansible_os_family == 'Nfs' or (ansible_os_family == 'UnionTech' and ansible_distribution_release == 'kongzi')
      service: name=mariadb state=restarted enabled=yes

    - name: enable MySQL daemon on AliOS 7
      when: ansible_os_family == 'Alibaba' and ansible_distribution_major_version >= 7
      service: name=mariadb state=restarted enabled=yes

    - name: enable MySQL on Ubuntu
      when: ansible_os_family == 'Debian'
      service: name=mariadb state=restarted enabled=yes

    - name: enable MySQL on Kylin402/UOS
      when: (ansible_os_family == 'Kylin' and ansible_distribution_version == '4.0.2') or ansible_os_family == 'Uos' or ansible_os_family == 'Uniontech os server 20 enterprise'
      service: name=mariadb state=restarted enabled=yes

    - name: change root password
      shell: $change_password_cmd
      register: change_root_result
      ignore_errors: yes

    - name: grant remote access
      when: change_root_result.rc == 0
      shell: $grant_access_cmd

    - name: rollback MySQL installation on RedHat 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_major_version < 7 and change_root_result.rc != 0 and install_result.changed == True
      shell: rpm -ev mysql mysql-server

    - name: rollback MySQL installation on RedHat 7
      when: ansible_os_family == 'RedHat' and ansible_distribution_major_version >= 7 and change_root_result.rc != 0 and install_result.changed == True
      shell: rpm -ev mariadb mariadb-server
      
    - name: rollback MySQL installation on Kylin10
      when: ansible_os_family == 'Kylin' and ansible_distribution_major_version == 10 and change_root_result.rc != 0 and install_result.changed == True
      shell: rpm -ev mariadb mariadb-server

    - name: rollback MySQL installation on AliOS 7
      when: ansible_os_family == 'Alibaba' and ansible_distribution_major_version >= 7 and change_root_result.rc != 0 and install_result.changed == True
      shell: rpm -ev mariadb mariadb-server

    - name: rollback MySql installation on Ubuntu
      when: ansible_os_family == 'Debian' and change_root_result.rc != 0 and install_result.changed == True
      apt: pkg={{item}} state=absent update_cache=yes
      with_items:
        - mariadb-client
        - mariadb-server

    - name: rollback MySql installation on Kylin402
      when: ansible_os_family == 'Kylin' and ansible_distribution_version == '4.0.2' and change_root_result.rc != 0 and install_result.changed == True
      apt: pkg={{item}} state=absent update_cache=yes
      with_items:
        - mariadb-client
        - mariadb-server

    - name: failure
      fail: >
        msg="failed to change root password of MySQL, see prior error in task 'change root password'; the possible cause
        is the machine used to have MySQL installed and removed, the previous password of root user is remaining on the
        machine; try using --login-password. We have rolled back the MySQL installation so you can safely run install_db
        again with --login-password set."
      when: change_root_result.rc != 0 and install_result.changed == False
'''

        if not args.root_password and not args.login_password:
            args.root_password = '''"''"'''
            more_cmd = ' '
            for ip in current_host_ips:
                if not ip:
                    continue
                more_cmd += "GRANT ALL PRIVILEGES ON *.* TO 'root'@'{}' IDENTIFIED BY '' WITH GRANT OPTION;".format(ip)
            grant_access_cmd = '''/usr/bin/mysql -u root -e ''' \
                               '''"GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '' WITH GRANT OPTION; '''\
                               '''GRANT ALL PRIVILEGES ON *.* TO 'root'@'{}' IDENTIFIED BY '' WITH GRANT OPTION; '''\
                               '''{} FLUSH PRIVILEGES;"'''.format(args.host, more_cmd)
        else:
            if not args.root_password:
                args.root_password = args.login_password
            more_cmd = ' '
            for ip in current_host_ips:
                if not ip:
                    continue
                more_cmd += "GRANT ALL PRIVILEGES ON *.* TO 'root'@'{}' IDENTIFIED BY '{}' WITH GRANT OPTION;".format(ip, args.root_password)
            grant_access_cmd = '''/usr/bin/mysql -u root -p{root_pass} -e '''\
                               '''"GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '{root_pass}' WITH GRANT OPTION; '''\
                               '''GRANT ALL PRIVILEGES ON *.* TO 'root'@'{host}' IDENTIFIED BY '{root_pass}' WITH GRANT OPTION; '''\
                               '''{more_cmd} FLUSH PRIVILEGES;"'''.format(root_pass=args.root_password, host=args.host, more_cmd=more_cmd)

        if args.login_password is not None:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root -p{{login_password}} password {{root_password}}'
        else:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root password {{root_password}}'

        pre_install_script = '''
#!/bin/bash
{0}

###################
#Check DNS hijacking
###################

hostname=`hostname`

pintret=`ping -c 1 -W 2 $hostname 2>/dev/null | head -n1`
echo $pintret | grep 'PING' > /dev/null
[ $? -ne 0 ] && exit 0

ip=`echo $pintret | cut -d' ' -f 3 | cut -d'(' -f 2 | cut -d')' -f 1`

ip_1=`echo $ip | cut -d'.' -f 1`
[ "127" = "$ip_1" ] && exit 0

ip addr | grep $ip > /dev/null
[ $? -eq 0 ] && exit 0

echo "The hostname($hostname) of your machine is resolved to IP($ip) which is none of IPs of your machine.
It's likely your DNS server has been hijacking, please try fixing it or add \"ip_of_your_host $hostname\" to /etc/hosts.
DNS hijacking will cause MySQL not working."
exit 1
'''.format(configure_yum_repo_script)
        fd, pre_install_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(pre_install_script)

        def cleanup_pre_install_script():
            os.remove(pre_install_script_path)

        self.install_cleanup_routine(cleanup_pre_install_script)

        post_install_script = mysql_db_config_script
        fd, post_install_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(post_install_script)

        def cleanup_post_install_script():
            os.remove(post_install_script_path)

        self.install_cleanup_routine(cleanup_post_install_script)

        t = string.Template(yaml)
        if args.yum:
            yum_repo = args.yum
        else:
            yum_repo = 'false'
        yaml = t.substitute({
            'host': args.host,
            'change_password_cmd': change_root_password_cmd,
            'root_password': args.root_password,
            'login_password': args.login_password,
            'grant_access_cmd': grant_access_cmd,
            'pre_install_script': pre_install_script_path,
            'yum_folder': ctl.zstack_home,
            'yum_repo': yum_repo,
            'post_install_script': post_install_script_path
        })

        ansible(yaml, args.host, args.debug, args.ssh_key)

class UpgradeHACmd(Command):
    '''This feature only support zstack offline image currently'''
    host_post_info_list = []
    current_dir = os.path.dirname(os.path.realpath(__file__))
    conf_dir = "/var/lib/zstack/ha/"
    private_key_name = conf_dir + "ha_key"
    conf_file = conf_dir + "ha.yaml"
    logger_dir = "/var/log/zstack/"
    logger_file = "ha.log"
    community_iso = "/opt/ZStack-Community-x86_64-DVD-1.4.0.iso"
    bridge = ""
    SpinnerInfo.spinner_status = {'upgrade_repo':False,'stop_mevoco':False, 'upgrade_mevoco':False,'upgrade_db':False,
                      'backup_db':False, 'check_init':False, 'start_mevoco':False}
    ha_config_content = None

    def __init__(self):
        super(UpgradeHACmd, self).__init__()
        self.name = "upgrade_ha"
        self.description =  "upgrade high availability environment for ZStack-Enterprise."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--zstack-enterprise-installer','--enterprise',
                            help="The new zstack-enterprise installer package, get it from http://cdn.zstack.io/product_downloads/zstack-enterprise/",
                            required=True)
        parser.add_argument('--iso',
                            help="get it from http://cdn.zstack.io/product_downloads/iso/",
                            required=True)

    def upgrade_repo(self, iso, tmp_iso, host_post_info):
        command = (
                  "yum clean --enablerepo=zstack-local metadata &&  pkg_list=`rsync | grep \"not installed\" | awk"
                  " '{ print $2 }'` && for pkg in $pkg_list; do yum --disablerepo=* --enablerepo=zstack-local install "
                  "-y $pkg; done;")
        run_remote_command(command, host_post_info)
        command = "mkdir -p %s" %  tmp_iso
        run_remote_command(command, host_post_info)
        command = "mount -o loop %s %s" % (iso, tmp_iso)
        run_remote_command(command, host_post_info)
        command = "rsync -au --delete %s /opt/zstack-dvd/%s/%s/"  % (tmp_iso, ctl.BASEARCH, ctl.ZS_RELEASE)
        run_remote_command(command, host_post_info)
        command = "umount %s" % tmp_iso
        run_remote_command(command, host_post_info)
        command = linux.get_checked_rm_dir_cmd(tmp_iso)
        run_remote_command(command, host_post_info)

    def check_file_exist(self, file, host_post_info_list):
        if os.path.isabs(file) is False:
            error("Make sure you pass file name with absolute path")
        else:
            if os.path.isfile(file) is False:
                error("Didn't find file %s" % file)
            else:
                for host_post_info in host_post_info_list:
                    if file_dir_exist("path=%s" % file, host_post_info) is False:
                        copy_arg = CopyArg()
                        copy_arg.src = file
                        copy_arg.dest = file
                        copy(copy_arg, host_post_info)

    # do not enable due to lot of customer version
    def check_file_md5sum(self):
        pass

    def check_mn_running(self,host_post_info):
        cmd = create_check_mgmt_node_command(timeout=4, mn_node=host_post_info.host)
        cmd(False)
        if cmd.return_code != 0:
            error("Check management node %s status failed, make sure the status is running before upgrade" % host_post_info.host)
        else:
            state = get_mgmt_node_state_from_result(cmd)
            if state is None:
                error(
                    'The management node %s status is: Unknown, please start the management node before upgrade' % host_post_info.host)
            if state:
                return 0
            else:
                error('The management node %s is starting, please wait a few seconds to upgrade' % host_post_info.host)

    def upgrade_mevoco(self, mevoco_installer, host_post_info):
        mevoco_dir = os.path.dirname(mevoco_installer)
        mevoco_bin = os.path.basename(mevoco_installer)
        command = "rm -rf /tmp/zstack_upgrade.lock && cd %s && bash %s -u -i " % (mevoco_dir, mevoco_bin)
        logger.debug("[ HOST: %s ] INFO: starting run shell command: '%s' " % (host_post_info.host, command))
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                                   (UpgradeHACmd.private_key_name, host_post_info.host, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))


    def run(self, args):
        # create log
        create_log(UpgradeHACmd.logger_dir, UpgradeHACmd.logger_file)
        spinner_info = SpinnerInfo()
        spinner_info.output = "Checking system and init environment"
        spinner_info.name = 'check_init'
        SpinnerInfo.spinner_status['check_init'] = True
        ZstackSpinner(spinner_info)
        if os.path.isfile(UpgradeHACmd.conf_file) is not True:
            error("Didn't find HA config file %s, please contact support for upgrade" % UpgradeHACmd.conf_file)
        host_inventory = UpgradeHACmd.conf_dir + 'host'
        yum_repo = get_yum_repo_from_property()
        private_key_name = UpgradeHACmd.conf_dir+ "ha_key"

        if args.iso is None:
            community_iso = UpgradeHACmd.community_iso
        else:
            community_iso = args.iso

        mn_list = get_ha_mn_list(UpgradeHACmd.conf_file)
        host1_ip = mn_list[0]
        host2_ip = mn_list[1]
        if len(mn_list) > 2:
            host3_ip = mn_list[2]

        # init host1 parameter
        self.host1_post_info = HostPostInfo()
        self.host1_post_info.host = host1_ip
        self.host1_post_info.host_inventory = host_inventory
        self.host1_post_info.private_key = private_key_name
        self.host1_post_info.yum_repo = yum_repo
        self.host1_post_info.post_url = ""

        # init host2 parameter
        self.host2_post_info = HostPostInfo()
        self.host2_post_info.host = host2_ip
        self.host2_post_info.host_inventory = host_inventory
        self.host2_post_info.private_key = private_key_name
        self.host2_post_info.yum_repo = yum_repo
        self.host2_post_info.post_url = ""

        if len(mn_list) > 2:
            # init host3 parameter
            self.host3_post_info = HostPostInfo()
            self.host3_post_info.host = host3_ip
            self.host3_post_info.host_inventory = host_inventory
            self.host3_post_info.private_key = private_key_name
            self.host3_post_info.yum_repo = yum_repo
            self.host3_post_info.post_url = ""

        UpgradeHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info]
        if len(mn_list) > 2:
            UpgradeHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info, self.host3_post_info]

        for host in UpgradeHACmd.host_post_info_list:
            # to do check mn all running
            self.check_mn_running(host)

        for file in [args.mevoco_installer, community_iso]:
            self.check_file_exist(file, UpgradeHACmd.host_post_info_list)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to upgrade repo"
        spinner_info.name = "upgrade_repo"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['upgrade_repo'] = True
        ZstackSpinner(spinner_info)
        rand_dir_name = uuid.uuid4()
        tmp_iso =  "/tmp/%s/iso/" % rand_dir_name
        for host_post_info in UpgradeHACmd.host_post_info_list:
            self.upgrade_repo(community_iso, tmp_iso, host_post_info)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Stopping mevoco"
        spinner_info.name = "stop_mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['stop_mevoco'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in UpgradeHACmd.host_post_info_list:
            stop_mevoco(host_post_info)

        # backup db before upgrade
        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to backup database"
        spinner_info.name = "backup_db"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['backup_db'] = True
        ZstackSpinner(spinner_info)
        (status, output) =  commands.getstatusoutput("zstack-ctl dump_mysql >> /dev/null 2>&1")

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to upgrade mevoco"
        spinner_info.name = "upgrade_mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['upgrade_mevoco'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in UpgradeHACmd.host_post_info_list:
            self.upgrade_mevoco(args.mevoco_installer, host_post_info)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to upgrade database"
        spinner_info.name = "upgrade_db"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['upgrade_db'] = True
        ZstackSpinner(spinner_info)
        (status, output) =  commands.getstatusoutput("zstack-ctl upgrade_db")
        if status != 0:
            error("Upgrade mysql failed: %s" % output)
        else:
            logger.debug("SUCC: shell command: 'zstack-ctl upgrade_db' successfully" )

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting mevoco"
        spinner_info.name = "start_mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['start_mevoco'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in UpgradeHACmd.host_post_info_list:
            start_remote_mn(host_post_info)

        SpinnerInfo.spinner_status['start_mevoco'] = False
        time.sleep(.2)

        info(colored("\nUpgrade HA successfully!","blue"))


class AddManagementNodeCmd(Command):
    SpinnerInfo.spinner_status = {'check_init':False,'add_key':False,'deploy':False,'config':False,'start':False,'install_ui':False}
    install_pkgs = ['openssl']
    logger_dir = '/var/log/zstack/'
    logger_file = 'zstack-ctl.log'
    def __init__(self):
        super(AddManagementNodeCmd, self).__init__()
        self.name = "add_multi_management"
        self.description =  "add multi management node."
        ctl.register_command(self)
    def install_argparse_arguments(self, parser):
        parser.add_argument('--host-list','--hosts',nargs='+',
                            help="All hosts connect info follow below format, example: 'zstack-ctl add_multi_management --hosts root:passwd1@host1_ip root:passwd2@host2_ip ...' ",
                            required=True)
        parser.add_argument('--force-reinstall','-f',action="store_true", default=False)
        parser.add_argument('--ssh-key',
                            help="the path of private key for SSH login $host; if provided, Ansible will use the "
                                 "specified key as private key to SSH login the $host, default will use zstack private key",
                            default=None)

    def add_public_key_to_host(self, key_path, host_info):
        command ='timeout 10 sshpass -p %s ssh-copy-id -o UserKnownHostsFile=/dev/null -o PubkeyAuthentication=no' \
                 ' -o StrictHostKeyChecking=no -i %s root@%s' % (shell_quote(host_info.remote_pass), key_path, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("Copy public key '%s' to host: '%s' failed:\n %s" % (key_path, host_info.host,  output))

    def deploy_mn_on_host(self,args, host_info, key):
        if args.force_reinstall is True:
            command = 'zstack-ctl install_management_node --host=%s --ssh-key="%s" --force-reinstall' % (host_info.remote_user+':'+host_info.remote_pass+'@'+host_info.host, key)
        else:
            command = 'zstack-ctl install_management_node --host=%s --ssh-key="%s"' % (host_info.remote_user+':'+host_info.remote_pass+'@'+host_info.host, key)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("deploy mn on host %s failed:\n %s" % (host_info.host, output))

    def install_ui_on_host(self, key, host_info):
        command = 'zstack-ctl install_ui --host=%s --ssh-key=%s' % (host_info.host, key)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("deploy ui on host %s failed:\n %s" % (host_info.host, output))

    def config_mn_on_host(self, key, host_info):
        command = "mkdir -p `dirname %s`" % ctl.properties_file_path
        run_remote_command(command, host_info)
        command = "scp -i %s %s root@%s:%s" % (key, ctl.properties_file_path, host_info.host, ctl.properties_file_path)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("copy config to host %s failed:\n %s" % (host_info.host, output))
        command = "ssh -q -i %s -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s zstack-ctl configure " \
                  "management.server.ip=%s && zstack-ctl save_config" % (key, host_info.host, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("config management server %s failed:\n %s" % (host_info.host, output))

    def start_mn_on_host(self, host_info, key):
        command = "ssh -q -i %s -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s zstack-ctl " \
                  "start_node " % (key, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        command = "mkdir -p /usr/local/zstack/apache-tomcat/webapps/zstack/static/zstack-repo" \
                  "ln -s /opt/zstack-dvd/x86_64 /usr/local/zstack/apache-tomcat/webapps/zstack/static/zstack-repo/x86_64" \
                  "ln -s /opt/zstack-dvd/aarch64 /usr/local/zstack/apache-tomcat/webapps/zstack/static/zstack-repo/aarch64"
        run_remote_command(command, host_info, True, True)
        if status != 0:
            error("start node on host %s failed:\n %s" % (host_info.host, output))
        command = "ssh -q -i %s -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@%s zstack-ctl " \
                  "start_ui" % (key, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("start ui on host %s failed:\n %s" % (host_info.host, output))

    def install_packages(self, pkg_list, host_info):
        distro = platform.dist()[0]
        if distro in RPM_BASED_OS:
            for pkg in pkg_list:
                yum_install_package(pkg, host_info)
        elif distro in DEB_BASED_OS:
            apt_install_packages(pkg_list, host_info)

    def run(self, args):
        create_log(AddManagementNodeCmd.logger_dir, AddManagementNodeCmd.logger_file)
        host_info_list = []
        if args.ssh_key is None:
            args.ssh_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa.pub"
        private_key = args.ssh_key.split('.')[0]

        spinner_info = SpinnerInfo()
        spinner_info.output = "Checking system and init environment"
        spinner_info.name = 'check_init'
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['check_init'] = True
        ZstackSpinner(spinner_info)

        for host in args.host_list:
            inventory_file = ctl.zstack_home + "/../../../ansible/hosts"
            host_info = HostPostInfo()
            host_info.private_key = private_key
            host_info.host_inventory =  inventory_file
            (host_info.remote_user, host_info.remote_pass, host_info.host, host_info.remote_port) = check_host_info_format(host)
            check_host_password(host_info.remote_pass, host_info.host)
            command = "cat %s | grep %s || echo %s >> %s" % (inventory_file, host_info.host, host_info.host, inventory_file)
            (status, output) = commands.getstatusoutput(command)
            if status != 0 :
                error(output)
            host_info_list.append(host_info)
        for host_info in host_info_list:
            spinner_info = SpinnerInfo()
            spinner_info.output = "Add public key to host %s" % host_info.host
            spinner_info.name = 'add_key'
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
            SpinnerInfo.spinner_status['add_key'] = True
            ZstackSpinner(spinner_info)
            self.add_public_key_to_host(args.ssh_key, host_info)

            spinner_info = SpinnerInfo()
            spinner_info.output = "Deploy management node to host %s" % host_info.host
            spinner_info.name = 'deploy'
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
            SpinnerInfo.spinner_status['deploy'] = True
            ZstackSpinner(spinner_info)
            self.deploy_mn_on_host(args, host_info, private_key)
            self.install_packages(AddManagementNodeCmd.install_pkgs, host_info)

            spinner_info = SpinnerInfo()
            spinner_info.output = "Config management node on host %s" % host_info.host
            spinner_info.name = 'config'
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
            SpinnerInfo.spinner_status['config'] = True
            ZstackSpinner(spinner_info)
            self.config_mn_on_host(private_key, host_info)

            spinner_info = SpinnerInfo()
            spinner_info.output = "Install UI on host %s" % host_info.host
            spinner_info.name = 'install_ui'
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
            SpinnerInfo.spinner_status['install_ui'] = True
            ZstackSpinner(spinner_info)
            self.install_ui_on_host(private_key, host_info)

            spinner_info = SpinnerInfo()
            spinner_info.output = "Start management node on host %s" % host_info.host
            spinner_info.name = 'start'
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
            SpinnerInfo.spinner_status['start'] = True
            ZstackSpinner(spinner_info)
            self.start_mn_on_host(host_info,private_key)

        SpinnerInfo.spinner_status['start'] = False
        time.sleep(0.2)
        info(colored("\nAll management nodes add successfully",'blue'))

class RecoverHACmd(Command):
    '''This feature only support zstack offline image currently'''
    host_post_info_list = []
    current_dir = os.path.dirname(os.path.realpath(__file__))
    conf_dir = "/var/lib/zstack/ha/"
    conf_file = conf_dir + "ha.yaml"
    host_inventory = conf_dir + 'host'
    private_key = conf_dir + 'ha_key'
    logger_dir = "/var/log/zstack/"
    logger_file = "ha.log"
    bridge = ""
    SpinnerInfo.spinner_status = {'cluster':False, 'mysql':False,'mevoco':False, 'check_init':False, 'cluster':False}
    ha_config_content = None
    def __init__(self):
        super(RecoverHACmd, self).__init__()
        self.name = "recover_ha"
        self.description =  "Recover high availability environment for Mevoco."
        ctl.register_command(self)


    def stop_mysql_service(self, host_post_info):
        command = "service mysql stop"
        run_remote_command(command, host_post_info)
        mysqld_status = run_remote_command("netstat -ltnp | grep :4567[[:space:]]", host_post_info,
                                           return_status=True)
        if mysqld_status is True:
            run_remote_command("lsof -i tcp:4567 | awk 'NR!=1 {print $2}' | xargs kill -9", host_post_info)

    def reboot_cluster_service(self, host_post_info):
        service_status("haproxy", "state=started", host_post_info)
        service_status("keepalived", "state=started", host_post_info)

    def recover_mysql(self, host_post_info, host_post_info_list):
        for host_info in host_post_info_list:
            self.stop_mysql_service(host_info)
        command = "service mysql bootstrap"
        status, output = run_remote_command(command,host_post_info,True,True)
        if status is False:
            return False
        for host_info in host_post_info_list:
            if host_info.host != host_post_info.host:
                command = "service mysql start"
                status, output = run_remote_command(command,host_info,True,True)
                if status is False:
                    return False
        command = "service mysql restart"
        status, output = run_remote_command(command,host_post_info,True,True)
        return status

    def sync_prometheus(self, host_post_info):
        # sync prometheus data
        sync_arg = SyncArg()
        sync_arg.src = '/var/lib/zstack/prometheus/'
        sync_arg.dest = '/var/lib/zstack/prometheus/'
        sync(sync_arg, host_post_info)

    def run(self, args):
        create_log(UpgradeHACmd.logger_dir, UpgradeHACmd.logger_file)
        spinner_info = SpinnerInfo()
        spinner_info.output = "Checking system and init environment"
        spinner_info.name = 'check_init'
        SpinnerInfo.spinner_status['check_init'] = True
        ZstackSpinner(spinner_info)
        host3_exist = False
        if os.path.isfile(RecoverHACmd.conf_file) is not True:
            error("Didn't find HA config file %s, please use traditional 'zstack-ctl install_ha' to recover your cluster" % RecoverHACmd.conf_file)

        if os.path.exists(RecoverHACmd.conf_file):
            with open(RecoverHACmd.conf_file, 'r') as f:
                RecoverHACmd.ha_config_content = yaml.load(f)

        if RecoverHACmd.ha_config_content['host_list'] is None:
            error("Didn't find host_list in config file %s" % RecoverHACmd.conf_file)

        host_list = RecoverHACmd.ha_config_content['host_list'].split(',')
        if len(host_list) == 2:
            host1_ip = host_list[0]
            host2_ip = host_list[1]
        if len(host_list) == 3:
            host3_exist = True
            host3_ip = host_list[2]

        if os.path.exists(RecoverHACmd.conf_file) and RecoverHACmd.ha_config_content is not None :
            if "bridge_name" in RecoverHACmd.ha_config_content:
                RecoverHACmd.bridge = RecoverHACmd.ha_config_content['bridge_name']
            else:
                error("Didn't find 'bridge_name' in config file %s" % RecoverHACmd.conf_file)

        local_ip = get_ip_by_interface(RecoverHACmd.bridge)
        host_post_info_list = []

        # init host1 parameter
        host1_post_info = HostPostInfo()
        host1_post_info.host = host1_ip
        host1_post_info.host_inventory = RecoverHACmd.host_inventory
        host1_post_info.private_key = RecoverHACmd.private_key
        host_post_info_list.append(host1_post_info)

        host2_post_info = HostPostInfo()
        host2_post_info.host = host2_ip
        host2_post_info.host_inventory = RecoverHACmd.host_inventory
        host2_post_info.private_key = RecoverHACmd.private_key
        host_post_info_list.append(host2_post_info)

        if host3_exist is True:
            host3_post_info = HostPostInfo()
            host3_post_info.host = host3_ip
            host3_post_info.host_inventory = RecoverHACmd.host_inventory
            host3_post_info.private_key = RecoverHACmd.private_key
            host_post_info_list.append(host3_post_info)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to recovery mysql"
        spinner_info.name = "mysql"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
        SpinnerInfo.spinner_status['mysql'] = True
        ZstackSpinner(spinner_info)
        mysql_recover_status = False
        for host_post_info in host_post_info_list:
            recover_status = self.recover_mysql(host_post_info, host_post_info_list)
            if recover_status is True:
                mysql_recover_status = True
                break
        if mysql_recover_status is False:
            error("Recover mysql failed! Please check log /var/log/zstack/ha.log")

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to recovery cluster"
        spinner_info.name = "cluster"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
        SpinnerInfo.spinner_status['cluster'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in host_post_info_list:
            self.reboot_cluster_service(host_post_info)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to sync monitor data"
        spinner_info.name = "prometheus"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
        SpinnerInfo.spinner_status['prometheus'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in host_post_info_list:
            if host_post_info.host != local_ip:
                self.sync_prometheus(host_post_info)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting Mevoco"
        spinner_info.name = "mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
        SpinnerInfo.spinner_status['mevoco'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in host_post_info_list:
            start_remote_mn(host_post_info)

        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
        time.sleep(.3)
        info(colored("The cluster has been recovered successfully!", "blue"))


class InstallHACmd(Command):
    '''This feature only support zstack offline image currently'''
    host_post_info_list = []
    current_dir = os.path.dirname(os.path.realpath(__file__))
    conf_dir = "/var/lib/zstack/ha/"
    conf_file = conf_dir + "ha.yaml"
    logger_dir = "/var/log/zstack/"
    logger_file = "ha.log"
    bridge = ""
    SpinnerInfo.spinner_status = {'mysql':False,'haproxy_keepalived':False,
                      'Mevoco':False, 'stop_mevoco':False, 'check_init':False, 'recovery_cluster':False}
    ha_config_content = None
    def __init__(self):
        super(InstallHACmd, self).__init__()
        self.name = "install_ha"
        self.description =  "install high availability environment for Mevoco."
        self.sensitive_args = ['--mysql-root-password', '--root-pass', '--mysql-user-password', '--user-pass']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host1-info','--h1',
                            help="The first host connect info follow below format: 'root:password@ip_address' ",
                            required=True)
        parser.add_argument('--host2-info','--h2',
                            help="The second host connect info follow below format: 'root:password@ip_address' ",
                            required=True)
        parser.add_argument('--host3-info','--h3',
                            help="The third host connect info follow below format: 'root:password@ip_address' ",
                            default=False)
        parser.add_argument('--vip',
                            help="The virtual IP address for HA setup",
                            default=None)
        parser.add_argument('--gateway',
                            help="The gateway IP address for HA setup",
                            default=None)
        parser.add_argument('--bridge',
                            help="The bridge device name, default is br_eth0",
                            )
        parser.add_argument('--mysql-root-password','--root-pass',
                            help="Password of MySQL root user", default="zstack123")
        parser.add_argument('--mysql-user-password','--user-pass',
                            help="Password of MySQL user zstack", default="zstack123")
        parser.add_argument('--rabbit-password','--rabbit-pass',
                            help="obsoleted since 3.0.1",
                            default="zstack123")
        parser.add_argument('--drop', action='store_true', default=False,
                            help="Force delete mysql data for re-deploy HA")
        parser.add_argument('--keep-db', action='store_true', default=False,
                            help='keep existing zstack database and not raise error')
        parser.add_argument('--recovery-from-this-host','--recover',
                            action='store_true', default=False,
                            help="This argument for admin to recovery mysql from the last shutdown mysql server")
        parser.add_argument('--perfect-mode', action='store_true', default=False,
                            help="This mode will re-connect mysql faster")


    def get_formatted_netmask(self, device_name):
        '''This function will return formatted netmask. eg. 172.20.12.16/24 will return 24'''
        netmask = socket.inet_ntoa(fcntl.ioctl(socket.socket(socket.AF_INET, socket.SOCK_DGRAM),
                                                    35099, struct.pack('256s', device_name))[20:24])
        formatted_netmask = sum([bin(int(x)).count('1') for x in netmask.split('.')])
        return formatted_netmask


    def run(self, args):
        spinner_info = SpinnerInfo()
        spinner_info.output = "Checking system and init environment"
        spinner_info.name = 'check_init'
        SpinnerInfo.spinner_status['check_init'] = True
        ZstackSpinner(spinner_info)
        if args.bridge is None:
            InstallHACmd.bridge = 'br_eth0'
        else:
            InstallHACmd.bridge = args.bridge
        if os.path.exists(InstallHACmd.conf_file):
            with open(InstallHACmd.conf_file, 'r') as f:
                InstallHACmd.ha_config_content = yaml.load(f)

        if args.vip is None and args.recovery_from_this_host is False:
            error("Install HA must assign a vip")

        # check gw ip is available
        if args.gateway is None:
            if get_default_gateway_ip() is None:
                error("Can't get the gateway IP address from system, please check your route table or pass specific " \
                      "gateway through \"--gateway\" argument")
            else:
                gateway_ip = get_default_gateway_ip()
        else:
            gateway_ip = args.gateway
        (status, output) = commands.getstatusoutput('ping -c 1 %s' % gateway_ip)
        if status != 0:
            error("The gateway %s unreachable!" % gateway_ip)
        # check input host info
        host1_info = args.host1_info
        host1_connect_info_list = check_host_info_format(host1_info)
        args.host1 = host1_connect_info_list[2]
        args.host1_password = host1_connect_info_list[1]
        host2_info = args.host2_info
        host2_connect_info_list = check_host_info_format(host2_info)
        args.host2 = host2_connect_info_list[2]
        args.host2_password = host2_connect_info_list[1]
        if args.host3_info is not False:
            host3_info = args.host3_info
            host3_connect_info_list = check_host_info_format(host3_info)
            args.host3 = host3_connect_info_list[2]
            args.host3_password = host3_connect_info_list[1]

        # check root password is available
        if args.host1_password != args.host2_password:
            error("Host1 password and Host2 password must be the same, Please change one of them!")
        elif args.host3_info is not False:
            if not args.host1_password == args.host2_password == args.host3_password:
                error("All hosts root password must be the same. Please check your host password!")
        check_host_password(args.host1_password, args.host1)
        check_host_password(args.host2_password, args.host2)
        if args.host3_info is not False:
            check_host_password(args.host3_password, args.host3)

        # check image type
        zstack_local_repo = os.path.isfile("/etc/yum.repos.d/zstack-local.repo")
        galera_repo = os.path.isfile("/etc/yum.repos.d/galera.repo")
        if zstack_local_repo is False or galera_repo is False:
            error("This feature only support ZStack community CentOS 7 image")

        # check network configuration
        interface_list = os.listdir('/sys/class/net/')
        if InstallHACmd.bridge not in interface_list and args.recovery_from_this_host is False:
            error("Make sure you have already run the 'zs-network-setting' to setup the network environment, or set the"
                  " bridge name with --bridge, default bridge name is br_eth0 ")
        if InstallHACmd.bridge.split('br_')[1] not in interface_list:
            error("bridge %s should add the interface %s, make sure you have setup the interface or specify the right"
                  " bridge name" % (InstallHACmd.bridge, InstallHACmd.bridge.split('br_')[1]))

        # check keepalived label should not longer than 15 characters
        if len(InstallHACmd.bridge) >= 13:
            error("bridge name length cannot be longer than 13 characters")

        # check user start this command on host1
        if args.recovery_from_this_host is False:
            local_ip = get_ip_by_interface(InstallHACmd.bridge)
            if args.host1 != local_ip:
                error("Please run this command at host1 %s, or change your host1 ip to local host ip" % args.host1)

        # check user input wrong host2 ip
        if args.host2 == args.host1:
            error("The host1 and host2 should not be the same ip address!")
        elif args.host3_info is not False:
            if args.host2 == args.host3 or args.host1 == args.host3:
                error("The host1, host2 and host3 should not be the same ip address!")

        # create log
        create_log(InstallHACmd.logger_dir, InstallHACmd.logger_file)
        # create config
        if not os.path.exists(InstallHACmd.conf_dir):
            os.makedirs(InstallHACmd.conf_dir)
        yum_repo = get_yum_repo_from_property()
        private_key_name = InstallHACmd.conf_dir+ "ha_key"
        public_key_name = InstallHACmd.conf_dir+ "ha_key.pub"
        if os.path.isfile(public_key_name) is not True:
            command = "echo -e  'y\n'|ssh-keygen -q -t rsa -N \"\" -f %s" % private_key_name
            (status, output) = commands.getstatusoutput(command)
            if status != 0:
                error("Generate private key %s failed! Generate manually or rerun the process!" % private_key_name)
        with open(public_key_name) as public_key_file:
            public_key = public_key_file.read()

        # create inventory file
        with  open('%s/host' % InstallHACmd.conf_dir,'w') as f:
            f.writelines([args.host1+'\n', args.host2+'\n'])
        if args.host3_info is not False:
            with  open('%s/host' % InstallHACmd.conf_dir,'w') as f:
                f.writelines([args.host1+'\n', args.host2+'\n', args.host3+'\n'])

        #host_inventory = '%s,%s' % (args.host1, args.host2)
        host_inventory = InstallHACmd.conf_dir + 'host'

        # init host1 parameter
        self.host1_post_info = HostPostInfo()
        self.host1_post_info.host = args.host1
        self.host1_post_info.host_inventory = host_inventory
        self.host1_post_info.private_key = private_key_name
        self.host1_post_info.yum_repo = yum_repo
        self.host1_post_info.vip = args.vip
        self.host1_post_info.gateway_ip = gateway_ip
        self.host1_post_info.rabbit_password = args.rabbit_password
        self.host1_post_info.mysql_password = args.mysql_root_password
        self.host1_post_info.mysql_userpassword = args.mysql_user_password
        self.host1_post_info.post_url = ""
        self.host_post_info_list.append(self.host1_post_info)

        # init host2 parameter
        self.host2_post_info = HostPostInfo()
        self.host2_post_info.host = args.host2
        self.host2_post_info.host_inventory = host_inventory
        self.host2_post_info.private_key = private_key_name
        self.host2_post_info.yum_repo = yum_repo
        self.host2_post_info.vip = args.vip
        self.host2_post_info.gateway_ip = gateway_ip
        self.host2_post_info.rabbit_password = args.rabbit_password
        self.host2_post_info.mysql_password = args.mysql_root_password
        self.host2_post_info.mysql_userpassword = args.mysql_user_password
        self.host2_post_info.post_url = ""
        self.host_post_info_list.append(self.host2_post_info)

        if args.host3_info is not False:
            # init host3 parameter
            self.host3_post_info = HostPostInfo()
            self.host3_post_info.host = args.host3
            self.host3_post_info.host_inventory = host_inventory
            self.host3_post_info.private_key = private_key_name
            self.host3_post_info.yum_repo = yum_repo
            self.host3_post_info.vip = args.vip
            self.host3_post_info.gateway_ip = gateway_ip
            self.host3_post_info.rabbit_password = args.rabbit_password
            self.host3_post_info.mysql_password = args.mysql_root_password
            self.host3_post_info.mysql_userpassword = args.mysql_user_password
            self.host3_post_info.post_url = ""
            self.host_post_info_list.append(self.host3_post_info)


        # init all variables in map
        local_map = {
            "mysql_connect_timeout" : 60000,
            "mysql_socket_timeout" : 60000
        }
        if args.perfect_mode is True:
            local_map['mysql_connect_timeout'] = 2000
            local_map['mysql_socket_timeout'] = 2000

        add_public_key_command = 'if [ ! -d ~/.ssh ]; then mkdir -p ~/.ssh; chmod 700 ~/.ssh; fi && if [ ! -f ~/.ssh/authorized_keys ]; ' \
                                      'then touch ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; fi && pub_key="%s";grep ' \
                                      '"%s" ~/.ssh/authorized_keys > /dev/null; if [ $? -eq 1 ]; ' \
                                      'then echo "%s" >> ~/.ssh/authorized_keys; fi  && exit 0;'\
                                      % (public_key.strip('\n'), public_key.strip('\n'), public_key.strip('\n'))

        # add ha public key to host1
        ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                  "PubkeyAuthentication=no -o StrictHostKeyChecking=no root@%s '%s'" % \
                                  (shell_quote(args.host1_password), args.host1, add_public_key_command)
        (status, output) = commands.getstatusoutput(ssh_add_public_key_command)
        if status != 0:
            error(output)

        # add ha public key to host2
        ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                  "PubkeyAuthentication=no -o StrictHostKeyChecking=no root@%s '%s' " % \
                                  (shell_quote(args.host2_password), args.host2, add_public_key_command)
        (status, output) = commands.getstatusoutput(ssh_add_public_key_command)
        if status != 0:
            error(output)

        # add ha public key to host3
        if args.host3_info is not False:
            ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                              "PubkeyAuthentication=no -o StrictHostKeyChecking=no root@%s '%s' " % \
                                              (shell_quote(args.host3_password), args.host3, add_public_key_command)
            (status, output) = commands.getstatusoutput(ssh_add_public_key_command)
            if status != 0:
                error(output)


        # sync ansible key in two host
        copy_arg = CopyArg()
        copy_arg.src = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/"
        copy_arg.dest = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/"
        copy(copy_arg,self.host2_post_info)
        command = "chmod 600 %s" % copy_arg.src + "id_rsa"
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            copy(copy_arg,self.host3_post_info)
            run_remote_command(command, self.host3_post_info)

        # check whether to recovery the HA cluster
        if args.recovery_from_this_host is True:
            if os.path.exists(InstallHACmd.conf_file) and InstallHACmd.ha_config_content is not None and args.bridge is None:
                if "bridge_name" in InstallHACmd.ha_config_content:
                    InstallHACmd.bridge = InstallHACmd.ha_config_content['bridge_name']

            local_ip = get_ip_by_interface(InstallHACmd.bridge)
            if local_ip != args.host1 and local_ip != args.host2:
                if args.host3_info is not False:
                    if local_ip != args.host3:
                        error("Make sure you are running the 'zs-network-setting' command on host1 or host2 or host3")
                else:
                    error("Make sure you are running the 'zs-network-setting' command on host1 or host2")

            # stop mevoco
            spinner_info = SpinnerInfo()
            spinner_info.output = "Stop Mevoco on all management nodes"
            spinner_info.name = "stop_mevoco"
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
            SpinnerInfo.spinner_status['stop_mevoco'] = True
            ZstackSpinner(spinner_info)
            for host_info in self.host_post_info_list:
                stop_mevoco(host_info)

            spinner_info = SpinnerInfo()
            spinner_info.output = "Starting to recovery mysql from this host"
            spinner_info.name = "recovery_cluster"
            SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
            SpinnerInfo.spinner_status['recovery_cluster'] = True
            ZstackSpinner(spinner_info)
            # kill mysql process to make sure mysql bootstrap can work
            service_status("mysql", "state=stopped", self.host1_post_info)
            mysqld_status = run_remote_command("netstat -ltnp | grep :4567[[:space:]]", self.host1_post_info, return_status=True)
            if mysqld_status is True:
                run_remote_command("lsof -i tcp:4567 | awk 'NR!=1 {print $2}' | xargs kill -9", self.host1_post_info)

            service_status("mysql", "state=stopped", self.host2_post_info)
            mysqld_status = run_remote_command("netstat -ltnp | grep :4567[[:space:]] ", self.host2_post_info, return_status=True)
            if mysqld_status is True:
                run_remote_command("lsof -i tcp:4567 | awk 'NR!=1 {print $2}' | xargs kill -9", self.host2_post_info)

            if args.host3_info is not False:
                service_status("mysql", "state=stopped", self.host3_post_info)
                mysqld_status = run_remote_command("netstat -ltnp | grep :4567[[:space:]]", self.host3_post_info, return_status=True)
                if mysqld_status is True:
                    run_remote_command("lsof -i tcp:4567 | awk 'NR!=1 {print $2}' | xargs kill -9", self.host3_post_info)

            command = "service mysql bootstrap"
            (status, output) = commands.getstatusoutput(command)
            if status != 0:
                error(output)
            else:
                #command = "service mysql start"
                if local_ip == self.host1_post_info.host:
                    # make sure vip will be on this host, so start haproxy firstly
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    #run_remote_command(command, self.host2_post_info)
                    service_status("mysql","state=started", self.host2_post_info)
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    if args.host3_info is not False:
                        #run_remote_command(command, self.host3_post_info)
                        service_status("mysql","state=started", self.host3_post_info)
                        service_status("haproxy","state=started", self.host3_post_info)
                        service_status("keepalived","state=started", self.host3_post_info)
                    #command = "service mysql restart"
                    #run_remote_command(command, self.host1_post_info)
                    service_status("mysql","state=restarted", self.host1_post_info)

                elif local_ip == self.host2_post_info.host:
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    #run_remote_command(command, self.host1_post_info)
                    service_status("mysql","state=started", self.host1_post_info)
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    if args.host3_info is not False:
                        #run_remote_command(command, self.host3_post_info)
                        service_status("mysql","state=started", self.host3_post_info)
                        service_status("haproxy","state=started", self.host3_post_info)
                        service_status("keepalived","state=started", self.host3_post_info)
                    #command = "service mysql restart"
                    #run_remote_command(command, self.host2_post_info)
                    service_status("mysql","state=restarted", self.host2_post_info)
                else:
                    # localhost must be host3
                    service_status("haproxy","state=started", self.host3_post_info)
                    service_status("keepalived","state=started", self.host3_post_info)
                    #run_remote_command(command, self.host1_post_info)
                    service_status("mysql","state=started", self.host1_post_info)
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    service_status("mysql","state=started", self.host2_post_info)
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    #command = "service mysql restart"
                    #run_remote_command(command, self.host2_post_info)
                    service_status("mysql","state=restarted", self.host3_post_info)
                # sync prometheus data
                sync_arg = SyncArg()
                sync_arg.src = '/var/lib/zstack/prometheus/'
                sync_arg.dest = '/var/lib/zstack/prometheus/'
                sync(sync_arg, self.host2_post_info)
                if args.host3_info is not False:
                    sync(sync_arg, self.host3_post_info)

                # start mevoco
                spinner_info.output = "Starting Mevoco"
                spinner_info.name = "mevoco"
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['mevoco'] = True
                ZstackSpinner(spinner_info)

                for host_info in self.host_post_info_list:
                    start_mevoco(host_info)

                SpinnerInfo.spinner_status['mevoco'] = False
                time.sleep(.2)
            info("The cluster has been recovered!")
            sys.exit(0)

        # generate ha config
        host_list = "%s,%s" % (self.host1_post_info.host, self.host2_post_info.host)
        if args.host3_info is not False:
            host_list = "%s,%s,%s" % (self.host1_post_info.host, self.host2_post_info.host, self.host3_post_info.host)
        ha_conf_file = open(InstallHACmd.conf_file, 'w')
        ha_info = {'vip':args.vip, 'gateway':self.host1_post_info.gateway_ip, 'bridge_name':InstallHACmd.bridge,
                   'mevoco_url':'http://' + args.vip + ':8888', 'cluster_url':'http://'+ args.vip +':9132/zstack', 'host_list':host_list}
        yaml.dump(ha_info, ha_conf_file, default_flow_style=False)

        command = "mkdir -p %s" % InstallHACmd.conf_dir
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)

        copy_arg = CopyArg()
        copy_arg.src = InstallHACmd.conf_dir
        copy_arg.dest = InstallHACmd.conf_dir
        copy(copy_arg,self.host2_post_info)
        command = "chmod 600 %s" % InstallHACmd.conf_dir + "ha_key"
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(copy_arg,self.host3_post_info)
            run_remote_command(command, self.host3_post_info)

        # get iptables from system config
        service_status("iptables","state=restarted",self.host1_post_info)
        service_status("iptables","state=restarted",self.host2_post_info)
        if args.host3_info is not False:
            service_status("iptables","state=restarted",self.host3_post_info)
        # remove mariadb for avoiding conflict with mevoco install process
        command = "rpm -q mariadb | grep 'not installed' || yum remove -y mariadb"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(command, self.host3_post_info)

        command = "hostnamectl set-hostname zstack-1"
        run_remote_command(command, self.host1_post_info)
        command = "hostnamectl set-hostname zstack-2"
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            command = "hostnamectl set-hostname zstack-3"
            run_remote_command(command, self.host3_post_info)

        # remove old zstack-1 and zstack-2 in hosts file
        update_file("/etc/hosts", "regexp='\.*zstack\.*' state=absent", self.host1_post_info)
        update_file("/etc/hosts", "regexp='\.*zstack\.*' state=absent", self.host2_post_info)
        update_file("/etc/hosts", "line='%s zstack-1'" % args.host1, self.host1_post_info)
        update_file("/etc/hosts", "line='%s zstack-2'" % args.host2, self.host1_post_info)
        if args.host3_info is not False:
            update_file("/etc/hosts", "line='%s zstack-3'" % args.host3, self.host1_post_info)
        update_file("/etc/hosts", "line='%s zstack-1'" % args.host1, self.host2_post_info)
        update_file("/etc/hosts", "line='%s zstack-2'" % args.host2, self.host2_post_info)
        if args.host3_info is not False:
            update_file("/etc/hosts", "line='%s zstack-3'" % args.host3, self.host2_post_info)
        if args.host3_info is not False:
            update_file("/etc/hosts", "line='%s zstack-1'" % args.host1, self.host3_post_info)
            update_file("/etc/hosts", "line='%s zstack-2'" % args.host2, self.host3_post_info)
            update_file("/etc/hosts", "line='%s zstack-3'" % args.host3, self.host3_post_info)

        #save iptables at last
        command = " iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -s %s/32 -j ACCEPT" % (self.host2_post_info.host, self.host2_post_info.host)
        run_remote_command(command, self.host1_post_info)
        if args.host3_info is not False:
            command = " iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -s %s/32 -j ACCEPT" % (self.host3_post_info.host, self.host3_post_info.host)
            run_remote_command(command, self.host1_post_info)
        command = " iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -s %s/32 -j ACCEPT" % (self.host1_post_info.host, self.host1_post_info.host)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            command = " iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -s %s/32 -j ACCEPT" % (self.host3_post_info.host, self.host3_post_info.host)
            run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            command = " iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -s %s/32 -j ACCEPT" % (self.host1_post_info.host, self.host1_post_info.host)
            run_remote_command(command, self.host3_post_info)
            command = " iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 || iptables -I INPUT -s %s/32 -j ACCEPT" % (self.host2_post_info.host, self.host2_post_info.host)
            run_remote_command(command, self.host3_post_info)

        # stop haproxy and keepalived service for avoiding terminal status  disturb
        command = "service keepalived stop && service haproxy stop || echo True"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(command, self.host3_post_info)

        #pass all the variables to other HA deploy process
        InstallHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info]
        if args.host3_info is not False:
            InstallHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info, self.host3_post_info]
        # setup mysql ha
        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to deploy Mysql HA"
        spinner_info.name = 'mysql'
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['mysql'] = True
        ZstackSpinner(spinner_info)
        MysqlHA()()

        # setup haproxy and keepalived
        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to deploy Haproxy and Keepalived"
        spinner_info.name = 'haproxy_keepalived'
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['haproxy_keepalived'] = True
        ZstackSpinner(spinner_info)
        HaproxyKeepalived()()

        #install database on local management node
        command = "zstack-ctl stop"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(command, self.host3_post_info)
        if args.keep_db is True:
            command = "zstack-ctl deploydb --keep-db --host=%s --port=3306 --zstack-password=%s --root-password=%s" \
                           % (args.host1, args.mysql_user_password, args.mysql_root_password)
            run_remote_command(command, self.host1_post_info)
        elif args.drop is True:
            command = "zstack-ctl deploydb --drop --host=%s --port=3306 --zstack-password=%s --root-password=%s" \
                           % (args.host1, args.mysql_user_password, args.mysql_root_password)
            run_remote_command(command, self.host1_post_info)
        else:
            command = "zstack-ctl deploydb --host=%s --port=3306 --zstack-password=%s --root-password=%s" \
                           % (args.host1, args.mysql_user_password, args.mysql_root_password)
            run_remote_command(command, self.host1_post_info)

        command = "zstack-ctl configure DB.url=jdbc:mysql://%s:53306/{database}?connectTimeout=%d\&socketTimeout=%d"\
                       % (args.vip, local_map['mysql_connect_timeout'], local_map['mysql_socket_timeout'])
        run_remote_command(command, self.host1_post_info)

        # copy zstack-1 property to zstack-2 and update the management.server.ip
        # update zstack-1 firstly
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.serverIp\.0' line='CloudBus.serverIp.0=%s'" % args.vip, self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.serverIp\.1' state=absent" , self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='management\.server\.ip' line='management.server.ip = %s'" %
                    args.host1, self.host1_post_info)
        copy_arg = CopyArg()
        copy_arg.src = ctl.properties_file_path
        copy_arg.dest = ctl.properties_file_path
        copy(copy_arg, self.host2_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='management\.server\.ip' line='management.server.ip = %s'"
                    % args.host2, self.host2_post_info)
        if args.host3_info is not False:
            copy(copy_arg, self.host3_post_info)
            update_file("%s" % ctl.properties_file_path,
                        "regexp='management\.server\.ip' line='management.server.ip = %s'"
                        % args.host3, self.host3_post_info)

        #finally, start zstack-1 and zstack-2
        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting Mevoco"
        spinner_info.name = "mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['mevoco'] = True
        ZstackSpinner(spinner_info)
        # Add zstack-ctl start to rc.local for auto recovery when system reboot
        command = "service iptables save"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(command, self.host3_post_info)
        command = "zstack-ctl install_ui"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(command, self.host3_post_info)
        command = "zstack-ctl start"
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                                             (private_key_name, args.host1, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (args.host1, output))
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                                             (private_key_name, args.host2, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (args.host2, output))
        if args.host3_info is not False:
            (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                                                 (private_key_name, args.host3, command))
            if status != 0:
                error("Something wrong on host: %s\n %s" % (args.host3, output))
        SpinnerInfo.spinner_status['mevoco'] = False
        time.sleep(0.2)

        #sync imagestore key
        copy_arg = CopyArg()
        copy_arg.src = ctl.zstack_home + "/../../../imagestore/bin/certs/"
        copy_arg.dest = ctl.zstack_home + "/../../../imagestore/bin/certs/"
        copy(copy_arg, self.host2_post_info)
        if args.host3_info is not False:
            copy(copy_arg, self.host2_post_info)

        print '''HA deploy finished!
Mysql user 'root' password: %s
Mysql user 'zstack' password: %s
Mevoco is running, visit %s in Chrome or Firefox with default user/password : %s
You can check the cluster status at %s with user/passwd : %s
       ''' % (args.mysql_root_password, args.mysql_user_password,
              colored('http://%s:8888' % args.vip, 'blue'), colored('admin/password', 'yellow'),
              colored('http://%s:9132/zstack' % args.vip, 'blue'), colored('zstack/zstack123', 'yellow'))

class HaproxyKeepalived(InstallHACmd):
    def __init__(self):
        super(HaproxyKeepalived, self).__init__()
        self.name = "haproxy and keepalived init"
        self.description = "haproxy and keepalived setup"
        self.host_post_info_list = InstallHACmd.host_post_info_list
        self.host1_post_info = self.host_post_info_list[0]
        self.host2_post_info = self.host_post_info_list[1]
        if len(self.host_post_info_list) == 3:
            self.host3_post_info = self.host_post_info_list[2]
        self.yum_repo = self.host1_post_info.yum_repo
        self.vip = self.host1_post_info.vip
        self.gateway = self.host1_post_info.gateway_ip

    def __call__(self):
        command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q haproxy keepalived"
                        " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                        "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % self.yum_repo
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        update_file("/etc/sysconfig/rsyslog","regexp='^SYSLOGD_OPTIONS=\"\"' line='SYSLOGD_OPTIONS=\"-r -m 0\"'", self.host1_post_info)
        update_file("/etc/sysconfig/rsyslog","regexp='^SYSLOGD_OPTIONS=\"\"' line='SYSLOGD_OPTIONS=\"-r -m 0\"'", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            update_file("/etc/sysconfig/rsyslog","regexp='^SYSLOGD_OPTIONS=\"\"' line='SYSLOGD_OPTIONS=\"-r -m 0\"'", self.host3_post_info)
        update_file("/etc/rsyslog.conf","line='$ModLoad imudp'", self.host1_post_info)
        update_file("/etc/rsyslog.conf","line='$UDPServerRun 514'", self.host1_post_info)
        update_file("/etc/rsyslog.conf","line='local2.*   /var/log/haproxy.log'", self.host1_post_info)
        update_file("/etc/rsyslog.conf","line='$ModLoad imudp'", self.host2_post_info)
        update_file("/etc/rsyslog.conf","line='$UDPServerRun 514'", self.host2_post_info)
        update_file("/etc/rsyslog.conf","line='local2.*   /var/log/haproxy.log'", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            update_file("/etc/rsyslog.conf","line='$ModLoad imudp'", self.host3_post_info)
            update_file("/etc/rsyslog.conf","line='$UDPServerRun 514'", self.host3_post_info)
            update_file("/etc/rsyslog.conf","line='local2.*   /var/log/haproxy.log'", self.host3_post_info)
        command = "touch /var/log/haproxy.log"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        file_operation("/var/log/haproxy.log","owner=haproxy group=haproxy", self.host1_post_info)
        file_operation("/var/log/haproxy.log","owner=haproxy group=haproxy", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            file_operation("/var/log/haproxy.log","owner=haproxy group=haproxy", self.host3_post_info)
        service_status("rsyslog","state=restarted enabled=yes", self.host1_post_info)
        service_status("rsyslog","state=restarted enabled=yes", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("rsyslog","state=restarted enabled=yes", self.host3_post_info)

        haproxy_raw_conf = '''
global

    log         127.0.0.1 local2 emerg alert crit err warning notice info debug

    chroot      /var/lib/haproxy
    pidfile     /var/run/haproxy.pid
    maxconn     4000
    user        haproxy
    group       haproxy
    daemon

    # turn on stats unix socket
    stats socket /var/lib/haproxy/stats

#---------------------------------------------------------------------
# common defaults that all the 'listen' and 'backend' sections will
# use if not designated in their block
#---------------------------------------------------------------------
defaults
    mode                    http
    log                     global
    option                  httplog
    option                  dontlognull
    option http-server-close
    option forwardfor       except 127.0.0.0/8
    option                  redispatch
    retries                 3
    timeout http-request    10s
    timeout queue           1m
    timeout connect         10s
    timeout client          1m
    timeout server          1m
    timeout http-keep-alive 1m
    timeout check           1m
    timeout tunnel          60m
    maxconn                 6000


listen  admin_stats 0.0.0.0:9132
    mode        http
    stats uri   /zstack
    stats realm     Global\ statistics
    stats auth  zstack:zstack123

listen  proxy-mysql 0.0.0.0:53306
    mode tcp
    option tcplog
    balance source
    option httpchk OPTIONS * HTTP/1.1\\r\\nHost:\ www
    server zstack-1 {{ host1 }}:3306 weight 10 check port 6033 inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:3306 backup weight 10 check port 6033 inter 3s rise 2 fall 2
    option tcpka

# dashboard not installed, so haproxy will report error
listen  proxy-ui 0.0.0.0:8888
    mode http
    option  http-server-close
    balance source
    server zstack-1 {{ host1 }}:5000 weight 10 check inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:5000 weight 10 check inter 3s rise 2 fall 2
    option  tcpka
        '''
        if len(self.host_post_info_list) == 3:
            haproxy_raw_conf = '''
global

    log         127.0.0.1 local2 emerg alert crit err warning notice info debug

    chroot      /var/lib/haproxy
    pidfile     /var/run/haproxy.pid
    maxconn     4000
    user        haproxy
    group       haproxy
    daemon

    # turn on stats unix socket
    stats socket /var/lib/haproxy/stats

#---------------------------------------------------------------------
# common defaults that all the 'listen' and 'backend' sections will
# use if not designated in their block
#---------------------------------------------------------------------
defaults
    mode                    http
    log                     global
    option                  httplog
    option                  dontlognull
    option http-server-close
    option forwardfor       except 127.0.0.0/8
    option                  redispatch
    retries                 3
    timeout http-request    10s
    timeout queue           1m
    timeout connect         10s
    timeout client          1m
    timeout server          1m
    timeout http-keep-alive 1m
    timeout check           1m
    timeout tunnel          60m
    maxconn                 6000


listen  admin_stats 0.0.0.0:9132
    mode        http
    stats uri   /zstack
    stats realm     Global\ statistics
    stats auth  zstack:zstack123

listen  proxy-mysql 0.0.0.0:53306
    mode tcp
    option tcplog
    balance source
    option httpchk OPTIONS * HTTP/1.1\\r\\nHost:\ www
    server zstack-1 {{ host1 }}:3306 weight 10 check port 6033 inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:3306 backup weight 10 check port 6033 inter 3s rise 2 fall 2
    server zstack-3 {{ host3 }}:3306 backup weight 10 check port 6033 inter 3s rise 2 fall 2
    option tcpka

# dashboard not installed, so haproxy will report error
listen  proxy-ui 0.0.0.0:8888
    mode http
    option  http-server-close
    balance source
    server zstack-1 {{ host1 }}:5000 weight 10 check inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:5000 weight 10 check inter 3s rise 2 fall 2
    server zstack-3 {{ host3 }}:5000 weight 10 check inter 3s rise 2 fall 2
    option  tcpka
        '''

        haproxy_conf_template = jinja2.Template(haproxy_raw_conf)
        haproxy_host1_conf = haproxy_conf_template.render({
            'host1' : self.host1_post_info.host,
            'host2' : self.host2_post_info.host
        })
        if len(self.host_post_info_list) == 3:
            haproxy_host1_conf = haproxy_conf_template.render({
                'host1' : self.host1_post_info.host,
                'host2' : self.host2_post_info.host,
                'host3' : self.host3_post_info.host
            })

        # The host1 and host2 and host3 use the same config file
        host1_config, haproxy_host1_conf_file = tempfile.mkstemp()
        f1 = os.fdopen(host1_config, 'w')
        f1.write(haproxy_host1_conf)
        f1.close()

        def cleanup_haproxy_config_file():
            os.remove(haproxy_host1_conf_file)
        self.install_cleanup_routine(cleanup_haproxy_config_file)

        copy_arg = CopyArg()
        copy_arg.src = haproxy_host1_conf_file
        copy_arg.dest = "/etc/haproxy/haproxy.cfg"
        copy(copy_arg,self.host1_post_info)
        copy(copy_arg,self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(copy_arg,self.host3_post_info)

        #config haproxy firewall
        command = "iptables -C INPUT -p tcp -m tcp --dport 53306 -j ACCEPT > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport 53306 -j ACCEPT; " \
                  "iptables -C INPUT -p tcp -m tcp --dport 58080 -j ACCEPT > /dev/null 2>&1  ||  iptables -I INPUT -p tcp -m tcp --dport 58080 -j ACCEPT ; " \
                  "iptables -C INPUT -p tcp -m tcp --dport 55672 -j ACCEPT > /dev/null 2>&1  ||  iptables -I INPUT -p tcp -m tcp --dport 55672 -j ACCEPT ; " \
                       "iptables -C INPUT -p tcp -m tcp --dport 80 -j ACCEPT > /dev/null 2>&1  || iptables -I INPUT -p tcp -m tcp --dport 80 -j ACCEPT ; " \
                       "iptables -C INPUT -p tcp -m tcp --dport 9132 -j ACCEPT > /dev/null 2>&1 ||  iptables -I INPUT -p tcp -m tcp --dport 9132 -j ACCEPT ; " \
                       "iptables -C INPUT -p tcp -m tcp --dport 8888 -j ACCEPT > /dev/null 2>&1 ||  iptables -I INPUT -p tcp -m tcp --dport 8888 -j ACCEPT ; " \
                       "iptables -C INPUT -p tcp -m tcp --dport 6033 -j ACCEPT > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport 6033 -j ACCEPT; service iptables save "
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)

        #config keepalived
        keepalived_raw_config = '''
! Configuration File for keepalived
global_defs {
   router_id HAPROXY_LOAD
}
vrrp_script Monitor_Haproxy {
 script "/usr/local/bin/keepalived-kill.sh"
 interval 2
 weight 5
}
vrrp_instance VI_1 {
    # use the same state with host2, so no master node, recovery will not race to control the vip
   state BACKUP
   interface {{ bridge }}
   virtual_router_id {{ vrouter_id }}
   priority {{ priority }}
   nopreempt
   advert_int 1
   authentication {
      auth_type PASS
      auth_pass {{ auth_passwd }}
   }
   track_script {
      Monitor_Haproxy
}
   virtual_ipaddress {
      {{ vip }}/{{ netmask }} label {{ bridge }}:0
 }
}
        '''

        virtual_router_id = random.randint(1, 255)
        auth_pass = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))
        master_priority = 92
        slave_priority = 91
        second_slave_priority = 90
        keepalived_template = jinja2.Template(keepalived_raw_config)
        keepalived_host1_config = keepalived_template.render({
            'bridge' : InstallHACmd.bridge,
            'vrouter_id': virtual_router_id,
            'priority': master_priority,
            'auth_passwd': auth_pass,
            'vip': self.vip,
            'netmask': self.get_formatted_netmask(InstallHACmd.bridge)
        })

        keepalived_host2_config = keepalived_template.render({
            'bridge' : InstallHACmd.bridge,
            'vrouter_id': virtual_router_id,
            'priority': slave_priority,
            'auth_passwd': auth_pass,
            'vip': self.vip,
            'netmask': self.get_formatted_netmask(InstallHACmd.bridge)
        })

        if len(self.host_post_info_list) == 3:
            keepalived_host3_config = keepalived_template.render({
                'vrouter_id': virtual_router_id,
                'priority': second_slave_priority,
                'auth_passwd': auth_pass,
                'vip': self.vip,
                'netmask': self.get_formatted_netmask(InstallHACmd.bridge)
            })

        host1_config, keepalived_host1_config_file = tempfile.mkstemp()
        f1 = os.fdopen(host1_config, 'w')
        f1.write(keepalived_host1_config)
        f1.close()
        host2_config, keepalived_host2_config_file = tempfile.mkstemp()
        f2 = os.fdopen(host1_config, 'w')
        f2.write(keepalived_host2_config)
        f2.close()
        if len(self.host_post_info_list) == 3:
            host3_config, keepalived_host3_config_file = tempfile.mkstemp()
            f3 = os.fdopen(host3_config, 'w')
            f3.write(keepalived_host3_config)
            f3.close()

        def cleanup_keepalived_config_file():
            os.remove(keepalived_host1_config_file)
            os.remove(keepalived_host2_config_file)
            if len(self.host_post_info_list) == 3:
                os.remove(keepalived_host3_config_file)
            self.install_cleanup_routine(cleanup_keepalived_config_file)

        copy_arg = CopyArg()
        copy_arg.src = keepalived_host1_config_file
        copy_arg.dest = "/etc/keepalived/keepalived.conf"
        copy(copy_arg, self.host1_post_info)
        copy_arg = CopyArg()
        copy_arg.src = keepalived_host2_config_file
        copy_arg.dest = "/etc/keepalived/keepalived.conf"
        copy(copy_arg, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy_arg = CopyArg()
            copy_arg.src = keepalived_host3_config_file
            copy_arg.dest = "/etc/keepalived/keepalived.conf"
            copy(copy_arg, self.host3_post_info)

        # copy keepalived-kill.sh to host
        copy_arg = CopyArg()
        copy_arg.src = "%s/conf/keepalived-kill.sh" % InstallHACmd.current_dir
        copy_arg.dest = "/usr/local/bin/keepalived-kill.sh"
        copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(copy_arg, self.host1_post_info)
        copy(copy_arg, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(copy_arg, self.host3_post_info)

        # restart haproxy and keepalived
        service_status("keepalived", "state=restarted enabled=yes", self.host1_post_info)
        service_status("keepalived", "state=restarted enabled=yes", self.host2_post_info)
        service_status("haproxy", "state=restarted enabled=yes", self.host1_post_info)
        service_status("haproxy", "state=restarted enabled=yes", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("keepalived", "state=restarted enabled=yes", self.host3_post_info)
            service_status("haproxy", "state=restarted enabled=yes", self.host3_post_info)


class MysqlHA(InstallHACmd):
    def __init__(self):
        super(MysqlHA, self).__init__()
        self.host_post_info_list = InstallHACmd.host_post_info_list
        self.host1_post_info = self.host_post_info_list[0]
        self.host2_post_info = self.host_post_info_list[1]
        if len(self.host_post_info_list) == 3:
            self.host3_post_info = self.host_post_info_list[2]
        self.yum_repo = self.host1_post_info.yum_repo
        self.mysql_password = self.host1_post_info.mysql_password

    def __call__(self):
        command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q MariaDB-Galera-server xinetd rsync openssl-libs "
                   " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                   "--disablerepo=* --enablerepo=%s,mariadb install -y $pkg; done;") % self.yum_repo
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        # Generate galera config file and copy to host1 host2
        galera_raw_config= '''[mysqld]
skip-name-resolve=1
character-set-server=utf8
binlog_format=ROW
default-storage-engine=innodb
innodb_autoinc_lock_mode=2
innodb_locks_unsafe_for_binlog=1
max_connections=2048
query_cache_size=0
query_cache_type=0
bind_address= {{ host1 }}
wsrep_provider=/usr/lib64/galera/libgalera_smm.so
wsrep_cluster_name="galera_cluster"
wsrep_cluster_address="gcomm://{{ host2 }},{{ host1 }}"
wsrep_slave_threads=1
wsrep_certify_nonPK=1
wsrep_max_ws_rows=131072
wsrep_max_ws_size=1073741824
wsrep_debug=0
wsrep_convert_LOCK_to_trx=0
wsrep_retry_autocommit=1
wsrep_auto_increment_control=1
wsrep_drupal_282555_workaround=0
wsrep_causal_reads=0
wsrep_notify_cmd=
wsrep_sst_method=rsync
'''
        if len(self.host_post_info_list) == 3:
        # Generate galera config file and copy to host1 host2 host3
            galera_raw_config= '''[mysqld]
skip-name-resolve=1
character-set-server=utf8
binlog_format=ROW
default-storage-engine=innodb
innodb_autoinc_lock_mode=2
innodb_locks_unsafe_for_binlog=1
max_connections=2048
query_cache_size=0
query_cache_type=0
bind_address= {{ host1 }}
wsrep_provider=/usr/lib64/galera/libgalera_smm.so
wsrep_cluster_name="galera_cluster"
wsrep_cluster_address="gcomm://{{ host3 }},{{ host2 }},{{ host1 }}"
wsrep_slave_threads=1
wsrep_certify_nonPK=1
wsrep_max_ws_rows=131072
wsrep_max_ws_size=1073741824
wsrep_debug=0
wsrep_convert_LOCK_to_trx=0
wsrep_retry_autocommit=1
wsrep_auto_increment_control=1
wsrep_drupal_282555_workaround=0
wsrep_causal_reads=0
wsrep_notify_cmd=
wsrep_sst_method=rsync
'''
        galera_config_template = jinja2.Template(galera_raw_config)

        galera_config_host1 = galera_config_template.render({
            'host1' : self.host1_post_info.host,
            'host2' : self.host2_post_info.host
        })
        if len(self.host_post_info_list) == 3:
            galera_config_host1 = galera_config_template.render({
                'host1' : self.host1_post_info.host,
                'host2' : self.host2_post_info.host,
                'host3' : self.host3_post_info.host
            })

        galera_config_host2 = galera_config_template.render({
            'host1' : self.host2_post_info.host,
            'host2' : self.host1_post_info.host
        })
        if len(self.host_post_info_list) == 3:
            galera_config_host2 = galera_config_template.render({
                'host1' : self.host2_post_info.host,
                'host2' : self.host3_post_info.host,
                'host3' : self.host1_post_info.host
            })

        if len(self.host_post_info_list) == 3:
            galera_config_host3 = galera_config_template.render({
                'host1' : self.host3_post_info.host,
                'host2' : self.host1_post_info.host,
                'host3' : self.host2_post_info.host
            })

        host1_config, galera_config_host1_file = tempfile.mkstemp()
        f1 = os.fdopen(host1_config, 'w')
        f1.write(galera_config_host1)
        f1.close()

        host2_config, galera_config_host2_file = tempfile.mkstemp()
        f2 = os.fdopen(host2_config, 'w')
        f2.write(galera_config_host2)
        f2.close()

        if len(self.host_post_info_list) == 3:
            host3_config, galera_config_host3_file = tempfile.mkstemp()
            f3 = os.fdopen(host3_config, 'w')
            f3.write(galera_config_host3)
            f3.close()

        def cleanup_galera_config_file():
            os.remove(galera_config_host1_file)
            os.remove(galera_config_host2_file)
            if len(self.host_post_info_list) == 3:
                os.remove(galera_config_host3_file)
        self.install_cleanup_routine(cleanup_galera_config_file)

        copy_arg = CopyArg()
        copy_arg.src = galera_config_host1_file
        copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
        copy(copy_arg, self.host1_post_info)
        copy_arg = CopyArg()
        copy_arg.src = galera_config_host2_file
        copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
        copy(copy_arg, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy_arg = CopyArg()
            copy_arg.src = galera_config_host3_file
            copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
            copy(copy_arg, self.host3_post_info)

        # restart mysql service to enable galera config
        command = "service mysql stop || true"
        #service_status("mysql", "state=stopped", self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        #last stop node should be the first node to do bootstrap
        run_remote_command(command, self.host1_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        command = "service mysql bootstrap"
        run_remote_command(command, self.host1_post_info)
        run_remote_command("service mysql start && chkconfig mysql on", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command("service mysql start && chkconfig mysql on", self.host3_post_info)
        run_remote_command("service mysql restart && chkconfig mysql on", self.host1_post_info)

        init_install = run_remote_command("mysql -u root --password='' -e 'exit' ", self.host1_post_info, return_status=True)
        if init_install is True:
            #command = "mysql -u root --password='' -Bse \"show status like 'wsrep_%%';\""
            #galera_status = run_remote_command(command, self.host2_post_info)
            #create zstack user
            command =" mysql -u root --password='' -Bse 'grant ALL PRIVILEGES on *.* to zstack@\"localhost\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES on *.* to zstack@\"zstack-1\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES on *.* to zstack@\"%%\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES on *.* to root@\"%%\" Identified by \"%s\";" \
                          "grant ALL PRIVILEGES on *.* to root@\"localhost\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES ON *.* TO root@\"%%\" IDENTIFIED BY \"%s\" WITH GRANT OPTION; " \
                          "flush privileges;'" % (self.host1_post_info.mysql_userpassword, self.host1_post_info.mysql_userpassword,
                                                 self.host1_post_info.mysql_userpassword,self.host1_post_info.mysql_password,
                                                 self.host1_post_info.mysql_password, self.host1_post_info.mysql_password)
            (status, output) = run_remote_command(command, self.host1_post_info, True, True)
            if status is False:
                time.sleep(5)
                (status, output) = run_remote_command(command, self.host1_post_info, True, True)
                if status is False:
                    error("Failed to set mysql 'zstack' and 'root' password, the reason is %s" % output)

        # config mysqlchk_status.sh on zstack-1 and zstack-2
        mysqlchk_raw_script = '''#!/bin/sh
MYSQL_HOST="{{ host1 }}"
MYSQL_PORT="3306"
MYSQL_USERNAME="{{ mysql_username }}"
MYSQL_PASSWORD="{{ mysql_password }}"
/usr/bin/mysql -h$MYSQL_HOST -u$MYSQL_USERNAME -p$MYSQL_PASSWORD -e "show databases;" > /dev/null
if [ "$?" -eq 0 ]
then
        # mysql is fine, return http 200
        /bin/echo -e "HTTP/1.1 200 OK"
        /bin/echo -e "Content-Type: Content-Type: text/plain"
        /bin/echo -e "MySQL is running."
else
        # mysql is fine, return http 503
        /bin/echo -e "HTTP/1.1 503 Service Unavailable"
        /bin/echo -e "Content-Type: Content-Type: text/plain"
        /bin/echo -e "MySQL is *down*."
fi
'''
        mysqlchk_template = jinja2.Template(mysqlchk_raw_script)
        mysqlchk_script_host1 = mysqlchk_template.render({
            'host1' : self.host1_post_info.host,
            'mysql_username' : "zstack",
            'mysql_password' : self.host1_post_info.mysql_userpassword
        })
        mysqlchk_script_host2 = mysqlchk_template.render({
            'host1' : self.host2_post_info.host,
            'mysql_username' : "zstack",
            'mysql_password' : self.host2_post_info.mysql_userpassword
        })
        if len(self.host_post_info_list) == 3:
            mysqlchk_script_host3 = mysqlchk_template.render({
                'host1' : self.host3_post_info.host,
                'mysql_username' : "zstack",
                'mysql_password' : self.host3_post_info.mysql_userpassword
            })


        host1_config, mysqlchk_script_host1_file = tempfile.mkstemp()
        f1 = os.fdopen(host1_config, 'w')
        f1.write(mysqlchk_script_host1)
        f1.close()

        host2_config, mysqlchk_script_host2_file = tempfile.mkstemp()
        f2 = os.fdopen(host2_config, 'w')
        f2.write(mysqlchk_script_host2)
        f2.close()

        if len(self.host_post_info_list) == 3:
            host3_config, mysqlchk_script_host3_file = tempfile.mkstemp()
            f3 = os.fdopen(host3_config, 'w')
            f3.write(mysqlchk_script_host3)
            f3.close()

        def cleanup_mysqlchk_script():
            os.remove(mysqlchk_script_host1_file)
            os.remove(mysqlchk_script_host2_file)
            if len(self.host_post_info_list) == 3:
                os.remove(mysqlchk_script_host3_file)
            self.install_cleanup_routine(cleanup_mysqlchk_script)

        copy_arg = CopyArg()
        copy_arg.src = mysqlchk_script_host1_file
        copy_arg.dest = "/usr/local/bin/mysqlchk_status.sh"
        copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(copy_arg,self.host1_post_info)

        copy_arg = CopyArg()
        copy_arg.src = mysqlchk_script_host2_file
        copy_arg.dest = "/usr/local/bin/mysqlchk_status.sh"
        copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(copy_arg,self.host2_post_info)

        if len(self.host_post_info_list) == 3:
            copy_arg = CopyArg()
            copy_arg.src = mysqlchk_script_host3_file
            copy_arg.dest = "/usr/local/bin/mysqlchk_status.sh"
            copy_arg.args = "mode='u+x,g+x,o+x'"
            copy(copy_arg,self.host3_post_info)

        # check network
        check_network_raw_script='''#!/bin/bash
MYSQL_HOST="{{ host }}"
MYSQL_PORT="3306"
MYSQL_USERNAME="root"
MYSQL_PASSWORD="{{ mysql_root_password }}"
# Checking partner ...
ping -c 4 -w 4 $1 > /dev/null 2>&1
if [ $? -ne 0 ]; then
    # Checking gateway ...
    ping -c 4 -w 4 $2 > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Network ERROR! Kill MySQL NOW!" >> /var/log/check-network.log
        pgrep -f mysql | xargs kill -9
    else
        echo "Setting the primary of Galera." >> /var/log/check-network.log
        /usr/bin/mysql -h$MYSQL_HOST -u$MYSQL_USERNAME -p$MYSQL_PASSWORD -e "SET GLOBAL wsrep_provider_options='pc.bootstrap=YES';" > /dev/null
    fi
fi
TIMEST=`date`
echo $TIMEST >> /var/log/check-network.log
        '''
        galera_check_network = jinja2.Template(check_network_raw_script)
        galera_check_network_host1 = galera_check_network.render({
            'host' : self.host1_post_info.host,
            'mysql_root_password' : self.host1_post_info.mysql_password
        })
        galera_check_network_host2 = galera_check_network.render({
            'host' : self.host2_post_info.host,
            'mysql_root_password' : self.host1_post_info.mysql_password
        })

        host1_config, galera_check_network_host1_file = tempfile.mkstemp()
        f1 = os.fdopen(host1_config, 'w')
        f1.write(galera_check_network_host1)
        f1.close()

        host2_config, galera_check_network_host2_file = tempfile.mkstemp()
        f2 = os.fdopen(host2_config, 'w')
        f2.write(galera_check_network_host2)
        f2.close()

        def cleanup_gelerachk_script():
            os.remove(galera_check_network_host1_file)
            os.remove(galera_check_network_host2_file)
            self.install_cleanup_routine(cleanup_gelerachk_script)

        copy_arg = CopyArg()
        copy_arg.src = galera_check_network_host1_file
        copy_arg.dest = "/usr/local/zstack/check-network.sh"
        copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(copy_arg,self.host1_post_info)

        copy_arg = CopyArg()
        copy_arg.src = galera_check_network_host2_file
        copy_arg.dest = "/usr/local/zstack/check-network.sh"
        copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(copy_arg,self.host2_post_info)

        # set cron task for network status
        cron("check_node_2_status1","job=\"/usr/local/zstack/check-network.sh %s %s\"" % (self.host2_post_info.host,
                                                                                         self.host2_post_info.gateway_ip),
                                                                                         self.host1_post_info)
        cron("check_node_2_status2","job=\"sleep 30;/usr/local/zstack/check-network.sh %s %s\"" % (self.host2_post_info.host,
                                                                                         self.host2_post_info.gateway_ip),
                                                                                         self.host1_post_info)
        cron("check_node_1_status1","job=\"/usr/local/zstack/check-network.sh %s %s\"" % (self.host1_post_info.host,
                                                                                         self.host1_post_info.gateway_ip),
                                                                                         self.host2_post_info)
        cron("check_node_1_status2","job=\"sleep 30;/usr/local/zstack/check-network.sh %s %s\"" % (self.host1_post_info.host,
                                                                                                 self.host1_post_info.gateway_ip),
                                                                                                 self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            cron("check_node_1_status1","job=\"/usr/local/zstack/check-network.sh %s %s\" state=absent" %
                 (self.host1_post_info.host, self.host1_post_info.gateway_ip), self.host2_post_info)
            cron("check_node_1_status2","job=\"sleep 30;/usr/local/zstack/check-network.sh %s %s\" state=absent" %
                 (self.host1_post_info.host, self.host1_post_info.gateway_ip), self.host2_post_info)
            cron("check_node_2_status1","job=\"/usr/local/zstack/check-network.sh %s %s\" state=absent" %
                 (self.host2_post_info.host, self.host2_post_info.gateway_ip), self.host1_post_info)
            cron("check_node_2_status2","job=\"sleep 30;/usr/local/zstack/check-network.sh %s %s\" state=absent" %
                 (self.host2_post_info.host, self.host2_post_info.gateway_ip), self.host1_post_info)

        #config xinetd for service check
        copy_arg = CopyArg()
        copy_arg.src = "%s/conf/mysql-check" % InstallHACmd.current_dir
        copy_arg.dest = "/etc/xinetd.d/mysql-check"
        copy(copy_arg,self.host1_post_info)
        copy(copy_arg,self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(copy_arg,self.host3_post_info)

        # add service name
        update_file("/etc/services", "line='mysqlcheck      6033/tcp     #MYSQL status check'", self.host1_post_info)
        update_file("/etc/services", "line='mysqlcheck      6033/tcp     #MYSQL status check'", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            update_file("/etc/services", "line='mysqlcheck      6033/tcp     #MYSQL status check'", self.host3_post_info)

        # start service
        command = "systemctl daemon-reload"
        run_remote_command(command,self.host1_post_info)
        run_remote_command(command,self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command,self.host3_post_info)
        service_status("xinetd","state=restarted enabled=yes",self.host1_post_info)
        service_status("xinetd","state=restarted enabled=yes",self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("xinetd","state=restarted enabled=yes",self.host3_post_info)

        # add crontab for backup mysql
        cron("backup_zstack_db","minute='0' hour='1,13' job='/usr/bin/zstack-ctl dump_mysql >>"
                                " /var/log/zstack/ha.log 2>&1' ", self.host1_post_info)
        cron("backup_zstack_db","minute='0' hour='7,19' job='/usr/bin/zstack-ctl dump_mysql >>"
                                " /var/log/zstack/ha.log 2>&1' ", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            cron("backup_zstack_db","minute='0' hour='1' job='/usr/bin/zstack-ctl dump_mysql >>"
                                    " /var/log/zstack/ha.log 2>&1' ", self.host1_post_info)
            cron("backup_zstack_db","minute='0' hour='9' job='/usr/bin/zstack-ctl dump_mysql >>"
                                " /var/log/zstack/ha.log 2>&1' ", self.host2_post_info)
            cron("backup_zstack_db","minute='0' hour='17' job='/usr/bin/zstack-ctl dump_mysql >>"
                                    " /var/log/zstack/ha.log 2>&1' ", self.host3_post_info)
        service_status("crond","state=started enabled=yes",self.host1_post_info)
        service_status("crond","state=started enabled=yes",self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("crond","state=started enabled=yes",self.host3_post_info)

class RabbitmqHA(InstallHACmd):
    def __init__(self):
        super(RabbitmqHA, self).__init__()
        self.name = "rabbitmq ha"
        self.description = "rabbitmq HA setup"
    def __call__(self):
        info("zstack no longer depend on rabbitmq, exit")

class ResetRabbitCmd(Command):
    def __init__(self):
        super(ResetRabbitCmd, self).__init__()
        self.name = "reset_rabbitmq"
        self.description = "Reset RabbitMQ message broker on local machine based on current configuration in zstack.properties."
        ctl.register_command(self)
    def run(self, args):
        info("zstack no longer depend on rabbitmq, exit")

class InstallRabbitCmd(Command):
    def __init__(self):
        super(InstallRabbitCmd, self).__init__()
        self.name = "install_rabbitmq"
        self.description = "install RabbitMQ message broker on local or remote machine."
        ctl.register_command(self)

    def run(self, args):
        info("zstack no longer depend on rabbitmq, exit")


class MysqlRestrictConnection(Command):
    def __init__(self):
        super(MysqlRestrictConnection, self).__init__()
        self.name = "mysql_restrict_connection"
        self.description = "set mysql restrict connection for account: root, zstack, zstack_ui"
        self.sensitive_args = ['--restrict', '--restore', '--root-password', '--include-root']
        self.file="%s/mysql_restrict_connection" % ctl.USER_ZSTACK_HOME_DIR
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--root-password', required=True,
                            help="Current mysql root password")
        parser.add_argument('--restrict', required=False, action="store_true",
                            help="Set mysql restrict connection")
        parser.add_argument('--restore', required=False, action="store_true",
                            help="Restore mysql restrict connection")
        parser.add_argument('--include-root', required=False, action="store_true",
                            help='Set mysql restrict connection including root account')

    def check_root_password(self, root_password, remote_ip=None):
        if remote_ip is not None:
            status, output = commands.getstatusoutput(
                "mysql -u root -p%s -h '%s' -e 'show databases;'" % (root_password, remote_ip))
        else:
            status, output = commands.getstatusoutput(
                "mysql -u root -p%s -e 'show databases;'" % root_password)

        if status != 0:
            error(output)


    def get_db_portal(self):
        db_host, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        if db_user != "zstack":
            error("DB.user in the zstack.properties is not set to zstack")

        return db_host, db_port, db_user, db_password

    def get_ui_db_portal(self):
        ui_db_host, ui_db_port, ui_db_user, ui_db_password = ctl.get_live_mysql_portal(ui=True)

        if ui_db_user != "zstack_ui":
            error("db_username in the zstack.ui.properties is not set to zstack_ui")

        return ui_db_host, ui_db_port, ui_db_user, ui_db_password

    def get_mn_ip(self):
        mn_ip = ctl.read_property('management.server.ip')
        if not mn_ip:
            error("management.server.ip not configured")
        if 0 != shell_return("ip a | grep 'inet ' | grep -w '%s'" % mn_ip):
            error("management.server.ip[%s] is not found on any device" % mn_ip)

        return mn_ip

    def grant_restrict_privilege(self, db_password, ui_db_password, root_password_, host, include_root):
        grant_access_cmd = " GRANT USAGE ON *.* TO 'zstack'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION;" % (host, db_password)
        grant_access_cmd = grant_access_cmd + (" GRANT USAGE ON *.* TO 'zstack_ui'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION;" % (host, ui_db_password))

        if include_root:
            grant_access_cmd = grant_access_cmd + (" GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION;" % (host, root_password_))

        return grant_access_cmd

    def grant_restore_privilege(self, db_password, ui_db_password, root_password_):
        grant_access_cmd = " DELETE FROM user WHERE Host != 'localhost' AND Host != '127.0.0.1' AND Host != '::1' AND Host != '%%';" \
               " GRANT USAGE ON *.* TO 'zstack'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION;" \
               " GRANT USAGE ON *.* TO 'zstack_ui'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION;" \
               " GRANT USAGE ON *.* TO 'root'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION;" % (db_password, ui_db_password, root_password_)
        return grant_access_cmd

    def delete_privilege(self, host, include_root):
        if include_root:
            grant_access_cmd = " DELETE FROM user WHERE Host='%s' and (User='zstack' or User = 'zstack_ui' or User = 'root');" % host
        else:
            grant_access_cmd = " DELETE FROM user WHERE Host='%s' and (User='zstack' or User = 'zstack_ui');" % host
        return grant_access_cmd

    def grant_views_definer_privilege(self, root_password, remote_ip=None):
        if remote_ip is not None:
            status, output = commands.getstatusoutput(
                "mysql -N -u root -p%s -h '%s' -e 'select definer from information_schema.VIEWS limit 1;'" % (root_password, remote_ip))
        else:
            status, output = commands.getstatusoutput(
                "mysql -N -u root -p%s -e 'select definer from information_schema.VIEWS limit 1;'" % root_password)

        if status != 0:
            error("failed to get mysql views definer: %s" % output)

        if output is not None and output.strip() != "":
            user, host = output.split("@")
            return  "USE mysql;  GRANT USAGE ON *.* TO '%s'@%s IDENTIFIED BY '%s' WITH GRANT OPTION;" % (user, host, root_password)

        return ""

    def run(self, args):
        if args.restrict and args.restore:
            error("argument: '--restrict' or '--restore' can only choose one")
        if args.restrict == False and args.restore == False:
            error("Must select a argument: '--restrict' or '--restore'")

        root_password_ = ''.join(map(check_special_root, args.root_password))
        self.check_root_password(root_password_)

        db_host, db_port, db_user, db_password = self.get_db_portal()
        ui_db_host, ui_db_port, ui_db_user, ui_db_password = self.get_ui_db_portal()

        restrict_ips = []
        is_ha = check_ha()
        if is_ha:
            zsha2_utils = Zsha2Utils()
            self.check_root_password(root_password_, zsha2_utils.config['peerip'])

            restrict_ips.append(zsha2_utils.config['dbvip'])
            restrict_ips.append(zsha2_utils.config['nodeip'])
            restrict_ips.append(zsha2_utils.config['peerip'])
        else:
            restrict_ips.append(db_host)
            if ui_db_host != db_host:
                restrict_ips.append(ui_db_host)

        if args.restrict:
            grant_access_cmd = "USE mysql;" + self.delete_privilege("%", args.include_root)

            for ip in restrict_ips:
                grant_access_cmd = grant_access_cmd + self.grant_restrict_privilege(db_password, ui_db_password, root_password_, ip, args.include_root)
            grant_access_cmd = grant_access_cmd + self.grant_restrict_privilege(db_password, ui_db_password, root_password_, "127.0.0.1", args.include_root)

            grant_access_cmd = grant_access_cmd + " FLUSH PRIVILEGES;"
            grant_views_access_cmd = self.grant_views_definer_privilege(root_password_)

            shell('''mysql -u root -p%s -e "%s %s"''' % (root_password_, grant_views_access_cmd, grant_access_cmd))

            restrict_flags = "root" if args.include_root else "non-root"
            shell("echo %s > %s" % (restrict_flags, self.file))

            if is_ha:
                remote_grant_views_access_cmd = self.grant_views_definer_privilege(root_password_, zsha2_utils.config['peerip'])
                zsha2_utils.excute_on_peer('''`mysql -u root -p%s -e "%s %s"` \n echo %s > %s''' % (root_password_, remote_grant_views_access_cmd, grant_access_cmd, restrict_flags, self.file))

            info("Successfully set mysql restrict connection")
            return

        if args.restore:
            grant_access_cmd = "USE mysql;"
            grant_access_cmd = grant_access_cmd + self.grant_restore_privilege(db_password, ui_db_password, root_password_) + " FLUSH PRIVILEGES;"

            shell('''mysql -u root -p%s -e "%s"''' % (root_password_, grant_access_cmd))
            linux.rm_file_force(self.file)

            if is_ha:
                zsha2_utils.excute_on_peer('''`mysql -u root -p%s -e "%s"`\n rm -f %s''' % (root_password_, grant_access_cmd, self.file))

            info("Successfully restore mysql restrict connection")
            return

class ChangeMysqlPasswordCmd(Command):
    def __init__(self):
        super(ChangeMysqlPasswordCmd, self).__init__()
        self.name = "change_mysql_password"
        self.description = (
            "Change mysql password for root or normal user"
        )

        # non-root users whose password can be changed by this command
        self.normal_users = ['zstack', 'zstack_ui']
        self.sensitive_args = ['--root-password', '-root', '--new-password', '-new']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--root-password','-root',
                            help="Current mysql root password",
                            required=True)
        parser.add_argument('--user-name','-user',
                            help="The user you want to change password",
                            required=True)
        parser.add_argument('--new-password','-new',
                            help="New mysql password of root or normal user,A strong password must contain at least 8 characters in length, and include a combination of letters, numbers and special characters.",
                            required=True)
        parser.add_argument('--remote-ip','-ip',
                            help="Mysql ip address if didn't install on localhost",
                            )

    def check_username_password(self, root_password, remote_ip):
        if remote_ip is not None:
            status, output = commands.getstatusoutput("mysql -u root -p%s -h '%s' -e 'show databases;'" % (root_password, remote_ip))
        else:
            status, output = commands.getstatusoutput("mysql -u root -p%s -e 'show databases;'" % root_password)
        if status != 0:
            error(output)

    def get_mysql_user_hosts(self, user, root_password, remote_ip):
        if remote_ip is None:
            remote_ip = "localhost"
        status, output = commands.getstatusoutput(
            '''mysql -u root -p{root_pass} -h{remote_ip} mysql -BN -e \"select Host from user where User='{user}';\"''' \
                    .format(root_pass=root_password, remote_ip=remote_ip, user=user))
        if status != 0:
            error(output)

        hosts = []

        # in mariadb 10.4, no grants user cannot change password
        for host in output.split("\n"):
            status, output = commands.getstatusoutput(
                '''mysql -u root -p{root_pass} -h{remote_ip} mysql -e \"SHOW GRANTS FOR '{user}'@'{host}';\"'''\
                    .format(root_pass=root_password, remote_ip=remote_ip, user=user, host=host))
            if status == 0:
                hosts.append(host)
        return hosts


    def run(self, args):
        root_password_ = ''.join(map(check_special_root, args.root_password))
        new_password_ = ''.join(map(check_special_new, args.new_password))
        self.check_username_password(root_password_, args.remote_ip)
        if check_pswd_rules(args.new_password) == False:
            error("Failed! The password you entered doesn't meet the password policy requirements.\nA strong password must contain at least 8 characters in length, and include a combination of letters, numbers and special characters.")
        if (args.user_name in self.normal_users) or (args.user_name == 'root'):
            set_password_sql = ""
            for host in self.get_mysql_user_hosts(args.user_name, root_password_, args.remote_ip):
                set_password_sql += "SET PASSWORD FOR '{user}'@'{host}' = PASSWORD('{new_pass}');".format(user=args.user_name, host=host, new_pass=new_password_)
            set_password_sql += "FLUSH PRIVILEGES;"
            if args.remote_ip is not None:
                sql = '''mysql -u root -p{root_pass} -h '{ip}' -e "{sql}" '''.format(root_pass=root_password_, ip=args.remote_ip, sql=set_password_sql)
            else:
                sql = '''mysql -u root -p{root_pass} -e "{sql}" '''.format(root_pass=root_password_, sql=set_password_sql)

            status, output = commands.getstatusoutput(sql)
            if status != 0:
                error(output)
            info("Change mysql password for user '%s' successfully! " % args.user_name)
            if args.user_name == 'zstack':
                info(colored("Please change 'DB.password' in 'zstack.properties' then restart zstack to make the changes effective" , 'yellow'))
            elif args.user_name == 'zstack_ui':
                info(colored("Please change 'db_password' in 'zstack.ui.properties' then restart zstack ui to make the changes effective" , 'yellow'))
        else:
           error("Only support changing %s and root password" % ', '.join(self.normal_users))

class DumpMysqlCmd(Command):
    mysql_backup_dir = "/var/lib/zstack/mysql-backup/"
    remote_backup_dir = "/var/lib/zstack/from-zstack-remote-backup/"
    ui_backup_dir = "/var/lib/zstack/ui/"
    zstone_backup_dir = "/var/lib/zstack/zstone/"

    def __init__(self):
        super(DumpMysqlCmd, self).__init__()
        self.name = "dump_mysql"
        self.description = (
            "Dump mysql database for backup"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--file-name',
                            help="The filename prefix you want to save the backup database under local backup dir, default filename "
                                 "prefix is 'zstack-backup-db', local backup dir is '/var/lib/zstack/mysql-backup/'",
                            default="zstack-backup-db")
        parser.add_argument('--file-path',
                            help="specify a absolute path to dump db, default is '/var/lib/zstack/mysql-backup/zstack-backup-db-$TIMESTAMP.gz'",
                            required=False)
        parser.add_argument('--keep-amount',type=int,
                            help="The amount of backup files you want to keep, older backup files will be deleted, default number is 60",
                            default=60)
        parser.add_argument('--host-info','--host','--h',
                           help="ZStack will sync the backup database and ui data to remote host dir '/var/lib/zstack/from-zstack-remote-backup/', "
                                "the host-info format: 'root@ip_address:port(default port 22)' ",
                           required=False)
        parser.add_argument('--delete-expired-file','--delete','--d',
                            action='store_true',
                            help="ZStack will delete expired files under remote host backup dir /var/lib/zstack/from-zstack-remote-backup/ "
                                 "to make sure the content under remote host backup dir synchronize with local backup dir",
                            required=False)
        parser.add_argument('--append-sql-file',
                            help="specify a append sql to operate zstack database",
                            required=False)
        parser.add_argument('--remote-keep-amount', type=int,
                            help="The amount of files you want to keep on remote host, older files will be deleted, default number is 60",
                            required=False)

    def sync_local_backup_db_to_remote_host(self, args, user, private_key, remote_host_ip, remote_host_port):
        (status, output, stderr) = shell_return_stdout_stderr("mkdir -p %s" % self.ui_backup_dir)
        if status != 0:
            error(stderr)

        command ='timeout 10 sshpass ssh -p %s -i %s %s@%s "mkdir -p %s"' % (remote_host_port, private_key, user, remote_host_ip, self.remote_backup_dir)
        (status, output, stderr) = shell_return_stdout_stderr(command)
        if status != 0:
            error(stderr)
        sync_command = "rsync -lr -e 'ssh -i %s -p %s'  %s %s %s %s@%s:%s" % (private_key, remote_host_port,
                                                                              self.mysql_backup_dir, self.ui_backup_dir,
                                                                              self.zstone_backup_dir, user,
                                                                              remote_host_ip, self.remote_backup_dir)
        (status, output, stderr) = shell_return_stdout_stderr(sync_command)
        if status != 0:
            error(stderr)
        if args.delete_expired_file is True:
            amount = args.remote_keep_amount if args.remote_keep_amount else args.keep_amount
            (status, output, stderr) = shell_return_stdout_stderr('ssh -p %s -i %s %s@%s "ls -rt %s"' % (
                remote_host_port, private_key, user, remote_host_ip, self.remote_backup_dir))
            if status != 0:
                error(stderr)
            file_list = output.split("\n")[:-1]
            if len(file_list) > amount:
                new_file_list = [os.path.join(self.remote_backup_dir, x) for x in file_list[:len(file_list)-amount]]
                need_delete_file_path = " ".join(new_file_list)
                shell_return_stdout_stderr('ssh -p %s -i %s %s@%s "rm -f %s"' % (remote_host_port, private_key, user,
                                                                                 remote_host_ip, need_delete_file_path))

    def get_db_local_hostname_from_zsha2(self):
        if not os.path.exists("/usr/local/bin/zsha2"):
            return None

        r, o, _ = shell_return_stdout_stderr("sudo -i /usr/local/bin/zsha2 status -json")
        if r == 0:
            zshas_status_info = simplejson.loads(o)
            r, o, _ = shell_return_stdout_stderr("/usr/local/bin/zsha2 show-config")
            if r == 0:
                zsha2_config_info = simplejson.loads(o)
                if zshas_status_info['ownsVip']:
                    return zsha2_config_info['nodeip']
                else:
                    return zsha2_config_info['peerip']

    def is_exist_zstone_db(self, db_ip, db_port, db_user, db_pwd):
        command = '''mysql -h %s -P %s -u %s --password='%s' -e "show databases;" | grep zstone ''' \
                  % (db_ip, db_port, db_user, db_pwd)
        (status, output, stderr) = shell_return_stdout_stderr(command)
        if status != 0:
            return False
        if 'zstone' == output.strip("\n"):
            return True
        return False

    def get_zstone_db_user_info(self):
        return "zstndump", "zstndump.db.password"

    def run(self, args):
        (db_hostname, db_port, db_user, db_password) = ctl.get_live_mysql_portal()
        (ui_db_hostname, ui_db_port, ui_db_user, ui_db_password) = ctl.get_live_mysql_portal(ui=True)
        file_name = args.file_name
        keep_amount = args.keep_amount
        backup_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if os.path.exists(self.mysql_backup_dir) is False:
            os.mkdir(self.mysql_backup_dir)

        if os.path.exists(self.zstone_backup_dir) is False:
            os.mkdir(self.zstone_backup_dir)

        db_local_hostname = self.get_db_local_hostname_from_zsha2()
        if not db_local_hostname:
            db_local_hostname = db_hostname

        if args.file_path:
            db_backupf_file_path = args.file_path
        else:
            db_backupf_file_path = self.mysql_backup_dir + db_local_hostname + "-" + file_name + "-" + backup_timestamp + ".gz"

        zstone_backup_file_path = self.zstone_backup_dir + db_local_hostname + "-" + "zstone-backup-db" + "-" + backup_timestamp + ".gz"

        if args.delete_expired_file is not False and args.host_info is None:
            error("Please specify remote host info with '--host' before you want to delete remote host expired files")

        mysqldump_options = "--single-transaction --quick"
        if db_hostname == "localhost" or db_hostname == "127.0.0.1":
            command_1 = "mysqldump --databases -u %s --password='%s' -P %s %s -d zstack zstack_rest" \
                        % (db_user, db_password, db_port, mysqldump_options)
            command_2 = "mysqldump --databases -u %s --password='%s' -P %s %s zstack zstack_rest %s" \
                        % (db_user, db_password, db_port, mysqldump_options, mysqldump_skip_tables)
        else:
            command_1 = "mysqldump --databases -u %s --password='%s' --host %s -P %s %s -d zstack zstack_rest" \
                        % (db_user, db_password, db_hostname, db_port, mysqldump_options)
            command_2 = "mysqldump --databases -u %s --password='%s' --host %s -P %s %s zstack zstack_rest %s" \
                        % (db_user, db_password, db_hostname, db_port, mysqldump_options, mysqldump_skip_tables)

        if ui_db_hostname == "localhost" or ui_db_hostname == "127.0.0.1":
            command_3 = "mysqldump --databases -u %s --password='%s' -P %s %s -f zstack_ui zstack_mini" \
                        % (ui_db_user, ui_db_password, ui_db_port, mysqldump_options)
        else:
            command_3 = "mysqldump --databases -u %s --password='%s' --host %s -P %s %s -f zstack_ui zstack_mini" \
                        % (ui_db_user, ui_db_password, ui_db_hostname, ui_db_port, mysqldump_options)

        if args.append_sql_file:
            append_sql_command = "echo 'USE `zstack`;\n'; cat %s;" % args.append_sql_file
        else:
            append_sql_command = ""

        cmd = ShellCmd("(%s; %s; %s %s) | gzip > %s" % (command_1, command_2, append_sql_command, command_3, db_backupf_file_path))
        cmd(True)
        info("Successfully backed up database. You can check the file at %s" % db_backupf_file_path)

        zstone_db_user, zstone_db_pwd = self.get_zstone_db_user_info()
        if self.is_exist_zstone_db(db_hostname, db_port, zstone_db_user, zstone_db_pwd):
            if db_hostname == "localhost" or db_hostname == "127.0.0.1":
                zstone_backup_cmd = "mysqldump --databases -u %s --password='%s' -P %s %s -f zstone %s" \
                        % (zstone_db_user, zstone_db_pwd, db_port, mysqldump_options, zstone_db_dump_skip_tables)
            else:
                zstone_backup_cmd = "mysqldump --databases -u %s --password='%s' --host %s -P %s %s -f zstone %s" \
                        % (zstone_db_user, zstone_db_pwd, db_hostname, db_port, mysqldump_options, zstone_db_dump_skip_tables)

            cmd = ShellCmd("(%s) | gzip > %s" % (zstone_backup_cmd, zstone_backup_file_path))
            cmd(True)
            info("Successfully backed up zstone database. You can check the file at %s" % zstone_backup_file_path)

            # remove old zstone backup file
            if len(os.listdir(self.zstone_backup_dir)) > keep_amount:
                backup_files_list = [s for s in os.listdir(self.zstone_backup_dir) if os.path.isfile(os.path.join(self.zstone_backup_dir, s))]
                backup_files_list.sort(key=lambda s: os.path.getmtime(os.path.join(self.zstone_backup_dir, s)))
                for expired_file in backup_files_list:
                    if expired_file not in backup_files_list[-keep_amount:]:
                        os.remove(self.zstone_backup_dir + expired_file)

        # remove old file
        if len(os.listdir(self.mysql_backup_dir)) > keep_amount:
            backup_files_list = [s for s in os.listdir(self.mysql_backup_dir) if os.path.isfile(os.path.join(self.mysql_backup_dir, s))]
            backup_files_list.sort(key=lambda s: os.path.getmtime(os.path.join(self.mysql_backup_dir, s)))
            for expired_file in backup_files_list:
                if expired_file not in backup_files_list[-keep_amount:]:
                    os.remove(self.mysql_backup_dir + expired_file)
        #remote backup
        if args.host_info is not None:
            host_info = args.host_info
            host_connect_info_list = check_host_info_format(host_info, with_public_key=True)
            remote_host_user = host_connect_info_list[0]
            remote_host_ip = host_connect_info_list[2]
            remote_host_port = host_connect_info_list[3]
            key_path = os.path.expanduser("~/.ssh/")
            private_key = key_path + "id_rsa"
            public_key = key_path + "id_rsa.pub"
            if os.path.isfile(public_key) is not True:
                error("Didn't find public key: %s" % public_key)
            if os.path.isfile(private_key) is not True:
                error("Didn't find private key: %s" % private_key)
            check_host_connection_with_key(remote_host_ip, remote_host_user, private_key, remote_host_port)

            self.sync_local_backup_db_to_remote_host(args, remote_host_user, private_key, remote_host_ip, remote_host_port)
            if args.delete_expired_file is False:
                info("Sync ZStack backup to remote host %s:%s successfully! " % (remote_host_ip, self.remote_backup_dir))
            else:
                info("Sync ZStack backup to remote host %s:%s and delete expired files on remote successfully! " % (remote_host_ip, self.remote_backup_dir))


class RestoreMysqlPreCheckCmd(Command):
    def __init__(self):
        super(RestoreMysqlPreCheckCmd, self).__init__()
        self.name = "check_restore_mysql"
        self.description = (
            "check before restore mysql data from backup file"
        )
        self.hide = False # expose check command since it's no harm and useful
        self.sensitive_args = ['--mysql-root-password']
        self.hostname = None
        self.port = None
        self.check_fail_list = []
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--from-file', '-f',
                            help="The backup filename under /var/lib/zstack/mysql-backup/ ",
                            required=True)
        parser.add_argument('--mysql-root-password',
                            help="mysql root password of zstack database",
                            default="")

    def execute_sql(self, password, sql):
        return shell_return_stdout_stderr("mysql -uroot --password=%s -P %s --host=%s -e \"%s\""
                                          % (shell_quote(password), self.port, self.hostname, sql))

    def finish_check(self):
        if len(self.check_fail_list) != 0:
            error_msg = string.join(self.check_fail_list, '\n')
            error(error_msg)
        else:
            info("Check pass")

    def run(self, args):
        (self.hostname, self.port, _, _) = ctl.get_live_mysql_portal()
        r, o, e = self.execute_sql(args.mysql_root_password, "show databases like 'zstack'")
        if r != 0:
            self.check_fail_list.append("Failed to connect to jdbc:mysql://%s:%s with root password '%s'" % (
                self.hostname, self.port, args.mysql_root_password))
        elif not o.strip():
            self.finish_check()
            return

        if os.path.exists(args.from_file) is False:
            self.check_fail_list.append("File not exists: %s." % args.from_file)
        try:
            error_if_tool_is_missing('gunzip')
        except CtlError as err:
            self.check_fail_list.append(err.message)

        # tag::check_restore_mysql[]
        create_tmp_table = "drop table if exists `TempVolumeEO`; " \
                           "create table `TempVolumeEO` like .`VolumeEO`;"

        check_sql = "select tv.uuid,`name`,installPath from `TempVolumeEO` tv where tv.uuid in " \
        "(select uuid from `VolumeEO`)" \
        " and tv.installPath != (select installPath from `VolumeEO` where uuid = tv.uuid);"

        drop_table = "drop table if exists `TempVolumeEO`;"
        # end::check_restore_mysql[]

        fd, fname = tempfile.mkstemp()
        os.write(fd, create_tmp_table + "\n")
        shell("gunzip < %s | sed -ne 's/INSERT INTO `VolumeEO`/INSERT INTO `TempVolumeEO`/p' >> %s" % (args.from_file, fname))
        os.lseek(fd, 0, os.SEEK_END)
        os.write(fd, check_sql + "\n" + drop_table)
        os.close(fd)

        r, o, e = self.execute_sql(args.mysql_root_password, "use zstack; source %s;" % fname)
        os.remove(fname)

        if r != 0:
            self.check_fail_list.append("Check failed. Reason: %s." % e)
        elif o:
            self.check_fail_list.append("The install path of some volume(s) has been changed. Restoring mysql has risk:\n%s" % o)

        self.finish_check()


class RestoreMysqlCmd(Command):
    status, all_local_ip = commands.getstatusoutput("ip a")

    def __init__(self):
        super(RestoreMysqlCmd, self).__init__()
        self.name = "restore_mysql"
        self.description = (
            "Restore mysql data from backup file"
        )
        self.hide = False # should expose restore_mysql rather than rollback_db
        self.sensitive_args = ['--mysql-root-password', '--ui-mysql-root-password']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--from-file', '-f',
                            help="The backup file full path",
                            required=True)
        parser.add_argument('--mysql-root-password',
                            help="mysql root password of zstack database",
                            default=None)
        parser.add_argument('--ui-mysql-root-password',
                            help="mysql root password of zstack_ui database, same as --mysql-root-password by default",
                            default=None)
        parser.add_argument('--skip-ui',
                            help="skip restore ui db",
                            action="store_true",
                            default=False)
        parser.add_argument('--only-restore-self',
                            help="This config is for multi node restore mysql, do not set it manually.",
                            action="store_true",
                            default=False)
        parser.add_argument('--skip-check',
                            help="Skip security checks. This may cause vm brain splitting, NOT recommended",
                            action="store_true",
                            default=False)

    def test_mysql_connection(self, db_password, db_port, db_hostname):
        command = "mysql -uroot --password=%s -P %s  %s -e 'show databases'  >> /dev/null 2>&1" \
                      % (shell_quote(db_password), db_port, db_hostname)
        try:
            shell_no_pipe(command)
        except:
            error("Failed to connect to jdbc:mysql://%s:%s with root password '%s'" % (db_hostname, db_port, db_password))

    def run(self, args):
        (db_hostname, db_port, _, _) = ctl.get_live_mysql_portal()
        (ui_db_hostname, ui_db_port, _, _) = ctl.get_live_mysql_portal(ui=True)

        # only root user can restore database
        db_password = args.mysql_root_password
        ui_db_password = args.ui_mysql_root_password if args.ui_mysql_root_password is not None else args.mysql_root_password
        db_backup_name = args.from_file
        db_hostname_origin_cp = db_hostname
        ui_db_hostname_origin_cp = ui_db_hostname

        if os.path.exists(db_backup_name) is False:
            error("Didn't find file: %s ! Stop recover database! " % db_backup_name)
        error_if_tool_is_missing('gunzip')
        check_gunzip_file(db_backup_name)

        if not args.skip_check:
            ctl.internal_run('check_restore_mysql', "-f %s --mysql-root-password %s" % (db_backup_name, db_password))

        # get deploy type
        restorer = RestorerFactory.get_restorer(db_hostname_origin_cp, db_password, db_port)

        # test mysql connection
        if db_hostname == "localhost" or db_hostname == "127.0.0.1" or restorer.is_local_ip(db_hostname):
            db_hostname = ""
        else:
            db_hostname = "--host %s" % db_hostname
        self.test_mysql_connection(db_password, db_port, db_hostname)

        if ui_db_hostname == "localhost" or ui_db_hostname == "127.0.0.1" or restorer.is_local_ip(db_hostname):
            ui_db_hostname = ""
        else:
            ui_db_hostname = "--host %s" % ui_db_hostname
        self.test_mysql_connection(ui_db_password, ui_db_port, ui_db_hostname)

        cmd = create_check_mgmt_node_command()
        cmd(False)
        running = get_mgmt_node_state_from_result(cmd) is True

        info("Backing up database before restore data ...")
        ctl.internal_run('dump_mysql')
        restorer.stop_node(args)

        info("Restoring database ...")
        for database in ['zstack', 'zstack_rest']:
            command = "mysql -uroot --password=%s -P %s  %s" \
                      " -e 'drop database if exists %s; create database %s'  >> /dev/null 2>&1" \
                      % (shell_quote(db_password), db_port, db_hostname, database, database)
            shell_no_pipe(command)

            # modify DEFINER of view, trigger and so on
            # from: /* ... */ /*!50017 DEFINER=`old_user`@`old_hostname`*/ /*...
            # to:   /* ... */ /*!50017 DEFINER=`root`@`new_hostname`*/ /*...
            # Disable ha
            # from: (###,'enable','enable HA or not','ha','true','true')
            # to: (###,'enable','enable HA or not','ha','true','false')
            command = "gunzip < %s | sed -e '/DROP DATABASE IF EXISTS/d' -e '/CREATE DATABASE .* IF NOT EXISTS/d' " \
                      "| sed 's/DEFINER=`[^\*\/]*`@`[^\*\/]*`/DEFINER=`root`@`%s`/' " \
                      "| sed \"s/,'enable','enable HA or not','ha','true','true')/" \
                      ",'enable','enable HA or not','ha','true','false')/g\" " \
                      "| mysql -uroot --password=%s %s -P %s --one-database %s" \
                      % (db_backup_name, db_hostname_origin_cp, shell_quote(db_password),
                         db_hostname, db_port, database)
            shell_no_pipe(command)

        restorer.restore_other_node(args)
        if args.skip_ui:
            if running:
                info("Successfully restored database. Start management node now.")
                restorer.start_node(args)
            else:
                info("Successfully restored database. You can start node manually.")
            warn('The VM HA in the global setting (config) is disabled while restore database, '
                 'enable it after management node is running if needed.')
            return

        ctl.internal_run('stop_ui')
        info("Restoring UI database ...")

        ui_db_names = ['zstack_ui']
        if shell_return('gunzip < %s | grep -q \'USE `zstack_mini`;\'' % db_backup_name) == 0:
            ui_db_names.append('zstack_mini')

        for database in ui_db_names:
            command = "mysql -uroot --password=%s -P %s  %s" \
                      " -e 'drop database if exists %s; create database %s' >> /dev/null 2>&1" \
                      % (shell_quote(ui_db_password), db_port, ui_db_hostname, database, database)
            shell_no_pipe(command)
            command = "gunzip < %s | sed -e '/DROP DATABASE IF EXISTS/d' -e '/CREATE DATABASE .* IF NOT EXISTS/d' " \
                      "| sed 's/DEFINER=`[^\*\/]*`@`[^\*\/]*`/DEFINER=`root`@`%s`/' " \
                      "| mysql -uroot --password=%s %s -P %s --one-database %s" \
                      % (db_backup_name, ui_db_hostname_origin_cp, shell_quote(ui_db_password), ui_db_hostname, ui_db_port, database)
            shell_no_pipe(command)

        info("Successfully restored database. You can start node by running zstack-ctl start.")
        warn('The VM HA in the global setting (config) is disabled while restore database, '
             'enable it after management node is running if needed.')

class RestorerFactory(object):
    @staticmethod
    def get_restorer(db_hostname, db_root_password, db_port):
        _, output, _ = shell_return_stdout_stderr("systemctl is-enabled zstack-ha")
        if output and output.strip() == "enabled":
            return MultiMysqlRestorer()
        return SingleMysqlRestorer()

class MysqlRestorer(object):
    def start_node(self, args):
        raise Exception('function start_node not be implemented')

    def stop_node(self, args):
        raise Exception('function stop_node not be implemented')

    def restore_other_node(self, args):
        raise Exception('function restore_other_node not be implemented')

    def is_local_ip(self, db_hostname):
        raise Exception('function all_local_ip not be implemented')


class MultiMysqlRestorer(MysqlRestorer):
    def __init__(self):
        self.utils = Zsha2Utils()
        _, self.all_local_ip = commands.getstatusoutput("ip a")

    def start_node(self, args):
        if not args.only_restore_self:
            info("Starting self node...")
            shell("/usr/local/bin/zsha2 start-node")
            info("Starting peer node...")
            self.utils.excute_on_peer("/usr/local/bin/zsha2 start-node")

    def stop_node(self, args):
        if not args.only_restore_self:
            info("Stopping self node...")
            shell("/usr/local/bin/zsha2 stop-node -keepui")
            info("Stopping peer node...")
            self.utils.excute_on_peer("/usr/local/bin/zsha2 stop-node -keepui")
        else:
            cmd = create_check_mgmt_node_command()
            cmd(False)
            self_running = get_mgmt_node_state_from_result(cmd) is True
            if self_running:
                warn("How can self node still running? Stopping ...")
                shell("/usr/local/bin/zsha2 stop-node -keepui")

    def restore_other_node(self, args):
        if not args.only_restore_self:
            info("Restoring peer node database...")
            slave_file_path = "/var/lib/zstack/tmp-db-backup.gz"
            self.utils.scp_to_peer(args.from_file, slave_file_path)
            self.utils.excute_on_peer(
                "zstack-ctl restore_mysql --mysql-root-password '%s' --skip-ui --skip-check -f %s --only-restore-self && rm -f %s"
                % (args.mysql_root_password, slave_file_path, slave_file_path))
            info("Succeed to restore zstack peer node data")

    def is_local_ip(self, db_hostname):
        return db_hostname in self.all_local_ip or db_hostname == self.utils.config['dbvip']


class SingleMysqlRestorer(MysqlRestorer):
    def __init__(self):
        _, self.all_local_ip = commands.getstatusoutput("ip a")

    def start_node(self, args):
        ctl.internal_run('start_node')

    def stop_node(self, args):
        ctl.internal_run('stop_node')

    def restore_other_node(self, args):
        pass

    def is_local_ip(self, db_hostname):
        return db_hostname in self.all_local_ip


class ZBoxBackupScanCmd(Command):
    def __init__(self):
        super(ZBoxBackupScanCmd, self).__init__()
        self.name = "scan_zbox_backup"
        self.description = (
            "get ZStack backup details from zbox."
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--path', '-p',
                            help="The absolutely zbox mount path, usually under /var/",
                            required=False)

    def run(self, args):
        if args.path:
            self.print_zbox_backup(args.path)
            return

        for dir_name in os.listdir('/var'):
            if not re.match("zbox-[a-z0-9]{10}", dir_name):
                continue
            self.print_zbox_backup(os.path.join('/var', dir_name))

    @staticmethod
    def print_zbox_backup(zbox_path):
        backup_dir = os.path.join(zbox_path, 'zstack-backup')
        if not os.path.isdir(backup_dir):
            return

        for install_dir_name in os.listdir(backup_dir):
            if not re.match("[0-9.]*-[a-z0-9]{32}", install_dir_name):
                continue
            backup_install_path = os.path.join(backup_dir, install_dir_name)
            version = install_dir_name.split("-")[0]
            mysql_path = os.path.join(backup_install_path, 'mysql-backup-%s.gz' % version)
            conf_path = os.path.join(backup_install_path, 'recover.conf')
            name_path = os.path.join(backup_install_path, 'name')

            if not os.path.exists(mysql_path):
                continue

            if not os.path.exists(name_path):
                name = "unknown"
            else:
                with open(name_path, 'r') as fd:
                    name = fd.read().strip()

            create_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.stat(mysql_path).st_mtime))
            info("name:\t\t\t%s\nversion:\t\t%s\nmysql backup path:\t%s\nconfig path:\t\t%s\ncreate date:\t\t%s\n\n"
                 % (name, version, mysql_path, conf_path, create_date))

class ZBoxBackupRestoreCmd(Command):
    def __init__(self):
        super(ZBoxBackupRestoreCmd, self).__init__()
        self.name = "restore_zbox_backup"
        self.description = (
            "restore ZStack from zbox backup"
        )
        self.hide = True
        self.sensitive_args = ['--mysql-root-password', '--ui-mysql-root-password']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--from-file', '-f',
                            help="The mysql backup filename under /var/zbox-${zbox-uuid}/zstack-backup/${backupname}-${version}-${backup-uuid}/",
                            required=True)
        parser.add_argument('--mysql-root-password',
                            help="mysql root password of zstack database",
                            default=None)
        parser.add_argument('--ui-mysql-root-password',
                            help="mysql root password of zstack_ui database, same as --mysql-root-password by default",
                            default=None)

    def run(self, args):
        pswd_arg = "--mysql-root-password %s" % args.mysql_root_password if args.mysql_root_password else ""
        ui_pswd_arg = "--ui-mysql-root-password %s" % args.ui_mysql_root_password if args.ui_mysql_root_password else ""

        info("Restoring database...")
        ctl.internal_run('restore_mysql', "-f %s %s %s" % (args.from_file, pswd_arg, ui_pswd_arg))

        recover_succ = [False]

        def get_progress():
            progress_path = os.path.join(ctl.zstack_home, "../../temp/RecoverExternalBackup.log")
            linux.rm_file_force(progress_path)
            while not os.path.exists(progress_path):
                time.sleep(1)

            with open(progress_path, 'r') as f:
                while not time.sleep(1):
                    lines = f.readlines()
                    for line in lines:
                        if line.strip().startswith('EOF'):
                            recover_succ[0] = line.strip().endswith("success")
                            return

                        info(colored(line.strip(), 'red' if line.startswith("fail") else 'blue'))

        t = threading.Thread(target=get_progress)
        t.start()

        info("Starting management node...")
        zsha2 = os.path.exists("/usr/local/bin/zsha2")
        if zsha2:
            shell("/usr/local/bin/zsha2 start-node")
        else:
            ctl.internal_run("start")

        info("If you do not care about the progress, you can exit now by pressing Ctrl+Z.")
        t.join()

        if recover_succ[0] and zsha2:
            info("Starting peer management node...")
            Zsha2Utils().excute_on_peer("/usr/local/bin/zsha2 start-node")
        elif not recover_succ[0]:
            sys.exit(1)


class PullDatabaseBackupCmd(Command):
    mysql_backup_dir = "/var/lib/zstack/mysql-backup/"
    ZSTORE_PROTOSTR = "zstore://"

    def __init__(self):
        super(PullDatabaseBackupCmd, self).__init__()
        self.name = "pull_database_backup"
        self.description = (
            "pull database backup from backup storage"
        )
        self.sensitive_args = ['--backup-storage-url']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--backup-storage-url',
                            help="The backup storage install url, must include username, password, hostnamem, ssh port,"
                                 " install path. e.g. ssh://username:password@hostname:port/bspath",
                            required=True)
        parser.add_argument('--backup-install-path',
                            help="database backup install path",
                            required=True)
        parser.add_argument('--registry-port', '-p',
                            help="image store",
                            default=None)
        parser.add_argument('--json', '-j',
                            help="output via json",
                            action="store_true",
                            default=False)

    def run(self, args):
        back_info = args.backup_install_path.replace(self.ZSTORE_PROTOSTR, "").replace("/", ":")
        local_path = os.path.join(self.mysql_backup_dir, "zsdb")
        if not os.path.exists(self.mysql_backup_dir):
            os.mkdir(self.mysql_backup_dir)

        cmd = "pull -installpath %s %s" % (local_path, back_info)
        runImageStoreCliCmd(args.backup_storage_url, args.registry_port, cmd)

        def print_info():
            metadata['installPath'] = new_path
            if args.json:
                info(simplejson.dumps(metadata))
            else:
                info("export path\t\t\t\t\t\t\tversion\ttype\tcreated time\n%s\t%s\t%s\t%s" % (
                    metadata['installPath'], metadata['version'], metadata['type'], metadata['createdTime']))

        def get_metadata():
            try:
                root = simplejson.loads(text)
                desc = root['desc']
                metadata = simplejson.loads(desc)
                metadata['type'] = metadata['type'] if 'type' in metadata.keys() else 'unknown'
                assert metadata['name'] and metadata['version'] and metadata['createdTime']
                return metadata
            except:
                shell("rm -f %s*" % local_path)
                error("it is not a database backup")

        with open(local_path + ".imf2", 'r') as fd:
            text = fd.read()
            metadata = get_metadata()
        os.remove(local_path + ".imf2")

        new_path = os.path.join(self.mysql_backup_dir, metadata['name'])
        os.rename(local_path, new_path)
        print_info()


class ScanDatabaseBackupCmd(Command):
    BACKUP_NAME = "zsbak"
    ZSTORE_PROTOSTR = "zstore://"

    def __init__(self):
        super(ScanDatabaseBackupCmd, self).__init__()
        self.name = "scan_database_backup"
        self.description = (
            "scan database backups from backup storage"
        )
        self.sensitive_args = ['']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--backup-storage-url',
                            help="The backup storage install url, must include username, password, hostname, ssh port,"
                                 " install path. e.g. ssh://username:password@hostname:port/bspath."
                                 " If password has special characters, you need to URL encode it."
                                 " For example, '@' -> '%%40'  '#' -> '%%23'"
                                 " '?' -> '%%3F'  ':' -> '%%3A'  '%%' -> '%%25'",
                            required=True)
        parser.add_argument('--json', '-j',
                            help="output via json",
                            action="store_true",
                            default=False)
        parser.add_argument('--registry-port', '-p',
                            help="image store",
                            default=None)

    def run(self, args):
        cmd = "images -name %s" % self.BACKUP_NAME
        _, out, _ = runImageStoreCliCmd(args.backup_storage_url, args.registry_port, cmd)
        roots = simplejson.loads(out)
        backups = []
        for root in roots:
            metadata = simplejson.loads(root['desc'])
            metadata['size'] = root['size'] if root['size'] else root['virtualsize']
            metadata['installPath'] = "%s%s/%s" % (self.ZSTORE_PROTOSTR, root['name'], root['id'])
            backups.append(metadata)

        if args.json:
            info(simplejson.dumps(backups))
        elif backups:
            info("name\t\t\tinstall path\t\t\t\t\tversion\ttype\tsize\t\tcreated time")
            for backup in backups:
                info("%s\t%s\t%s\t%s\t%s\t%s" % (backup['name'], backup['installPath'], backup['version'],
                                                 backup['type'], backup['size'], backup['createdTime']))


def runImageStoreCliCmd(raw_bs_url, registry_port, command, is_exception=True):
    ZSTORE_CLI_PATH = "/usr/local/zstack/imagestore/bin/zstcli"
    ZSTORE_CLI_CA = "/var/lib/zstack/imagestorebackupstorage/package/certs/ca.pem"
    ZSTORE_DEF_PORT = 8000

    def prepare_ca():
        temp_dir = tempfile.mkdtemp()
        scp_cmd = "sshpass -p %s scp -P %s -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s@%s:%s %s" % \
                  (shell_quote(password), port, username, hostname, ZSTORE_CLI_CA, temp_dir)
        shell(scp_cmd)
        return os.path.join(temp_dir, 'ca.pem')

    def check_server():
        start_cmd = "/usr/local/zstack/imagestore/bin/zstore -conf /usr/local/zstack/imagestore/bin/zstore.yaml -logfile /var/log/zstack/zstack-store/zstore.log"
        ssh_cmd = "sshpass -p %s ssh -p %s -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s@%s" % (
            shell_quote(password), port, username, hostname)

        shell("%s 'ps -e | grep zstore || %s'" % (ssh_cmd, start_cmd))

    url = urlparse.urlparse(raw_bs_url)
    if not url.username or not url.password or not url.hostname:
        error("wrong url, get guide from help.")

    username = urllib2.unquote(url.username)
    password = urllib2.unquote(url.password)
    hostname = urllib2.unquote(url.hostname)

    port = (url.port, 22)[url.port is None]
    registry_port = (ZSTORE_DEF_PORT, registry_port)[registry_port is not None]

    check_server()
    ca_path = prepare_ca()

    cmd = "%s -json -rootca %s -url %s:%s %s" % (ZSTORE_CLI_PATH, ca_path, hostname, registry_port, command)
    code, o, e = shell_return_stdout_stderr(cmd)
    linux.rm_dir_force(os.path.dirname(ca_path))
    if code != 0 and is_exception:
        error("fail to run image store cli[%s]: %s" % (command, e))

    return code, o, e

def get_db(self, collect_dir):
    command = "cp `zstack-ctl dump_mysql | awk '{ print $10 }'` %s" % collect_dir
    shell(command, False)

class CollectLogCmd(Command):
    zstack_log_dir = "/var/log/zstack/"
    vrouter_log_dir_list = ["/home/vyos/zvr", "/var/log/zstack"]
    host_log_list = ['zstack.log','zstack-kvmagent.log','zstack-iscsi-filesystem-agent.log',
                     'zstack-agent/collectd.log','zstack-agent/server.log', 'mini-fencer.log']
    bs_log_list = ['zstack-sftpbackupstorage.log','ceph-backupstorage.log','zstack-store/zstore.log']
    ps_log_list = ['ceph-primarystorage.log']
    # management-server.log is not in the same dir, will collect separately
    mn_log_list = ['deploy.log', 'ha.log', 'zstack-console-proxy.log', 'zstack.log', 'zstack-cli', 'zstack-ui-server.log',
                   'zstack-dashboard.log', 'zstack-ctl.log']
    collect_lines = 100000
    logger_dir = '/var/log/zstack/'
    logger_file = 'zstack-ctl.log'
    failed_flag = False

    def __init__(self):
        super(CollectLogCmd, self).__init__()
        self.name = "collect_log"
        self.description = (
            "Collect log for diagnose"
        )
        self.hide = True
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--force', help='Force use this deprecated command', action="store_true", default=False)
        parser.add_argument('--db', help='collect database for diagnose ', action="store_true", default=False)
        parser.add_argument('--mn-only', help='only collect management log', action="store_true", default=False)
        parser.add_argument('--full', help='collect full management logs and host logs', action="store_true", default=False)
        parser.add_argument('--host', help='only collect management log and specific host log')

    def get_db(self, collect_dir):
        command = "cp `zstack-ctl dump_mysql | awk '{ print $10 }'` %s" % collect_dir
        shell(command, False)

    def compress_and_fetch_log(self, local_collect_dir, tmp_log_dir, host_post_info):
        command = "cd %s && tar zcf ../collect-log.tar.gz . --ignore-failed-read --warning=no-file-changed || true" % tmp_log_dir
        run_remote_command(command, host_post_info)
        fetch_arg = FetchArg()
        fetch_arg.src =  "%s/../collect-log.tar.gz " % tmp_log_dir
        fetch_arg.dest = local_collect_dir
        fetch_arg.args = "fail_on_missing=yes flat=yes"
        fetch(fetch_arg, host_post_info)
        command = "rm -rf %s %s/../collect-log.tar.gz" % (tmp_log_dir, tmp_log_dir)
        run_remote_command(command, host_post_info)
        (status, output) = commands.getstatusoutput("cd %s && tar zxf collect-log.tar.gz" % local_collect_dir)
        if status != 0:
            warn("Uncompress %s/collect-log.tar.gz meet problem: %s" % (local_collect_dir, output))

        (status, output) = commands.getstatusoutput("rm -f %s/collect-log.tar.gz" % local_collect_dir)


    @ignoreerror
    def get_system_log(self, host_post_info, tmp_log_dir):
        # collect uptime and last reboot log and dmesg
        host_info_log = tmp_log_dir + "host_info"
        command = "uptime > %s && last reboot >> %s && free -h >> %s && cat /proc/cpuinfo >> %s  && ip addr >> %s && df -h >> %s" % \
                  (host_info_log, host_info_log, host_info_log, host_info_log, host_info_log, host_info_log)
        run_remote_command(command, host_post_info, True, True)
        command = "if [ ! -f '/var/log/dmesg' ]; then dmesg > /var/log/dmesg; fi; cp /var/log/dmesg* %s" % tmp_log_dir
        run_remote_command(command, host_post_info)
        command = "cp /var/log/messages* %s" % tmp_log_dir
        run_remote_command(command, host_post_info)
        command = "route -n > %s/route_table" % tmp_log_dir
        run_remote_command(command, host_post_info)
        command = "iptables-save > %s/iptables_info" % tmp_log_dir
        run_remote_command(command, host_post_info)
        command = "ebtables-save > %s/ebtables_info" % tmp_log_dir
        run_remote_command(command, host_post_info)
        command = "journalctl -x > %s/journalctl_info" % tmp_log_dir
        run_remote_command(command, host_post_info)

    @ignoreerror
    def get_sharedblock_log(self, host_post_info, tmp_log_dir):
        info_verbose("Collecting sharedblock log from : %s ..." % host_post_info.host)
        target_dir = tmp_log_dir + "sharedblock"
        command = "mkdir -p %s " % target_dir
        run_remote_command(command, host_post_info)

        command = "lsblk -p -o NAME,TYPE,FSTYPE,LABEL,UUID,VENDOR,MODEL,MODE,WWN,SIZE > %s/lsblk_info || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "ls -l /dev/disk/by-id > %s/ls_dev_disk_by-id_info && echo || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "ls -l /dev/disk/by-path >> %s/ls_dev_disk_by-id_info && echo || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "multipath -ll -v3 >> %s/ls_dev_disk_by-id_info || true" % target_dir
        run_remote_command(command, host_post_info)

        command = "cp /var/log/sanlock.log* %s || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "cp /var/log/lvmlock/lvmlockd.log* %s || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "lvmlockctl -i > %s/lvmlockctl_info || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "sanlock client status -D > %s/sanlock_client_info || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "sanlock client host_status -D > %s/sanlock_host_info || true" % target_dir
        run_remote_command(command, host_post_info)

        command = "lvs --nolocking -t -oall > %s/lvm_lvs_info || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "vgs --nolocking -t -oall > %s/lvm_vgs_info || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "lvmconfig --type diff > %s/lvm_config_diff_info || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "cp -r /etc/lvm/ %s || true" % target_dir
        run_remote_command(command, host_post_info)
        command = "cp -r /etc/sanlock %s || true" % target_dir
        run_remote_command(command, host_post_info)

    def get_pkg_list(self, host_post_info, tmp_log_dir):
        command = "rpm -qa | sort > %s/pkg_list" % tmp_log_dir
        run_remote_command(command, host_post_info)

    @ignoreerror
    def get_vrouter_log(self, host_post_info, collect_dir):
        #current vrouter log is very small, so collect all logs for debug
        if check_host_reachable(host_post_info) is True:
            info_verbose("Collecting log from vrouter: %s ..." % host_post_info.host)
            for vrouter_log_dir in CollectLogCmd.vrouter_log_dir_list:
                local_collect_dir = collect_dir + 'vrouter-%s/' % host_post_info.host
                tmp_log_dir = "/var/log/zstack-tmp-log/"
                command = "mkdir -p %s " % tmp_log_dir
                run_remote_command(command, host_post_info)
                command = "/opt/vyatta/sbin/vyatta-save-config.pl && cp /config/config.boot %s" % tmp_log_dir
                run_remote_command(command, host_post_info)
                command = "cp -r %s %s" % (vrouter_log_dir, tmp_log_dir)
                run_remote_command(command, host_post_info)
                self.compress_and_fetch_log(local_collect_dir, tmp_log_dir, host_post_info)
        else:
            warn("Vrouter %s is unreachable!" % host_post_info.host)

    @ignoreerror
    def get_host_log(self, host_post_info, collect_dir, collect_full_log=False):
        if check_host_reachable(host_post_info) is True:
            info_verbose("Collecting log from host: %s ..." % host_post_info.host)
            tmp_log_dir = "%s/tmp-log/" % CollectLogCmd.zstack_log_dir
            local_collect_dir = collect_dir + 'host-%s/' %  host_post_info.host
            try:
                # file system broken shouldn't block collect log process
                if not os.path.exists(local_collect_dir):
                    os.makedirs(local_collect_dir)
                command = "mkdir -p %s " % tmp_log_dir
                run_remote_command(command, host_post_info)

                for log in CollectLogCmd.host_log_list:
                    if 'zstack-agent' in log:
                        command = "mkdir -p %s" % tmp_log_dir + '/zstack-agent/'
                        run_remote_command(command, host_post_info)
                    host_log = CollectLogCmd.zstack_log_dir + '/' + log
                    collect_log = tmp_log_dir + '/' + log
                    if file_dir_exist("path=%s" % host_log, host_post_info):
                        if collect_full_log:
                            for num in range(1, 16):
                                log_name = "%s.%s.gz" % (host_log, num)
                                command = "/bin/cp -rf %s %s/" % (log_name, tmp_log_dir)
                                (status, output) = run_remote_command(command, host_post_info, True, True)
                            command = "/bin/cp -rf %s %s/" % (host_log, tmp_log_dir)
                            (status, output) = run_remote_command(command, host_post_info, True, True)
                        else:
                            command = "tail -n %d %s > %s " % (CollectLogCmd.collect_lines, host_log, collect_log)
                            run_remote_command(command, host_post_info)
            except SystemExit:
                warn("collect log on host %s failed" % host_post_info.host)
                logger.warn("collect log on host %s failed" % host_post_info.host)
                command = linux.get_checked_rm_dir_cmd(tmp_log_dir)
                CollectLogCmd.failed_flag = True
                run_remote_command(command, host_post_info)
                return 1

            command = 'test "$(ls -A "%s" 2>/dev/null)" || echo The directory is empty' % tmp_log_dir
            (status, output) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
            if "The directory is empty" in output:
                warn("Didn't find log on host: %s " % (host_post_info.host))
                command = linux.get_checked_rm_dir_cmd(tmp_log_dir)
                run_remote_command(command, host_post_info)
                return 0
            self.get_system_log(host_post_info, tmp_log_dir)
            self.get_sharedblock_log(host_post_info, tmp_log_dir)
            self.get_pkg_list(host_post_info, tmp_log_dir)
            self.compress_and_fetch_log(local_collect_dir,tmp_log_dir,host_post_info)

        else:
            warn("Host %s is unreachable!" % host_post_info.host)

    @ignoreerror
    def get_storage_log(self, host_post_info, collect_dir, storage_type, collect_full_log=False):
        collect_log_list = []
        if check_host_reachable(host_post_info) is True:
            info_verbose("Collecting log from %s storage: %s ..." % (storage_type, host_post_info.host))
            tmp_log_dir = "%s/tmp-log/" % CollectLogCmd.zstack_log_dir
            local_collect_dir = collect_dir + storage_type + '-' + host_post_info.host+ '/'
            try:
            # file system broken shouldn't block collect log process
                if not os.path.exists(local_collect_dir):
                    os.makedirs(local_collect_dir)
                command = "rm -rf %s && mkdir -p %s " % (tmp_log_dir, tmp_log_dir)
                run_remote_command(command, host_post_info)
                if '_ps' in storage_type:
                    collect_log_list = CollectLogCmd.ps_log_list
                elif '_bs' in storage_type:
                    collect_log_list = CollectLogCmd.bs_log_list
                else:
                    warn("unknown storage type: %s" % storage_type)
                for log in collect_log_list:
                    if 'zstack-store' in log:
                        command = "mkdir -p %s" % tmp_log_dir + '/zstack-store/'
                        run_remote_command(command, host_post_info)
                    storage_agent_log = CollectLogCmd.zstack_log_dir + '/' + log
                    collect_log = tmp_log_dir + '/' + log
                    if file_dir_exist("path=%s" % storage_agent_log, host_post_info):
                        if collect_full_log:
                            for num in range(1, 16):
                                log_name = "%s.%s.gz" % (storage_agent_log, num)
                                command = "/bin/cp -rf %s %s/" % (log_name, tmp_log_dir)
                                (status, output) = run_remote_command(command, host_post_info, True, True)
                            command = "/bin/cp -rf %s %s/" % (storage_agent_log, tmp_log_dir)
                            (status, output) = run_remote_command(command, host_post_info, True, True)
                        else:
                            command = "tail -n %d %s > %s " % (CollectLogCmd.collect_lines, storage_agent_log, collect_log)
                            run_remote_command(command, host_post_info)
            except SystemExit:
                logger.warn("collect log on storage: %s failed" % host_post_info.host)
                command = linux.get_checked_rm_dir_cmd(tmp_log_dir)
                CollectLogCmd.failed_flag = True
                run_remote_command(command, host_post_info)
            command = 'test "$(ls -A "%s" 2>/dev/null)" || echo The directory is empty' % tmp_log_dir
            (status, output) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
            if "The directory is empty" in output:
                warn("Didn't find log on storage host: %s " % host_post_info.host)
                command = linux.get_checked_rm_dir_cmd(tmp_log_dir)
                run_remote_command(command, host_post_info)
                return 0
            self.get_system_log(host_post_info, tmp_log_dir)
            self.get_pkg_list(host_post_info, tmp_log_dir)
            self.compress_and_fetch_log(local_collect_dir,tmp_log_dir, host_post_info)
        else:
            warn("%s storage %s is unreachable!" % (storage_type, host_post_info.host))

    def get_host_ssh_info(self, host_ip, type):
        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        query = MySqlCommandLineQuery()
        query.host = db_hostname
        query.port = db_port
        query.user = db_user
        query.password = db_password
        query.table = 'zstack'
        if type == 'host':
            query.sql = "select * from HostVO where managementIp='%s'" % host_ip
            host_uuid = query.query()[0]['uuid']
            query.sql = "select * from KVMHostVO where uuid='%s'" % host_uuid
            ssh_info = query.query()[0]
            username = ssh_info['username']
            password = ssh_info['password']
            ssh_port = ssh_info['port']
            return (username, password, ssh_port)
        elif type == "sftp_bs":
            query.sql = "select * from SftpBackupStorageVO where hostname='%s'" % host_ip
            ssh_info = query.query()[0]
            username = ssh_info['username']
            password = ssh_info['password']
            ssh_port = ssh_info['sshPort']
            return (username, password, ssh_port)
        elif type == "ceph_bs":
            query.sql = "select * from CephBackupStorageMonVO where hostname='%s'" % host_ip
            ssh_info = query.query()[0]
            username = ssh_info['sshUsername']
            password = ssh_info['sshPassword']
            ssh_port = ssh_info['sshPort']
            return (username, password, ssh_port)
        elif type == "imageStore_bs":
            query.sql = "select * from ImageStoreBackupStorageVO where hostname='%s'" % host_ip
            ssh_info = query.query()[0]
            username = ssh_info['username']
            password = ssh_info['password']
            ssh_port = ssh_info['sshPort']
            return (username, password, ssh_port)
        elif type == "ceph_ps":
            query.sql = "select * from CephPrimaryStorageMonVO where hostname='%s'" % host_ip
            ssh_info = query.query()[0]
            username = ssh_info['sshUsername']
            password = ssh_info['sshPassword']
            ssh_port = ssh_info['sshPort']
            return (username, password, ssh_port)
        elif type == "vrouter":
            query.sql = "select value from GlobalConfigVO where name='vrouter.password'"
            password = query.query()
            username = "vyos"
            ssh_port = 22
            return (username, password, ssh_port)
        else:
            warn("unknown target type: %s" % type)

    @ignoreerror
    def get_management_node_log(self, collect_dir, host_post_info, collect_full_log=False):
        '''management.log maybe not exist, so collect latest files, maybe a tarball'''
        if check_host_reachable(host_post_info) is True:
            mn_ip = host_post_info.host
            info("Collecting log from management node %s ..." % mn_ip)
            local_collect_dir = collect_dir + "/management-node-%s/" % mn_ip + '/'
            if not os.path.exists(local_collect_dir):
                os.makedirs(local_collect_dir)

            tmp_log_dir = "%s/../../logs/tmp-log/" % ctl.zstack_home
            command = 'rm -rf %s && mkdir -p %s' % (tmp_log_dir, tmp_log_dir)
            run_remote_command(command, host_post_info)

            command = "mn_log=`find %s/../../logs/management-serve* -maxdepth 1 -type f -printf" \
                          " '%%T+\\t%%p\\n' | sort -r | awk '{print $2; exit}'`; /bin/cp -rf $mn_log %s" % (ctl.zstack_home, tmp_log_dir)
            (status, output) = run_remote_command(command, host_post_info, True, True)
            if status is not True:
                warn("get management-server log failed: %s" % output)

            # collect zstack-ui log if exists
            command = "/bin/cp -f  %s %s" % (os.path.join(ctl.read_ui_property('log'),'zstack-ui-server.log'), tmp_log_dir)
            (status, output) = run_remote_command(command, host_post_info, True, True)
            if status is not True:
                warn("get zstack-ui-server log failed: %s" % output)

            command = "/bin/cp -f  %s/../../logs/zstack-api.log %s" % (ctl.zstack_home, tmp_log_dir)
            (status, output) = run_remote_command(command, host_post_info, True, True)
            if status is not True:
                warn("get zstack-api log failed: %s" % output)

            command = "/bin/cp -f  %s/../../logs/catalina.out %s" % (ctl.zstack_home, tmp_log_dir)
            (status, output) = run_remote_command(command, host_post_info, True, True)
            if status is not True:
                warn("get catalina log failed: %s" % output)

            if collect_full_log:
                for item in range(0, 15):
                    log_name = "management-server-" + (datetime.today() - timedelta(days=item)).strftime("%Y-%m-%d")
                    command = "/bin/cp -rf %s/../../logs/%s* %s/" % (ctl.zstack_home, log_name, tmp_log_dir)
                    (status, output) = run_remote_command(command, host_post_info, True, True)

                    log_name = "catalina." + (datetime.today() - timedelta(days=item)).strftime("%Y-%m-%d")
                    command = "/bin/cp -rf %s/../../logs/%s* %s/" % (ctl.zstack_home, log_name, tmp_log_dir)
                    (status, output) = run_remote_command(command, host_post_info, True, True)

            for log in CollectLogCmd.mn_log_list:
                if file_dir_exist("path=%s/%s" % (CollectLogCmd.zstack_log_dir, log), host_post_info):
                    command = "tail -n %d %s/%s > %s/%s " \
                              % (CollectLogCmd.collect_lines, CollectLogCmd.zstack_log_dir, log, tmp_log_dir, log)
                    run_remote_command(command, host_post_info)

            self.get_system_log(host_post_info, tmp_log_dir)
            self.get_pkg_list(host_post_info, tmp_log_dir)

            self.compress_and_fetch_log(local_collect_dir, tmp_log_dir, host_post_info)
        else:
            warn("Management node %s is unreachable!" % host_post_info.host)

    @ignoreerror
    def get_local_mn_log(self, collect_dir, collect_full_log=False):
        info_verbose("Collecting log from this management node ...")
        mn_log_dir = collect_dir + 'management-node-%s' % get_default_ip()
        if not os.path.exists(mn_log_dir):
            os.makedirs(mn_log_dir)

        command = "mn_log=`find %s/../..//logs/management-serve* -maxdepth 1 -type f -printf '%%T+\\t%%p\\n' | sort -r | " \
                "awk '{print $2; exit}'`; /bin/cp -rf $mn_log %s/" % (ctl.zstack_home, mn_log_dir)
        (status, output) = commands.getstatusoutput(command)
        if status !=0:
            warn("get management-server log failed: %s" % output)

        # collect zstack-ui log if exists
        command = "/bin/cp -f  %s %s" % (os.path.join(ctl.read_ui_property('log'),'zstack-ui-server.log'), mn_log_dir)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            warn("get zstack-ui-server log failed: %s" % output)

        command = "/bin/cp -f  %s/../../logs/zstack-api.log %s" % (ctl.zstack_home, mn_log_dir)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            warn("get zstack-api log failed: %s" % output)

        command = "/bin/cp -f  %s/../../logs/catalina.out %s" % (ctl.zstack_home, mn_log_dir)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            warn("get catalina log failed: %s" % output)

        if collect_full_log:
            for item in range(0, 15):
                log_name = "management-server-" + (datetime.today() - timedelta(days=item)).strftime("%Y-%m-%d")
                command = "/bin/cp -rf %s/../../logs/%s* %s/" % (ctl.zstack_home, log_name, mn_log_dir)
                (status, output) = commands.getstatusoutput(command)

                log_name = "catalina." + (datetime.today() - timedelta(days=item)).strftime("%Y-%m-%d")
                command = "/bin/cp -rf %s/../../logs/%s* %s/" % (ctl.zstack_home, log_name, mn_log_dir)
                (status, output) = commands.getstatusoutput(command)

        for log in CollectLogCmd.mn_log_list:
            if os.path.exists(CollectLogCmd.zstack_log_dir + log):
                command = ( "tail -n %d %s/%s > %s/%s " % (CollectLogCmd.collect_lines, CollectLogCmd.zstack_log_dir, log, mn_log_dir, log))
                (status, output) = commands.getstatusoutput(command)
                if status != 0:
                    warn("get %s failed: %s" % (log, output))
        host_info_log = mn_log_dir + "/host_info"
        command = "uptime > %s && last reboot >> %s && free -h >> %s && cat /proc/cpuinfo >> %s  && ip addr >> %s && df -h >> %s" % \
                  (host_info_log, host_info_log, host_info_log, host_info_log, host_info_log, host_info_log)
        commands.getstatusoutput(command)
        command = "cp /var/log/dmesg* /var/log/messages* %s/" % mn_log_dir
        commands.getstatusoutput(command)
        command = "cp %s/*git-commit %s/" % (ctl.zstack_home, mn_log_dir)
        commands.getstatusoutput(command)
        command = " rpm -qa | sort  > %s/pkg_list" % mn_log_dir
        commands.getstatusoutput(command)
        command = " rpm -qa | sort  > %s/pkg_list" % mn_log_dir
        commands.getstatusoutput(command)
        command = "journalctl -x > %s/journalctl_info" % mn_log_dir
        commands.getstatusoutput(command)

    def generate_tar_ball(self, run_command_dir, detail_version, time_stamp):
        (status, output) = commands.getstatusoutput("cd %s && tar zcf collect-log-%s-%s.tar.gz collect-log-%s-%s"
                                                    % (run_command_dir, detail_version, time_stamp, detail_version, time_stamp))
        if status != 0:
            error("Generate tarball failed: %s " % output)

    def generate_host_post_info(self, host_ip, type):
        host_post_info = HostPostInfo()
        # update inventory
        with open(ctl.zstack_home + "/../../../ansible/hosts") as f:
            old_hosts = f.read()
            if host_ip not in old_hosts:
                with open(ctl.zstack_home + "/../../../ansible/hosts", "w") as f:
                    new_hosts = host_ip + "\n" + old_hosts
                    f.write(new_hosts)
        (host_user, host_password, host_port) = self.get_host_ssh_info(host_ip, type)
        if host_user != 'root' and host_password is not None:
            host_post_info.become = True
            host_post_info.remote_user = host_user
            host_post_info.remote_pass = host_password
        host_post_info.remote_port = host_port
        host_post_info.host = host_ip
        host_post_info.host_inventory = ctl.zstack_home + "/../../../ansible/hosts"
        host_post_info.private_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa"
        host_post_info.post_url = ""
        return host_post_info


    def run(self, args):
        if not args.force:
            warn("collect_log is deprecated, please use `zstack-ctl configured_collect_log` instead, "
                 "if you have a clear reason not to use `zstack-ctl configured_collect_log`, "
                 "you can use `zstack-ctl collect_log --force`")
            return
        warn("although you force use this deprecated command, we also suggest you use `zstack-ctl "
             "configured_collect_log` instead.")
        # dump mn status
        mn_pid = get_management_node_pid()
        if mn_pid:
            kill_process(mn_pid, signal.SIGQUIT)
            kill_process(mn_pid, signal.SIGUSR2)

        run_command_dir = os.getcwd()
        time_stamp =  datetime.now().strftime("%Y-%m-%d_%H-%M")
        # create log
        create_log(CollectLogCmd.logger_dir, CollectLogCmd.logger_file)
        if get_detail_version() is not None:
            detail_version = get_detail_version().replace(' ','_')
        else:
            hostname, port, user, password = ctl.get_live_mysql_portal()
            detail_version = get_zstack_version(hostname, port, user, password)
        # collect_dir used to store the collect-log
        collect_dir = run_command_dir + '/collect-log-%s-%s/' % (detail_version, time_stamp)
        if not os.path.exists(collect_dir):
            os.makedirs(collect_dir)
        if len(get_mn_list()) > 1:
            warn("there are multiple zstack management node[hostName: %s] exist, need to collect management log on others manually" %
                 map(lambda x: x["hostName"], get_mn_list()))
        if os.path.exists(InstallHACmd.conf_file) is not True:
            self.get_local_mn_log(collect_dir, args.full)
        else:
            # this only for HA due to db will lost mn info if mn offline
            mn_list = get_ha_mn_list(InstallHACmd.conf_file)
            for mn_ip in mn_list:
                host_post_info = HostPostInfo()
                host_post_info.remote_user = 'root'
                # this will be changed in the future
                host_post_info.remote_port = '22'
                host_post_info.host = mn_ip
                host_post_info.host_inventory = InstallHACmd.conf_dir + 'host'
                host_post_info.post_url = ""
                host_post_info.private_key = InstallHACmd.conf_dir + 'ha_key'
                self.get_management_node_log(collect_dir, host_post_info, args.full)

        #collect bs log
        sftp_bs_vo = get_host_list("SftpBackupStorageVO")
        for bs in sftp_bs_vo:
            bs_ip = bs['hostname']
            self.get_storage_log(self.generate_host_post_info(bs_ip, "sftp_bs"), collect_dir, "sftp_bs")

        ceph_bs_vo = get_host_list("CephBackupStorageMonVO")
        for bs in ceph_bs_vo:
            bs_ip = bs['hostname']
            self.get_storage_log(self.generate_host_post_info(bs_ip, "ceph_bs"), collect_dir, "ceph_bs")

        imageStore_bs_vo = get_host_list("ImageStoreBackupStorageVO")
        for bs in imageStore_bs_vo:
            bs_ip = bs['hostname']
            self.get_storage_log(self.generate_host_post_info(bs_ip, "imageStore_bs"), collect_dir, "imageStore_bs")

        #collect ps log
        ceph_ps_vo = get_host_list("CephPrimaryStorageMonVO")
        for ps in ceph_ps_vo:
            ps_ip = ps['hostname']
            self.get_storage_log(self.generate_host_post_info(ps_ip,"ceph_ps"), collect_dir, "ceph_ps")

        #collect vrouter log
        vrouter_ip_list = get_vrouter_list()
        for vrouter_ip in vrouter_ip_list:
            self.get_vrouter_log(self.generate_host_post_info(vrouter_ip, "vrouter"),collect_dir)

        if args.db is True:
            self.get_db(collect_dir)
        if args.mn_only is not True:
            host_vo = get_host_list("HostVO")

            #collect host log
            for host in host_vo:
                if args.host is not None:
                    host_ip = args.host
                else:
                    host_ip = host['managementIp']

                host_type = host['hypervisorType']
                if host_type == "KVM":
                    self.get_host_log(self.generate_host_post_info(host_ip, "host"), collect_dir, args.full)
                if args.host is not None:
                    break

        self.generate_tar_ball(run_command_dir, detail_version, time_stamp)
        if CollectLogCmd.failed_flag is True:
            info_verbose("The collect log generate at: %s/collect-log-%s-%s.tar.gz" % (run_command_dir, detail_version, time_stamp))
            info_verbose(colored("Please check the reason of failed task in log: %s\n" % (CollectLogCmd.logger_dir + CollectLogCmd.logger_file), 'yellow'))
        else:
            info_verbose("The collect log generate at: %s/collect-log-%s-%s.tar.gz" % (run_command_dir, detail_version, time_stamp))


def is_hyper_converged_host():
    r, o = commands.getstatusoutput("bootstrap is_deployed")
    if r != 0 or o.strip() != "true":
        return False
    return True

def is_zsv_env():
    properties_file_path = os.path.join(os.environ['ZSTACK_HOME'], 'WEB-INF/classes/zstack.properties')
    properties = PropertyFile(properties_file_path)
    return properties.read_property('deploy_mode') == 'zsv'

def get_hci_full_version():
    detailed_version_file = "/usr/local/hyperconverged/conf/VERSION"
    if os.path.exists(detailed_version_file):
        with open(detailed_version_file, 'r') as fd:
            return fd.read().strip()
    else:
        return None

def get_hci_detail_version():
    full_version = get_hci_full_version()
    return None if full_version is None else full_version.rsplit("-", 2)[0]

def get_zsv_version():
    detailed_version_file = os.path.join(os.environ['ZSTACK_HOME'], 'WEB-INF', 'classes', 'zsphere_config', 'version')
    if os.path.exists(detailed_version_file):
        with open(detailed_version_file, 'r') as fd:
            return fd.read().strip()
    else:
        return ''

class ConfiguredCollectLogCmd(Command):
    logger_dir = '/var/log/zstack/'
    logger_file = 'zstack-ctl.log'
    zstack_log_dir = "/var/log/zstack/"
    ui_log_download_dir = os.path.join(ctl.ZSTACK_UI_HOME, "public/logs/")

    def __init__(self):
        super(ConfiguredCollectLogCmd, self).__init__()
        self.name = "configured_collect_log"
        self.description = (
            "Configured collect log for diagnose"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--from-date',
                            help='collect logs from datetime below format:\'yyyy-MM-dd\' or \'yyyy-MM-dd_hh:mm:ss\',default datetime is 24h ago',
                            default=None)
        parser.add_argument('--to-date',
                            help='collect logs up to datetime below format:\'yyyy-MM-dd\' or \'yyyy-MM-dd_hh:mm:ss\',default datetime is current datetime',
                            default=None)
        parser.add_argument('--since',
                            help='collect logs from N days(--since Nd) or hours(--since Nh) before, for example,if you input \'--since 2d\',\
                                 we will collect logs from the previous two days',
                            default=None)
        parser.add_argument('--check', help='preview collection file size', action="store_true", default=False)
        parser.add_argument('-p', help='input the path to your custom yaml',
                            default=None)
        parser.add_argument('--full', help='collect full log except db (default choose)', action="store_true",
                            default=False)
        parser.add_argument('--full-db', help='collect full log and db', action="store_true", default=False)
        parser.add_argument('--mn-only', help='only collect managenode log', action="store_true", default=False)
        parser.add_argument('--mn-db', help='collect managementnode log and db', action="store_true", default=False)
        parser.add_argument('--mn-host', help='collect managementnode and host log', action="store_true", default=False)
        parser.add_argument('--thread', help='max collect log thread number', default=None)
        parser.add_argument('--hosts', help='only collect specific hosts log, separate host ips with commas')
        parser.add_argument('--timeout', help='wait for log thread collect timeout, default is 300 seconds', default=300)
        parser.add_argument('--dump-thread-info', help='dump threads info', default=False)
        parser.add_argument('--dumptime', help='wait for dumping threads time, default is 10 seconds', type=int, default=10)
        parser.add_argument('--destination', help='collect logs to the specified directory', default=None)
        parser.add_argument('--combination', help='collect logs in a combined way, including mn/mn_db/host/bs/ps/vrouter/pxeserver/baremetalv2gateway, such as \'mn,host,ps\'',
                            default=None)
        parser.add_argument('--clear-log', help='clear log collected through UI', default=None)
        parser.add_argument('--scsi-diagnose', help='only collect host syslog', action="store_true", default=False)
        parser.add_argument('--mn-diagnose', help='only collect zstack management logs', action="store_true", default=False)
        parser.add_argument('--no-tarball', help='not to compress collected logs into a tar gzip file', action="store_true", default=False)
        parser.add_argument('--collect-dir-name', help='use given log collection dir name, other then automatically generated one', default=None)

    def clear_log_file(self, log_name):
        if "/" in log_name:
            error("clear log failed, value[%s] is invalid" % log_name)
        
        log_path = self.ui_log_download_dir + log_name
        if os.path.isfile(log_path):
            shell('rm -f %s' % log_path)
            info("clear log file[%s] successfully!" % log_path)
        elif os.path.isdir(log_path):
            shell('rm -rf %s' % log_path)
            info("clear log dir[%s] successfully!" % log_path)
        else:
            error("clear log failed, file [%s] does not exist" % log_path)

    def run(self, args):
        if args.clear_log:
            self.clear_log_file(args.clear_log)
            return
        
        # dump mn status
        mn_pid = get_management_node_pid()
        if mn_pid:
            kill_process(mn_pid, signal.SIGQUIT)
            kill_process(mn_pid, signal.SIGUSR2)
        time_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        # create log
        create_log(self.logger_dir, self.logger_file)

        detail_version = None
        if is_hyper_converged_host():
            detail_version = get_hci_detail_version()
        elif get_detail_version() is not None:
            detail_version = get_detail_version().replace(' ', '_')

        if detail_version is None:
            hostname, port, user, password = ctl.get_live_mysql_portal()
            detail_version = get_zstack_version(hostname, port, user, password)

        run_command_dir = os.getcwd()
        if args.destination:
            run_command_dir = args.destination
        log_collector.CollectFromYml(ctl, run_command_dir, detail_version, time_stamp, args)


class ChangeIpCmd(Command):
    def __init__(self):
        super(ChangeIpCmd, self).__init__()
        self.name = "change_ip"
        self.description = (
            "update new management ip address to zstack property file"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--ip', help='The new IP address of management node.'
                                         'This operation will update the new ip address to '
                                         'zstack config file' , required=True)
        parser.add_argument('--cloudbus_server_ip', help='The new IP address of CloudBus.serverIp.0, default will use value from --ip', required=False)
        parser.add_argument('--mysql_ip', help='The new IP address of DB.url, default will use value from --ip', required=False)
        parser.add_argument('--root-password',
                            help='When mysql_restrict_connection is enabled, --root-password needs to be set ',
                            required=False)

    def isVirtualIp(self, ip):
        return shell("ip a | grep -w %s" % ip, False).strip().endswith("zs")

    def check_mysql_password(self, user, password):
        status, output = commands.getstatusoutput("mysql -u%s -p%s -e 'show databases;'" % (user, password))
        if status != 0:
            error(output)

    def restoreMysqlConnection(self, root_password):
        _, db_user, db_password = ctl.get_database_portal()
        _, ui_db_user, ui_db_password = ctl.get_ui_database_portal()

        if db_user != "zstack":
            error("need to set 'DB.user = zstack' in zstack.properties when updating mysql restrict connection")
        if ui_db_user != "zstack_ui":
            error("need to set 'db_username = zstack_ui' in zstack.ui.properties when updating mysql restrict connection")

        self.check_mysql_password(db_user, db_password)
        self.check_mysql_password(ui_db_user, ui_db_password)

        grant_access_cmd = " DELETE FROM user WHERE Host != 'localhost' AND Host != '127.0.0.1' AND Host != '::1' AND Host != '%%';" \
                           " GRANT USAGE ON *.* TO 'zstack'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION;" \
                           " GRANT USAGE ON *.* TO 'zstack_ui'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION;" \
                           " GRANT USAGE ON *.* TO 'root'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION;" % (
                               db_password, ui_db_password, root_password)

        grant_access_cmd = "USE mysql;" + grant_access_cmd + " FLUSH PRIVILEGES;"
        shell('''mysql -u root -p%s -e "%s"''' % (root_password, grant_access_cmd))

    def checkMysqlConnection(self, mysql_ip, root_password):
        (status, output) = commands.getstatusoutput("cat %s/mysql_restrict_connection" % ctl.USER_ZSTACK_HOME_DIR)
        if status != 0 or (output != "non-root" and output != "root"):
            return

        if shell_return("ip a | grep 'inet ' | grep -w '%s'" % mysql_ip) != 0:
            return

        if root_password is None:
            error("--root-password needs to be set")

        self.restoreMysqlConnection(root_password)
        if output == "non-root":
            shell("zstack-ctl mysql_restrict_connection --root-password %s --restrict" % root_password)
        elif output == "root":
            shell("zstack-ctl mysql_restrict_connection --root-password %s --restrict --include-root" % root_password)

        info("update mysql restrict connection successfully")

    def run(self, args):
        if args.ip == '0.0.0.0':
            raise CtlError('for your data safety, please do NOT use 0.0.0.0 as the listen address')
        if args.cloudbus_server_ip is not None:
            cloudbus_server_ip = args.cloudbus_server_ip
        else:
            cloudbus_server_ip = args.ip
        if args.mysql_ip is not None:
            mysql_ip = args.mysql_ip
        else:
            mysql_ip = args.ip
        if args.root_password is not None:
            root_password_ = ''.join(map(check_special_root, args.root_password))
            self.check_mysql_password("root", root_password_)

        if check_ha():
            error("please change to single management before change ip")

        zstack_conf_file = ctl.properties_file_path
        ip_check = re.compile('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
        for input_ip in [cloudbus_server_ip, mysql_ip]:
            if not ip_check.match(input_ip):
                info("The ip address you input: %s seems not a valid ip" % input_ip)
                return 1
            if self.isVirtualIp(input_ip):
                info("The ip address you input: %s is a virtual ip" % input_ip)
                return 1

        # Update /etc/hosts
        if os.path.isfile(zstack_conf_file):
            old_ip = ctl.read_property('management.server.ip')
            if old_ip is not None:
                if not ip_check.match(old_ip):
                    info("The ip address[%s] read from [%s] seems not a valid ip" % (old_ip, zstack_conf_file))
                    return 1

            # read from env other than /etc/hostname in case of impact of DHCP SERVER
            old_hostname = shell("hostname").replace("\n","")
            new_hostname = args.ip.replace(".","-")
            if old_hostname != "localhost" and old_hostname != "localhost.localdomain":
               new_hostname = old_hostname

            if old_ip != None:
                shell('sed -i "/^%s .*$/d" /etc/hosts' % old_ip)
            else:
                shell('sed -i "/^.* %s$/d" /etc/hosts' % new_hostname)

            shell('echo "%s %s" >> /etc/hosts' % (args.ip, new_hostname))
            shell('hostnamectl set-hostname %s' % new_hostname)
            shell('export HOSTNAME=%s' % new_hostname)

            if old_ip != None:
                info("Update /etc/hosts, old_ip:%s, new_ip:%s" % (old_ip, args.ip))
            else:
                info("Update /etc/hosts, new_ip:%s" % args.ip)

        else:
            info("Didn't find %s, skip update new ip" % zstack_conf_file  )
            return 1

       # Update zstack config file
        if os.path.isfile(zstack_conf_file):
            shell("yes | cp %s %s.bak" % (zstack_conf_file, zstack_conf_file))
            ctl.write_properties([
              ('CloudBus.serverIp.0', cloudbus_server_ip),
            ])
            info("Update cloudbus server ip %s in %s " % (cloudbus_server_ip, zstack_conf_file))
            ctl.write_properties([
              ('management.server.ip', args.ip),
            ])
            info("Update management server ip %s in %s " % (args.ip, zstack_conf_file))

            cpo_ip = ctl.read_property('consoleProxyOverriddenIp')
            if cpo_ip is None or cpo_ip == '' or cpo_ip == old_ip:
                ctl.write_properties([
                    ('consoleProxyOverriddenIp', args.ip),
                ])
                info("Update console proxy overridden ip %s in %s " % (args.ip, zstack_conf_file))

            old_chrony_ips = ctl.read_property_list('chrony.serverIp.')
            if len(old_chrony_ips) == 1 and old_chrony_ips[0][1] == old_ip:
                # management.server.ip has been setted when zstack install
                ctl.write_property(old_chrony_ips[0][0], args.ip)
                info("Update chrony server ip %s in %s " % (args.ip, zstack_conf_file))

            # update zstack db url
            db_url = ctl.read_property('DB.url')
            db_old_ip = re.findall(r'[0-9]+(?:\.[0-9]{1,3}){3}|localhost', db_url)
            if not self.isVirtualIp(db_old_ip[0]) and not db_old_ip[0] == ctl.read_property('management.server.vip'):
                db_new_url = db_url.split(db_old_ip[0])[0] + mysql_ip + db_url.split(db_old_ip[0])[1]
                ctl.write_properties([
                    ('DB.url', db_new_url),
                ])
                info("Update mysql new url %s in %s " % (db_new_url, zstack_conf_file))

            # update zstack_ui db url
            if os.path.isfile(ctl.ui_properties_file_path):
                db_url = ctl.read_ui_property('db_url')
                db_old_ip = re.findall(r'[0-9]+(?:\.[0-9]{1,3}){3}|localhost', db_url)
                if not self.isVirtualIp(db_old_ip[0]) and not db_old_ip[0] == ctl.read_property('management.server.vip'):
                    db_new_url = db_url.split(db_old_ip[0])[0] + mysql_ip + db_url.split(db_old_ip[0])[1]
                    ctl.write_ui_properties([
                        ('db_url', db_new_url),
                    ])
                    info("Update mysql new url %s in %s " % (db_new_url, ctl.ui_properties_file_path))

            # update mysql restrict connection configuration
            self.checkMysqlConnection(args.ip, args.root_password)
        else:
            info("Didn't find %s, skip update new ip" % zstack_conf_file  )
            return 1

        # Update iptables
        mysql_ports = {3306}
        ports = mysql_ports

        cmd = "/sbin/iptables-save | grep INPUT | grep '%s'" % '\\|'.join('dport %s ' % port for port in ports)
        o = ShellCmd(cmd)
        o(False)
        if o.return_code == 0:
            old_rules = o.stdout.splitlines()
        else:
            old_rules = []

        iptstrs = shell("/sbin/iptables-save").splitlines()
        for rule in old_rules:
            iptstrs.remove(rule)

        (tmp_fd, tmp_path) = tempfile.mkstemp()
        tmp_fd = os.fdopen(tmp_fd, 'w')
        tmp_fd.write('\n'.join(iptstrs))
        tmp_fd.close()
        shell('/sbin/iptables-restore < %s' % tmp_path)
        os.remove(tmp_path)

        if mysql_ip != args.ip:
            ports -= mysql_ports
        for port in ports:
            shell('iptables -A INPUT -p tcp --dport %s -j REJECT' % port)
            shell('iptables -I INPUT -p tcp --dport %s -d %s -j ACCEPT' % (port, args.ip))
            shell('iptables -I INPUT -p tcp --dport %s -d 127.0.0.1 -j ACCEPT' % port)

        info("update iptables rules successfully")
        info("Change ip successfully")


class InstallManagementNodeCmd(Command):
    def __init__(self):
        super(InstallManagementNodeCmd, self).__init__()
        self.name = "install_management_node"
        self.description = (
            "install ZStack management node from current machine to a remote machine with zstack.properties."
            "\nNOTE: please configure current node before installing node on other machines"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='target host IP user and password, for example, root:password@192.168.0.212, to install ZStack management node to a remote machine', required=True)
        parser.add_argument('--install-path', help='the path on remote machine where Apache Tomcat will be installed, which must be an absolute path; [DEFAULT]: /usr/local/zstack', default='/usr/local/zstack')
        parser.add_argument('--source-dir', help='the source folder containing Apache Tomcat package and zstack.war, if omitted, it will default to a path related to $ZSTACK_HOME')
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--force-reinstall', help="delete existing Apache Tomcat and resinstall ZStack", action="store_true", default=False)
        parser.add_argument('--yum', help="Use ZStack predefined yum repositories. The valid options include: alibase,aliepel,163base,ustcepel,zstack-local. NOTE: only use it when you know exactly what it does.", default=None)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def add_public_key_to_host(self, key_path, host_info):
        command ='timeout 10 sshpass -p %s ssh-copy-id -o UserKnownHostsFile=/dev/null -o PubkeyAuthentication=no' \
                 ' -o StrictHostKeyChecking=no -i %s root@%s' % (shell_quote(host_info.remote_pass), key_path, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("Copy public key '%s' to host: '%s' failed:\n %s" % (key_path, host_info.host,  output))

    def run(self, args):
        if not os.path.isabs(args.install_path):
            raise CtlError('%s is not an absolute path' % args.install_path)

        if not args.source_dir:
            args.source_dir = os.path.join(ctl.zstack_home, "../../../")

        if not os.path.isdir(args.source_dir):
            raise CtlError('%s is not an directory' % args.source_dir)

        if not args.yum:
            args.yum = get_yum_repo_from_property()

        if args.ssh_key is None:
            args.ssh_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa.pub"
        private_key = args.ssh_key.split('.')[0]

        inventory_file = ctl.zstack_home + "/../../../ansible/hosts"
        host_info = HostPostInfo()
        host_info.private_key = private_key
        host_info.host_inventory =  inventory_file
        (host_info.remote_user, host_info.remote_pass, host_info.host, host_info.remote_port) = check_host_info_format(args.host)

        check_host_password(host_info.remote_pass, host_info.host)

        self.add_public_key_to_host(args.ssh_key, host_info)

        apache_tomcat = None
        zstack = None
        apache_tomcat_zip_name = None
        for file in os.listdir(args.source_dir):
            full_path = os.path.join(args.source_dir, file)
            if file.startswith('apache-tomcat') and file.endswith('zip') and os.path.isfile(full_path):
                apache_tomcat = full_path
                apache_tomcat_zip_name = file
            if file == 'zstack.war':
                zstack = full_path

        if not apache_tomcat:
            raise CtlError('cannot find Apache Tomcat ZIP in %s, please use --source-dir to specify the directory containing the ZIP' % args.source_dir)

        if not zstack:
            raise CtlError('cannot find zstack.war in %s, please use --source-dir to specify the directory containing the WAR file' % args.source_dir)

        pypi_path = os.path.join(ctl.zstack_home, "static/pypi/")
        if not os.path.isdir(pypi_path):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % pypi_path)

        pypi_tar_path = os.path.join(ctl.zstack_home, "static/pypi.tar.bz")
        static_path = os.path.join(ctl.zstack_home, "static")
        shell('cd %s; tar jcf pypi.tar.bz pypi' % static_path)

        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      root: $install_path
      yum_repo: "$yum_repo"

  tasks:
    - name: check remote env on RedHat OS 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      script: $pre_script_on_rh6

    - name: prepare remote environment
      script: $pre_script

    - name: sync repo from remote management node
      script: $sync_repo

    - name: install dependencies on RedHat OS from user defined repo
      when: ansible_os_family == 'RedHat' and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y dmidecode java-1.8.0-openjdk wget python-devel gcc autoconf tar gzip unzip python-pip openssh-clients sshpass bzip2 sudo libselinux-python python-setuptools iptables-services libffi-devel openssl-devel

    - name: install dependencies on RedHat OS from system repos
      when: ansible_os_family == 'RedHat' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y dmidecode java-1.8.0-openjdk wget python-devel gcc autoconf tar gzip unzip python-pip openssh-clients sshpass bzip2 sudo libselinux-python python-setuptools iptables-services libffi-devel openssl-devel

    - name: set java 8 as default runtime
      when: ansible_os_family == 'RedHat'
      shell: update-alternatives --install /usr/bin/java java /usr/lib/jvm/jre-1.8.0/bin/java 0; update-alternatives --set java /usr/lib/jvm/jre-1.8.0/bin/java

    - name: add ppa source for openjdk-8 on Ubuntu 14.04
      when: ansible_os_family == 'Debian' and ansible_distribution_version == '14.04'
      shell: add-apt-repository ppa:openjdk-r/ppa -y; apt-get update

    - name: install openjdk on Ubuntu 14.04
      when: ansible_os_family == 'Debian' and ansible_distribution_version == '14.04'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - openjdk-8-jdk

    - name: install openjdk on Ubuntu 16.04
      when: ansible_os_family == 'Debian' and ansible_distribution_version == '16.04'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - openjdk-8-jdk

    - name: set java 8 as default runtime
      when: ansible_os_family == 'Debian' and ansible_distribution_version == '14.04'
      shell: update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java 0; update-alternatives --install /usr/bin/javac javac /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/javac 0; update-alternatives --set java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java; update-alternatives --set javac /usr/lib/jvm/java-8-openjdk-amd64/bin/javac

    - name: install dependencies Debian OS
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - wget
        - python-dev
        - gcc
        - autoconf
        - tar
        - gzip
        - unzip
        - python-pip
        - sshpass
        - bzip2
        - sudo
        - python-setuptools

    - stat: path=/usr/bin/mysql
      register: mysql_path

    - name: install MySQL client for RedHat 6 from user defined repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7' and yum_repo != 'false' and (mysql_path.stat.exists == False)
      shell: yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y mysql

    - name: install MySQL client for RedHat 6 from system repo
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7' and yum_repo == 'false' and (mysql_path.stat.exists == False)
      shell: yum --nogpgcheck install -y mysql

    - name: install MySQL client for RedHat 7 from user defined repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and yum_repo != 'false' and (mysql_path.stat.exists == False)
      shell: yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y mariadb

    - name: install MySQL client for RedHat 7 from system repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and yum_repo == 'false' and (mysql_path.stat.exists == False)
      shell: yum --nogpgcheck install -y mariadb

    - name: install MySQL client for Ubuntu/Debian
      when: ansible_os_family == 'Debian' and (mysql_path.stat.exists == False)
      apt: pkg={{item}}
      with_items:
        - mysql-client

    - name: copy pypi tar file
      copy: src=$pypi_tar_path dest=$pypi_tar_path_dest

    - name: untar pypi
      shell: "cd /tmp/; tar jxf $pypi_tar_path_dest"

    - name: install pip from local source
      shell: "easy_install -i file://$pypi_path/simple --upgrade pip"

    - name: install ansible from local source
      pip: name="ansible" extra_args="-i file://$pypi_path/simple --ignore-installed --trusted-host localhost"

    - name: install virtualenv
      pip: name="virtualenv" extra_args="-i file://$pypi_path/simple --ignore-installed --trusted-host localhost"

    - name: copy Apache Tomcat
      copy: src=$apache_path dest={{root}}/$apache_tomcat_zip_name

    - name: copy zstack.war
      copy: src=$zstack_path dest={{root}}/zstack.war

    - name: install ZStack
      script: $post_script

    - name: copy zstack.properties
      copy: src=$properties_file dest={{root}}/apache-tomcat/webapps/zstack/WEB-INF/classes/zstack.properties

    - name: mount zstack-dvd
      file:
        src: /opt/zstack-dvd
        dest: $install_path/apache-tomcat/webapps/zstack/static/zstack-dvd
        state: link
        force: yes

    - name: setup zstack account
      script: $setup_account

    - name: change owner of /var/lib/zstack/
      shell: "mkdir -p /var/lib/zstack/; chown -R zstack:zstack /var/lib/zstack/"
'''

        pre_script = '''
{0}

whereis zstack-ctl
if [ $$? -eq 0 ]; then
   zstack-ctl stop_node
fi

apache_path={1}/apache-tomcat
if [[ -d $$apache_path ]] && [[ {2} -eq 0 ]]; then
   echo "found existing Apache Tomcat directory $$apache_path; please use --force-reinstall to delete it and re-install"
   exit 1
fi

rm -rf {3}
mkdir -p {4}
'''.format(configure_yum_repo_script,
           args.install_path,
           int(args.force_reinstall),
           args.install_path,
           args.install_path)
        fd, pre_script_path = tempfile.mkstemp(suffix='.sh')
        os.fdopen(fd, 'w').write(pre_script)

        pre_script_on_rh6 = '''
ZSTACK_INSTALL_LOG='/tmp/zstack_installation.log'
rpm -qi python-crypto >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Management node remote installation failed. You need to manually remove python-crypto by \n\n \`rpm -ev python-crypto\` \n\n in remote management node; otherwise it will conflict with ansible's pycrypto." >>$ZSTACK_INSTALL_LOG
    exit 1
fi
'''
        t = string.Template(pre_script_on_rh6)

        fd, pre_script_on_rh6_path = tempfile.mkstemp(suffix='.sh')
        os.fdopen(fd, 'w').write(pre_script_on_rh6)

        def cleanup_pre_script():
            os.remove(pre_script_path)
            os.remove(pre_script_on_rh6_path)

        self.install_cleanup_routine(cleanup_pre_script)
        post_script = '''
set -e
filename=$apache_tomcat_zip_name
foldername="$${filename%.*}"
apache_path=$install_path/apache-tomcat
unzip $apache -d $install_path
ln -s $install_path/$$foldername $$apache_path
unzip $zstack -d $$apache_path/webapps/zstack

chmod a+x $$apache_path/bin/*

cat >> $$apache_path/bin/setenv.sh <<EOF
export CATALINA_OPTS=" -Djava.net.preferIPv4Stack=true -Dcom.sun.management.jmxremote=true"
EOF

install_script="$$apache_path/webapps/zstack/WEB-INF/classes/tools/install.sh"

eval "bash $$install_script zstack-ctl"
eval "bash $$install_script zstack-cli"

set +e
grep "ZSTACK_HOME" ~/.bashrc > /dev/null
if [ $$? -eq 0 ]; then
    sed -i "s#export ZSTACK_HOME=.*#export ZSTACK_HOME=$$apache_path/webapps/zstack#" ~/.bashrc
else
    echo "export ZSTACK_HOME=$$apache_path/webapps/zstack" >> ~/.bashrc
fi

which ansible-playbook &> /dev/null
if [ $$? -ne 0 ]; then
    pip install -i file://$pypi_path/simple --trusted-host localhost ansible
fi
'''
        t = string.Template(post_script)
        post_script = t.substitute({
            'install_path': args.install_path,
            'apache': os.path.join(args.install_path, apache_tomcat_zip_name),
            'zstack': os.path.join(args.install_path, 'zstack.war'),
            'apache_tomcat_zip_name': apache_tomcat_zip_name,
            'pypi_path': '/tmp/pypi/'
        })

        fd, post_script_path = tempfile.mkstemp(suffix='.sh')
        os.fdopen(fd, 'w').write(post_script)

        def cleanup_post_script():
            os.remove(post_script_path)

        self.install_cleanup_routine(cleanup_post_script)

        setup_account = '''id -u zstack >/dev/null 2>&1
if [ $$? -eq 0 ]; then
    usermod -d $install_path zstack
else
    useradd -d $install_path zstack && mkdir -p $install_path && chown -R zstack.zstack $install_path
fi
grep 'zstack' /etc/sudoers >/dev/null || echo 'zstack        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
grep '^root' /etc/sudoers >/dev/null || echo 'root        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
sed -i '/requiretty$$/d' /etc/sudoers
chown -R zstack.zstack $install_path
mkdir /home/zstack && chown -R zstack.zstack /home/zstack
zstack-ctl setenv ZSTACK_HOME=$install_path/apache-tomcat/webapps/zstack
'''
        t = string.Template(setup_account)
        setup_account = t.substitute({
            'install_path': args.install_path
        })

        fd, setup_account_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(setup_account)

        def clean_up():
            os.remove(setup_account_path)

        self.install_cleanup_routine(clean_up)

        sync_repo = '''
# check /opt/zstack-dvd
if [ ! -d /opt/zstack-dvd ]; then
    echo "/opt/zstack-dvd not found, please download ZStack ISO and execute '# zstack-upgrade -r PATH_TO_ZSTACK_ISO'"
    exit 1
fi

# prepare yum repo file
cat > /etc/yum.repos.d/zstack-online-base.repo << EOF
[zstack-online-base]
name=zstack-online-base
baseurl=${BASEURL}
gpgcheck=0
enabled=0
EOF

cat > /etc/yum.repos.d/zstack-online-ceph.repo << EOF
[zstack-online-ceph]
name=zstack-online-ceph
baseurl=${BASEURL}/ceph
gpgcheck=0
enabled=0
EOF

cat > /etc/yum.repos.d/zstack-online-uek4.repo << EOF
[zstack-online-uek4]
name=zstack-online-uek4
baseurl=${BASEURL}/uek4
gpgcheck=0
enabled=0
EOF

cat > /etc/yum.repos.d/zstack-online-galera.repo << EOF
[zstack-online-galera]
name=zstack-online-galera
baseurl=${BASEURL}/galera
gpgcheck=0
enabled=0
EOF

cat > /etc/yum.repos.d/zstack-online-qemu-kvm-ev.repo << EOF
[zstack-online-qemu-kvm-ev]
name=zstack-online-qemu-kvm-ev
baseurl=${BASEURL}/qemu-kvm-ev
gpgcheck=0
enabled=0
EOF

cat > /etc/yum.repos.d/zstack-online-mlnx-ofed.repo << EOF
[zstack-online-mlnx-ofed]
name=zstack-online-mlnx-ofed
baseurl=${BASEURL}/mlnx-ofed
gpgcheck=0
enabled=0
EOF

cat > /etc/yum.repos.d/zstack-online-virtio-win.repo << EOF
[zstack-online-virtio-win]
name=zstack-online-virtio-win
baseurl=${BASEURL}/virtio-win
gpgcheck=0
enabled=0
EOF

# close epel
yum clean all >/dev/null 2>&1
if [ -f /etc/yum.repos.d/epel.repo ]; then
    sed -i 's/enabled=1/enabled=0/g' /etc/yum.repos.d/epel.repo
fi

# install necessary packages
pkg_list="createrepo curl yum-utils"
yum -y --disablerepo=* --enablerepo=zstack-online-base install $${pkg_list} >/dev/null 2>&1 || exit 1

# reposync
mkdir -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/ >/dev/null 2>&1
umount /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/qemu-kvm-ev >/dev/null 2>&1
mv /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Packages /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/ >/dev/null 2>&1
reposync -r zstack-online-base -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/ --norepopath -m -d
reposync -r zstack-online-ceph -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/ceph --norepopath -d
reposync -r zstack-online-uek4 -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/uek4 --norepopath -d
reposync -r zstack-online-galera -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/galera --norepopath -d
reposync -r zstack-online-qemu-kvm-ev -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/qemu-kvm-ev --norepopath -d
reposync -r zstack-online-virtio-win -p /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/virtio-win --norepopath -d
rm -f /etc/yum.repos.d/zstack-online-*.repo

# createrepo
createrepo -g /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/comps.xml /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/ >/dev/null 2>&1 || exit 1
rm -rf /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/repodata >/dev/null 2>&1
mv /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/* /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/ >/dev/null 2>&1
rm -rf /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/Base/ >/dev/null 2>&1
createrepo /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/ceph/ >/dev/null 2>&1 || exit 1
createrepo /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/uek4/ >/dev/null 2>&1 || exit 1
createrepo /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/galera >/dev/null 2>&1 || exit 1
createrepo /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/qemu-kvm-ev >/dev/null 2>&1 || exit 1
createrepo /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/virtio-win >/dev/null 2>&1 || exit 1

# sync .repo_version
echo ${repo_version} > /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/.repo_version

# clean up
rm -f /opt/zstack-dvd/${BASEARCH}/${ZS_RELEASE}/comps.xml
yum clean all >/dev/null 2>&1
'''
        command = "yum --disablerepo=* --enablerepo=zstack-mn repoinfo | grep Repo-baseurl | awk -F ' : ' '{ print $NF }'"
        (status, baseurl, stderr) = shell_return_stdout_stderr(command)
        if status != 0:
            baseurl = 'http://localhost:%s/zstack/static/zstack-dvd/' % ctl.get_mn_port()

        with open('/opt/zstack-dvd/{}/{}/.repo_version'.format(ctl.BASEARCH, ctl.ZS_RELEASE)) as f:
            repoversion = f.readline().strip()

        t = string.Template(sync_repo)
        sync_repo = t.substitute({
            'BASEURL': baseurl.strip(),
            'BASEARCH': ctl.BASEARCH,
            'ZS_RELEASE': ctl.ZS_RELEASE,
            'repo_version': repoversion
        })

        fd, sync_repo_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(sync_repo)

        def clean_up():
            os.remove(sync_repo_path)
        self.install_cleanup_routine(clean_up)

        t = string.Template(yaml)
        if args.yum:
            yum_repo = args.yum
        else:
            yum_repo = 'false'
        yaml = t.substitute({
            'host': host_info.host,
            'install_path': args.install_path,
            'apache_path': apache_tomcat,
            'zstack_path': zstack,
            'pre_script': pre_script_path,
            'pre_script_on_rh6': pre_script_on_rh6_path,
            'post_script': post_script_path,
            'properties_file': ctl.properties_file_path,
            'apache_tomcat_zip_name': apache_tomcat_zip_name,
            'pypi_tar_path': pypi_tar_path,
            'pypi_tar_path_dest': '/tmp/pypi.tar.bz',
            'pypi_path': '/tmp/pypi/',
            'yum_folder': ctl.zstack_home,
            'yum_repo': yum_repo,
            'setup_account': setup_account_path,
            'sync_repo' : sync_repo_path
        })

        ansible(yaml, host_info.host, args.debug, private_key)
        info('successfully installed new management node on machine(%s)' % host_info.host)

class ShowConfiguration(Command):
    def __init__(self):
        super(ShowConfiguration, self).__init__()
        self.name = "show_configuration"
        self.description = "a shortcut that prints contents of zstack.properties to screen"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--pretty', '-p', help='Make configuration prettier', action='store_true', default=False)

    def run(self, args):
        properties = ctl.read_all_properties()
        if args.pretty:
            maxlength = max([len(key[0]) for key in properties])
            ret = [' = '.join([key[0].ljust(maxlength), key[1]]) for key in properties]
        else :
            ret = [' = '.join(map(str, key)) for key in properties]

        info('\n'.join(ret))

class GetConfiguration(Command):
    def __init__(self):
        super(GetConfiguration, self).__init__()
        self.name = "get_configuration"
        self.description = "get one configuration by name"
        ctl.register_command(self)

    def run(self, args):
        if not os.path.exists(ctl.properties_file_path):
            raise CtlError('cannot find properties file(%s)' % ctl.properties_file_path)

        if not ctl.extra_arguments:
            raise CtlError('please input variable name that you want')

        if len(ctl.extra_arguments) > 1:
            raise CtlError('do not enter multiple variables')

        properties = PropertyFile(ctl.properties_file_path)
        value = properties.read_property(ctl.extra_arguments[0])
        if value:
            info(value)
        else :
            raise CtlError('{} is not configured.'.format(ctl.extra_arguments[0]))

class MNServerPortChange(Command):
    def __init__(self):
        super(MNServerPortChange, self).__init__()
        self.name = "change_server_ports"
        self.description = "Modify the port related to mn service. Restart mn after modification to take effect"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--update_value', help='Modified port value', required=True)

    def run(self, args):
        if not os.path.exists(ctl.properties_file_path):
            raise CtlError('cannot find properties file(%s)' % ctl.properties_file_path)
        if not os.path.exists(ctl.ui_properties_file_path):
            raise CtlError('cannot find properties file(%s)' % ctl.ui_properties_file_path)
        if not os.path.exists(ctl.tomcat_xml_file_path):
            raise CtlError('cannot find properties file(%s)' % ctl.tomcat_xml_file_path)
        ctl.write_property('RESTFacade.port', args.update_value)
        ctl.write_ui_property("mn_port", args.update_value)
        original_port = shell(
            ''' awk '/<Connector executor=\"tomcatThreadPool\"  port=\"[0-9]+\"/ { match($0, /port=\"([0-9]+)\"/, arr); print arr[1] }' %s''' % ctl.tomcat_xml_file_path).strip(
            '\t\n\r')
        if len(original_port) == 0:
            error = "tomcat original_port no found"
            logger.debug(error)
            raise CtlError(error)
        shell(
            "sed -i 's/<Connector executor=\"tomcatThreadPool\"  port=\"[0-9]\+\"/<Connector executor=\"tomcatThreadPool\"  port=\"%s\"/' %s" % (
                args.update_value, ctl.tomcat_xml_file_path))
        linux.sync_file(ctl.tomcat_xml_file_path)
        success_info = 'Successfully modify the port from %s to %s, please restart mn to take effect' % (original_port, args.update_value)
        info(success_info)
        logger.debug(success_info)

class SetEnvironmentVariableCmd(Command):
    PATH = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "zstack-ctl/ctl-env")

    def __init__(self):
        super(SetEnvironmentVariableCmd, self).__init__()
        self.name = "setenv"
        self.description = "set variables to zstack-ctl variable file at %s\nExample:\n\tzstack-ctl setenv CATALINA_OPTS='-Xmx8192M'" % self.PATH
        ctl.register_command(self)

    def need_zstack_home(self):
        return False

    def run(self, args):
        if not ctl.extra_arguments:
            raise CtlError('please input variables that are in format of "key=value" split by space')

        if not os.path.isdir(ctl.USER_ZSTACK_HOME_DIR):
            raise CtlError('cannot find home directory(%s) of user "zstack"' % ctl.USER_ZSTACK_HOME_DIR)

        with use_user_zstack():
            path_dir = os.path.dirname(self.PATH)
            if not os.path.isdir(path_dir):
                os.makedirs(path_dir)

            with open(self.PATH, 'a'):
                # create the file if not existing
                pass

        env = PropertyFile(self.PATH)
        arg_str = ' '.join(ctl.extra_arguments)
        env.write_properties([arg_str.split('=', 1)])

class UnsetEnvironmentVariableCmd(Command):
    NAME = 'unsetenv'

    def __init__(self):
        super(UnsetEnvironmentVariableCmd, self).__init__()
        self.name = self.NAME
        self.description = (
            'unset variables in %s' % SetEnvironmentVariableCmd.PATH
        )
        ctl.register_command(self)

    def run(self, args):
        if not os.path.exists(SetEnvironmentVariableCmd.PATH):
            return

        if not ctl.extra_arguments:
            raise CtlError('please input a list of variable names you want to unset')

        env = PropertyFile(SetEnvironmentVariableCmd.PATH)
        env.delete_properties(ctl.extra_arguments)
        info('unset zstack environment variables: %s' % ctl.extra_arguments)


class GetEnvironmentVariableCmd(Command):
    NAME = 'getenv'

    def __init__(self):
        super(GetEnvironmentVariableCmd, self).__init__()
        self.name = self.NAME
        self.description = (
              "get variables from %s" % SetEnvironmentVariableCmd.PATH
        )
        ctl.register_command(self)

    def run(self, args):
        if not os.path.exists(SetEnvironmentVariableCmd.PATH):
            raise CtlError('cannot find the environment variable file at %s' % SetEnvironmentVariableCmd.PATH)

        ret = []
        if ctl.extra_arguments:
            env = PropertyFile(SetEnvironmentVariableCmd.PATH)
            for key in ctl.extra_arguments:
                value = env.read_property(key)
                if value:
                    ret.append('%s=%s' % (key, value))
        else:
            env = PropertyFile(SetEnvironmentVariableCmd.PATH)
            for k, v in env.read_all_properties():
                ret.append('%s=%s' % (k, v))

        info('\n'.join(ret))

# For UI 1.x
class InstallDashboardCmd(Command):
    def __init__(self):
        super(InstallDashboardCmd, self).__init__()
        self.name = "install_ui"
        self.description = "install ZStack Web UI"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='target host IP, for example, 192.168.0.212, to install ZStack web UI; if omitted, it will be installed on local machine')
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)
        parser.add_argument('--yum', help="Use ZStack predefined yum repositories. The valid options include: alibase,aliepel,163base,ustcepel,zstack-local. NOTE: only use it when you know exactly what it does.", default=None)
        parser.add_argument('--force', help="delete existing virtualenv and resinstall zstack ui and all dependencies", action="store_true", default=False)

    def _install_to_local(self, args):
        install_script = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/install.sh")
        if not os.path.isfile(install_script):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % install_script)

        info('found installation script at %s, start installing ZStack web UI' % install_script)
        if args.force:
            shell('bash %s zstack-dashboard force' % install_script)
        else:
            shell('bash %s zstack-dashboard' % install_script)

    def run(self, args):
        if not args.host:
            self._install_to_local(args)
            return

        if not args.yum:
            args.yum = get_yum_repo_from_property()

        tools_path = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/")
        if not os.path.isdir(tools_path):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % tools_path)

        ui_binary = None
        for l in os.listdir(tools_path):
            if l.startswith('zstack_dashboard'):
                ui_binary = l
                break

        if not ui_binary:
            raise CtlError('cannot find zstack-dashboard package under %s, please make sure you have installed ZStack management node' % tools_path)

        ui_binary_path = os.path.join(tools_path, ui_binary)

        pypi_path = os.path.join(ctl.zstack_home, "static/pypi/")
        if not os.path.isdir(pypi_path):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % pypi_path)

        pypi_tar_path = os.path.join(ctl.zstack_home, "static/pypi.tar.bz")
        if not os.path.isfile(pypi_tar_path):
            static_path = os.path.join(ctl.zstack_home, "static")
            os.system('cd %s; tar jcf pypi.tar.bz pypi' % static_path)

        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      virtualenv_root: /var/lib/zstack/virtualenv/zstack-dashboard
      yum_repo: "$yum_repo"

  tasks:
    - name: pre-install script
      when: ansible_os_family == 'RedHat' and yum_repo != 'false'
      script: $pre_install_script

    - name: install Python pip for RedHat OS from user defined repo
      when: ansible_os_family == 'RedHat' and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y libselinux-python python-pip bzip2 python-devel gcc autoconf

    - name: install Python pip for RedHat OS from system repo
      when: ansible_os_family == 'RedHat' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y libselinux-python python-pip bzip2 python-devel gcc autoconf

    - name: copy zstack-dashboard package
      copy: src=$src dest=$dest

    - name: copy pypi tar file
      copy: src=$pypi_tar_path dest=$pypi_tar_path_dest

    - name: untar pypi
      shell: "cd /tmp/; tar jxf $pypi_tar_path_dest"

    - name: install Python pip for Ubuntu
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - python-pip
        - iptables-persistent

    - name: install pip from local source
      shell: "cd $pypi_path/simple/pip/; pip install --ignore-installed pip*.tar.gz"

    - shell: virtualenv --version | grep "12.1.1"
      register: virtualenv_ret
      ignore_errors: True

    - name: install virtualenv
      pip: name=virtualenv version=12.1.1 extra_args="--ignore-installed --trusted-host localhost -i file://$pypi_path/simple"
      when: virtualenv_ret.rc != 0

    - name: create virtualenv
      shell: "rm -rf {{virtualenv_root}} && virtualenv {{virtualenv_root}}"

    - name: install zstack-dashboard
      pip: name=$dest extra_args="--trusted-host localhost -i file://$pypi_path/simple" virtualenv="{{virtualenv_root}}"

'''

        pre_script = configure_yum_repo_script
        fd, pre_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(pre_script)

        def cleanup_prescript():
            os.remove(pre_script_path)

        self.install_cleanup_routine(cleanup_prescript)
        t = string.Template(yaml)
        if args.yum:
            yum_repo = args.yum
        else:
            yum_repo = 'false'
        yaml = t.substitute({
            "src": ui_binary_path,
            "dest": os.path.join('/tmp', ui_binary),
            "host": args.host,
            'pre_install_script': pre_script_path,
            'pypi_tar_path': pypi_tar_path,
            'pypi_tar_path_dest': '/tmp/pypi.tar.bz',
            'pypi_path': '/tmp/pypi/',
            'yum_folder': ctl.zstack_home,
            'yum_repo': yum_repo
        })

        ansible(yaml, args.host, ssh_key=args.ssh_key)

# For UI 2.0
class InstallZstackUiCmd(Command):
    def __init__(self):
        super(InstallZstackUiCmd, self).__init__()
        self.name = "install_ui"
        self.description = "install ZStack web UI"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='target host IP, for example, 192.168.0.212, to install ZStack web UI; if omitted, it will be installed on local machine')
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; If provided, Ansible will use the specified key as private key to SSH login the $host", default=None)
    def _install_to_local(self, args):
        ui_install_log = os.path.join(ctl.ZSTACK_UI_HOME, "logs")
        create_log(ui_install_log,'ui-install.log')
        install_script = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/zstack_ui.bin")
        params = " ".join(sys.argv[2:])
        if not os.path.isfile(install_script):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % install_script)
        install_script = install_script+" "+params
        info('found installation script at %s, start installing ZStack web UI' % install_script)
        shell("runuser -l root -s /bin/bash -c 'bash %s > %s'" % (install_script, os.path.join(ui_install_log,'ui-install.log')))

    def install_mini_ui(self):
        mini_bin = "/opt/zstack-dvd/{}/{}/zstack_mini_server.bin".format(ctl.BASEARCH, ctl.ZS_RELEASE)
        if not os.path.exists(mini_bin):
            raise CtlError('cannot find %s, please make sure you have the mini installation package.' % mini_bin)
        shell('bash {}'.format(mini_bin))

    def run(self, args):
        ui_mode = ctl.read_property('ui_mode')
        if ui_mode == 'mini':
            self.install_mini_ui()

        if not args.host:
            self._install_to_local(args)
            return
        # remote install
        tools_path = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/")
        if not os.path.isdir(tools_path):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % tools_path)

        ui_binary = 'zstack_ui.bin'
        if not ui_binary in os.listdir(tools_path):
            raise CtlError('cannot find zstack-ui package under %s, please make sure you have installed ZStack management node' % tools_path)
        ui_binary_path = os.path.join(tools_path, ui_binary)
        yaml = '''---
- hosts: ${host}
  remote_user: root
  tasks:
    - name: create zstack-ui directory
      shell: "mkdir -p ${ui_home}/tmp"
    - name: copy zstack-ui package
      copy: src=${src} dest=${dest}
    - name: decompress zstack-ui package
      shell: "rm -rf ${ui_home}/tmp; unzip ${dest} -d ${ui_home}/tmp"
'''

        t = string.Template(yaml)
        yaml = t.substitute({
            "src": ui_binary_path,
            "dest": os.path.join(ctl.ZSTACK_UI_HOME, ui_binary),
            "ui_home": ctl.ZSTACK_UI_HOME,
            "host": args.host
        })

        ansible(yaml, args.host, ssh_key=args.ssh_key)

class BootstrapCmd(Command):
    def __init__(self):
        super(BootstrapCmd, self).__init__()
        self.name = 'bootstrap'
        self.description = (
            'create user and group of "zstack" and add "zstack" to sudoers;'
            '\nthis command is only needed by installation script'
            ' and users that install ZStack manually'
        )
        ctl.register_command(self)

    def need_zstack_user(self):
        return False

    def run(self, args):
        shell('id -u zstack 2>/dev/null || (useradd -d %s zstack -s /bin/false && mkdir -p %s && chown -R zstack.zstack %s)' % (ctl.USER_ZSTACK_HOME_DIR, ctl.USER_ZSTACK_HOME_DIR, ctl.USER_ZSTACK_HOME_DIR))
        shell("grep 'zstack' /etc/sudoers || echo 'zstack        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers")
        shell('mkdir -p %s && chown zstack:zstack %s' % (ctl.USER_ZSTACK_HOME_DIR, ctl.USER_ZSTACK_HOME_DIR))


class UpgradeManagementNodeCmd(Command):
    def __init__(self):
        super(UpgradeManagementNodeCmd, self).__init__()
        self.name = "upgrade_management_node"
        self.description = 'upgrade the management node to a specified version'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='IP or DNS name of the machine to upgrade the management node, for example, zstack-ctl upgrade_management_node --host=192.168.0.212 --war-file=/usr/local/zstack/zstack.war, to upgrade ZStack management node to a remote machine', default=None)
        parser.add_argument('--war-file', help='path to zstack.war. A HTTP/HTTPS url or a path to a local zstack.war', required=True)
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def run(self, args):
        error_if_tool_is_missing('unzip')
        need_download = args.war_file.startswith('http')
        if need_download:
            error_if_tool_is_missing('wget')

        upgrade_tmp_dir = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'upgrade', time.strftime('%Y-%m-%d-%H-%M-%S', time.localtime()))
        shell('mkdir -p %s' % upgrade_tmp_dir)

        property_file_backup_path = os.path.join(upgrade_tmp_dir, 'zstack.properties')

        class NewWarFilePath(object):
            self.path = None

        new_war = NewWarFilePath()

        if not need_download:
            new_war.path = expand_path(args.war_file)
            if not os.path.exists(new_war.path):
                raise CtlError('%s not found' % new_war.path)

        def local_upgrade():
            def backup():
                ctl.internal_run('save_config', '--save-to %s' % os.path.dirname(property_file_backup_path))

                shell('cp -r %s %s' % (ctl.zstack_home, upgrade_tmp_dir))
                info('backup %s to %s' % (ctl.zstack_home, upgrade_tmp_dir))

            def download_war_if_needed():
                if need_download:
                    new_war.path = os.path.join(upgrade_tmp_dir, 'new', 'zstack.war')
                    shell_no_pipe('wget --no-check-certificate %s -O %s' % (args.war_file, new_war.path))
                    info('downloaded new zstack.war to %s' % new_war.path)

            def stop_node():
                info('start to stop the management node ...')
                ctl.internal_run('stop_node')

            def upgrade():
                info('start to upgrade the management node ...')
                linux.rm_dir_force(ctl.zstack_home)
                if ctl.zstack_home.endswith('/'):
                    webapp_dir = os.path.dirname(os.path.dirname(ctl.zstack_home))
                else:
                    webapp_dir = os.path.dirname(ctl.zstack_home)

                shell('cp %s %s' % (new_war.path, webapp_dir))
                ShellCmd('unzip %s -d zstack' % os.path.basename(new_war.path), workdir=webapp_dir)()
                #create local repo folder for possible zstack local yum repo
                zstack_dvd_repo = '{}/zstack/static/zstack-repo'.format(webapp_dir)
                shell('rm -f {0}; mkdir -p {0};ln -s /opt/zstack-dvd/x86_64 {0}/x86_64; ln -s /opt/zstack-dvd/aarch64 {0}/aarch64; ln -s /opt/zstack-dvd/mips64el {0}/mips64el; ln -s /opt/zstack-dvd/loongarch64 {0}/loongarch64; chown -R zstack:zstack {0}'.format(zstack_dvd_repo))

            def restore_config():
                info('restoring the zstack.properties ...')
                ctl.internal_run('restore_config', '--restore-from %s' % os.path.dirname(property_file_backup_path))

            def restore_custom_pcidevice_xml():
                info('restoring the customPciDevices.xml ...')
                custom_pcidevice_xml_path = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'apache-tomcat/webapps/zstack/WEB-INF/classes/mevoco/pciDevice/')
                custom_pcidevice_xml_backup_path = os.path.join(upgrade_tmp_dir, 'zstack/WEB-INF/classes/mevoco/pciDevice/customPciDevices.xml')
                if not os.path.isfile(custom_pcidevice_xml_backup_path):
                    info('no backup customPciDevices.xml found')
                    return

                if not os.path.isdir(custom_pcidevice_xml_path):
                    info('%s does not exists' % custom_pcidevice_xml_path)
                    return

                copyfile(custom_pcidevice_xml_backup_path, os.path.join(custom_pcidevice_xml_path, 'customPciDevices.xml'))
                info('successfully restored the customPciDevices.xml')

            def copy_tools():
                info("copy third-party tools to zstack install path ...")
                src_tools_path = "/opt/zstack-dvd/%s/%s/tools" % (ctl.BASEARCH, ctl.ZS_RELEASE)
                dst_tools_path = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools")
                if os.path.exists(src_tools_path):
                    shell("cp -rn %s/* %s >/dev/null 2>&1" % (src_tools_path, dst_tools_path))
                    info("successfully copied third-party tools to zstack install path")

            def install_tools():
                info('upgrading zstack-cli, zstack-ctl; this may cost several minutes ...')
                install_script = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/install.sh")
                if not os.path.isfile(install_script):
                    raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % install_script)

                shell("bash %s zstack-cli" % install_script)
                shell("bash %s zstack-ctl" % install_script)
                info('successfully upgraded zstack-cli, zstack-ctl')

            def save_new_war():
                sdir = os.path.join(ctl.zstack_home, "../../../")
                shell('yes | cp %s %s' % (new_war.path, sdir))

            def chown_to_zstack():
                info('change permission to user zstack')
                shell('chown -R zstack:zstack %s' % os.path.join(ctl.zstack_home, '../../'))

            backup()
            download_war_if_needed()
            stop_node()
            upgrade()
            restore_config()
            restore_custom_pcidevice_xml()
            copy_tools()
            install_tools()
            save_new_war()
            chown_to_zstack()

            info('----------------------------------------------\n'
                 'Successfully upgraded the ZStack management node to a new version.\n'
                 'We backup the old zstack as follows:\n'
                 '\tzstack.properties: %s\n'
                 '\tzstack folder: %s\n'
                 'Please test your new ZStack. If everything is OK and stable, you can manually delete those backup by deleting %s.\n'
                 'Otherwise you can use them to rollback to the previous version\n'
                 '-----------------------------------------------\n' %
                 (property_file_backup_path, os.path.join(upgrade_tmp_dir, 'zstack'), upgrade_tmp_dir))

        def remote_upgrade():
            need_copy = 'true'
            src_war = new_war.path
            dst_war = '/tmp/zstack.war'

            if need_download:
                need_copy = 'false'
                src_war = args.war_file
                dst_war = args.war_file

            upgrade_script = '''
zstack-ctl upgrade_management_node --war-file=$war_file
if [ $$? -ne 0 ]; then
    echo 'failed to upgrade the remote management node'
    exit 1
fi

if [ "$need_copy" == "true" ]; then
    rm -f $war_file
fi
'''
            t = string.Template(upgrade_script)
            upgrade_script = t.substitute({
                'war_file': dst_war,
                'need_copy': need_copy
            })

            fd, upgrade_script_path = tempfile.mkstemp(suffix='.sh')
            os.fdopen(fd, 'w').write(upgrade_script)

            def cleanup_upgrade_script():
                os.remove(upgrade_script_path)

            self.install_cleanup_routine(cleanup_upgrade_script)

            yaml = '''---
- hosts: $host
  remote_user: root

  vars:
    need_copy: "$need_copy"

  tasks:
    - name: copy zstack.war to remote
      copy: src=$src_war dest=$dst_war
      when: need_copy == 'true'

    - name: upgrade management node
      script: $upgrade_script
      register: output
      ignore_errors: yes

    - name: failure
      fail: msg="failed to upgrade the remote management node. {{ output.stdout }} {{ output.stderr }}"
      when: output.rc != 0
'''
            t = string.Template(yaml)
            yaml = t.substitute({
                "src_war": src_war,
                "dst_war": dst_war,
                "host": args.host,
                "need_copy": need_copy,
                "upgrade_script": upgrade_script_path
            })

            info('start to upgrade the remote management node; the process may cost several minutes ...')

            if args.ssh_key is None:
                args.ssh_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa.pub"
            private_key = args.ssh_key.split('.')[0]

            ansible(yaml, args.host, args.debug, ssh_key=private_key)
            info('upgraded the remote management node successfully')


        if args.host:
            remote_upgrade()
        else:
            local_upgrade()

class UpgradeMultiManagementNodeCmd(Command):
    logger_dir = '/var/log/zstack'
    logger_file = 'zstack-ctl.log'
    SpinnerInfo.spinner_status = {'stop_local':False, 'upgrade_local':False , 'start_local':False, 'upgrade':False, 'stop':False, 'start':False}
    def __init__(self):
        super(UpgradeMultiManagementNodeCmd, self).__init__()
        self.name = "upgrade_multi_management_node"
        self.description = 'upgrade the management cluster'
        ctl.register_command(self)

    def start_mn(self, host_post_info):
        command = "zstack-ctl start_node && zstack-ctl start_ui"
        #Ansible finish command will lead mn stop, so use ssh native connection to start mn
        (status, output) = commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s '%s'" %
                                                    (host_post_info.private_key, host_post_info.host, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))

    def install_argparse_arguments(self, parser):
        parser.add_argument('--installer-bin','--bin',
                            help="The new version installer package with absolute path",
                            required=True)
        parser.add_argument('--force', '-F',
                            help="Force upgrade when database upgrading dry-run failed",
                            action='store_true', default=False)

    def run(self, args):
        if os.path.isfile(args.installer_bin) is not True:
            error("Didn't find install package %s" % args.installer_bin)
        create_log(UpgradeMultiManagementNodeCmd.logger_dir, UpgradeMultiManagementNodeCmd.logger_file)
        mn_vo = get_host_list("ManagementNodeVO")
        local_mn_ip = get_default_ip()
        mn_ip_list = []
        cmd = create_check_mgmt_node_command()
        cmd(False)
        if not get_mgmt_node_state_from_result(cmd):
            error("Local management node status is not Running, can't make sure ZStack status is healthy")
        for mn in mn_vo:
            mn_ip_list.append(mn['hostName'])
        mn_ip_list.insert(0, mn_ip_list.pop(mn_ip_list.index(local_mn_ip)))
        all_mn_ip = ' '.join(mn_ip_list)
        info(" Will upgrade all 'Running' management nodes: %s" % colored(all_mn_ip,'green'))
        ssh_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa.pub"
        private_key = ssh_key.split('.')[0]
        inventory_file = ctl.zstack_home + "/../../../ansible/hosts"
        for mn_ip in mn_ip_list:
            if mn_ip != local_mn_ip:
                host_info = HostPostInfo()
                host_info.host = mn_ip
                host_info.private_key = private_key
                host_info.host_inventory =  inventory_file
                host_reachable = check_host_reachable(host_info, True)
                if host_reachable is True:
                    spinner_info = SpinnerInfo()
                    spinner_info.output = "Stop remote management node %s" % mn_ip
                    spinner_info.name = "stop_%s" % mn_ip
                    SpinnerInfo.spinner_status['stop_%s' % mn_ip] = False
                    SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                    SpinnerInfo.spinner_status['stop_%s' % mn_ip] = True
                    ZstackSpinner(spinner_info)
                    command = "zstack-ctl stop_node"
                    run_remote_command(command, host_info)
                else:
                    # running management node will block upgrade process
                    error("Management node %s is unreachable, please sync public key %s to other management nodes" % (mn_ip, ssh_key))
            else:
                spinner_info = SpinnerInfo()
                spinner_info.output = "Stop local management node %s" % mn_ip
                spinner_info.name = "stop_local"
                SpinnerInfo.spinner_status['stop_local'] = False
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['stop_local'] = True
                ZstackSpinner(spinner_info)
                command = "zstack-ctl stop_node"
                shell(command)


        for mn_ip in mn_ip_list:
            host_info = HostPostInfo()
            host_info.host = mn_ip
            host_info.private_key = private_key
            host_info.host_inventory =  inventory_file
            if mn_ip == local_mn_ip:
                spinner_info = SpinnerInfo()
                spinner_info.output = "Upgrade management node on localhost(%s)" % local_mn_ip
                spinner_info.name = 'upgrade_local'
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['upgrade_local'] = True
                ZstackSpinner(spinner_info)
                linux.rm_dir_force("/tmp/zstack_upgrade.lock")
                if args.force is True:
                    shell("bash %s -u -F" % args.installer_bin)
                else:
                    shell("bash %s -u" % args.installer_bin)

                spinner_info = SpinnerInfo()
                spinner_info.output = "Start management node on localhost(%s)" % local_mn_ip
                spinner_info.name = 'start'
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['start_local'] = True
                ZstackSpinner(spinner_info)
                shell("zstack-ctl start_node && zstack-ctl start_ui")

            else:
                spinner_info = SpinnerInfo()
                spinner_info.output = "Upgrade management node on host %s" % mn_ip
                spinner_info.name = 'upgrade'
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['upgrade'] = True
                ZstackSpinner(spinner_info)
                war_file = ctl.zstack_home + "/../../../apache-tomcat/webapps/zstack.war"
                ssh_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa"
                status,output = commands.getstatusoutput("zstack-ctl upgrade_management_node --host %s --ssh-key %s --war-file %s" % (mn_ip, ssh_key, war_file))
                if status != 0:
                    error(output)

                spinner_info = SpinnerInfo()
                spinner_info.output = "Start management node on host %s" % mn_ip
                spinner_info.name = 'start'
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['start'] = True
                ZstackSpinner(spinner_info)
                self.start_mn(host_info)

        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status, False)
        time.sleep(0.3)
        info(colored("All management nodes upgrade successfully!",'blue'))

class UpgradeDbCmd(Command):
    def __init__(self):
        super(UpgradeDbCmd, self).__init__()
        self.name = 'upgrade_db'
        self.description = (
            'upgrade the database from current version to a new version'
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--force', help='bypass management nodes status check.'
                            '\nNOTE: only use it when you know exactly what it does', action='store_true', default=False)
        parser.add_argument('--no-backup', help='do NOT backup the database. If the database is very large and you have manually backup it, using this option will fast the upgrade process. [DEFAULT] false', default=False)
        parser.add_argument('--dry-run', help='Check if db could be upgraded. [DEFAULT] not set', action='store_true', default=False)
        parser.add_argument('--update-schema-version', help='update the schema_version checksum in the environment. [DEFAULT] not set', action='store_true', default=False)

    def run(self, args):
        error_if_tool_is_missing('mysqldump')
        error_if_tool_is_missing('mysql')

        db_url = ctl.get_db_url()
        db_url_params = db_url.split('//')
        db_url = db_url_params[0] + '//' + db_url_params[1].split('/')[0]
        db_url = '%s/zstack' % db_url.rstrip('/')

        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()

        flyway_path = os.path.join(ctl.zstack_home, 'WEB-INF/classes/tools/flyway-3.2.1/flyway')
        if not os.path.exists(flyway_path):
            raise CtlError('cannot find %s. Have you run upgrade_management_node?' % flyway_path)

        upgrading_schema_dir = os.path.join(ctl.zstack_home, 'WEB-INF/classes/db/upgrade/')
        if not os.path.exists(upgrading_schema_dir):
            raise CtlError('cannot find %s. Have you run upgrade_management_node?' % upgrading_schema_dir)

        ctl.check_if_management_node_has_stopped(args.force)

        if args.dry_run:
            info('Dry run finished. Database could be upgraded. ')
            return True

        def update_db_config():
            update_db_config_script = mysql_db_config_script

            fd, update_db_config_script_path = tempfile.mkstemp()
            os.fdopen(fd, 'w').write(update_db_config_script)
            info('update_db_config_script_path is: %s' % update_db_config_script_path)
            ShellCmd('bash %s' % update_db_config_script_path)()
            os.remove(update_db_config_script_path)

        def backup_current_database():
            if args.no_backup:
                return

            info('start to backup the database ...')

            db_backup_path = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'db_backup', time.strftime('%Y-%m-%d-%H-%M-%S', time.localtime()), 'backup.sql')
            shell('mkdir -p %s' % os.path.dirname(db_backup_path))
            if db_password:
                shell('mysqldump -u %s -p%s --host %s --port %s -d zstack > %s' % (db_user, db_password, db_hostname, db_port, db_backup_path))
                shell('mysqldump -u %s -p%s --host %s --port %s zstack %s >> %s' % (db_user, db_password, db_hostname, db_port, mysqldump_skip_tables, db_backup_path))
            else:
                shell('mysqldump -u %s --host %s --port %s -d zstack > %s' % (db_user, db_hostname, db_port, db_backup_path))
                shell('mysqldump -u %s --host %s --port %s zstack %s >> %s' % (db_user, db_hostname, db_port, mysqldump_skip_tables, db_backup_path))

            info('successfully backup the database to %s' % db_backup_path)

        def create_schema_version_table_if_needed():
            if db_password:
                out = shell('''mysql -u %s -p%s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_password, db_hostname, db_port))
            else:
                out = shell('''mysql -u %s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_hostname, db_port))

            if 'schema_version' in out:
                return

            info('version table "schema_version" is not existing; initializing a new version table first')

            if db_password:
                shell_no_pipe('bash %s baseline -baselineVersion=0.6 -baselineDescription="0.6 version" -user=%s -password=%s -url=%s' %
                      (flyway_path, db_user, db_password, db_url))
            else:
                shell_no_pipe('bash %s baseline -baselineVersion=0.6 -baselineDescription="0.6 version" -user=%s -url=%s' %
                      (flyway_path, db_user, db_url))

        def execute_sql(sql):
            if db_password:
                shell('''mysql -u %s -p%s --host %s --port %s -t zstack -e "%s"''' %
                            (db_user, db_password, db_hostname, db_port, sql))
            else:
                shell('''mysql -u %s --host %s --port %s -t zstack -e "%s"''' %
                            (db_user, db_hostname, db_port, sql))

        def migrate():
            try:
                schema_path = 'filesystem:%s' % upgrading_schema_dir

                if db_password:
                    shell_no_pipe('bash %s migrate -outOfOrder=true -user=%s -password=%s -url=%s -locations=%s' % (
                    flyway_path, db_user, db_password, db_url, schema_path))
                else:
                    shell_no_pipe('bash %s migrate -outOfOrder=true -user=%s -url=%s -locations=%s' % (
                    flyway_path, db_user, db_url, schema_path))
            except Exception as e:
                sql = "update schema_version set checksum = 249136114 where script = 'V3.5.0.1__schema.sql' and checksum = -1670610242"
                execute_sql(sql)
                raise e

            info('Successfully upgraded the database to the latest version.\n')

        update_db_config()
        backup_current_database()
        create_schema_version_table_if_needed()

        # fix ZSTAC-23352
        if args.update_schema_version:
            update_sql = "update schema_version set checksum = -1670610242 where script = 'V3.5.0.1__schema.sql' and checksum = 249136114"
            execute_sql(update_sql)

        # fix MINI-1498
        update_sql = "update schema_version set checksum = '-1450264399' where script = 'V3.6.0__schema.sql' and checksum = '-111240960'"
        execute_sql(update_sql)

        migrate()

class UpgradeUIDbCmd(Command):
    def __init__(self):
        super(UpgradeUIDbCmd, self).__init__()
        self.name = 'upgrade_ui_db'
        self.description = (
            'upgrade the zstack_ui database from current version to a new version'
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--force', help='bypass zstack ui status check.'
                            '\nNOTE: only use it when you know exactly what it does', action='store_true', default=False)
        parser.add_argument('--no-backup', help='do NOT backup the zstack_ui database. If the database is very large and you have manually backup it, using this option will fast the upgrade process. [DEFAULT] false', default=False)
        parser.add_argument('--dry-run', help='Check if zstack_ui database could be upgraded. [DEFAULT] not set', action='store_true', default=False)

    def run(self, args):
        error_if_tool_is_missing('mysqldump')
        error_if_tool_is_missing('mysql')

        db_url = ctl.get_ui_db_url()
        db_url_params = db_url.split('//')
        db_url = db_url_params[0] + '//' + db_url_params[1].split('/')[0]
        db_url = '%s/zstack_ui' % db_url.rstrip('/')

        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal(ui=True)

        flyway_path = os.path.join(ctl.zstack_home, 'WEB-INF/classes/tools/flyway-3.2.1/flyway')
        if not os.path.exists(flyway_path):
            raise CtlError('cannot find %s. Have you run upgrade_management_node?' % flyway_path)

        upgrading_schema_dir = Ctl.ZSTACK_UI_DB_MIGRATE
        if not os.path.exists(upgrading_schema_dir):
            raise CtlError('cannot find %s' % upgrading_schema_dir)

        if not args.force:
            (status, output)= commands.getstatusoutput("zstack-ctl ui_status")
            if status == 0 and 'Running' in output:
                raise CtlError('ZStack UI is still running. Please stop it before upgrade zstack_ui database.')

        if args.dry_run:
            info('Dry run finished. zstack_ui database could be upgraded. ')
            return True

        def backup_current_database():
            if args.no_backup:
                return

            info('start to backup the zstack_ui database ...')

            db_backup_path = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'db_backup', time.strftime('%Y-%m-%d-%H-%M-%S', time.localtime()), 'ui_backup.sql')
            shell('mkdir -p %s' % os.path.dirname(db_backup_path))
            if db_password:
                shell('mysqldump -u %s -p%s --host %s --port %s zstack_ui > %s' % (db_user, db_password, db_hostname, db_port, db_backup_path))
            else:
                shell('mysqldump -u %s --host %s --port %s zstack_ui > %s' % (db_user, db_hostname, db_port, db_backup_path))

            info('successfully backup the zstack_ui database to %s' % db_backup_path)

        def create_schema_version_table_if_needed():
            if db_password:
                out = shell('''mysql -u %s -p%s --host %s --port %s -t zstack_ui -e "show tables like 'schema_version'"''' %
                            (db_user, db_password, db_hostname, db_port))
            else:
                out = shell('''mysql -u %s --host %s --port %s -t zstack_ui -e "show tables like 'schema_version'"''' %
                            (db_user, db_hostname, db_port))

            if 'schema_version' in out:
                return

            info('version table "schema_version" is not existing; initializing a new version table first')

            if db_password:
                shell_no_pipe('bash %s baseline -baselineVersion=2.3.1 -baselineDescription="2.3.1 version" -user=%s -password=%s -url=%s' %
                      (flyway_path, db_user, db_password, db_url))
            else:
                shell_no_pipe('bash %s baseline -baselineVersion=2.3.1 -baselineDescription="2.3.1 version" -user=%s -url=%s' %
                      (flyway_path, db_user, db_url))

        def migrate():
            schema_path = 'filesystem:%s' % upgrading_schema_dir

            if db_password:
                shell_no_pipe('bash %s migrate -outOfOrder=true -user=%s -password=%s -url=%s -locations=%s' % (flyway_path, db_user, db_password, db_url, schema_path))
                shell_no_pipe('bash %s %s %s %s %s' % (ctl.ZSTACK_UI_DB_MIGRATE_SH,db_user,db_password, db_hostname,db_port))
            else:
                shell_no_pipe('bash %s migrate -outOfOrder=true -user=%s -url=%s -locations=%s' % (flyway_path, db_user, db_url, schema_path))
                shell_no_pipe('bash %s %s %s %s %s' % (ctl.ZSTACK_UI_DB_MIGRATE_SH,db_user,'zstack.ui.password', db_hostname,db_port))

            info('Successfully upgraded the zstack_ui database to the latest version.\n')

        backup_current_database()
        create_schema_version_table_if_needed()
        migrate()

class UpgradeCtlCmd(Command):
    def __init__(self):
        super(UpgradeCtlCmd, self).__init__()
        self.name = 'upgrade_ctl'
        self.description = (
            'upgrade the zstack-ctl to a new version'
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--package', help='the path to the new zstack-ctl package', required=True)

    def run(self, args):
        error_if_tool_is_missing('pip')

        path = expand_path(args.package)
        if not os.path.exists(path):
            raise CtlError('%s not found' % path)

        pypi_path = os.path.join(ctl.zstack_home, "static/pypi/")
        if not os.path.isdir(pypi_path):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % pypi_path)

        install_script = '''set -e
which virtualenv &>/dev/null
if [ $$? != 0 ]; then
    pip install -i file://$pypi_path/simple --trusted-host localhost virtualenv
fi

CTL_VIRENV_PATH=/var/lib/zstack/virtualenv/zstackctl
rm -rf $$CTL_VIRENV_PATH
virtualenv $$CTL_VIRENV_PATH
. $$CTL_VIRENV_PATH/bin/activate

pip install -i file://$pypi_path/simple --trusted-host --ignore-installed $package || exit 1
chmod +x /usr/bin/zstack-ctl
'''

        script(install_script, {"pypi_path": pypi_path, "package": args.package})
        info('successfully upgraded zstack-ctl to %s' % args.package)

class RollbackManagementNodeCmd(Command):
    def __init__(self):
        super(RollbackManagementNodeCmd, self).__init__()
        self.name = "rollback_management_node"
        self.description = "rollback the management node to a previous version if the upgrade fails"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='the IP or DNS name of machine to rollback the management node')
        parser.add_argument('--war-file', help='path to zstack.war. A HTTP/HTTPS url or a path to a local zstack.war', required=True)
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)
        parser.add_argument('--property-file', help="the path to zstack.properties. If omitted, the current zstack.properties will be used", default=None)

    def run(self, args):
        error_if_tool_is_missing('unzip')

        rollback_tmp_dir = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'rollback', time.strftime('%Y-%m-%d-%H-%M-%S', time.localtime()))
        shell('mkdir -p %s' % rollback_tmp_dir)
        need_download = args.war_file.startswith('http')

        class Info(object):
            def __init__(self):
                self.war_path = None
                self.property_file = None

        rollbackinfo = Info()

        def local_rollback():
            def backup_current_zstack():
                info('start to backup the current zstack ...')
                shell('cp -r %s %s' % (ctl.zstack_home, rollback_tmp_dir))
                info('backup %s to %s' % (ctl.zstack_home, rollback_tmp_dir))
                info('successfully backup the current zstack to %s' % os.path.join(rollback_tmp_dir, os.path.basename(ctl.zstack_home)))

            def download_war_if_needed():
                if need_download:
                    rollbackinfo.war_path = os.path.join(rollback_tmp_dir, 'zstack.war')
                    shell_no_pipe('wget --no-check-certificate %s -O %s' % (args.war_file, rollbackinfo.war_path))
                    info('downloaded zstack.war to %s' % rollbackinfo.war_path)
                else:
                    rollbackinfo.war_path = expand_path(args.war_file)
                    if not os.path.exists(rollbackinfo.war_path):
                        raise CtlError('%s not found' % rollbackinfo.war_path)

            def save_property_file_if_needed():
                if not args.property_file:
                    ctl.internal_run('save_config', '--save-to %s' % rollback_tmp_dir)
                    rollbackinfo.property_file = os.path.join(rollback_tmp_dir, 'zstack.properties')
                else:
                    rollbackinfo.property_file = args.property_file
                    if not os.path.exists(rollbackinfo.property_file):
                        raise CtlError('%s not found' % rollbackinfo.property_file)

            def stop_node():
                info('start to stop the management node ...')
                ctl.internal_run('stop_node')

            def rollback():
                info('start to rollback the management node ...')
                linux.rm_dir_force(ctl.zstack_home)
                shell('unzip %s -d %s' % (rollbackinfo.war_path, ctl.zstack_home))

            def restore_config():
                info('restoring the zstack.properties ...')
                ctl.internal_run('restore_config', '--restore-from %s' % rollbackinfo.property_file)

            def install_tools():
                info('rollback zstack-cli, zstack-ctl to the previous version. This may cost several minutes ...')
                install_script = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/install.sh")
                if not os.path.isfile(install_script):
                    raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % install_script)

                shell("bash %s zstack-cli" % install_script)
                shell("bash %s zstack-ctl" % install_script)
                info('successfully upgraded zstack-cli, zstack-ctl')

            backup_current_zstack()
            download_war_if_needed()
            save_property_file_if_needed()
            stop_node()
            rollback()
            restore_config()
            install_tools()

            info('----------------------------------------------\n'
                 'Successfully rollback the ZStack management node to a previous version.\n'
                 'We backup the current zstack as follows:\n'
                 '\tzstack.properties: %s\n'
                 '\tzstack folder: %s\n'
                 'Please test your ZStack. If everything is OK and stable, you can manually delete those backup by deleting %s.\n'
                 '-----------------------------------------------\n' %
                 (rollbackinfo.property_file, os.path.join(rollback_tmp_dir, os.path.basename(ctl.zstack_home)), rollback_tmp_dir))

        def remote_rollback():
            error_if_tool_is_missing('wget')

            need_copy = 'true'
            src_war = rollbackinfo.war_path
            dst_war = '/tmp/zstack.war'

            if need_download:
                need_copy = 'false'
                src_war = args.war_file
                dst_war = args.war_file

            rollback_script = '''
zstack-ctl rollback_management_node --war-file=$war_file
if [ $$? -ne 0 ]; then
    echo 'failed to rollback the remote management node'
    exit 1
fi

if [ "$need_copy" == "true" ]; then
    rm -f $war_file
fi
'''

            t = string.Template(rollback_script)
            rollback_script = t.substitute({
                'war_file': dst_war,
                'need_copy': need_copy
            })

            fd, rollback_script_path = tempfile.mkstemp(suffix='.sh')
            os.fdopen(fd, 'w').write(rollback_script)

            def cleanup_rollback_script():
                os.remove(rollback_script_path)

            self.install_cleanup_routine(cleanup_rollback_script)

            yaml = '''---
- hosts: $host
  remote_user: root

  vars:
    need_copy: "$need_copy"

  tasks:
    - name: copy zstack.war to remote
      copy: src=$src_war dest=$dst_war
      when: need_copy == 'true'

    - name: rollback the management node
      script: $rollback_script
      register: output
      ignore_errors: yes

    - name: failure
      fail: msg="failed to rollback the remote management node. {{ output.stdout }} {{ output.stderr }}"
      when: output.rc != 0
'''

            t = string.Template(yaml)
            yaml = t.substitute({
                "src_war": src_war,
                "dst_war": dst_war,
                "host": args.host,
                "need_copy": need_copy,
                "rollback_script": rollback_script_path
            })

            info('start to rollback the remote management node; the process may cost several minutes ...')
            ansible(yaml, args.host, args.debug, ssh_key=args.ssh_key)
            info('successfully rollback the remote management node')

        if args.host:
            remote_rollback()
        else:
            local_rollback()

class RollbackDatabaseCmd(Command):
    def __init__(self):
        super(RollbackDatabaseCmd, self).__init__()
        self.name = 'rollback_db'
        self.description = "rollback the database to the previous version if the upgrade fails"
        self.sensitive_args = ['--root-password']
        self.hide = True # should use restore_mysql rather than rollback_db!
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--db-dump', help="the previous database dump file", required=True)
        parser.add_argument('--root-password', help="the password for mysql root user. [DEFAULT] empty password")
        parser.add_argument('--force', help='bypass management nodes status check.'
                            '\nNOTE: only use it when you know exactly what it does', action='store_true', default=False)

    def run(self, args):
        error_if_tool_is_missing('mysql')

        ctl.check_if_management_node_has_stopped(args.force)

        if not os.path.exists(args.db_dump):
            raise CtlError('%s not found' % args.db_dump)

        host, port, _, _ = ctl.get_live_mysql_portal()

        if args.root_password:
            cmd = ShellCmd('mysql -u root -p%s --host %s --port %s -e "select 1"' % (args.root_password, host, port))
        else:
            cmd = ShellCmd('mysql -u root --host %s --port %s -e "select 1"' % (host, port))

        cmd(False)
        if cmd.return_code != 0:
            error_not_exit('failed to test the mysql server. You may have provided a wrong password of the root user. Please use --root-password to provide the correct password')
            cmd.raise_error()

        info('start to rollback the database ...')

        if args.root_password:
            shell('mysql -u root -p%s --host %s --port %s -t zstack < %s' % (args.root_password, host, port, args.db_dump))
        else:
            shell('mysql -u root --host %s --port %s -t zstack < %s' % (host, port, args.db_dump))

        info('successfully rollback the database to the dump file %s' % args.db_dump)

# For UI 1.x
class StopDashboardCmd(Command):
    def __init__(self):
        super(StopDashboardCmd, self).__init__()
        self.name = 'stop_ui'
        self.description = "stop UI server on the local or remote host"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')

    def _remote_stop(self, host):
        cmd = '/etc/init.d/zstack-dashboard stop'
        ssh_run_no_pipe(host, cmd)

    def run(self, args):
        if args.host != 'localhost':
            self._remote_stop(args.host)
            return

        pidfile = '/var/run/zstack/zstack-dashboard.pid'
        if os.path.exists(pidfile):
            with open(pidfile, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                kill_process(pid)

        def stop_all():
            pid = find_process_by_cmdline('zstack_dashboard')
            if pid:
                kill_process(pid, signal.SIGKILL)
                stop_all()
            else:
                return

        stop_all()
        info('successfully stopped the UI server')

# For UI 2.0
class StopUiCmd(Command):
    USER_ZSTACK_HOME_DIR = os.path.expanduser('~zstack')
    ZSTACK_UI_HOME = os.path.join(USER_ZSTACK_HOME_DIR, 'zstack-ui/')
    ZSTACK_UI_START = os.path.join(ZSTACK_UI_HOME, 'scripts/start.sh')
    ZSTACK_UI_STOP = os.path.join(ZSTACK_UI_HOME, 'scripts/stop.sh')
    ZSTACK_UI_STATUS = os.path.join(ZSTACK_UI_HOME, 'scripts/status.sh')
    def __init__(self):
        super(StopUiCmd, self).__init__()
        self.name = 'stop_ui'
        self.description = "stop UI server on the local or remote host"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')

    def _remote_stop(self, host):
        cmd = 'zstack-ctl stop_ui'
        ssh_run_no_pipe(host, cmd)

    def stop_zstack_ui(self, args, show_info=True):
        if args.host != 'localhost':
            self._remote_stop(args.host)
            return
        stop_sh = 'runuser -l root -s /bin/bash -c "bash %s"' % StopUiCmd.ZSTACK_UI_STOP
        status_sh = 'runuser -l root -s /bin/bash -c "bash %s"' % StopUiCmd.ZSTACK_UI_STATUS
        (stop_code, stop_output) = commands.getstatusoutput(stop_sh)
        if stop_code != 0:
            info('failed to stop UI server since '+ stop_output)
            return
        portfile = '/var/run/zstack/zstack-ui.port'
        # kill pid by port
        if os.path.exists(portfile):
            with open(portfile, 'r') as fd2:
                port = fd2.readline()
                port = port.strip(' \t\n\r')
        else:
            port = '5000'
        (_, pids) = commands.getstatusoutput("netstat -lnp | grep ':%s' |  awk '{sub(/\/.*/,""); print $NF}'" % port)
        if _ == 0 and pids.strip() != '':
            info("find pids %s at ui port: %s, kill it" % (pids,port))
            logger.debug("find pids %s at ui port: %s, kill it" % (pids,port))
            commands.getstatusoutput("echo '%s' | xargs kill -9" % pids)
        (status_code, status_output) = commands.getstatusoutput(status_sh)
        # some server not inactive got 512
        if status_code == 512:
            info('failed to stop UI server since '+ status_output)
            return
        def clean_pid_port():
            shell('rm -f %s' % portfile)

        if show_info:
            info('successfully stopped the UI server')

    def stop_mini_ui(self):
        shell_return("systemctl stop zstack-mini")
        check_status = "zstack-ctl ui_status"
        (status_code, status_output) = commands.getstatusoutput(check_status)
        if status_code != 0 or "Running" in status_output:
            info('failed to stop MINI UI server on the localhost. Use zstack-ctl stop_ui to restart it.')
            return False

        if "Stopped" in status_output:
            mini_pid = get_ui_pid('mini')
            if mini_pid:
                kill_process(pid, signal.SIGKILL)
            linux.rm_dir_force("/var/run/zstack/zstack-mini-ui.port")
            linux.rm_dir_force("/var/run/zstack/zstack-mini-ui.pid")
            info('successfully stopped the MINI UI server')
            return True

    def run(self, args):
        ui_mode = ctl.read_property('ui_mode')
        if ui_mode == "mini":
            self.stop_zstack_ui(args, show_info=False)
            self.stop_mini_ui()
        else :
            self.stop_zstack_ui(args)

# For VDI UI 2.1
class StopVDIUiCmd(Command):
    def __init__(self):
        super(StopVDIUiCmd, self).__init__()
        self.name = 'stop_vdi'
        self.description = "stop VDI server on the local host"
        ctl.register_command(self)

    def run(self, args):
        pidfile = '/var/run/zstack/zstack-vdi.pid'
        if os.path.exists(pidfile):
            with open(pidfile, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                kill_process(pid)

        def stop_all():
            pid = find_process_by_cmdline('zstack-vdi')
            if pid:
                kill_process(pid, signal.SIGKILL)
                stop_all()
            else:
                return

        stop_all()
        info('successfully stopped the VDI server')

# For UI 1.x
class DashboardStatusCmd(Command):
    def __init__(self):
        super(DashboardStatusCmd, self).__init__()
        self.name = "ui_status"
        self.description = "check the UI server status on the local or remote host."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')
        parser.add_argument('--quiet', '-q', help='Do not log this action.', action='store_true', default=False)

    def _remote_status(self, host):
        cmd = '/etc/init.d/zstack-dashboard status'
        ssh_run_no_pipe(host, cmd)

    def run(self, args):
        self.quiet = args.quiet
        if args.host != 'localhost':
            self._remote_status(args.host)
            return

        ha_info_file = '/var/lib/zstack/ha/ha.yaml'
        pidfile = '/var/run/zstack/zstack-dashboard.pid'
        portfile = '/var/run/zstack/zstack-dashboard.port'
        if os.path.exists(pidfile):
            with open(pidfile, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                check_pid_cmd = ShellCmd('ps -p %s > /dev/null' % pid)
                check_pid_cmd(is_exception=False)
                if check_pid_cmd.return_code == 0:
                    if os.path.exists(ha_info_file):
                        with open(ha_info_file, 'r') as fd2:
                            ha_conf = yaml.load(fd2)
                            if check_ip_port(ha_conf['vip'], 8888):
                                info('UI status: %s [PID:%s] http://%s:8888' % (colored('Running', 'green'), pid, ha_conf['vip']))
                            else:
                                info('UI status: %s' % colored('Unknown', 'yellow'))
                            return
                    default_ip = get_default_ip()
                    if not default_ip:
                        info('UI status: %s [PID:%s]' % (colored('Running', 'green'), pid))
                    else:
                        if os.path.exists(portfile):
                            with open(portfile, 'r') as fd2:
                                port = fd2.readline()
                                port = port.strip(' \t\n\r')
                        else:
                            port = 5000
                        info('UI status: %s [PID:%s] http://%s:%s' % (colored('Running', 'green'), pid, default_ip, port))
                    return

        pid = find_process_by_cmdline('zstack_dashboard')
        if pid:
            info('UI status: %s [PID: %s]' % (colored('Zombie', 'yellow'), pid))
        else:
            info('UI status: %s [PID: %s]' % (colored('Stopped', 'red'), pid))

def get_ui_pid(ui_mode='zstack'):
    # no need to consider ha because it's not supported any more
    # ha_info_file = '/var/lib/zstack/ha/ha.yaml'
    pidfile = '/var/run/zstack/zstack-ui.pid'
    if ui_mode == 'mini':
        pidfile = '/var/run/zstack/zstack-mini-ui.pid'
    if os.path.exists(pidfile):
        with open(pidfile, 'r') as fd:
            pid = fd.readline().strip()
            if os.path.exists('/proc/%s' % pid):
                return pid

# For UI 2.0
class UiStatusCmd(Command):
    USER_ZSTACK_HOME_DIR = os.path.expanduser('~zstack')
    ZSTACK_UI_HOME = os.path.join(USER_ZSTACK_HOME_DIR, 'zstack-ui/')
    ZSTACK_UI_STATUS = os.path.join(ZSTACK_UI_HOME, 'scripts/status.sh')
    ZSTACK_UI_SSL = 'http'
    def __init__(self):
        super(UiStatusCmd, self).__init__()
        self.name = "ui_status"
        self.description = "check the UI server status on the local or remote host."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')
        parser.add_argument('--quiet', '-q', help='Do not log this action.', action='store_true', default=False)

    def _remote_status(self, host):
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl ui_status"' % host)

    def run(self, args):
        self.quiet = args.quiet
        if args.host != 'localhost':
            self._remote_status(args.host)
            return

        ui_mode = ctl.read_property('ui_mode')
        # no need to consider ha because it's not supported any more
        #ha_info_file = '/var/lib/zstack/ha/ha.yaml'
        portfile = '/var/run/zstack/zstack-ui.port'
        ui_port = 5000
        if ui_mode == "mini":
            portfile = '/var/run/zstack/zstack-mini-ui.port'
            ui_port = 8200
        if os.path.exists(portfile):
            with open(portfile, 'r') as fd2:
                port = fd2.readline()
                port = port.strip(' \t\n\r')
        else:
            port = ui_port

        def write_status(status):
            info('UI status: %s' % status)
        if ui_mode == "mini":
            pid = get_ui_pid(ui_mode)
            check_pid_cmd = ShellCmd('ps %s' % pid)
            output = check_pid_cmd(is_exception=False)
            cmd = create_check_ui_status_command(ui_port=ui_port, if_https='--ssl.enabled=true' in output)

            if not cmd:
                write_status('cannot detect status, no wget and curl installed')
                return

            cmd(False)

            if cmd.return_code != 0:
                if cmd.stdout or 'Failed' in cmd.stdout and pid:
                    write_status('Starting, should be ready in a few seconds')
                elif pid:
                    write_status(
                        '%s, the ui seems to become zombie as it stops responding APIs but the '
                        'process(PID: %s) is still running. Please stop the node using zstack-ctl stop_ui' %
                        (colored('Zombie', 'yellow'), pid))
                else:
                    write_status(colored('Stopped', 'red'))
                return False
            elif 'UP' in cmd.stdout:
                default_ip = get_ui_address()

                if not default_ip:
                    info('UI status: %s [PID:%s]' % (colored('Running', 'green'), pid))
                else:
                    http = 'https' if '--ssl.enabled=true' in output else 'http'
                    info('UI status: %s [PID:%s] %s://%s:%s' % (
                        colored('Running', 'green'), pid, http, default_ip, port))
            else:
                write_status(colored('Unknown', 'yellow'))
            return True
        default_protcol='http'
        if os.path.exists(StartUiCmd.HTTP_FILE):
            with open(StartUiCmd.HTTP_FILE, 'r') as fd2:
                default_protcol = fd2.readline()
                default_protcol = default_protcol.strip(' \t\n\r')
        cmd = ShellCmd("runuser -l root -s /bin/bash -c 'bash %s %s://%s:%s'" %
                       (UiStatusCmd.ZSTACK_UI_STATUS, default_protcol, '127.0.0.1', port), pipe=False)
        cmd(False)
        if cmd.return_code != 0:
            write_status(cmd.stdout)
            return False
        else:
            default_ip = get_ui_address()
            output = shell_return_stdout_stderr(
                "systemctl show --property MainPID  zstack-ui-nginx.service | awk -F= '{printf $2}'")
            output = output[1]
            if not default_ip:
                info('UI status: %s [PID:%s] ' % (colored('Running', 'green'),output))
            else:
                if os.path.exists(StartUiCmd.HTTP_FILE):
                    with open(StartUiCmd.HTTP_FILE, 'r') as fd2:
                        protcol = fd2.readline()
                        protcol = protcol.strip(' \t\n\r')
                        info('UI status: %s [PID:%s] %s://%s:%s' % (
                            colored('Running', 'green'),output, protcol, default_ip, port))

# For VDI UI 2.1
class VDIUiStatusCmd(Command):
    def __init__(self):
        super(VDIUiStatusCmd, self).__init__()
        self.name = "vdi_status"
        self.description = "check the VDI server status on the local host."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--quiet', '-q', help='Do not log this action.', action='store_true', default=False)

    def run(self, args):
        self.quiet = args.quiet
        pidfile = '/var/run/zstack/zstack-vdi.pid'
        portfile = '/var/run/zstack/zstack-vdi.port'
        port = 9000
        if os.path.exists(pidfile):
            with open(pidfile, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                check_pid_cmd = ShellCmd('ps -p %s > /dev/null' % pid)
                check_pid_cmd(is_exception=False)
                if check_pid_cmd.return_code == 0:
                    default_ip = get_default_ip()
                    if not default_ip:
                        info('VDI status: %s [PID:%s] http://%s:%s' % (colored('Running', 'green'), pid, default_ip,port))
                    else:
                        if os.path.exists(portfile):
                            with open(portfile, 'r') as fd2:
                                port = fd2.readline()
                                port = port.strip(' \t\n\r')
                        info('VDI UI status: %s [PID:%s] http://%s:%s' % (colored('Running', 'green'), pid, default_ip,port))
                    return

        pid = find_process_by_cmdline('zstack-vdi')
        if pid:
            info('VDI UI status: %s [PID: %s]' % (colored('Zombie', 'yellow'), pid))
        else:
            info('VDI UI status: %s [PID: %s]' % (colored('Stopped', 'red'), pid))

def mysql(cmd, db_hostname = None):
    (db_hostname_origin, db_port, db_user, db_password) = ctl.get_live_mysql_portal()
    db_hostname = db_hostname_origin if db_hostname else db_hostname_origin
    if db_hostname == "localhost" or db_hostname == "127.0.0.1" or (db_hostname in RestoreMysqlCmd.all_local_ip):
        db_hostname = ""
    else:
        db_hostname = "--host %s" % db_hostname
    command = "mysql -uzstack --password=%s -P %s %s zstack -e \"%s\"" % (shell_quote(db_password), db_port, db_hostname, cmd)
    r, o, e = shell_return_stdout_stderr(command)
    if r == 0:
        return o.strip()
    elif db_hostname != "":
        err = list()
        err.append('failed to execute shell command: %s' % command)
        err.append('return code: %s' % r)
        err.append('stdout: %s' % o)
        err.append('stderr: %s' % e)
        raise CtlError('\n'.join(err))
    else:
        db_hostname = "--host %s" % db_hostname_origin
        command = "mysql -uzstack --password=%s -P %s %s zstack -e \"%s\"" % (shell_quote(db_password), db_port, db_hostname, cmd)
        return shell(command).strip()


class CleanAnsibleCacheCmd(Command):
    def __init__(self):
        super(CleanAnsibleCacheCmd, self).__init__()
        self.name = "clean_ansible_cache"
        self.description = "clean ansible cache(.ansible.cache/) for system info"
        ctl.register_command(self)
    def run(self, args):
        cache_dir = os.path.join("/var/lib/zstack", ".ansible.cache")
        rmtree(cache_dir)


class RemovePrometheusDataCmd(Command):
    def __init__(self):
        super(RemovePrometheusDataCmd, self).__init__()
        self.name = "remove_prometheus_data"
        self.description = "remove prometheus corrupt data"
        ctl.register_command(self)

    def run(self, args):
        doDelete = False
        while True:
            answer = input("remove promethues data? (yes or no)\n")
            if any(answer.lower() == f for f in ["yes", 'y']):
                doDelete = True
                break
            elif any(answer.lower() == f for f in ['no', 'n']):
                break
            else:
                info('Please enter yes or no')

        if not doDelete:
            return

        # for prometheus 2.9.2
        data_path = "/var/lib/zstack/prometheus/data2"
        if os.path.exists(data_path):
            shell_return("systemctl stop prometheus2")
            rmtree(data_path)

        # for prometheus 1.8.2
        data_path = "/var/lib/zstack/prometheus/data"
        if os.path.exists(data_path):
            shell_return("systemctl stop prometheus")
            rmtree(data_path)


class ShowSessionCmd(Command):
    def __init__(self):
        super(ShowSessionCmd, self).__init__()
        self.name = "show_session_list"
        self.description = "show user session list"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--account', '-c', help='Show the designated account session lists')
    def run(self, args):
        command = "select a.name, count(1) from AccountVO a, SessionVO s where s.accountUuid = a.uuid group by a.name"
        result = mysql(command)
        if result is not None:
            output = result.splitlines()
            info("account sessions")
            info("---------------")
            count = 0
            for o in output[1:]:
                session = o.split()
                size = len(session)
                if args.account is None:
                    info(o)
                else:
                    if args.account.replace(" ", "") == "".join(session[:size - 1]):
                        info(o)
                    else:
                        continue
                count = int(session[size-1]) + count
            info("---------------")
            info("total   %d" % count)

class DropSessionCmd(Command):
    def __init__(self):
        super(DropSessionCmd, self).__init__()
        self.name = "drop_account_session"
        self.description = "drop account session"
        ctl.register_command(self)
    def install_argparse_arguments(self, parser):
        parser.add_argument('--all', '-a', help='Drop all sessions except which belong to admin account', action='store_true', default=False)
        parser.add_argument('--account', '-c', help='Drop the designated account sessions')
    def run(self, args):
        if not args.all:
            if args.account is None:
                return
            countCmd = "select count(1) from SessionVO where accountUuid = (select distinct(a.uuid) from AccountVO a, (select * from SessionVO)" \
                  " as s where s.accountUuid = a.uuid and a.name='%s')" % args.account
            command = "delete from SessionVO where accountUuid = (select distinct(a.uuid) from AccountVO a, (select * from SessionVO)" \
                  " as s where s.accountUuid = a.uuid and a.name='%s')" % args.account
            result = mysql(countCmd)
        else:
            countCmd = "select count(1) from SessionVO where accountUuid not in (select uuid from AccountVO where type='SystemAdmin')"
            command = "delete from SessionVO where accountUuid not in (select uuid from AccountVO where type='SystemAdmin')"
            result = mysql(countCmd)
        count = result.splitlines()
        if count is not None and len(count) > 0 and int(count[1]) > 0:
            mysql(command)
            info("drop %d sessions totally" % int(count[1]))
        else:
            info("drop 0 session")

class InstallLicenseCmd(Command):
    def __init__(self):
        super(InstallLicenseCmd, self).__init__()
        self.name = "install_license"
        self.description = "install zstack license"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--license', '-f', help="path to the license file", required=True)
        parser.add_argument('--prikey', help="[OPTIONAL] the path to the private key used to generate license request")

        parser.add_argument('--xsky', '-x', help="path to the xsky license file", required=False)
        parser.add_argument('--user', '-u', help="the monitor user", required=False)
        parser.add_argument('--password', '-p', help="the monitor password", required=False)
        parser.add_argument('--monitor', '-m', help="the monitor address", required=False)

    def run(self, args):
        def install_xsky_license(args):
            lpath = expand_path(args.xsky)

            if not os.path.isfile(lpath):
                raise CtlError('cannot find the license file at %s' % args.license)

            if args.user is None or args.password is None or args.monitor is None:
                raise CtlError('user|password|monitor is None')

            target = "/usr/local/hyperconverged/sds.license"
            scmd = ShellCmd("scp %s root@%s:%s" % (args.xsky, args.monitor, target))
            scmd(True)

            cmd = "xms-cli -user %s -p %s license activate %s" % (args.user, args.password, target)
            scmd = ShellCmd("ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s \"%s\"" % (args.monitor, cmd))
            scmd(True)

        def install_zstack_ukey_license(lpath):
            ctl.locate_zstack_home()
            toolsDir = os.path.join(ctl.zstack_home, "WEB-INF", "classes", "tools")
            utilPath = os.path.join(toolsDir, "zskey-util")
            machine = platform.machine()
            if machine == 'aarch64':
                utilPath = os.path.join(toolsDir, "zskey-util-aarch64")
            elif machine != 'x86_64':
                return False

            _, out, _ = shell_return_stdout_stderr("%s verify-and-update %s %d %s" % (utilPath, lpath, 1, "E40744673E5AA53"))
            if '"status": "ok",' not in out:
                return False

            jobj = simplejson.loads(out)
            return bool(jobj.get("license"))

        def install_zstack_license(args):
            lpath = expand_path(args.license)

            if not os.path.isfile(lpath):
                raise CtlError('cannot find the license file at %s' % args.license)

            if ctl.extra_arguments:
                raise CtlError('illegal arguments %s' % ctl.extra_arguments)

            ppath = None
            if args.prikey:
                ppath = expand_path(args.prikey)
                if not os.path.isfile(ppath):
                    raise CtlError('cannot find the private key file at %s' % args.prikey)

            license_folder = '/var/lib/zstack/license'
            shell('''mkdir -p %s''' % license_folder)
            shell('''chown zstack:zstack %s''' % license_folder)

            if shell_return("gzip -t %s" % lpath) == 0:
                packaged_license_folder = license_folder + '/packaged/' + datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
                shell('''mkdir -p %s''' % packaged_license_folder)
                shell('''tar zxf %s -C %s''' % (lpath, packaged_license_folder))
                shell('''chown -R zstack:zstack %s''' % packaged_license_folder)
                save_records(license_folder, packaged_license_folder)
                info("successfully installed the license files to %s" % packaged_license_folder)
            elif shell_return('grep -q "MIME-Version:" %s' % lpath) == 0:
                license_file_name = "license_" + uuid.uuid4().hex
                license_path = '%s/%s' % (license_folder, license_file_name)
                shell('''yes | cp %s %s''' % (lpath, license_path))
                shell('''chown zstack:zstack %s''' % license_path)
                save_records(license_folder, license_path)
                info("successfully installed the license file to %s" % license_path)
            else: # might be USB-key license
                if install_zstack_ukey_license(lpath):
                    info("successfully updated the USB-key license")
                else:
                    info("unexpected license file")

            if ppath:
                shell('''yes | cp %s %s/pri.key''' % (ppath, license_folder))
                shell('''chown zstack:zstack %s/pri.key''' % license_folder)
                info("successfully installed the private key file to %s/pri.key" % license_folder)

        # `license_path` may be a folder path
        def save_records(license_folder, license_path):
            with open('%s/install_license_records.txt' % license_folder, 'a') as fd:
                fd.write('%d %s\n' % (int(round(time.time() * 1000)), license_path))

        if args.license is not None:
            install_zstack_license(args)
        if args.xsky is not None:
            install_xsky_license(args)

# tag::deploymentProfiles[]
deploymentProfiles = {
        'small':  ( 4,  64, 0.6, 15),
        'medium': ( 8, 128, 0.5, 30),
        'large':  (16, 128, 0.4, 60),
        'default':( 12, 100, 0.6, 15),
}
# end::deploymentProfiles[]

class SetDeploymentCmd(Command):
    def __init__(self):
        super(SetDeploymentCmd, self).__init__()
        self.name = "set_deployment"
        self.description = "set instance offering size of management node"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--size', '-s', help="instance size, one of %s" % deploymentProfiles.keys(), required=True)

    def find_opt(self, opts, prefix):
        for opt in opts:
            if opt.startswith(prefix):
                return opt
        return None

    def build_catalina_opts(self, heap):
        co = ctl.get_env('CATALINA_OPTS')
        if not co:
            return '-Xmx%sG' % heap

        opts = co.split(' ')
        cur = self.find_opt(opts, '-Xmx')
        if cur is None:
            return '-Xmx%sG %s' % (heap, co)

        opts.remove(cur)
        return '-Xmx%sG %s' % (heap, ' '.join(opts))

    def run(self, args):
        s = args.size.lower()
        if not s in deploymentProfiles.keys():
            raise CtlError('unexpected size: %s' % args.size)

        heap, psize, ratio, sint = deploymentProfiles[s]
        # tag::setdeploymentconfig[]
        commands.getstatusoutput("zstack-ctl setenv CATALINA_OPTS='%s'" % self.build_catalina_opts(heap))
        commands.getstatusoutput("zstack-ctl configure DbFacadeDataSource.maxPoolSize=%s" % psize)
        commands.getstatusoutput("zstack-ctl configure KvmHost.maxThreads.ratio=%s" % ratio)
        commands.getstatusoutput("zstack-ctl configure Prometheus.scrapeInterval=%s" % sint)
        # end::setdeploymentconfig[]

class ClearLicenseCmd(Command):
    def __init__(self):
        super(ClearLicenseCmd, self).__init__()
        self.name = "clear_license"
        self.description = "clear and backup zstack license files"
        ctl.register_command(self)

    def run(self, args):
        license_folder = '/var/lib/zstack/license/'
        license_bck = license_folder + 'backup/' + datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        license_files = license_folder + '*.txt'
        license_pri_key = license_folder + 'pri.key'

        shell('''mkdir -p %s''' % license_bck)

        if os.path.exists(license_folder + 'license.txt'):
            shell('''/bin/mv -f %s %s''' % (license_files, license_bck))
            shell('''/bin/cp -f %s %s''' % (license_pri_key, license_bck))

        if os.path.exists(license_folder + 'license.bak'):
            shell('''/bin/mv %s %s''' % (os.path.join(license_folder, 'license.bak'), license_bck))

        if os.path.isdir(license_folder + 'packaged'):
            shell('''/bin/mv -f %s %s''' % (license_folder + 'packaged', license_bck))
            shell('''/bin/cp -f %s %s''' % (license_pri_key, license_bck))

        shell('''find %s -maxdepth 1 -name 'license_*' -type f -exec mv {} %s \;''' % (license_folder, license_bck))

        info("Successfully clear and backup zstack license files to " + license_bck)

# For UI 1.x
class StartDashboardCmd(Command):
    PID_FILE = '/var/run/zstack/zstack-dashboard.pid'

    def __init__(self):
        super(StartDashboardCmd, self).__init__()
        self.name = "start_ui"
        self.description = "start UI server on the local or remote host"
        ctl.register_command(self)
        if not os.path.exists(os.path.dirname(self.PID_FILE)):
            shell("mkdir -p %s" % os.path.dirname(self.PID_FILE))
            shell("mkdir -p /var/log/zstack")

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')
        parser.add_argument('--port', help="UI server port. [DEFAULT] 5000", default='5000')

    def _remote_start(self, host, params):
        cmd = '/etc/init.d/zstack-dashboard start --rabbitmq %s' % params
        ssh_run_no_pipe(host, cmd)
        info('successfully start the UI server on the remote host[%s]' % host)

    def _check_status(self, port):
        if os.path.exists(self.PID_FILE):
            with open(self.PID_FILE, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                check_pid_cmd = ShellCmd('ps -p %s > /dev/null' % pid)
                check_pid_cmd(is_exception=False)
                if check_pid_cmd.return_code == 0:
                    default_ip = get_default_ip()
                    if not default_ip:
                        info('UI server is still running[PID:%s]' % pid)
                    else:
                        info('UI server is still running[PID:%s], http://%s:%s' % (pid, default_ip, port))

                    return False

        pid = find_process_by_cmdline('zstack_dashboard')
        if pid:
            info('found a zombie UI server[PID:%s], kill it and start a new one' % pid)
            kill_process(pid, signal.SIGKILL)

        return True

    def run(self, args):
        ips = ctl.read_property_list("UI.vip.")

        if not ips:
            ips = ctl.read_property_list("CloudBus.serverIp.")
        if not ips:
            raise CtlError('no RabbitMQ IPs found in %s. The IPs should be configured as CloudBus.serverIp.0, CloudBus.serverIp.1 ... CloudBus.serverIp.N' % ctl.properties_file_path)

        ips = [v for k, v in ips]

        username = ctl.read_property("CloudBus.rabbitmqUsername")
        password = ctl.read_property("CloudBus.rabbitmqPassword")
        if username and not password:
            raise CtlError('CloudBus.rabbitmqUsername is configured but CloudBus.rabbitmqPassword is not. They must be both set or not set. Check %s' % ctl.properties_file_path)
        if not username and password:
            raise CtlError('CloudBus.rabbitmqPassword is configured but CloudBus.rabbitmqUsername is not. They must be both set or not set. Check %s' % ctl.properties_file_path)

        if username and password:
            urls = ["%s:%s@%s" % (username, password, ip) for ip in ips]
        else:
            urls = ips

        param = ','.join(urls)

        if args.host != 'localhost':
            self._remote_start(args.host, param)
            return

        virtualenv = '/var/lib/zstack/virtualenv/zstack-dashboard'
        if not os.path.exists(virtualenv):
            raise CtlError('%s not found. Are you sure the UI server is installed on %s?' % (virtualenv, args.host))

        if not self._check_status(args.port):
            return

        distro = platform.dist()[0]
        if distro in RPM_BASED_OS:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT && service iptables save)' % args.port)
        elif distro in DEB_BASED_OS:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT && /etc/init.d/iptables-persistent save)' % args.port)
        else:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT ' % args.port)

        scmd = '. %s/bin/activate\nZSTACK_DASHBOARD_PORT=%s nohup python -c "from zstack_dashboard import web; web.main()" --rabbitmq %s >/var/log/zstack/zstack-dashboard.log 2>&1 </dev/null &' % (virtualenv, args.port, param)
        script(scmd, no_pipe=True)

        @loop_until_timeout(5, 0.5)
        def write_pid():
            pid = find_process_by_cmdline('zstack_dashboard')
            if pid:
                with open(self.PID_FILE, 'w') as fd:
                    fd.write(str(pid))
                return True
            else:
                return False

        write_pid()
        pid = find_process_by_cmdline('zstack_dashboard')
        if not pid:
            info('fail to start UI server on the local host. Use zstack-ctl start_ui to restart it. zstack UI log could be found in /var/log/zstack/zstack-dashboard.log')
            return False

        default_ip = get_default_ip()
        if not default_ip:
            info('successfully started UI server on the local host, PID[%s]' % pid)
        else:
            info('successfully started UI server on the local host, PID[%s], http://%s:%s' % (pid, default_ip, args.port))

        os.system('mkdir -p /var/run/zstack/')
        with open('/var/run/zstack/zstack-dashboard.port', 'w') as fd:
            fd.write(args.port)

# For UI 2.0
class StartUiCmd(Command):
    PORT_FILE = '/var/run/zstack/zstack-ui.port'
    HTTP_FILE = '/var/run/zstack/zstack-ui.http'
    USER_ZSTACK_HOME_DIR = os.path.expanduser('~zstack')
    ZSTACK_UI_HOME = os.path.join(USER_ZSTACK_HOME_DIR, 'zstack-ui/')
    ZSTACK_UI_START = os.path.join(ZSTACK_UI_HOME, 'scripts/start.sh')
    ZSTACK_UI_STOP = os.path.join(ZSTACK_UI_HOME, 'scripts/stop.sh')
    def __init__(self):
        super(StartUiCmd, self).__init__()
        self.name = "start_ui"
        self.description = "start UI server on the local or remote host"
        self.sensitive_args = ['--ssl-keystore-password', '--db-password', '--redis-password']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')
        parser.add_argument('--mn-host', help="ZStack Management Host IP.")
        parser.add_argument('--mn-port', help="ZStack Management Host port.")
        parser.add_argument('--webhook-host', help="Webhook Host IP.")
        parser.add_argument('--webhook-port', help="Webhook Host port.")
        parser.add_argument('--server-port', help="UI server port.")
        parser.add_argument('--log', help="UI log folder.")
        parser.add_argument('--catalina-opts', help="UI catalina options, seperated by `,`")
        parser.add_argument('--timeout', help='Wait for ZStack UI startup timeout, default is 120 seconds.',
                            default=120)

        # arguments for https
        parser.add_argument('--enable-ssl', help="Enable HTTPS for ZStack UI.", action="store_true", default=False)
        parser.add_argument('--ssl-keyalias', help="HTTPS SSL KeyAlias.")
        parser.add_argument('--ssl-keystore', help="HTTPS SSL KeyStore Path.")
        parser.add_argument('--ssl-keystore-type', choices=['PKCS12', 'JKS'], type=str.upper, help="HTTPS SSL KeyStore Type.")
        parser.add_argument('--ssl-keystore-password', help="HTTPS SSL KeyStore Password.")
        parser.add_argument('--enable-http2', help="Enable HTTP2 for ZStack UI,must enable https first.")

        # arguments for ui_db
        parser.add_argument('--db-url', help="zstack_ui database jdbc url")
        parser.add_argument('--db-username', help="zstack_ui database username")
        parser.add_argument('--db-password', help="zstack_ui database password")

        # arguments for ui_redis
        parser.add_argument('--redis-password', help="zstack_ui redis password")

        # arguments for mini judgment
        parser.add_argument('--force', help="Force start_ui on mini", action='store_true', default=False)

    def _remote_start(self, host, mn_host, mn_port, webhook_host, webhook_port, server_port, log, enable_ssl, ssl_keyalias, ssl_keystore, ssl_keystore_type, ssl_keystore_password, db_url, db_username, db_password):
        if enable_ssl:
            cmd = 'zstack-ctl start_ui --mn-host %s --mn-port %s --webhook-host %s --webhook-port %s --server-port %s --log %s --enable-ssl --ssl-keyalias %s --ssl-keystore %s --ssl-keystore-type %s --ssl-keystore-password %s --db-url %s --db-username %s --db-password %s' % (mn_host, mn_port, webhook_host, webhook_port, server_port, log, ssl_keyalias, ssl_keystore, ssl_keystore_type, ssl_keystore_password, db_url, db_username, db_password)
        else:
            cmd = 'zstack-ctl start_ui --mn-host %s --mn-port %s --webhook-host %s --webhook-port %s --server-port %s --log %s --db-url %s --db-username %s --db-password %s' % (mn_host, mn_port, webhook_host, webhook_port, server_port, log, db_url, db_username, db_password)
        ssh_run_no_pipe(host, cmd)
        info('successfully start the UI server on the remote host[%s:%s]' % (host, server_port))

    def _check_status(self):
        cmd = ShellCmd("runuser -l root -s /bin/bash -c 'bash %s'" % (UiStatusCmd.ZSTACK_UI_STATUS),pipe=False)
        cmd(False)

        if cmd.return_code == 0:
            default_ip = get_ui_address()
            if not default_ip:
                info('UI status: %s ' % (colored('Running', 'green')))
            else:
                info('UI status: %s  //%s:%s' % (
                    colored('Running', 'green'), default_ip, "5000"))

                return False
        return True

    def _gen_default_ssl_keystore(self):
        key = OpenSSL.crypto.PKey()
        key.generate_key(OpenSSL.crypto.TYPE_RSA, 2048)
        cert = OpenSSL.crypto.X509()
        cert.set_serial_number(0)
        cert.get_subject().CN = "localhost"
        cert.set_issuer(cert.get_subject())
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10*365*24*60*60)
        cert.set_pubkey(key)
        cert.sign(key, 'sha256')
        p12 = OpenSSL.crypto.PKCS12()
        p12.set_privatekey(key)
        p12.set_certificate(cert)
        p12.set_friendlyname('zstackui')
        with open(ctl.ZSTACK_UI_KEYSTORE, 'w') as f:
            f.write(p12.export(b'password'))

    def _gen_ssl_keystore_pem_from_pkcs12(self, ssl_keystore, ssl_keystore_password):
        try:
            p12 = OpenSSL.crypto.load_pkcs12(file(ssl_keystore, 'rb').read(), ssl_keystore_password)
        except Exception as e:
            raise CtlError('failed to convert %s to %s because %s' % (ssl_keystore, ctl.ZSTACK_UI_KEYSTORE_PEM, str(e)))
        cert_pem = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, p12.get_certificate())
        pkey_pem = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, p12.get_privatekey())
        with open(ctl.ZSTACK_UI_KEYSTORE_PEM, 'w') as f:
            f.write(cert_pem + pkey_pem)

    def _get_db_info(self):
        # get default db_url, db_username, db_password etc.
        db_url_params = ctl.get_ui_db_url().split('//')
        self.db_url = db_url_params[0] + '//' + db_url_params[1].split('/')[0]
        if 'zstack_ui' not in self.db_url:
            self.db_url = '%s/zstack_ui' % self.db_url.rstrip('/')
        _, _, self.db_username, self.db_password = ctl.get_live_mysql_portal(ui=True)

    def _report_sns_global_property_updated(self, sns_cmd):
        mn_ip = ctl.read_property('management.server.ip')
        if not mn_ip:
            mn_ip = "127.0.0.1"
        mn_port = ctl.read_property('RESTFacade.port')
        if not mn_port:
            mn_port = 8080
        content_json = simplejson.dumps(sns_cmd)
        http_cmd = 'curl -X POST -H "Content-Type:application/json" -H "commandpath:/sns/globalpropertyupdated" -d \'%s\' --retry 5 http://%s:%s/zstack/asyncrest/sendcommand' % (content_json, mn_ip, mn_port)
        logger.debug('report sns global property updated')
        ShellCmd(http_cmd)

    def run_zstack_ui(self, args):

        if args.mn_host and not validate_ip(args.mn_host):
            raise CtlError('%s is invalid mn address' % args.mn_host)
        if args.webhook_host and not validate_ip(args.webhook_host):
            raise CtlError('%s is invalid webhook address' % args.webhook_host)

        if args.host != 'localhost':
            self._remote_start(args.host, args.mn_host, args.mn_port, args.webhook_host, args.webhook_port, args.server_port, args.log, args.enable_ssl, args.ssl_keyalias, args.ssl_keystore, args.ssl_keystore_type, args.ssl_keystore_password, args.db_url, args.db_username, args.db_password)
            return

        # init zstack.ui.properties
        ctl.internal_run('config_ui', '--init')

        # combine with zstack.ui.properties
        cfg_mn_host = ctl.read_ui_property("mn_host")
        cfg_mn_port = ctl.read_ui_property("mn_port")
        cfg_webhook_host = ctl.read_ui_property("webhook_host")
        cfg_webhook_port = ctl.read_ui_property("webhook_port")
        cfg_server_port = ctl.read_ui_property("server_port")
        cfg_log = ctl.read_ui_property("log")
        cfg_enable_ssl = ctl.read_ui_property("enable_ssl").lower()
        cfg_enable_http2 = ctl.read_ui_property("enable_http2").lower()
        cfg_ssl_keyalias = ctl.read_ui_property("ssl_keyalias")
        cfg_ssl_keystore = ctl.read_ui_property("ssl_keystore")
        cfg_ssl_keystore_type = ctl.read_ui_property("ssl_keystore_type")
        cfg_ssl_keystore_password = ctl.read_ui_property("ssl_keystore_password")
        cfg_catalina_opts = ctl.read_ui_property("catalina_opts")
        cfg_redis_password = ctl.read_ui_property("redis_password")

        custom_props = ""
        predefined_props = ["db_url", "db_username", "db_password", "mn_host", "mn_port", "webhook_host", "webhook_port", "server_port", "log", "enable_ssl", "ssl_keyalias", "ssl_keystore", "ssl_keystore_type", "ssl_keystore_password", "catalina_opts"]
        for k, v in ctl.read_all_ui_properties():
            if k not in predefined_props:
                custom_props += " --%s=%s" % (k, v)

        if not args.mn_host:
            args.mn_host = cfg_mn_host
        if not args.mn_port:
            args.mn_port = cfg_mn_port
        if not args.webhook_host:
            args.webhook_host = cfg_webhook_host
        if not args.webhook_port:
            args.webhook_port = cfg_webhook_port
        if not args.server_port:
            args.server_port = cfg_server_port
        if not args.log:
            args.log = cfg_log
        if not args.enable_ssl:
            args.enable_ssl = True if cfg_enable_ssl == 'true' else False
        if not args.enable_http2:
            args.enable_http2 = cfg_enable_http2
        if not args.ssl_keyalias:
            args.ssl_keyalias = cfg_ssl_keyalias
        if not args.ssl_keystore:
            args.ssl_keystore = cfg_ssl_keystore
        if not args.ssl_keystore_type:
            args.ssl_keystore_type = cfg_ssl_keystore_type
        if not args.ssl_keystore_password:
            args.ssl_keystore_password = cfg_ssl_keystore_password
        if not args.redis_password:
            args.redis_password = cfg_redis_password if cfg_redis_password else ''
        if not args.catalina_opts:
            args.catalina_opts = cfg_catalina_opts
        args.catalina_opts = ' '.join(args.catalina_opts.split(','))

        # create default ssl keystore anyway
        if not os.path.exists(ctl.ZSTACK_UI_KEYSTORE):
            self._gen_default_ssl_keystore()

        # server_port default value is 5443 if enable_ssl is True
        # if args.enable_ssl and args.webhook_port == '5000':
        #     args.webhook_port = '5443'
        if args.enable_ssl and args.server_port == '5000':
            args.server_port = '5443'

        # set http to https is enable ssl set
        webhook_ip = ctl.read_property('management.server.vip')
        if not webhook_ip:
            webhook_ip = 'localhost'
        system_webhook_url = '%s:%s/webhook/zwatch' % (webhook_ip, args.server_port)
        ticket_webhook_url = '%s:%s/webhook/ticket' % (webhook_ip, args.server_port)
        if args.enable_ssl:
            system_webhook_url = 'https://' + system_webhook_url
            ticket_webhook_url = 'https://' + ticket_webhook_url
        else:
            system_webhook_url = 'http://' + system_webhook_url
            ticket_webhook_url = 'http://' + ticket_webhook_url

        ctl.write_property('ticket.sns.topic.http.url', ticket_webhook_url)
        ctl.write_property('sns.systemTopic.endpoints.http.url', system_webhook_url)

        # tell mn the sns global property has changed
        sns_cmd = UpdateSNSGlobalPropertyCmd()
        sns_cmd.ticketTopicHttpURL = ticket_webhook_url
        sns_cmd.systemTopicHttpEndpointURL = system_webhook_url
        self._report_sns_global_property_updated(sns_cmd)

        if not os.path.exists(args.ssl_keystore):
            raise CtlError('%s not found.' % args.ssl_keystore)
        # copy args.ssl_keystore to ctl.ZSTACK_UI_KEYSTORE_CP
        if args.ssl_keystore != ctl.ZSTACK_UI_KEYSTORE and args.ssl_keystore != ctl.ZSTACK_UI_KEYSTORE_CP:
            copyfile(args.ssl_keystore, ctl.ZSTACK_UI_KEYSTORE_CP)
            args.ssl_keystore = ctl.ZSTACK_UI_KEYSTORE_CP

        # convert args.ssl_keystore to .pem
        #if args.ssl_keystore_type == 'PKCS12' and os.path.exists(ctl.ZSTACK_UI_KEYSTORE_PEM):
        #    (status, output) = commands.getstatusoutput('mv %s ' % ctl.ZSTACK_UI_KEYSTORE_PEM_OLD)
        if args.ssl_keystore_type != 'PKCS12' and not os.path.exists(ctl.ZSTACK_UI_KEYSTORE_PEM):
            raise CtlError('%s not found.' % ctl.ZSTACK_UI_KEYSTORE_PEM)
        if args.ssl_keystore_type == 'PKCS12' and not os.path.exists(ctl.ZSTACK_UI_KEYSTORE_PEM):
            self._gen_ssl_keystore_pem_from_pkcs12(args.ssl_keystore, args.ssl_keystore_password)

        # auto configure consoleProxyCertFile if not configured already
        if args.ssl_keystore_type == 'PKCS12' and not ctl.read_property('consoleProxyCertFile'):
            ctl.write_property('consoleProxyCertFile', ctl.ZSTACK_UI_KEYSTORE_PEM)

        # ui_db use encrypted db_password in args
        self._get_db_info()
        if not args.db_url or args.db_url.strip() == '':
            args.db_url = self.db_url
        if not args.db_username or args.db_username.strip() == '':
            args.db_username = self.db_username
        if not args.db_password or args.db_password.strip() == '':
            cipher = AESCipher()
            if not cipher.is_encrypted(self.db_password):
                args.db_password = cipher.encrypt(self.db_password)
            else:
                args.db_password = self.db_password

        zstackui = ctl.ZSTACK_UI_HOME
        if not os.path.exists(zstackui):
            raise CtlError('%s not found. Are you sure the UI server is installed on %s?' % (zstackui, args.host))

        # ui still running
        #if not self._check_status():
        #    return

        distro = platform.dist()[0]
        if distro in RPM_BASED_OS:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT && service iptables save)' % args.server_port)
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && service iptables save)' % (args.server_port, args.server_port))
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && service iptables save)' % (args.webhook_port, args.webhook_port))
        elif distro in DEB_BASED_OS:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT && /etc/init.d/iptables-persistent save)' % args.server_port)
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && /etc/init.d/iptables-persistent save)' % (args.server_port, args.server_port))
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && /etc/init.d/iptables-persistent save)' % (args.webhook_port, args.webhook_port))
        else:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT ' % args.server_port)
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT ' % (args.server_port, args.server_port))
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT ' % (args.webhook_port, args.webhook_port))
        enableSSL = 'false'
        with open(StartUiCmd.HTTP_FILE, 'w') as fd:
            fd.write('http')
        if args.enable_ssl:
            enableSSL = 'true'
            with open(StartUiCmd.HTTP_FILE, 'w') as fd:
                fd.write('https')
        realpem = ctl.ZSTACK_UI_KEYSTORE_PEM
        if ctl.read_property('consoleProxyCertFile'):
            logger.debug('user consoleProxyCertFile as ui pem')
            realpem = ctl.read_property('consoleProxyCertFile')
        scmd = Template("runuser -l root -s /bin/bash -c 'bash ${STOP} && sleep 2 && LOGGING_PATH=${LOGGING_PATH} bash ${START} --mn.host=${MN_HOST} --mn.port=${MN_PORT} --webhook.host=${WEBHOOK_HOST} --webhook.port=${WEBHOOK_PORT} --server.port=${SERVER_PORT} --ssl.enabled=${SSL_ENABLE} --http2.enabled=${HTTP2_ENABLE} --ssl.keyalias=${SSL_KEYALIAS} --ssl.keystore=${SSL_KEYSTORE} --ssl.keystore-type=${SSL_KEYSTORE_TYPE} --ssl.keystore-password=${SSL_KETSTORE_PASSWORD} --db.url=${DB_URL} --db.username=${DB_USERNAME} --db.password=${DB_PASSWORD} --redis.password=${REDIS_PASSWORD} ${CUSTOM_PROPS} --ssl.pem=${ZSTACK_UI_KEYSTORE_PEM}'")

        scmd = scmd.substitute(LOGGING_PATH=args.log,STOP=StartUiCmd.ZSTACK_UI_STOP,START=StartUiCmd.ZSTACK_UI_START,MN_HOST=args.mn_host,MN_PORT=args.mn_port,WEBHOOK_HOST=args.webhook_host,WEBHOOK_PORT=args.webhook_port,SERVER_PORT=args.server_port,SSL_ENABLE=enableSSL,HTTP2_ENABLE=args.enable_http2,SSL_KEYALIAS=args.ssl_keyalias,SSL_KEYSTORE=args.ssl_keystore,SSL_KEYSTORE_TYPE=args.ssl_keystore_type,SSL_KETSTORE_PASSWORD=args.ssl_keystore_password,DB_URL=args.db_url,DB_USERNAME=args.db_username,DB_PASSWORD=args.db_password,REDIS_PASSWORD=args.redis_password,ZSTACK_UI_KEYSTORE_PEM=realpem,CUSTOM_PROPS=custom_props)

        shell("ps aux| grep zstack-ui/scripts/start.sh | awk '{print $2}'|xargs kill -9",is_exception=False)
        script(scmd, no_pipe=True)
        os.system('mkdir -p /var/run/zstack/')
        with open(StartUiCmd.PORT_FILE, 'w') as fd:
            fd.write(args.server_port)

        timeout = int(args.timeout)
        @loop_until_timeout(timeout)
        def check_ui_status():
            command = 'zstack-ctl ui_status'
            (status, output) = commands.getstatusoutput(command)
            if status != 0:
                return False

            return "Running" in output

        if not check_ui_status():
            info('fail to start UI server on the localhost. Use zstack-ctl start_ui to restart it. zstack UI log could be found in %s' % os.path.join(ctl.read_ui_property('log'),'zstack-ui-server.log'))
            shell('zstack-ctl stop_ui')
            linux.rm_dir_force("/var/run/zstack/zstack-ui.port")
            return False
        if args.enable_ssl:
            UiStatusCmd.ZSTACK_UI_SSL = 'https'
        else:
            UiStatusCmd.ZSTACK_UI_SSL = 'http'


        default_ip = get_default_ip()
        if not default_ip:
            info('successfully started UI server on the local host')
        else:
            info('successfully started UI server on the local host %s://%s:%s' % ('https' if args.enable_ssl else 'http', default_ip, args.server_port))

    def run_mini_ui(self):
        shell_return("systemctl start zstack-mini")
        @loop_until_timeout(60)
        def check_ui_status():
            command = 'zstack-ctl ui_status'
            (status, output) = commands.getstatusoutput(command)
            if status != 0:
                return False
            return "Running" in output

        if not check_ui_status():
            info('failed to start MINI UI server on the localhost. Use zstack-ctl start_ui to restart it.')
            shell('systemctl stop zstack-mini')
            linux.rm_dir_force("/var/run/zstack/zstack-mini-ui.port")
            linux.rm_dir_force("/var/run/zstack/zstack-mini-ui.pid")
            return False

        default_ip = get_default_ip()
        mini_pid = get_ui_pid('mini')
        mini_port = 8200
        ui_addr = ", http://{}:{}".format(default_ip, mini_port) if default_ip else ""
        info('successfully started MINI UI server on the local host, PID[{}]{}'.format(mini_pid, ui_addr))


    def run(self, args):
        def encrypt_properties_if_need():
            cipher = AESCipher()
            for key in Ctl.NEED_ENCRYPT_PROPERTIES_UI:
                value = ctl.read_ui_property(key)
                if value and not cipher.is_encrypted(value):
                    ctl.write_ui_property(key, cipher.encrypt(value))

        ui_mode = ctl.read_property('ui_mode')
        encrypt_properties_if_need()
        if ui_mode == "zstack":
            self.run_zstack_ui(args)
        elif ui_mode == "mini" and not args.force:
            self.run_mini_ui()
        elif ui_mode == "mini" and args.force:
            self.run_zstack_ui(args)
        elif ui_mode == None:
            self.run_zstack_ui(args)
        else :
            raise CtlError("Unknown ui_mode {}, please make sure your configuration is correct.".format(ui_mode))

# For UI 2.0
class ConfigUiCmd(Command):
    def __init__(self):
        super(ConfigUiCmd, self).__init__()
        self.name = "config_ui"
        self.description = "configure zstack.ui.properties"
        self.sensitive_args = ['--ssl-keystore-password', '--db-password', '--redis-password']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        ui_logging_path = os.path.join(ctl.ZSTACK_UI_HOME, "logs")
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to set properties in zstack.ui.properties on the remote machine')
        parser.add_argument('--init', help='init zstack ui properties to default values', action="store_true", default=False)
        parser.add_argument('--restore', help='restore zstack ui properties to default values', action="store_true", default=False)
        parser.add_argument('--mn-host', help="ZStack Management Host IP. [DEFAULT] 127.0.0.1")
        parser.add_argument('--mn-port', help="ZStack Management Host port. [DEFAULT] 8080")
        parser.add_argument('--webhook-host', help="Webhook Host IP. [DEFAULT] 127.0.0.1")
        parser.add_argument('--webhook-port', help="Webhook Host port. [DEFAULT] 5001")
        parser.add_argument('--server-port', help="UI server port. [DEFAULT] 5000")
        parser.add_argument('--ui-address', help="ZStack UI Address.")
        parser.add_argument('--log', help="UI log folder. [DEFAULT] %s" % ui_logging_path)
        parser.add_argument('--catalina-opts', help="UI catalina options, seperated by `,`")

        # arguments for https
        parser.add_argument('--enable-ssl', choices=['True', 'False'], type=str.title, help="Enable HTTPS for ZStack UI. [DEFAULT] False")
        parser.add_argument('--ssl-keyalias', help="HTTPS SSL KeyAlias. [DEFAULT] zstackui")
        parser.add_argument('--ssl-keystore', help="HTTPS SSL KeyStore Path. [DEFAULT] %s" % ctl.ZSTACK_UI_KEYSTORE)
        parser.add_argument('--ssl-keystore-type', choices=['PKCS12', 'JKS'], type=str.upper, help="HTTPS SSL KeyStore Type. [DEFAULT] PKCS12")
        parser.add_argument('--ssl-keystore-password', help="HTTPS SSL KeyStore Password. [DEFAULT] password")
        parser.add_argument('--enable-http2',choices=['True', 'False'], type=str.title, help="Enable HTTP2 for ZStack UI. [DEFAULT] False")

        # arguments for ui_db
        parser.add_argument('--db-url', help="zstack_ui database jdbc url.")
        parser.add_argument('--db-username', help="username of zstack_ui database.")
        parser.add_argument('--db-password', help="password of zstack_ui database.")

        # arguments for ui_redis
        parser.add_argument('--redis-password', help="password of zstack_ui redis")

    def _configure_remote_node(self, args):
        shell_no_pipe('ssh %s "/usr/bin/zstack-ctl config_ui %s"' % (args.host, ' '.join(ctl.extra_arguments)))

    def run(self, args):
        ui_logging_path = os.path.join(ctl.ZSTACK_UI_HOME, "logs")
        if args.host:
            self._configure_remote_node(args)
            return

        zstackui = ctl.ZSTACK_UI_HOME
        if not os.path.exists(zstackui):
            raise CtlError('%s not found. Are you sure the UI server is installed?' % zstackui)

        if args.mn_host and not validate_ip(args.mn_host):
            raise CtlError('%s is invalid mn address' % args.mn_host)
        if args.webhook_host and not validate_ip(args.webhook_host):
            raise CtlError('%s is invalid webhook address' % args.webhook_host)
        if args.ui_address and not validate_ip(args.ui_address):
            raise CtlError('%s is invalid ui address' % args.ui_address)

        # init zstack.ui.properties
        if args.init:
            if not ctl.read_ui_property("mn_host"):
                ctl.write_ui_property("mn_host", '127.0.0.1')
            if not ctl.read_ui_property("mn_port"):
                ctl.write_ui_property("mn_port", '8080')
            if not ctl.read_ui_property("webhook_host"):
                ctl.write_ui_property("webhook_host", '127.0.0.1')
            if not ctl.read_ui_property("webhook_port"):
                # from 4.0 set webhook_port to 5001,since the 5000 is for nginx
                ctl.write_ui_property("webhook_port", '5001')
            if not ctl.read_ui_property("server_port"):
                ctl.write_ui_property("server_port", '5000')
            # from 4.0 set webhook_port to 5001,since the 5000 is for nginx
            if ctl.read_ui_property("webhook_port") == ctl.read_ui_property("server_port"):
            #'webhook port same with server port in zstack.ui.properties, auto set webhook port to server port +1'
                port = ctl.read_ui_property("server_port")
                port = str(int(port)+1)
                ctl.write_ui_property("webhook_port", port)
            if not ctl.read_ui_property("log"):
                ctl.write_ui_property("log", ui_logging_path)
            if not ctl.read_ui_property("enable_ssl"):
                ctl.write_ui_property("enable_ssl", 'false')
            if not ctl.read_ui_property("enable_http2"):
                ctl.write_ui_property("enable_http2", 'false')
            if not ctl.read_ui_property("ssl_keyalias"):
                ctl.write_ui_property("ssl_keyalias", 'zstackui')
            if not ctl.read_ui_property("ssl_keystore"):
                ctl.write_ui_property("ssl_keystore", ctl.ZSTACK_UI_KEYSTORE)
            if not ctl.read_ui_property("ssl_keystore_type"):
                ctl.write_ui_property("ssl_keystore_type", 'PKCS12')
            if not ctl.read_ui_property("ssl_keystore_password"):
                ctl.write_ui_property("ssl_keystore_password", 'password')
            if not ctl.read_ui_property("server.ssl.enabled-protocols"):
                ctl.write_ui_property("server.ssl.enabled-protocols", 'TLSv1.2')
            if not ctl.read_ui_property("db_url"):
                ctl.write_ui_property("db_url", 'jdbc:mysql://127.0.0.1:3306')
            if not ctl.read_ui_property("db_username"):
                ctl.write_ui_property("db_username", 'zstack_ui')
            if not ctl.read_ui_property("db_password"):
                ctl.write_ui_property("db_password", 'zstack.ui.password')
            if not ctl.read_ui_property("redis_password"):
                ctl.write_ui_property("redis_password", 'zstack.redis.password')
            if not ctl.read_ui_property("catalina_opts"):
                ctl.write_ui_property("catalina_opts", ctl.ZSTACK_UI_CATALINA_OPTS)
            return

        # restore to default values
        if args.restore:
            ctl.clear_ui_properties()
            ctl.write_ui_property("mn_host", '127.0.0.1')
            ctl.write_ui_property("mn_port", '8080')
            ctl.write_ui_property("webhook_host", '127.0.0.1')
            ctl.write_ui_property("webhook_port", '5001')
            ctl.write_ui_property("server_port", '5000')
            ctl.write_ui_property("log", ui_logging_path)
            ctl.write_ui_property("enable_ssl", 'false')
            ctl.write_ui_property("enable_http2", 'false')
            ctl.write_ui_property("ssl_keyalias", 'zstackui')
            ctl.write_ui_property("ssl_keystore", ctl.ZSTACK_UI_KEYSTORE)
            ctl.write_ui_property("ssl_keystore_type", 'PKCS12')
            ctl.write_ui_property("ssl_keystore_password", 'password')
            ctl.write_ui_property("server.ssl.enabled-protocols", 'TLSv1.2')
            ctl.write_ui_property("db_url", 'jdbc:mysql://127.0.0.1:3306')
            ctl.write_ui_property("db_username", 'zstack_ui')
            ctl.write_ui_property("db_password", 'zstack.ui.password')
            ctl.write_ui_property("redis_password", 'zstack.redis.password')
            ctl.write_ui_property("catalina_opts", ctl.ZSTACK_UI_CATALINA_OPTS)
            return

        # `--key=value` type of params
        if ctl.extra_arguments:
            properties = [ l.split('=', 1) for l in ctl.extra_arguments ]
            for k, v in properties:
                if not k.startswith('--'):
                    raise CtlError('custom param %s is invalid, must begin with --' % k)
                ctl.write_ui_property(k.lstrip('--'), v)

        # use 5443 instead if enable_ssl
        # This is a HACK: modify enable_ssl config will update server_port (webhook_port will not change)
        if args.enable_ssl is not None:
            current_server_port = ctl.read_ui_property("server_port")
            if args.enable_ssl.lower() == 'true' and current_server_port == '5000':
                print('Enable SSL: The server port is updated to 5443. Restart UI server to make the configuration take effect.')
                args.server_port = '5443'
            elif args.enable_ssl.lower() == 'false' and current_server_port == '5443':
                print('Disable SSL: The server port is updated to 5000. Restart UI server to make the configuration take effect.')
                args.server_port = '5000'

        # copy args.ssl_keystore to ctl.ZSTACK_UI_KEYSTORE_CP
        if args.ssl_keystore and args.ssl_keystore != ctl.ZSTACK_UI_KEYSTORE:
            if not os.path.exists(args.ssl_keystore):
                raise CtlError('%s not found.' % args.ssl_keystore)
            if args.ssl_keystore != ctl.ZSTACK_UI_KEYSTORE_CP:
                copyfile(args.ssl_keystore, ctl.ZSTACK_UI_KEYSTORE_CP)
                args.ssl_keystore = ctl.ZSTACK_UI_KEYSTORE_CP

        if args.mn_host or args.mn_host == '':
            ctl.write_ui_property("mn_host", args.mn_host.strip())
        if args.mn_port or args.mn_port == '':
            ctl.write_ui_property("mn_port", args.mn_port.strip())
        if args.webhook_host or args.webhook_host == '':
            ctl.write_ui_property("webhook_host", args.webhook_host.strip())
        if args.webhook_port or args.webhook_port == '':
            ctl.write_ui_property("webhook_port", args.webhook_port.strip())
        if args.server_port or args.server_port == '':
            ctl.write_ui_property("server_port", args.server_port.strip())
            distro = platform.dist()[0]
            if distro in RPM_BASED_OS:
                shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && service iptables save)' % (args.server_port, args.server_port))
            elif distro in DEB_BASED_OS:
                shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && /etc/init.d/iptables-persistent save)' % (args.server_port, args.server_port))
            else:
                shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT ' % (args.server_port, args.server_port))
        if args.log or args.log == '':
            ctl.write_ui_property("log", args.log.strip())

        # https
        if args.enable_ssl:
            ctl.write_ui_property("enable_ssl", args.enable_ssl.lower())
        if args.enable_http2:
            ctl.write_ui_property("enable_http2", args.enable_http2.lower())
        if args.ssl_keyalias or args.ssl_keyalias == '':
            ctl.write_ui_property("ssl_keyalias", args.ssl_keyalias.strip())
        if args.ssl_keystore or args.ssl_keystore == '':
            ctl.write_ui_property("ssl_keystore", args.ssl_keystore.strip())
        if args.ssl_keystore_type or args.ssl_keystore_type == '':
            ctl.write_ui_property("ssl_keystore_type", args.ssl_keystore_type.strip())
        if args.ssl_keystore_password or args.ssl_keystore_password == '':
            ctl.write_ui_property("ssl_keystore_password", args.ssl_keystore_password.strip())

        # ui_db
        if args.db_url or args.db_url == '':
            ctl.write_ui_property("db_url", args.db_url.strip())
        if args.db_username or args.db_username == '':
            ctl.write_ui_property("db_username", args.db_username.strip())
        if args.db_password or args.db_password == '':
            ctl.write_ui_property("db_password", args.db_password.strip())
        if args.redis_password or args.redis_password == '':
            ctl.write_ui_property("redis_password", args.redis_password.strip())


        # ui_address
        if args.ui_address:
            ctl.write_ui_property("ui_address", args.ui_address.strip())

        # catalina opts
        if args.catalina_opts:
            ctl.write_ui_property("catalina_opts", args.catalina_opts)

# For UI 2.0
class ShowUiCfgCmd(Command):
    def __init__(self):
        super(ShowUiCfgCmd, self).__init__()
        self.name = "show_ui_config"
        self.description = "a shortcut that prints contents of zstack.ui.properties to screen"
        ctl.register_command(self)

    def run(self, args):
        zstackui = ctl.ZSTACK_UI_HOME
        if not os.path.exists(zstackui):
            raise CtlError('%s not found. Are you sure the UI server is installed?' % zstackui)

        shell_no_pipe('cat %s' % ctl.ui_properties_file_path)

# For VDI PORTAL 2.1
class StartVDIUICmd(Command):
    PID_FILE = '/var/run/zstack/zstack-vdi.pid'
    PORT_FILE = '/var/run/zstack/zstack-vdi.port'

    def __init__(self):
        super(StartVDIUICmd, self).__init__()
        self.name = "start_vdi"
        self.description = "start VDI UI server on the local host"
        ctl.register_command(self)
        if not os.path.exists(os.path.dirname(self.PID_FILE)):
            shell("mkdir -p %s" % os.path.dirname(self.PID_FILE))

    def install_argparse_arguments(self, parser):
        ui_logging_path = os.path.normpath(os.path.join(ctl.zstack_home, "../../logs/"))
        vdi_war = "/opt/zstack-dvd/{}/{}/zstack-vdi.war".format(ctl.BASEARCH, ctl.ZS_RELEASE)
        parser.add_argument('--mn-port', help="ZStack Management Host port. [DEFAULT] 8080", default='8080')
        parser.add_argument('--webhook-port', help="Webhook Host port. [DEFAULT] 9000", default='9000')
        parser.add_argument('--server-port', help="UI server port. [DEFAULT] 9000", default='9000')
        parser.add_argument('--vdi-path', help="VDI path. [DEFAULT] {}".format(vdi_war), default=vdi_war)
        parser.add_argument('--log', help="UI log folder. [DEFAULT] %s" % ui_logging_path, default=ui_logging_path)

    def _check_status(self):
        VDI_UI_PORT = 9000
        if os.path.exists(self.PORT_FILE):
            with open(self.PORT_FILE, 'r') as fd:
                VDI_UI_PORT = fd.readline()
                VDI_UI_PORT = VDI_UI_PORT.strip(' \t\n\r')
        if os.path.exists(self.PID_FILE):
            with open(self.PID_FILE, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                check_pid_cmd = ShellCmd('ps -p %s > /dev/null' % pid)
                check_pid_cmd(is_exception=False)
                if check_pid_cmd.return_code == 0:
                    default_ip = get_default_ip()
                    if not default_ip:
                        info('VDI UI is still running[PID:%s]' % pid)
                    else:
                        info('VDI UI is still running[PID:%s], http://%s:%s' % (pid, default_ip, VDI_UI_PORT))
                    return False

        pid = find_process_by_cmdline('zstack-vdi')
        if pid:
            info('found a zombie VDI UI server[PID:%s], kill it and start a new one' % pid)
            kill_process(pid, signal.SIGKILL)
        return True

    def run(self, args):
        shell("mkdir -p %s" % args.log)
        zstack_vdi =  args.vdi_path
        if not os.path.exists(zstack_vdi):
            raise CtlError('%s not found. Are you sure the VDI UI server is installed ?' % (zstack_vdi))

        # vdi ui still running
        if not self._check_status():
            return

        distro = platform.dist()[0]
        if distro in RPM_BASED_OS:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && service iptables save)' % (args.server_port, args.server_port))
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && service iptables save)' % (args.webhook_port, args.webhook_port))
        elif distro in DEB_BASED_OS:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && /etc/init.d/iptables-persistent save)' % (args.server_port, args.server_port))
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT && /etc/init.d/iptables-persistent save)' % (args.webhook_port, args.webhook_port))
        else:
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT ' % (args.server_port, args.server_port))
            shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport %s -j ACCEPT ' % (args.webhook_port, args.webhook_port))

        scmd = "runuser -l zstack -s /bin/bash -c 'LOGGING_PATH=%s java -jar -Dmn.port=%s -Dwebhook.port=%s -Dserver.port=%s %s >>%s/zstack-vdi.log 2>&1 &'" % (args.log, args.mn_port, args.webhook_port, args.server_port, args.vdi_path, args.log)

        script(scmd, no_pipe=True)

        @loop_until_timeout(5, 0.5)
        def write_pid():
            pid = find_process_by_cmdline('zstack-vdi')
            if pid:
                with open(self.PID_FILE, 'w') as fd:
                    fd.write(str(pid))
                return True
            else:
                return False

        write_pid()
        pid = find_process_by_cmdline('zstack-vdi')
        if not pid:
            info('fail to start VDI UI server on the localhost. Use zstack-ctl start_vdi to restart it. zstack VDI portal log could be found in %s/zstack-vdi.log' % args.log)
            return False

        default_ip = get_default_ip()
        if not default_ip:
            info('successfully started VDI UI server on the local host, PID[%s]' % pid)
        else:
            info('successfully started VDI UI server on the local host, PID[%s], http://%s:%s' % (pid, default_ip, args.server_port))

        os.system('mkdir -p /var/run/zstack/')
        with open('/var/run/zstack/zstack-vdi.port', 'w') as fd:
            fd.write(args.server_port)

class GetZStackVersion(Command):
    def __init__(self):
        super(GetZStackVersion, self).__init__()
        self.name = "get_version"
        self.description = "get zstack version from database, eg. 2.4.0"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('-a', '--addition', help="print zstack additional version", required=False, action='store_true')

    def run(self, args):
        if args.addition:
            sys.stdout.write(self.get_additional_version() + '\n')
        else:
            sys.stdout.write(self.get_main_version_from_db() + '\n')

    def get_main_version_from_db(self):
        hostname, port, user, password = ctl.get_live_mysql_portal()
        return get_zstack_version(hostname, port, user, password)

    # cube:  'AliyunHCI-Z 1.1.0'
    # zsv:   'ZSphere 4.0.0'
    # cloud: ''
    def get_additional_version(self):
        if is_hyper_converged_host():
            version = get_hci_detail_version()
            if not version:
                return ''
            clips = version.rsplit("-", 1)
            return '%s %s' % (clips[0], clips[1]) if len(clips) == 2 else version
        elif is_zsv_env():
            version = get_zsv_version()
            return 'ZSphere ' + version if version else 'ZSphere Unknown'
        else:
            return ''

class ResetAdminPasswordCmd(Command):
    SYSTEM_ADMIN_TYPE = 'SystemAdmin'

    def __init__(self):
        super(ResetAdminPasswordCmd, self).__init__()
        self.name = "reset_password"
        self.description = "reset ZStack admin account password, if not set, default is 'password'"
        self.sensitive_args = ['--password']
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--password', help="the new password of admin. If not set, the default is 'password'")

    def run(self, args):
        info("start reset password")

        def get_sha512_pwd(password):
            new_password = [password, args.password][args.password is not None]
            return hashlib.sha512(new_password).hexdigest()

        sha512_pwd = get_sha512_pwd('password')
        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        query = MySqlCommandLineQuery()
        query.host = db_hostname
        query.port = db_port
        query.user = db_user
        query.password = db_password
        query.table = 'zstack'
        query.sql = "update AccountVO set password='%s' where type='%s'" % (sha512_pwd, self.SYSTEM_ADMIN_TYPE)
        query.query()

        def reset_privilege_admin(origin_password, initial_uuid):
            sha512_pwd = get_sha512_pwd(origin_password)
            query = MySqlCommandLineQuery()
            query.host = db_hostname
            query.port = db_port
            query.user = db_user
            query.password = db_password
            query.table = 'zstack'
            query.sql = "update IAM2VirtualIDVO set password='%s' where uuid='%s'" % (sha512_pwd, initial_uuid)
            query.query()

        identy_types = ctl.read_property('IDENTITY_INIT_TYPE')
        if identy_types and 'PRIVILEGE_ADMIN' in identy_types:
            reset_privilege_admin('Sysadmin#', '274fdae86f4d4dda8d50c02ca7521fac')
            reset_privilege_admin('Secadmin#', '9b44d7b3ce36418685b53c236b901160')
            reset_privilege_admin('Secauditor#', 'e2e2cf3ae26c44379ab0bb4c7bc1e77e')

        info("reset password succeed")


class MiniResetHostCmd(Command):
    def __init__(self):
        super(MiniResetHostCmd, self).__init__()
        self.name = "reset_mini_host"
        self.description = "reset mini host"
        ctl.register_command(self)

        self.target = {"local", "peer", "both"}
        self.script_path = "/tmp/reset_mini.py"
        self.local_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reset_mini.py")
        self.key = "/usr/local/zstack/mini_fencer.key"
        _, self.sn, _ = shell_return_stdout_stderr("dmidecode -s system-serial-number")
        self.sn = self.sn.strip()

    def install_argparse_arguments(self, parser):
        parser.add_argument('--target', help='reset target, could be %s, default is both' % self.target, required=False)

    def run(self, args):
        args = self._intercept(args)
        if args.target in ["peer", "both"]:
            peer_ip = self._get_peer_address()
            info("reseting host %s ..." % peer_ip)
            self._copy_script(peer_ip)
            self._run_script(peer_ip)
            self._wait_node_has_ip("peer")
        if args.target in ["local", "both"]:
            info("reseting local host ...")
            self._run_script()
            self._wait_node_has_ip("local")
        info("mini host reset complete!")

    def _write_to_temp_file(self, content):
        (tmp_fd, tmp_path) = tempfile.mkstemp()
        tmp_fd = os.fdopen(tmp_fd, 'w')
        tmp_fd.write(content)
        tmp_fd.close()
        return tmp_path

    def _check_root_password(self):
        import getpass
        if sys.stdin.isatty():
            password = getpass.getpass(prompt='Enter root password for localhost to continue...\n')
        else:
            print("Enter root password for localhost to continue...\n")
            password = sys.stdin.readline().rstrip()
        tmpfile = self._write_to_temp_file(str(password))
        r = shell_return("timeout 5 sshpass -f %s ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null 127.0.0.1 date" % tmpfile)
        os.remove(tmpfile)
        if r != 0:
            error("check root password of localhost failed!")

    def _intercept(self, args):
        self._check_root_password()
        if args.target == "local":
            return args

        if args.target is None or args.target.strip() == "":
            warn("target not specified, will reset node A and B both...")
            time.sleep(3)
            args.target = "both"

        _, o, _ = shell_return_stdout_stderr("curl 127.0.0.1:7274/bootstrap/hosts/local")
        j = simplejson.loads(o)
        if j.get("peer") is None:
            error("Can not connect to peer, you can reset local node via "
                            "'zstack-ctl reset_mini_host --target local'")
        return args

    def _wait_node_has_ip(self, node):
        info("script copy complete\nwaiting node %s reset complete ..." % node)
        for i in range(100):
            if self._node_has_special_ip(node):
                return
            time.sleep(6)
        error("%s reset not success after 600 secondes" % node)

    @staticmethod
    def _node_has_special_ip(node):
        _, o, _ = shell_return_stdout_stderr("curl 127.0.0.1:7274/bootstrap/hosts/local")
        try:
            j = simplejson.loads(o)
        except Exception:
            return False
        if j.get(node) is None:
            return False
        return "100.66.66" in j.get(node).get("ipv4Address")

    def _validate_args(self, args):
        if args.target not in self.target:
            error("target must be local, peer or both")

    @staticmethod
    def _get_peer_address():
        _, o, _ = shell_return_stdout_stderr("curl 127.0.0.1:7274/bootstrap/hosts/local")
        j = simplejson.loads(o)
        return j.get("peer").get("ipv4Address")

    def _ssh_no_auth(self, peer_ip):
        r = shell_return("timeout 5 ssh root@%s date" % peer_ip)
        if r == 0:
            return True
        r = shell_return("timeout 5 ssh -i %s root@%s date" % (self.key, peer_ip))
        if r == 0:
            return False
        error("can not connect %s via ssh" % peer_ip)

    def _run_script(self, peer_ip=None):
        if not peer_ip:
            shell_return("/bin/cp %s %s" % (self.local_script_path, self.script_path))
            shell_return("python %s > /tmp/reset_mini.log 2>&1" % self.script_path)
        elif self._ssh_no_auth(peer_ip):
            cmd = ShellCmd("ssh root@%s 'nohup python %s > /tmp/reset_mini.log 2>&1 &'" % (peer_ip, self.script_path))
            cmd(True)
        else:
            cmd = ShellCmd("ssh -i %s root@%s 'nohup python %s > /tmp/reset_mini.log 2>&1 &'" % (self.key, peer_ip, self.script_path))
            cmd(True)

    def _copy_script(self, peer_ip):
        if self._ssh_no_auth(peer_ip):
            cmd = ShellCmd("scp %s root@%s:%s" % (self.local_script_path, peer_ip, self.script_path))
            cmd(True)
        else:
            cmd = ShellCmd("scp -i %s %s root@%s:%s" % (self.key, self.local_script_path, peer_ip, self.script_path))
            cmd(True)


class SharedBlockQcow2SharedVolumeFixCmd(Command):
    def __init__(self):
        super(SharedBlockQcow2SharedVolumeFixCmd, self).__init__()
        self.name = "fix_sharedvolume"
        self.description = "fix qcow2 format shared volume on shared block primary storage"
        self.sensitive_args = ['--admin-password']
        ctl.register_command(self)

        self.support_operations = ["convert_volume", "delete_qcow2_volume", "commit_snapshot_to_image", "delete_shared_volume_snapshots"]
        self.key = "/usr/local/zstack/apache-tomcat/webapps/zstack/WEB-INF/classes/ansible/rsaKeys/id_rsa"
        self.script_path = "/tmp/zstack-convert-volume.py"

    def install_argparse_arguments(self, parser):
        parser.add_argument('--admin-password', help='password of zstack admin user', required=True)
        parser.add_argument('--operation', help='operation, may be: %s' % self.support_operations, required=True)
        parser.add_argument('--dryrun', help='run in dry run mode, default is True, be carefully if set to False', default="True")
        parser.add_argument('--backup-storage-uuid', help='backup storage uuid, need to specify in commit_snapshot_to_image', required=False)

    def run(self, args):
        if args.operation == "convert_volume":
            self._convert_volume(args)
        elif args.operation == "delete_qcow2_volume":
            self._delete_qcow2_volume(args)
        elif args.operation == "commit_snapshot_to_image":
            self._convert_snapshot(args)
        elif args.operation == "delete_shared_volume_snapshots":
            self._delete_snapshot(args)
        else:
            raise Exception("not in supported operations: %s" % self.support_operations)

    def _copy_script(self, hostIp):
        local_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fix_shared_volume.py")
        cmd = ShellCmd("scp -i %s %s root@%s:%s" % (self.key, local_script_path, hostIp, self.script_path))
        cmd(True)

    def _convert_volume(self, args):
        shared_volumes = self._find_shared_volumes()
        if len(shared_volumes) == 0:
            info("not found any shared volume need to be convert")
            return
        warn("found shared volumes[uuid: %s, name: %s] need to be convert" %
             (map(lambda x: x["uuid"], shared_volumes), map(lambda x: x["name"], shared_volumes)))
        for volume in shared_volumes:
            self._check_attached_vm_online(volume["uuid"])
        if args.dryrun.lower() != "false":
            info("run in dryrun mode, return now")
            return
        for volume in shared_volumes:
            hosts = self._select_host(volume["primaryStorageUuid"])
            self._deactivate_volume(volume, hosts)
            info("start do convert volume[uuid: %s, name: %s, installPath: %s] on host[ip: %s]" % (volume["uuid"], volume["name"], volume["installPath"], hosts[0]["managementIp"]))
            self._do_convert_volume(volume["installPath"], hosts[0]["managementIp"], volume["primaryStorageUuid"])
            info("do convert volume[uuid: %s, name: %s, installPath: %s] on host[ip: %s] done" % (volume["uuid"], volume["name"], volume["installPath"], hosts[0]["managementIp"]))
            self._update_format(volume["uuid"], "raw")

    def _run_sql(self, sql):
        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        query = MySqlCommandLineQuery()
        query.host = db_hostname
        query.port = db_port
        query.user = db_user
        query.password = db_password
        query.table = 'zstack'
        query.sql = sql
        return query.query()

    def _deactivate_volume(self, volume, hosts):
        info("deactivating volume[uuid: %s, name: %s, installPath: %s] on hosts[%s]..." %
             (volume["uuid"], volume["name"], volume["installPath"], map(lambda x: x["managementIp"], hosts)))
        volume_abs_path = volume["installPath"].replace("sharedblock:/", "/dev")
        for host in hosts:
            cmd = ShellCmd("ssh -i %s root@%s 'lvchange -an %s'" % (self.key, host["managementIp"], volume_abs_path))
            cmd(True)

    def _do_convert_volume(self, volume_install_path, hostIp, psUuid):
        # type: (str, str, str) -> void
        # 0. check lv tag, if start convet exists, raise;
        #    if convert done exists, raise
        # 1. create a lv with original lv size
        # 2. add tag start convert to original lv
        # 3. qemu-img convert
        # 4. add tag convert done and if success or remove tag and target lv if fail
        # 5. exchange name
        volume_abs_path = volume_install_path.replace("sharedblock:/", "/dev")
        self._copy_script(hostIp)
        cmd = ShellCmd("ssh -i %s root@%s 'python %s %s %s'" % (self.key, hostIp, self.script_path, "convert", volume_abs_path))
        cmd(True)

    def _check_attached_vm_online(self, volumeUuid):
        sql = "select vm.uuid from VmInstanceVO vm, ShareableVolumeVmInstanceRefVO ref where ref.vmInstanceUuid=vm.uuid and vm.state!='Stopped' and ref.volumeUuid='%s'" % volumeUuid
        result = self._run_sql(sql)
        if len(result) != 0:
            error("shared volume %s is attach on not stopped vm: %s, can not proceed" % (volumeUuid, result))

    def _select_host(self, ps_uuid):
        sql = "select host.* from HostVO host, SharedBlockGroupPrimaryStorageHostRefVO ref where ref.hostUuid=host.uuid and ref.primaryStorageUuid='%s' and ref.status='Connected' and host.status='Connected' order by ref.hostId" % ps_uuid
        r = self._run_sql(sql)
        if len(r) == 0:
            error("can not find proper host via sql: %s" % sql)
        return r

    def _find_shared_volumes(self, format="qcow2"):
        sql = "select vol.* from VolumeVO vol, PrimaryStorageVO ps where ps.Type='sharedblock' and vol.primaryStorageUuid = ps.uuid and vol.isShareable <> 0 and vol.format ='%s'" % format
        return self._run_sql(sql)

    def _find_shared_snapshots(self):
        sql = "select snap.* from VolumeVO vol, PrimaryStorageVO ps, VolumeSnapshotEO snap where ps.Type='sharedblock' and vol.primaryStorageUuid=ps.uuid and vol.uuid=snap.volumeUuid and vol.isShareable <> 0"
        return self._run_sql(sql)

    def _update_format(self, volumeUuid, format):
        sql = "update VolumeVO set VolumeVO.format='%s' where VolumeVO.uuid='%s'" % (format, volumeUuid)
        self._run_sql(sql)

    def _delete_qcow2_volume(self, args):
        shared_volumes = self._find_shared_volumes("raw")
        if len(shared_volumes) == 0:
            info("not found any shared volume need to be delete qcow2 file")
            return

        primary_storage_uuids = set()
        for volume in shared_volumes:
            primary_storage_uuids.add(volume["primaryStorageUuid"])
        for primary_storage_uuid in primary_storage_uuids:
            hosts = self._select_host(primary_storage_uuid)
            self._copy_script(hosts[0]["managementIp"])
            cmd = ShellCmd("ssh -i %s root@%s 'python %s %s %s'" %
                           (self.key, hosts[0]["managementIp"], self.script_path, "find_qcow2", primary_storage_uuid))
            cmd(True)
            warn("find qcow2 file [%s] of primary storage %s need to be delete" % (cmd.stdout, primary_storage_uuid))
        if args.dryrun.lower() != "false":
            info("run in dryrun mode, return now")
            return
        qcow2_files = []
        for primary_storage_uuid in primary_storage_uuids:
            hosts = self._select_host(primary_storage_uuid)
            cmd = ShellCmd("ssh -i %s root@%s 'python %s %s %s'" %
                           (self.key, hosts[0]["managementIp"], self.script_path, "delete_qcow2", primary_storage_uuid))
            cmd(True)
            qcow2_files.append(cmd.stdout)
        info("deleted qcow2 files: %s" % qcow2_files)

    def _convert_snapshot(self, args):
        snaps = self._find_shared_snapshots()
        if len(snaps) == 0:
            info("not found any snapshots of shared volume on sharedblock group storage")
            return
        warn("find snapshots of shared volume on sharedblock group primary storage: [name: %s, uuid: %s]" %
             (map(lambda x: x["name"], snaps), map(lambda x: x["uuid"], snaps)))
        if args.dryrun.lower() != "false":
            info("run in dryrun mode, return now")
            return
        if args.backup_storage_uuid is None or args.backup_storage_uuid == "":
            error("not specify backup_storage_uuid")

        for snap in snaps:
            info("start CreateDataVolumeTemplateFromVolumeSnapshot on snapshot[name:%s, uuid:%s]" % (snap["name"], snap["uuid"]))
            cmd = ShellCmd("zstack-cli LogInByAccount accountName=admin password=%s" % args.admin_password)
            cmd(True)
            imageName = "from-shared-volume-%s-snapshot-%s-%s" % (snap["volumeUuid"], snap["name"], snap["uuid"])
            cmd = ShellCmd("zstack-cli CreateDataVolumeTemplateFromVolumeSnapshot timeout=259200000 name=%s description=%s snapshotUuid=%s backupStorageUuids=%s" %
                           (imageName, imageName, snap["uuid"], args.backup_storage_uuid))
            cmd(True)
            info("CreateDataVolumeTemplateFromVolumeSnapshot on snapshot[name:%s, uuid:%s] done, named %s" % (snap["name"], snap["uuid"], imageName))

    def _delete_snapshot(self, args):
        snaps = self._find_shared_snapshots()
        if len(snaps) == 0:
            info("not found any snapshots of shared volume on sharedblock group storage")
            return
        warn("find snapshots of shared volume on sharedblock group primary storage: [name: %s, uuid: %s, installPath: %s]" %
             (map(lambda x: x["name"], snaps), map(lambda x: x["uuid"], snaps), map(lambda x: x["primaryStorageInstallPath"], snaps)))
        if args.dryrun.lower() != "false":
            info("run in dryrun mode, return now")
            return

        for snap in snaps:
            hosts = self._select_host(snap["primaryStorageUuid"])
            snapAbsPath = snap["primaryStorageInstallPath"].replace("sharedblock:/", "/dev")
            info("start delete on snapshot[name:%s, uuid:%s, installPath: %s] on host[ip: %s]" % (
                snap["name"], snap["uuid"], snap["primaryStorageInstallPath"], hosts[0]["managementIp"]))
            for host in hosts:
                cmd = ShellCmd(
                    "ssh -i %s root@%s 'lvchange -an %s'" % (self.key, host["managementIp"], snapAbsPath))
                cmd(True)
            cmd = ShellCmd("ssh -i %s root@%s 'lvremove -y %s'" % (self.key, hosts[0]["managementIp"], snapAbsPath))
            cmd(True)
            self._update_volumeSnapshotEO(snap["uuid"])
            self._update_VolumeSnapshotTreeEO(snap["volumeUuid"])

    def _update_volumeSnapshotEO(self, snapshotUuid):
        sql = "update VolumeSnapshotEO set VolumeSnapshotEO.deleted=NOW() where VolumeSnapshotEO.uuid='%s'" % snapshotUuid
        self._run_sql(sql)

    def _update_VolumeSnapshotTreeEO(self, volumeUuid):
        sql = "update VolumeSnapshotTreeEO set VolumeSnapshotTreeEO.deleted=NOW() where VolumeSnapshotTreeEO.volumeUuid='%s'" % volumeUuid
        self._run_sql(sql)


class DumpMNThreadCmd(Command):
    thread_dump_file = "zstack-mn-thread-dump.log"
    def __init__(self):
        super(DumpMNThreadCmd, self).__init__()
        self.name = "dump_mn_thread"
        self.description = "dump Java stack traces of ZStack MN threads"
        ctl.register_command(self)

    def run(self, args):
        mn_pid = get_management_node_pid()
        if not mn_pid:
            raise CtlError("ZStack MN is not running!")

        shell("sudo -u zstack jstack %s > %s" % (mn_pid, self.thread_dump_file))
        info("The Java stack traces of ZStack threads has been dumped to %s" % os.path.join(os.getcwd(), self.thread_dump_file))


class DumpMNTaskQueueCmd(Command):
    def __init__(self):
        super(DumpMNTaskQueueCmd, self).__init__()
        self.name = "dump_mn_queue"
        self.description = "dump ZStack MN task queue"
        ctl.register_command(self)

    def run(self, args):
        mn_pid = get_management_node_pid()
        if not mn_pid:
            raise CtlError("ZStack MN is not running!")

        shell("kill -USR2 %s" % mn_pid)
        mn_log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
        time.sleep(1)
        # only print last matched TASK QUEUE BLOCK
        output = shell("sed -n '/BEGIN TASK QUEUE DUMP/,/END TASK QUEUE DUMP/p' %s | tac | awk '/BEGIN TASK QUEUE DUMP/{ print; exit} 1' | tac " % mn_log_path)
        output = output.strip(' \t\n\r')
        info(output)


class TimelineCmd(Command):
    def __init__(self, stdout=sys.stdout):
        super(TimelineCmd, self).__init__()
        self.stdout = stdout
        self.name = "timeline"
        self.description = "dump execution timeline of given API or task UUID"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--log-file', required=True, default="", help='text or gzip archive log files, seperated by "," without whitespace')
        parser.add_argument('-k', '--key', required=True, default="", help='the API or task UUID for search. ' + timeline_doc)
        parser.add_argument('-t', '--top', type=int, default=0, help='show top N time consumers')
        parser.add_argument('-p', '--plot', action='store_true', help='generate a Gnuplot script')

    def run(self, args, log_file_list=[], diagnose_log_file=""):
        timeline = TaskTimeline()

        log_file_list = args.log_file.split(',')
        for log_file in log_file_list:
            if not os.path.isfile(log_file):
                raise CtlError("The log file %s was not found!" % args.log_file)
            if log_file.endswith('.gz'):
                f = gzip.open(log_file, 'r')
            else:
                f = open(log_file, 'r')

            timeline.build(f, args.key, diagnose_log_file)
            f.close()

        if diagnose_log_file:
            info("\nlogs with key word '%s' has been filtered into file %s\n" % (args.key, diagnose_log_file))
            with open(diagnose_log_file, 'w+') as f:
                f.write(''.join(timeline.logs))
            info("Execution Timeline:")
        timeline.dumpflow(self.stdout, args.top)

        if args.plot:
            timeline.generate_gantt(args.key)


class DiagnoseCmd(Command):
    ctl_timeline = "timeline"
    ctl_collect_log = "configured_collect_log"
    def __init__(self):
        super(DiagnoseCmd, self).__init__()
        self.name = "diagnose"
        self.description = "collect SBLK related logs and diagnose errors of given type, like scsi"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('-t',
                            '--type',
                            help='collect related logs and diagnose errors of given type [scsi, api]',
                            required=True)
        parser.add_argument('-d',
                            '--daytime',
                            help='number of recent days log to be collected, default is 5',
                            default=5)
        parser.add_argument('-s',
                            '--since',
                            help='collect logs from datetime below format:\'yyyy-MM-dd\' or \'yyyy-MM-dd_hh:mm:ss\', default datetime is 24h ago',
                            default=None)
        parser.add_argument('-k', '--key-word', default="", help='key word for search in mn logs, like apiid/taskid/uuid.')

    def run(self, args):
        from trait_parser import diagnose
        time_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        diagnose_log_file = '%s-diagnose-log-%s' % (args.type, time_stamp)
        log_dir = '-'.join(['diagnose', args.type, time_stamp])
        cllect_log_args_list = [self.ctl_collect_log, '--no-tarball', '--collect-dir-name', log_dir]

        if args.type == 'scsi':
            cllect_log_args_list.extend(['--scsi-diagnose'])

        elif args.type == 'mn':
            if not args.key_word:
                raise CtlError("the '-k' paramter is required when diagnose mn, run 'zstack-ctl diagnose -h' for more help.")
            args.daytime = 1
            cllect_log_args_list.extend([self.ctl_collect_log, '--mn-diagnose'])

        else:
            info('unknown argument %s, available types are [scsi, mn]' % args.type)
            return

        # DiagnoseCmd's '--since/daytime' mapped to ConfiguredCollectLogCmd's '--from-date/since'
        if args.since is not None:
            cllect_log_args_list.extend(['--from-date', args.since])
        else:
            cllect_log_args_list.extend(['--since', str(args.daytime) + 'd'])

        ctl_collect_log_args, _ = ctl.main_parser.parse_known_args(cllect_log_args_list)
        ctl.commands[self.ctl_collect_log](ctl_collect_log_args)

        info('Analyzing...')
        if args.type == 'mn':
            log_file_list = []
            for mn_log_dir in os.listdir(log_dir):
                mn_log_dir_path = os.path.join(log_dir, mn_log_dir)
                if os.path.isfile(mn_log_dir_path):
                    continue

                mn_logs = os.path.join(mn_log_dir_path, "mn-logs")
                for mn_log in os.listdir(mn_logs):
                    mn_log_path = os.path.join(mn_logs, mn_log)
                    log_file_list.append(mn_log_path)

            timeline_args, _ = ctl.main_parser.parse_known_args([
                self.ctl_timeline ,'--key', args.key_word, '--log-file', ','.join(log_file_list)
            ])

            ctl.commands[self.ctl_timeline](timeline_args, log_file_list, diagnose_log_file)
            return

        diagnose(log_dir, diagnose_log_file, args)


def main():
    AddManagementNodeCmd()
    BootstrapCmd()
    ChangeIpCmd()
    CollectLogCmd()
    ConfigureCmd()
    ConfiguredCollectLogCmd()
    DumpMysqlCmd()
    ChangeMysqlPasswordCmd()
    DeployDBCmd()
    DeployUIDBCmd()
    GetEnvironmentVariableCmd()
    InstallHACmd()
    InstallDbCmd()
    InstallRabbitCmd()
    InstallManagementNodeCmd()
    InstallLicenseCmd()
    ClearLicenseCmd()
    ShowConfiguration()
    GetConfiguration()
    MNServerPortChange()
    SetEnvironmentVariableCmd()
    SetDeploymentCmd()
    PullDatabaseBackupCmd()
    RollbackManagementNodeCmd()
    RollbackDatabaseCmd()
    ResetAdminPasswordCmd()
    ResetRabbitCmd()
    RestoreConfigCmd()
    RestartNodeCmd()
    RestoreMysqlPreCheckCmd()
    RestoreMysqlCmd()
    ZBoxBackupScanCmd()
    ZBoxBackupRestoreCmd()
    RecoverHACmd()
    ScanDatabaseBackupCmd()
    ShowStatus2Cmd()
    ShowStatus3Cmd()
    ShowStatusCmd()
    StartCmd()
    StopCmd()
    SaveConfigCmd()
    StartAllCmd()
    StopAllCmd()
    TailLogCmd()
    UnsetEnvironmentVariableCmd()
    UpgradeManagementNodeCmd()
    UpgradeMultiManagementNodeCmd()
    UpgradeDbCmd()
    UpgradeUIDbCmd()
    UpgradeCtlCmd()
    UpgradeHACmd()
    StartVDIUICmd()
    StopVDIUiCmd()
    VDIUiStatusCmd()
    ShowSessionCmd()
    DropSessionCmd()
    CleanAnsibleCacheCmd()
    RemovePrometheusDataCmd()
    GetZStackVersion()
    SharedBlockQcow2SharedVolumeFixCmd()
    MiniResetHostCmd()
    RefreshAuditCmd()
    MysqlProcessList()
    MysqlRestrictConnection()

    # If tools/zstack-ui.war exists, then install zstack-ui
    # else, install zstack-dashboard
    ctl.locate_zstack_home()
    InstallZstackUiCmd()
    StartUiCmd()
    StopUiCmd()
    UiStatusCmd()
    ConfigUiCmd()
    ShowUiCfgCmd()
    DumpMNThreadCmd()
    DumpMNTaskQueueCmd()
    TimelineCmd()
    DiagnoseCmd()

    try:
        ctl.run()
    except CtlError as e:
        if ctl.verbose:
            error_not_exit(traceback.format_exc())
        error(str(e))

if __name__ == '__main__':
    main()
