#!/usr/bin/python

import argparse
import sys
import os
import subprocess
import signal
import getpass
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
from zstacklib import *
import jinja2
import socket
import struct
import fcntl
import commands
import threading
import itertools

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
ret=$?
rm -f %s
exit $ret
EOF''' % (remote_path, cmd, remote_path, ' '.join(params), remote_path)

    scmd = ShellCmd('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  %s "%s"' % (ip, script), pipe=pipe)
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

class CtlError(Exception):
    pass

def warn(msg):
    sys.stdout.write(colored('WARNING: %s\n' % msg, 'yellow'))

def error(msg):
    sys.stderr.write(colored('ERROR: %s\n' % msg, 'red'))
    sys.exit(1)

def error_not_exit(msg):
    sys.stderr.write(colored('ERROR: %s\n' % msg, 'red'))

def info(*msg):
    if len(msg) == 1:
        out = '%s\n' % ''.join(msg)
    else:
        out = ''.join(msg)
    sys.stdout.write(out)

def get_detail_version():
    detailed_version_file = os.path.join(ctl.DEFAULT_ZSTACK_HOME, "VERSION")
    if os.path.exists(detailed_version_file):
        with open(detailed_version_file, 'r') as fd:
            detailed_version = fd.read()
            return detailed_version
    else:
        return None

def check_ip_port(host, port):
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((host, int(port)))
    return result == 0

def get_zstack_version(db_hostname, db_port, db_user, db_password):
    query = MySqlCommandLineQuery()
    query.host = db_hostname
    query.port = db_port
    query.user = db_user
    query.password = db_password
    query.table = 'zstack'
    query.sql = "select version from schema_version order by version desc"
    ret = query.query()

    v = ret[0]
    version = v['version']
    return version

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
    cmd = ShellCmd("""dev=`ip route|grep default|awk '{print $NF}'`; ip addr show $dev |grep "inet "|awk '{print $2}'|head -n 1 |awk -F '/' '{print $1}'""")
    cmd(False)
    return cmd.stdout.strip()

def get_yum_repo_from_property():
    yum_repo = ctl.read_property('Ansible.var.zstack_repo')
    if not yum_repo:
        return yum_repo

    # avoid http server didn't start when install package
    if 'zstack-mn' in yum_repo:
        yum_repo = yum_repo.replace("zstack-mn","zstack-local")
    if 'qemu-kvm-ev-mn' in yum_repo:
        yum_repo = yum_repo.replace("qemu-kvm-ev-mn","qemu-kvm-ev")
    return yum_repo

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

def expand_path(path):
    if path.startswith('~'):
        return os.path.expanduser(path)
    else:
        return os.path.abspath(path)

def check_host_info_format(host_info):
    '''check install ha and install multi mn node info format'''
    if '@' not in host_info:
        error("Host connect information should follow format: 'root:password@host_ip', please check your input!")
    else:
        # get user and password
        if ':' not in host_info.split('@')[0]:
            error("Host connect information should follow format: 'root:password@host_ip', please check your input!")
        else:
            user = host_info.split('@')[0].split(':')[0]
            password = host_info.split('@')[0].split(':')[1]
            if user != "" and user != "root":
                print "Only root user can be supported, please change user to root"
            if user == "":
                user = "root"
        # get ip and port
        if ':' not in host_info.split('@')[1]:
            ip = host_info.split('@')[1]
            port = '22'
        else:
            ip = host_info.split('@')[1].split(':')[0]
            port = host_info.split('@')[1].split(':')[1]
        return (user, password, ip, port)

def check_host_password(password, ip):
    command ='timeout 10 sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o  PubkeyAuthentication=no -o ' \
             'StrictHostKeyChecking=no  root@%s echo ""' % (password, ip)
    (status, output) = commands.getstatusoutput(command)
    if status != 0:
        error("Connect to host: '%s' with password '%s' failed! Please check password firstly and make sure you have "
              "disabled UseDNS in '/etc/ssh/sshd_config' on %s" % (ip, password, ip))



class SpinnerInfo(object):
    spinner_status = []
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

class UseUserZstack(object):
    def __init__(self):
        self.root_uid = None
        self.root_gid = None
        check_zstack_user()

    def __enter__(self):
        self.root_uid = os.getuid()
        self.root_gid = os.getgid()
        self.root_home = os.environ['HOME']

        os.setegid(grp.getgrnam('zstack').gr_gid)
        os.seteuid(pwd.getpwnam('zstack').pw_uid)
        os.environ['HOME'] = os.path.expanduser('~zstack')

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.seteuid(self.root_uid)
        os.setegid(self.root_gid)
        os.environ['HOME'] = self.root_home

def use_user_zstack():
    return UseUserZstack()

class PropertyFile(object):
    def __init__(self, path, use_zstack=True):
        self.path = path
        self.use_zstack = use_zstack
        if not os.path.isfile(self.path):
            raise CtlError('cannot find property file at %s' % self.path)

        with on_error("errors on reading %s" % self.path):
            self.config = ConfigObj(self.path, write_empty_values=True)

    def read_all_properties(self):
        with on_error("errors on reading %s" % self.path):
            return self.config.items()

    def delete_properties(self, keys):
        for k in keys:
            if k in self.config:
                del self.config[k]

        with use_user_zstack():
            self.config.write()

    def read_property(self, key):
        with on_error("errors on reading %s" % self.path):
            return self.config.get(key, None)

    def write_property(self, key, value):
        with on_error("errors on writing (%s=%s) to %s" % (key, value, self.path)):
            if self.use_zstack:
                with use_user_zstack():
                    self.config[key] = value
                    self.config.write()
            else:
                self.config[key] = value
                self.config.write()

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

class Ctl(object):
    DEFAULT_ZSTACK_HOME = '/usr/local/zstack/apache-tomcat/webapps/zstack/'
    USER_ZSTACK_HOME_DIR = os.path.expanduser('~zstack')
    LAST_ALIVE_MYSQL_IP = "MYSQL_LATEST_IP"
    LAST_ALIVE_MYSQL_PORT = "MYSQL_LATEST_PORT"

    def __init__(self):
        self.commands = {}
        self.command_list = []
        self.main_parser = CtlParser(prog='zstackctl', description="ZStack management tool", formatter_class=argparse.RawTextHelpFormatter)
        self.main_parser.add_argument('-v', help="verbose, print execution details", dest="verbose", action="store_true", default=False)
        self.zstack_home = None
        self.properties_file_path = None
        self.verbose = False
        self.extra_arguments = None

    def register_command(self, cmd):
        assert cmd.name, "command name cannot be None"
        assert cmd.description, "command description cannot be None"
        self.commands[cmd.name] = cmd
        self.command_list.append(cmd)

    def _locate_zstack_home(self):
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
        self.ssh_private_key = os.path.join(self.zstack_home, 'WEB-INF/classes/ansible/rsaKeys/id_rsa')
        self.ssh_public_key = os.path.join(self.zstack_home, 'WEB-INF/classes/ansible/rsaKeys/id_rsa.pub')
        if not os.path.isfile(self.properties_file_path):
            warn('cannot find %s, your ZStack installation may have crashed' % self.properties_file_path)

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
        if os.getuid() != 0:
            raise CtlError('zstack-ctl needs root privilege, please run with sudo')

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
        self.verbose = args.verbose
        globals()['verbose'] = self.verbose

        cmd = self.commands[args.sub_command_name]

        if cmd.need_zstack_home():
            self._locate_zstack_home()

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
            self._locate_zstack_home()

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

    def write_property(self, key, value):
        prop = PropertyFile(self.properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.write_property(key, value)

    def get_db_url(self):
        db_url = self.read_property("DB.url")
        if not db_url:
            db_url = self.read_property('DbFacadeDataSource.jdbcUrl')
        if not db_url:
            raise CtlError("cannot find DB url in %s. please set DB.url" % self.properties_file_path)
        return db_url

    def get_live_mysql_portal(self):
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
                sql = 'mysql --host=%s --port=%s --user=%s --password=%s -e "select 1"' % (hostname, port, user, password)
            else:
                sql = 'mysql --host=%s --port=%s --user=%s -e "select 1"' % (hostname, port, user)

            cmd = ShellCmd(sql)
            cmd(False)
            if cmd.return_code == 0:
                # record the IP and port, so next time we will try them first
                ctl.put_envs([
                    (self.LAST_ALIVE_MYSQL_IP, hostname),
                    (self.LAST_ALIVE_MYSQL_PORT, port)
                ])
                return hostname, port, user, password

            errors.append('failed to connect to the mysql server[hostname:%s, port:%s, user:%s, password:%s]: %s %s' % (
                hostname, port, user, password, cmd.stderr, cmd.stdout
            ))

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

class ShellCmd(object):
    def __init__(self, cmd, workdir=None, pipe=True):
        self.cmd = cmd
        if pipe:
            self.process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, cwd=workdir)
        else:
            self.process = subprocess.Popen(cmd, shell=True, cwd=workdir)

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

class Command(object):
    def __init__(self):
        self.name = None
        self.description = None
        self.hide = False
        self.cleanup_routines = []

    def install_argparse_arguments(self, parser):
        pass

    def install_cleanup_routine(self, func):
        self.cleanup_routines.append(func)

    def need_zstack_home(self):
        return True

    def need_zstack_user(self):
        return True

    def __call__(self, *args, **kwargs):
        try:
            self.run(*args)
        finally:
            for c in self.cleanup_routines:
                c()

    def run(self, args):
        raise CtlError('the command is not implemented')

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

    what_tool = use_tool()
    if what_tool == USE_CURL:
        return ShellCmd('''curl --noproxy --connect-timeout 1 --retry %s --retry-delay 0 --retry-max-time %s --max-time %s -H "Content-Type: application/json" -d '{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://%s:8080/zstack/api''' % (timeout, timeout, timeout, mn_node))
    elif what_tool == USE_WGET:
        return ShellCmd('''wget --no-proxy -O- --tries=%s --timeout=1  --header=Content-Type:application/json --post-data='{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://%s:8080/zstack/api''' % (timeout, mn_node))
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
            cmd = '''mysql -u %s -p%s --host %s --port %s -t %s -e "%s"''' % (self.user, self.password, self.host,
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

    def _stop_remote(self, args):
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  %s "/usr/bin/zstack-ctl status"' % args.host)

    def run(self, args):
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

            def write_status(status):
                info_list.append('MN status: %s' % status)

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
                else:
                    write_status(colored('Stopped', 'red'))
                return

            if 'false' in cmd.stdout:
                write_status('Starting, should be ready in a few seconds')
            elif 'true' in cmd.stdout:
                write_status(colored('Running', 'green') + ' [PID:%s]' % pid)
            else:
                write_status('Unknown')

        def show_version():
            try:
                db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
            except:
                info('version: %s' % colored('unknown, MySQL is not running', 'yellow'))
                return

            if db_password:
                cmd = ShellCmd('''mysql -u %s -p%s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_password, db_hostname, db_port))
            else:
                cmd = ShellCmd('''mysql -u %s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_hostname, db_port))

            cmd(False)
            if cmd.return_code != 0:
                info('version: %s' % colored('unknown, MySQL is not running', 'yellow'))
                return

            out = cmd.stdout
            if 'schema_version' not in out:
                version = '0.6'
            else:
                version = get_zstack_version(db_hostname, db_port, db_user, db_password)

            detailed_version = get_detail_version()
            if detailed_version is not None:
                info('version: %s (%s)' % (version, detailed_version))
            else:
                info('version: %s' % version)

        check_zstack_status()

        info('\n'.join(info_list))
        ctl.internal_run('ui_status')
        show_version()

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
        ctl.register_command(self)

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

class TailLogCmd(Command):
    def __init__(self):
        super(TailLogCmd, self).__init__()
        self.name = 'taillog'
        self.description = "shortcut to print management node log to stdout"
        ctl.register_command(self)

    def run(self, args):
        log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
        log_path = os.path.normpath(log_path)
        if not os.path.isfile(log_path):
            raise CtlError('cannot find %s' % log_path)

        script = ShellCmd('tail -f %s' % log_path, pipe=False)
        script()

class ConfigureCmd(Command):
    def __init__(self):
        super(ConfigureCmd, self).__init__()
        self.name = 'configure'
        self.description = "configure zstack.properties"
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

class StopAllCmd(Command):
    def __init__(self):
        super(StopAllCmd, self).__init__()
        self.name = 'stop'
        self.description = 'stop all ZStack related services including zstack management node, web UI' \
                           ' if those services are installed'
        ctl.register_command(self)

    def run(self, args):
        def stop_mgmt_node():
            info(colored('Stopping ZStack management node, it may take a few minutes...', 'blue'))
            ctl.internal_run('stop_node')

        def stop_ui():
            virtualenv = '/var/lib/zstack/virtualenv/zstack-dashboard'
            if not os.path.exists(virtualenv):
                info('skip stopping web UI, it is not installed')
                return

            info(colored('Stopping ZStack web UI, it may take a few minutes...', 'blue'))
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
            info(colored('Starting ZStack management node, it may take a few minutes...', 'blue'))
            if args.daemon:
                ctl.internal_run('start_node', '--daemon')
            else:
                ctl.internal_run('start_node')

        def start_ui():
            virtualenv = '/var/lib/zstack/virtualenv/zstack-dashboard'
            if not os.path.exists(virtualenv):
                info('skip starting web UI, it is not installed')
                return

            info(colored('Starting ZStack web UI, it may take a few minutes...', 'blue'))
            ctl.internal_run('start_ui')

        start_mgmt_node()
        start_ui()

class StartCmd(Command):
    START_SCRIPT = '../../bin/startup.sh'
    SET_ENV_SCRIPT = '../../bin/setenv.sh'

    def __init__(self):
        super(StartCmd, self).__init__()
        self.name = 'start_node'
        self.description = 'start the ZStack management node on this machine'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='SSH URL, for example, root@192.168.0.10, to start the management node on a remote machine')
        parser.add_argument('--timeout', help='Wait for ZStack Server startup timeout, default is 300 seconds.', default=300)
        parser.add_argument('--daemon', help='Start ZStack in daemon mode. Only used with systemd.', action='store_true', default=False)

    def _start_remote(self, args):
        info('it may take a while because zstack-ctl will wait for management node ready to serve API')
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  %s "/usr/bin/zstack-ctl start_node --timeout=%s"' % (args.host, args.timeout))

    def run(self, args):
        if args.host:
            self._start_remote(args)
            return

        # clean the error log before booting
        boot_error_log = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'bootError.log')
        shell('rm -f %s' % boot_error_log)

        pid = get_management_node_pid()
        if pid:
            info('the management node[pid:%s] is already running' % pid)
            return
        else:
            shell('rm -f %s' % os.path.join(os.path.expanduser('~zstack'), "management-server.pid"))

        def check_java_version():
            ver = shell('java -version 2>&1 | grep -w version')
            if '1.8' not in ver:
                raise CtlError('ZStack requires Java8, your current version is %s\n'
                               'please run "update-alternatives --config java" to set Java to Java8')

        def check_8080():
            if shell_return('netstat -nap | grep :8080 | grep LISTEN > /dev/null') == 0:
                raise CtlError('8080 is occupied by some process. Please use netstat to find out and stop it')

        def check_msyql():
            db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()

            if not check_ip_port(db_hostname, db_port):
                raise CtlError('unable to connect to %s:%s, please check if the MySQL is running and the firewall rules' % (db_hostname, db_port))

            with on_error('unable to connect to MySQL'):
                shell('mysql --host=%s --user=%s --password=%s --port=%s -e "select 1"' % (db_hostname, db_user, db_password, db_port))

        def check_rabbitmq():
            RABBIT_PORT = 5672

            def check_username_password_if_need(ip, username, password):
                if not username or not password:
                    return

                cmd = ShellCmd('curl -u %s:%s http://%s:15672/api/whoami' % (username, password, ip))
                cmd(False)
                if cmd.return_code == 7:
                    warn('unable to connect to the rabbitmq management plugin at %s:15672. The possible reasons are:\n'
                         '  1) the plugin is not installed, you can install it by "rabbitmq-plugins enable rabbitmq_management,"\n'
                         '     then restart the rabbitmq by "service rabbitmq-server restart"\n'
                         '  2) the port 15672 is blocked by the firewall\n'
                         'without the plugin, we cannot check the validity of the rabbitmq username/password configured in zstack.properties' % ip)

                elif cmd.return_code != 0:
                    cmd.raise_error()
                else:
                    if 'error' in cmd.stdout:
                        raise CtlError('unable tot connect to the rabbitmq server[ip:%s] with username/password configured in zstack.properties.\n'
                                       'If you have reset the rabbimtq server, get the username/password from zstack.properties and do followings on the rabbitmq server:\n'
                                       '1) rabbitmqctl add_user $username $password\n'
                                       '2) rabbitmqctl set_user_tags $username administrator\n'
                                       '3) rabbitmqctl set_permissions -p / $username ".*" ".*" ".*"\n' % ip)


            with on_error('unable to get RabbitMQ server IPs from %s, please check CloudBus.serverIp.0'):
                ips = ctl.read_property_list('CloudBus.serverIp.')
                if not ips:
                    raise CtlError('no RabbitMQ IPs defined in %s, please specify it use CloudBus.serverIp.0=the_ip' % ctl.properties_file_path)

                rabbit_username = ctl.read_property('CloudBus.rabbitmqUsername')
                rabbit_password = ctl.read_property('CloudBus.rabbitmqPassword')

                if rabbit_password and not rabbit_username:
                    raise CtlError('CloudBus.rabbitmqPassword is set but CloudBus.rabbitmqUsername is missing in zstack.properties')
                elif not rabbit_password and rabbit_username:
                    raise CtlError('CloudBus.rabbitmqUsername is set but CloudBus.rabbitmqPassword is missing in zstack.properties')

                success = False
                workable_ip = None
                for key, ip in ips:
                    if ":" in ip:
                        ip, port = ip.split(':')
                    else:
                        port = RABBIT_PORT

                    if check_ip_port(ip, port):
                        workable_ip = ip
                        success = True
                    else:
                        warn('cannot connect to the RabbitMQ server[ip:%s, port:%s]' % (ip, RABBIT_PORT))

                if not success:
                    raise CtlError('cannot connect to all RabbitMQ servers[ip:%s, port:%s] defined in %s' %
                                    (ips, RABBIT_PORT, ctl.properties_file_path))
                else:
                    check_username_password_if_need(workable_ip, rabbit_username, rabbit_password)

        def prepare_setenv():
            setenv_path = os.path.join(ctl.zstack_home, self.SET_ENV_SCRIPT)
            catalina_opts = [
                '-Djava.net.preferIPv4Stack=true',
                '-Dcom.sun.management.jmxremote=true',
                '-Djava.security.egd=file:/dev/./urandom',
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
                catalina_opts.append('-Xmx4096M')

            with open(setenv_path, 'w') as fd:
                fd.write('export CATALINA_OPTS=" %s"' % ' '.join(catalina_opts))

        def start_mgmt_node():
            shell('sudo -u zstack sh %s -DappName=zstack' % os.path.join(ctl.zstack_home, self.START_SCRIPT))

            info("successfully started Tomcat container; now it's waiting for the management node ready for serving APIs, which may take a few seconds")

        def wait_mgmt_node_start():
            log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
            timeout = int(args.timeout)
            @loop_until_timeout(timeout)
            def check():
                if os.path.exists(boot_error_log):
                    with open(boot_error_log, 'r') as fd:
                        raise CtlError('the management server fails to boot; details can be found in the log[%s],'
                                       'here is a brief of the error:\n%s' % (log_path, fd.read()))

                cmd = create_check_mgmt_node_command(1)
                cmd(False)
                return cmd.return_code == 0

            if not check():
                raise CtlError('no management-node-ready message received within %s seconds, please check error in log file %s' % (timeout, log_path))

        user = getpass.getuser()
        if user != 'root':
            raise CtlError('please use sudo or root user')

        check_java_version()
        check_8080()
        check_msyql()
        check_rabbitmq()
        prepare_setenv()
        start_mgmt_node()
        #sleep a while, since zstack won't start up so quickly
        time.sleep(5)

        try:
            wait_mgmt_node_start()
        except CtlError as e:
            try:
                info("the management node failed to start, stop it now ...")
                ctl.internal_run('stop_node')
            except:
                pass

            raise e

        if not args.daemon:
            shell('which systemctl >/dev/null 2>&1; [ $? -eq 0 ] && systemctl start zstack', is_exception = False)
        info('successfully started management node')

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

        pid = get_management_node_pid()
        if not pid:
            info('the management node has been stopped')
            return

        timeout = 30
        if not args.force:
            @loop_until_timeout(timeout)
            def wait_stop():
                return get_management_node_pid() is None

            shell('bash %s' % os.path.join(ctl.zstack_home, self.STOP_SCRIPT))
            if wait_stop():
                info('successfully stopped management node')
                return

        pid = get_management_node_pid()
        if pid:
            if not args.force:
                info('unable to stop management node within %s seconds, kill it' % timeout)
            with on_error('unable to kill -9 %s' % pid):
                shell('kill -9 %s' % pid)

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
        if not args.yum:
            args.yum = get_yum_repo_from_property()

        script = ShellCmd("ip addr |grep 'inet '|grep -v '127.0.0.1'|awk '{print $2}'|awk -F '/' '{print $1}'")
        script(True)
        current_host_ips = script.stdout.split('\n')

        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      root_password: $root_password
      login_password: $login_password
      yum_repo: "$yum_repo"

  tasks:
    - name: pre-install script
      script: $pre_install_script

    - name: install MySQL for RedHat 6 through user defined repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7' and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y mysql mysql-server
      register: install_result

    - name: install MySQL for RedHat 6 through system defined repos
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7' and yum_repo == 'false'
      shell: "yum clean metadata; yum --nogpgcheck install -y mysql mysql-server "
      register: install_result

    - name: install MySQL for RedHat 7 from local
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y  mariadb mariadb-server iptables-services
      register: install_result

    - name: install MySQL for RedHat 7 from local
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y  mariadb mariadb-server iptables-services
      register: install_result

    - name: install MySQL for Ubuntu
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - mariadb-client
        - mariadb-server
      register: install_result

    - name: open 3306 port
      when: ansible_os_family == 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 3306 -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 3306 -j ACCEPT && service iptables save)

    - name: open 3306 port
      when: ansible_os_family != 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 3306 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 3306 -j ACCEPT

    - name: run post-install script
      script: $post_install_script

    - name: enable MySQL daemon on RedHat 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      service: name=mysqld state=restarted enabled=yes

    - name: enable MySQL daemon on RedHat 7
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7'
      service: name=mariadb state=restarted enabled=yes

    - name: enable MySQL on Ubuntu
      when: ansible_os_family == 'Debian'
      service: name=mysql state=restarted enabled=yes

    - name: change root password
      shell: $change_password_cmd
      register: change_root_result
      ignore_errors: yes

    - name: grant remote access
      when: change_root_result.rc == 0
      shell: $grant_access_cmd

    - name: rollback MySQL installation on RedHat 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7' and change_root_result.rc != 0 and install_result.changed == True
      shell: rpm -ev mysql mysql-server

    - name: rollback MySQL installation on RedHat 7
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and change_root_result.rc != 0 and install_result.changed == True
      shell: rpm -ev mariadb mariadb-server

    - name: rollback MySql installation on Ubuntu
      when: ansible_os_family == 'Debian' and change_root_result.rc != 0 and install_result.changed == True
      apt: pkg={{item}} state=absent update_cache=yes
      with_items:
        - mysql-client
        - mysql-server

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
                more_cmd += "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '' WITH GRANT OPTION;"  % ip
            grant_access_cmd = '''/usr/bin/mysql -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '' WITH GRANT OPTION; %s FLUSH PRIVILEGES;"''' % (args.host, more_cmd)
        else:
            if not args.root_password:
                args.root_password = args.login_password
            more_cmd = ' '
            for ip in current_host_ips:
                if not ip:
                    continue
                more_cmd += "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION;"  % (ip, args.root_password)
            grant_access_cmd = '''/usr/bin/mysql -u root -p%s -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '%s' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION; %s FLUSH PRIVILEGES;"''' % (args.root_password, args.root_password, args.host, args.root_password, more_cmd)

        if args.login_password is not None:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root -p{{login_password}} password {{root_password}}'
        else:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root password {{root_password}}'

        pre_install_script = '''
if [ -f /etc/redhat-release ] ; then

grep ' 7' /etc/redhat-release
if [ $? -eq 0 ]; then
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=\$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
else
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=\$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
fi

[ -d /etc/yum.repos.d/ ] && echo -e "#aliyun base\n[alibase]\nname=CentOS-\$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

[ -d /etc/yum.repos.d/ ] && echo -e "#163 base\n[163base]\nname=CentOS-\$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo
fi

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
DNS hijacking will cause MySQL and RabbitMQ not working."
exit 1
'''
        fd, pre_install_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(pre_install_script)

        def cleanup_pre_install_script():
            os.remove(pre_install_script_path)

        self.install_cleanup_routine(cleanup_pre_install_script)

        post_install_script = '''
if [ -f /etc/mysql/mariadb.conf.d/50-server.cnf ]; then
    #ubuntu 16.04
    mysql_conf=/etc/mysql/mariadb.conf.d/50-server.cnf
elif [ -f /etc/mysql/my.cnf ]; then
    # Ubuntu 14.04
    mysql_conf=/etc/mysql/my.cnf
elif [ -f /etc/my.cnf ]; then
    # centos
    mysql_conf=/etc/my.cnf
fi

sed -i 's/^bind-address/#bind-address/' $mysql_conf
sed -i 's/^skip-networking/#skip-networking/' $mysql_conf
sed -i 's/^bind-address/#bind-address/' $mysql_conf
grep '^character-set-server' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    sed -i '/\[mysqld\]/a character-set-server=utf8\' $mysql_conf
fi
grep '^skip-name-resolve' $mysql_conf >/dev/null 2>&1
if [ $? -ne 0 ]; then
    sed -i '/\[mysqld\]/a skip-name-resolve\' $mysql_conf
fi
'''
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
    community_iso = "/opt/ZStack-Community-x86_64-DVD-1.4.0.iso"
    bridge = ""
    SpinnerInfo.spinner_status = {'upgrade_repo':False,'stop_mevoco':False, 'upgrade_mevoco':False,'upgrade_db':False,
                      'backup_db':False, 'upgrade_cassandra_db':False, 'check_init':False, 'start_mevoco':False}
    ha_config_content = None

    def __init__(self):
        super(UpgradeHACmd, self).__init__()
        self.name = "upgrade_ha"
        self.description =  "upgrade high availability environment for Mevoco."
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
        parser.add_argument('--mevoco-installer','--mevoco',
                            help="The new mevoco installer package, get it from http://www.mevoco.com/download/",
                            required=True)
        parser.add_argument('--iso',
                            help="get it from http://www.mevoco.com/mevoco-offline-install-from-custom-iso/",
                            required=True)

    def reset_dict_value(self, dict_name, value):
        return dict.fromkeys(dict_name, value)

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
        command = "rsync -au --delete %s /opt/zstack-dvd/" %  tmp_iso
        run_remote_command(command, host_post_info)
        command = "umount %s" % tmp_iso
        run_remote_command(command, host_post_info)
        command = "rm -rf %s" % tmp_iso
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
        cmd = create_check_mgmt_node_command(timeout=10, mn_node=host_post_info.host)
        cmd(False)
        if cmd.return_code != 0:
            error("Check management node %s status failed, make sure the status is running before upgrade" % host_post_info.host)
        else:
            if 'false' in cmd.stdout:
                error('The management node %s is starting, please wait a few seconds to upgrade' % host_post_info.host)
            elif  'true' in cmd.stdout:
                return 0
            else:
                error('The management node %s status is: Unknown, please start the management node before upgrade' % host_post_info.host)


    def stop_mevoco(self, host_post_info):
        command = "zstack-ctl stop_node && zstack-ctl stop_ui"
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                   (UpgradeHACmd.private_key_name, host_post_info.host, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))

    def upgrade_mevoco(self, mevoco_installer, host_post_info):
        mevoco_dir = os.path.dirname(mevoco_installer)
        mevoco_bin = os.path.basename(mevoco_installer)
        command = "rm -rf /tmp/zstack_upgrade.lock && cd %s && bash %s -u -i " % (mevoco_dir, mevoco_bin)
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                   (UpgradeHACmd.private_key_name, host_post_info.host, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))

    def start_mevoco(self, host_post_info):
        command = "zstack-ctl start_node && zstack-ctl start_ui"
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                   (UpgradeHACmd.private_key_name, host_post_info.host, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (host_post_info.host, output))
        logger.debug("[ HOST: %s ] SUCC: shell command: '%s' successfully" % (host_post_info.host, command))


    def run(self, args):
        # create log
        create_log(UpgradeHACmd.logger_dir)
        spinner_info = SpinnerInfo()
        spinner_info.output = "Checking system and init environment"
        spinner_info.name = 'check_init'
        SpinnerInfo.spinner_status['check_init'] = True
        ZstackSpinner(spinner_info)
        host_inventory = UpgradeHACmd.conf_dir + 'host'
        yum_repo = get_yum_repo_from_property()
        private_key_name = UpgradeHACmd.conf_dir+ "ha_key"

        if args.iso is None:
            community_iso = UpgradeHACmd.community_iso
        else:
            community_iso = args.iso

        # check input host info
        host1_info = args.host1_info
        host1_connect_info_list = check_host_info_format(host1_info)
        host1_ip = host1_connect_info_list[2]
        host1_password = host1_connect_info_list[1]
        host1_user = host1_connect_info_list[0]

        host2_info = args.host2_info
        host2_connect_info_list = check_host_info_format(host2_info)
        host2_ip = host2_connect_info_list[2]
        host2_password = host2_connect_info_list[1]
        host2_user = host2_connect_info_list[0]

        if args.host3_info is not False:
            host3_info = args.host3_info
            host3_connect_info_list = check_host_info_format(host3_info)
            host3_ip = host3_connect_info_list[2]
            host3_password = host3_connect_info_list[1]
            host3_user = host3_connect_info_list[0]

        # init host1 parameter
        self.host1_post_info = HostPostInfo()
        self.host1_post_info.host = host1_ip
        self.host1_post_info.host_inventory = host_inventory
        self.host1_post_info.private_key = private_key_name
        self.host1_post_info.remote_pass = host1_password
        self.host1_post_info.yum_repo = yum_repo
        self.host1_post_info.post_url = ""

        # init host2 parameter
        self.host2_post_info = HostPostInfo()
        self.host2_post_info.host = host2_ip
        self.host2_post_info.host_inventory = host_inventory
        self.host2_post_info.private_key = private_key_name
        self.host2_post_info.remote_pass = host2_password
        self.host2_post_info.yum_repo = yum_repo
        self.host2_post_info.post_url = ""

        if args.host3_info is not False:
            # init host3 parameter
            self.host3_post_info = HostPostInfo()
            self.host3_post_info.host = host3_ip
            self.host3_post_info.host_inventory = host_inventory
            self.host3_post_info.private_key = private_key_name
            self.host3_post_info.remote_pass = host3_password
            self.host3_post_info.yum_repo = yum_repo
            self.host3_post_info.post_url = ""

        UpgradeHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info]
        if args.host3_info is not False:
            UpgradeHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info, self.host3_post_info]

        for host in UpgradeHACmd.host_post_info_list:
            # to do check mn all running
            self.check_mn_running(host)

        for file in [args.mevoco_installer, args.iso]:
            self.check_file_exist(file, UpgradeHACmd.host_post_info_list)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to upgrade repo"
        spinner_info.name = "upgrade_repo"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['upgrade_repo'] = True
        ZstackSpinner(spinner_info)
        rand_int = random.randint(65535, 100000)
        tmp_iso =  "/tmp/%d/iso/" % rand_int
        for host_post_info in UpgradeHACmd.host_post_info_list:
            self.upgrade_repo(args.iso, tmp_iso, host_post_info)

        spinner_info = SpinnerInfo()
        spinner_info.output = "Stopping mevoco"
        spinner_info.name = "stop_mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['stop_mevoco'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in UpgradeHACmd.host_post_info_list:
            self.stop_mevoco(host_post_info)

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
        (status, output) =  commands.getstatusoutput("zstack-ctl deploy_cassandra_db")
        if status != 0:
            error("Upgrade Cassandra failed: %s" % output)
        else:
            logger.debug("SUCC: shell command: 'zstack-ctl deploy_cassandra_db' successfully")

        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting mevoco"
        spinner_info.name = "start_mevoco"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['start_mevoco'] = True
        ZstackSpinner(spinner_info)
        for host_post_info in UpgradeHACmd.host_post_info_list:
            self.start_mevoco(host_post_info)

        SpinnerInfo.spinner_status['start_mevoco'] = False
        time.sleep(.2)

        info("Upgrade HA successfully!")


class AddManagementNodeCmd(Command):
    SpinnerInfo.spinner_status = {'check_init':False,'add_key':False,'deploy':False,'config':False,'start':False,'install_ui':False}
    def __init__(self):
        super(AddManagementNodeCmd, self).__init__()
        self.name = "add_multi_management"
        self.description =  "add multi management node."
        ctl.register_command(self)
    def install_argparse_arguments(self, parser):
        parser.add_argument('--host-list','--hosts',nargs='+',
                            help="All hosts connect info follow below format: 'root:passwd1@host1_ip root:passwd2@host2_ip ...' ",
                            required=True)
        parser.add_argument('--ssh-key',
                            help="the path of private key for SSH login $host; if provided, Ansible will use the "
                                 "specified key as private key to SSH login the $host",
                            default=None)

    def add_public_key_to_host(self, key_path, host_info):
        command ='timeout 10 sshpass -p %s ssh-copy-id -o UserKnownHostsFile=/dev/null -o  PubkeyAuthentication=no' \
                 ' -o StrictHostKeyChecking=no -i %s root@%s' % (host_info.remote_pass, key_path, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("Copy public key '%s' to host: '%s' failed:\n %s" % (key_path, host_info.host,  output))

    def deploy_mn_on_host(self, host_info, key):
        command = 'zstack-ctl install_management_node --host=%s --ssh-key="%s"' % (host_info.host, key)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("deploy mn on host %s failed:\n %s" % (host_info.host, output))

    def install_ui_on_host(self, key, host_info):
        command = 'zstack-ctl install_ui --host=%s --ssh-key=%s' % (host_info.host, key)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("deploy ui on host %s failed:\n %s" % (host_info.host, output))

    def config_mn_on_host(self, key, host_info):
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
                  "start_node && zstack-ctl start_ui" % (key, host_info.host)
        (status, output) = commands.getstatusoutput(command)
        if status != 0:
            error("start node on host %s failed:\n %s" % (host_info.host, output))


    def run(self, args):
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
            host_info = HostPostInfo()
            (host_info.remote_user, host_info.remote_pass, host_info.host, host_info.remote_port) = check_host_info_format(host)
            check_host_password(host_info.remote_pass, host_info.host)
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
            self.deploy_mn_on_host(host_info, private_key)

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

        info(colored("\nAll management nodes add successfully",'yellow'))


class InstallHACmd(Command):
    '''This feature only support zstack offline image currently'''
    host_post_info_list = []
    current_dir = os.path.dirname(os.path.realpath(__file__))
    conf_dir = "/var/lib/zstack/ha/"
    conf_file = conf_dir + "ha.yaml"
    logger_dir = "/var/log/zstack/"
    bridge = ""
    SpinnerInfo.spinner_status = {'mysql':False,'rabbitmq':False, 'haproxy_keepalived':False,'Cassandra':False,
                      'Mevoco':False, 'check_init':False, 'recovery_cluster':False}
    ha_config_content = None
    def __init__(self):
        super(InstallHACmd, self).__init__()
        self.name = "install_ha"
        self.description =  "install high availability environment for Mevoco."
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
                            help="RabbitMQ password; if set, the password will be created on RabbitMQ for username "
                                 "specified by --rabbit-username. [DEFAULT] rabbitmq default password",
                            default="zstack123")
        parser.add_argument('--drop', action='store_true', default=False,
                            help="Force delete mysql data for re-deploy HA")
        parser.add_argument('--drop-cassandra', action='store_true', default=False,
                            help="Force drop cassandra keyspace for re-deploy HA")
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

    def get_ip_by_interface(self, device_name):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x8915,
                struct.pack('256s', device_name[:15])
            )[20:24])

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


        # check user start this command on host1
        if args.recovery_from_this_host is False:
            local_ip = self.get_ip_by_interface(InstallHACmd.bridge)
            if args.host1 != local_ip:
                error("Please run this command at host1 %s, or change your host1 ip to local host ip" % args.host1)

        # check user input wrong host2 ip
        if args.host2 == args.host1:
            error("The host1 and host2 should not be the same ip address!")
        elif args.host3_info is not False:
            if args.host2 == args.host3 or args.host1 == args.host3:
                error("The host1, host2 and host3 should not be the same ip address!")

        # create log
        create_log(InstallHACmd.logger_dir)
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
                                  "PubkeyAuthentication=no -o StrictHostKeyChecking=no  root@%s '%s'" % \
                                  (args.host1_password, args.host1, add_public_key_command)
        (status, output) = commands.getstatusoutput(ssh_add_public_key_command)
        if status != 0:
            error(output)

        # add ha public key to host2
        ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                  "PubkeyAuthentication=no -o StrictHostKeyChecking=no  root@%s '%s' " % \
                                  (args.host2_password, args.host2, add_public_key_command)
        (status, output) = commands.getstatusoutput(ssh_add_public_key_command)
        if status != 0:
            error(output)

        # add ha public key to host3
        if args.host3_info is not False:
            ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                              "PubkeyAuthentication=no -o StrictHostKeyChecking=no  root@%s '%s' " % \
                                              (args.host3_password, args.host3, add_public_key_command)
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

            local_ip = self.get_ip_by_interface(InstallHACmd.bridge)
            if local_ip != args.host1 and local_ip != args.host2:
                if args.host3_info is not False:
                    if local_ip != args.host3:
                        error("Make sure you are running the command on host1 or host2 or host3")
                else:
                    error("Make sure you are running the command on host1 or host2")
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
                    service_status("rabbitmq-server","state=started", self.host1_post_info)
                    #run_remote_command(command, self.host2_post_info)
                    service_status("mysql","state=started", self.host2_post_info)
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    service_status("rabbitmq-server","state=started", self.host2_post_info)
                    if args.host3_info is not False:
                        #run_remote_command(command, self.host3_post_info)
                        service_status("mysql","state=started", self.host3_post_info)
                        service_status("haproxy","state=started", self.host3_post_info)
                        service_status("keepalived","state=started", self.host3_post_info)
                        service_status("rabbitmq-server","state=started", self.host3_post_info)
                    #command = "service mysql restart"
                    #run_remote_command(command, self.host1_post_info)
                    service_status("mysql","state=restarted", self.host1_post_info)

                elif local_ip == self.host2_post_info.host:
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    service_status("rabbitmq-server","state=started", self.host2_post_info)
                    #run_remote_command(command, self.host1_post_info)
                    service_status("mysql","state=started", self.host1_post_info)
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    service_status("rabbitmq-server","state=started", self.host1_post_info)
                    if args.host3_info is not False:
                        #run_remote_command(command, self.host3_post_info)
                        service_status("mysql","state=started", self.host3_post_info)
                        service_status("haproxy","state=started", self.host3_post_info)
                        service_status("keepalived","state=started", self.host3_post_info)
                        service_status("rabbitmq-server","state=started", self.host3_post_info)
                    #command = "service mysql restart"
                    #run_remote_command(command, self.host2_post_info)
                    service_status("mysql","state=restarted", self.host2_post_info)
                else:
                    # localhost must be host3
                    service_status("haproxy","state=started", self.host3_post_info)
                    service_status("keepalived","state=started", self.host3_post_info)
                    service_status("rabbitmq-server","state=started", self.host3_post_info)
                    #run_remote_command(command, self.host1_post_info)
                    service_status("mysql","state=started", self.host1_post_info)
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    service_status("rabbitmq-server","state=started", self.host1_post_info)
                    service_status("mysql","state=started", self.host2_post_info)
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    service_status("rabbitmq-server","state=started", self.host2_post_info)
                    #command = "service mysql restart"
                    #run_remote_command(command, self.host2_post_info)
                    service_status("mysql","state=restarted", self.host3_post_info)

                # start mevoco
                spinner_info.output = "Starting Mevoco"
                spinner_info.name = "mevoco"
                SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
                SpinnerInfo.spinner_status['mevoco'] = True
                ZstackSpinner(spinner_info)
                command = "zstack-ctl start"
                (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s"
                                                                     % (private_key_name, args.host1, command))
                if status != 0:
                    error("Something wrong on host: %s\n %s" % (args.host1, output))
                (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s"
                                                                     % (private_key_name, args.host2, command))
                if status != 0:
                    error("Something wrong on host: %s\n %s" % (args.host2, output))
                if args.host3_info is not False:
                    (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s"
                                                                         % (private_key_name, args.host3, command))
                    if status != 0:
                        error("Something wrong on host: %s\n %s" % (args.host2, output))
                SpinnerInfo.spinner_status['mevoco'] = False
                time.sleep(.2)
            info("The cluster has been recovery!")
            sys.exit(0)

        # generate ha config
        host_list = "%s,%s" % (self.host1_post_info.host, self.host2_post_info.host)
        if args.host3_info is not False:
            host_list = "%s,%s,%s" % (self.host1_post_info.host, self.host2_post_info.host, self.host3_post_info)
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

        command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                       " ; iptables-save > /dev/null 2>&1" % (self.host2_post_info.host, self.host2_post_info.host)
        run_remote_command(command, self.host1_post_info)
        if args.host3_info is not False:
            command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host3_post_info.host, self.host3_post_info.host)
            run_remote_command(command, self.host1_post_info)
        command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                       " ; iptables-save > /dev/null 2>&1" % (self.host1_post_info.host, self.host1_post_info.host)
        run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host3_post_info.host, self.host3_post_info.host)
            run_remote_command(command, self.host2_post_info)
        if args.host3_info is not False:
            command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host1_post_info.host, self.host1_post_info.host)
            run_remote_command(command, self.host3_post_info)
            command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host2_post_info.host, self.host2_post_info.host)
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

        # setup rabbitmq ha
        spinner_info = SpinnerInfo()
        spinner_info.output ="Starting to deploy Rabbitmq HA"
        spinner_info.name = 'rabbitmq'
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['rabbitmq'] = True
        ZstackSpinner(spinner_info)
        RabbitmqHA()()

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
        command = "zstack-ctl configure CloudBus.rabbitmqPassword=%s" % args.mysql_user_password
        run_remote_command(command, self.host1_post_info)

        # cassandra HA only need to change the config file, so unnecessary to wrap the process in a class
        spinner_info = SpinnerInfo()
        spinner_info.output = "Starting to deploy Cassandra HA"
        spinner_info.name = "Cassandra"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        SpinnerInfo.spinner_status['Cassandra'] = True
        ZstackSpinner(spinner_info)
        update_file("%s/apache-cassandra-2.2.3/conf/cassandra.yaml" % ctl.USER_ZSTACK_HOME_DIR,
                    "regexp='seeds:' line='  - seeds: \"%s,%s\"'" % (args.host1, args.host2), self.host1_post_info)
        update_file("%s/apache-cassandra-2.2.3/conf/cassandra.yaml" % ctl.USER_ZSTACK_HOME_DIR,
                    "regexp='seeds:' line='  - seeds: \"%s,%s\"'" % (args.host1, args.host2), self.host2_post_info)
        if args.host3_info is not False:
            update_file("%s/apache-cassandra-2.2.3/conf/cassandra.yaml" % ctl.USER_ZSTACK_HOME_DIR,
                        "regexp='seeds:' line='  - seeds: \"%s,%s,%s\"'" % (args.host1, args.host2, args.host3), self.host1_post_info)
            update_file("%s/apache-cassandra-2.2.3/conf/cassandra.yaml" % ctl.USER_ZSTACK_HOME_DIR,
                        "regexp='seeds:' line='  - seeds: \"%s,%s,%s\"'" % (args.host1, args.host2, args.host3), self.host2_post_info)
            update_file("%s/apache-cassandra-2.2.3/conf/cassandra.yaml" % ctl.USER_ZSTACK_HOME_DIR,
                        "regexp='seeds:' line='  - seeds: \"%s,%s,%s\"'" % (args.host1, args.host2, args.host3), self.host3_post_info)

        # set cron task to sync data
        cron("sync_kairosdb_data","minute='0' hour='3' job='%s/apache-cassandra-2.2.3/javadoc/org/"
                                  "apache/cassandra/tools/nodetool repair 2>&1'" % ctl.USER_ZSTACK_HOME_DIR, self.host1_post_info)

        # copy zstack-1 property to zstack-2 and update the management.server.ip
        # update zstack-1 firstly
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.serverIp\.0' line='CloudBus.serverIp.0=%s'" % args.vip, self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.serverIp\.1' state=absent" , self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.rabbitmqUsername' line='CloudBus.rabbitmqUsername=zstack'",
                    self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.rabbitmqPassword' line='CloudBus.rabbitmqPassword=%s'"
                    % args.rabbit_password, self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^CloudBus\.rabbitmqHeartbeatTimeout' line='CloudBus.rabbitmqHeartbeatTimeout=10'",
                    self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^Cassandra\.contactPoints' line='Cassandra.contactPoints=%s,%s'"
                    % (args.host1, args.host2), self.host1_post_info)
        if args.host3_info is not False:
            update_file("%s" % ctl.properties_file_path,
                        "regexp='^Cassandra\.contactPoints' line='Cassandra.contactPoints=%s,%s,%s'"
                        % (args.host1, args.host2, args.host3), self.host1_post_info)
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

        if args.drop_cassandra is True:
            command = "zstack-ctl cassandra --stop"
            run_remote_command(command, self.host1_post_info)
            run_remote_command(command, self.host2_post_info)
            if args.host3_info is not False:
                run_remote_command(command, self.host3_post_info)
            # backup old cassandra dir avoid changing keyspace error
            command = "[ -d /var/lib/cassandra/ ] && mv /var/lib/cassandra/ /var/lib/cassandra-%s/ || true " \
                      % datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            run_remote_command(command, self.host1_post_info)
            run_remote_command(command, self.host2_post_info)
            if args.host3_info is not False:
                run_remote_command(command, self.host3_post_info)
                #command = "/usr/local/zstack/apache-cassandra-2.2.3/bin/cqlsh %s 9042 -e 'drop keyspace zstack_billing;'" % self.host1_post_info.host
                #run_remote_command(command, self.host1_post_info)
                #command = "/usr/local/zstack/apache-cassandra-2.2.3/bin/cqlsh %s 9042 -e 'drop keyspace zstack_logging;'" % self.host1_post_info.host
                #run_remote_command(command, self.host1_post_info)

        # start Cassadra 
        command = 'zstack-ctl cassandra --start --wait-timeout 120'
        (status, output) = commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                             (private_key_name, args.host1, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (args.host1, output))
        (status, output) = commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                             (private_key_name, args.host2, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (args.host2, output))
        if args.host3_info is not False:
            (status, output) = commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                                 (private_key_name, args.host3, command))
            if status != 0:
                error("Something wrong on host: %s\n %s" % (args.host3, output))

        spinner_info.output = "Deploy Cassandra DB"
        spinner_info.name = "Cassandra.DB"
        SpinnerInfo.spinner_status = reset_dict_value(SpinnerInfo.spinner_status,False)
        ZstackSpinner(spinner_info)

        # deploy cassandra_db
        command = 'zstack-ctl deploy_cassandra_db'
        run_remote_command(command, self.host1_post_info)

        # change Cassadra duplication number
        #self.update_cassadra = "ALTER KEYSPACE kairosdb WITH REPLICATION = { 'class' : " \
        #                       "'SimpleStrategy','replication_factor' : 3 };CONSISTENCY ONE;"
        #command = "%s/../../../apache-cassandra-2.2.3/bin/cqlsh %s 9042 -e \"%s\"" % \
        #               (os.environ['ZSTACK_HOME'], args.host1, self.update_cassadra)
        #run_remote_command(command, self.host1_post_info)

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
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                             (private_key_name, args.host1, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (args.host1, output))
        (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
                                                             (private_key_name, args.host2, command))
        if status != 0:
            error("Something wrong on host: %s\n %s" % (args.host2, output))
        if args.host3_info is not False:
            (status, output)= commands.getstatusoutput("ssh -o StrictHostKeyChecking=no -i %s root@%s %s" %
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
Rabbitmq user 'zstack' password: %s
Mevoco is running, visit %s in Chrome or Firefox with default user/password : %s
You can check the cluster status at %s with user/passwd : %s
       ''' % (args.mysql_root_password, args.mysql_user_password, args.rabbit_password,
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

listen  proxy-rabbitmq 0.0.0.0:55672
    mode tcp
    balance source
    timeout client  3h
    timeout server  3h
    server zstack-1 {{ host1 }}:5672 weight 10 check inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:5672 backup weight 10 check inter 3s rise 2 fall 2
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

listen  proxy-rabbitmq 0.0.0.0:55672
    mode tcp
    balance source
    timeout client  3h
    timeout server  3h
    server zstack-1 {{ host1 }}:5672 weight 10 check inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:5672 backup weight 10 check inter 3s rise 2 fall 2
    server zstack-3 {{ host3 }}:5672 backup weight 10 check inter 3s rise 2 fall 2
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
        command = "! iptables -C INPUT -p tcp -m tcp --dport 53306 -j ACCEPT > /dev/null 2>&1 && iptables -I INPUT -p tcp -m tcp --dport 53306 -j ACCEPT; " \
                  "! iptables -C INPUT -p tcp -m tcp --dport 58080 -j ACCEPT > /dev/null 2>&1  &&  iptables -I INPUT -p tcp -m tcp --dport 58080 -j ACCEPT ; " \
                  "! iptables -C INPUT -p tcp -m tcp --dport 55672 -j ACCEPT > /dev/null 2>&1  &&  iptables -I INPUT -p tcp -m tcp --dport 55672 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 80 -j ACCEPT > /dev/null 2>&1  && iptables -I INPUT -p tcp -m tcp --dport 80 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 9132 -j ACCEPT > /dev/null 2>&1 &&  iptables -I INPUT -p tcp -m tcp --dport 9132 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 8888 -j ACCEPT > /dev/null 2>&1 &&  iptables -I INPUT -p tcp -m tcp --dport 8888 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 6033 -j ACCEPT > /dev/null 2>&1 && iptables -I INPUT -p tcp -m tcp --dport 6033 -j ACCEPT; iptables-save "
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
 weight 2
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
        master_priority = 100
        slave_priority = 90
        second_slave_priority = 80
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
            run_remote_command(command, self.host1_post_info)

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
        self.host_post_info_list = InstallHACmd.host_post_info_list
        self.host1_post_info = self.host_post_info_list[0]
        self.host2_post_info = self.host_post_info_list[1]
        if len(self.host_post_info_list) == 3:
            self.host3_post_info = self.host_post_info_list[2]
        self.yum_repo = self.host1_post_info.yum_repo
        self.rabbit_password= self.host1_post_info.rabbit_password
    def __call__(self):
        command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q rabbitmq-server"
               " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
               "--disablerepo=* --enablerepo=%s,mariadb install -y $pkg; done;") % self.yum_repo
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        # clear erlang process for new deploy
        command = "echo True || pkill -f .*erlang.*  > /dev/null 2>&1 && rm -rf /var/lib/rabbitmq/* "
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)

        # to stop rabbitmq-server for new installation
        service_status("rabbitmq-server","state=stopped", self.host1_post_info, True)
        service_status("rabbitmq-server", "state=stopped", self.host2_post_info, True)
        if len(self.host_post_info_list) == 3:
            service_status("rabbitmq-server", "state=stopped", self.host3_post_info, True)

        # to start rabbitmq-server
        service_status("rabbitmq-server","state=started enabled=yes", self.host1_post_info)
        service_status("rabbitmq-server", "state=started enabled=yes", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("rabbitmq-server", "state=started enabled=yes", self.host3_post_info)
        # add zstack user in this cluster
        command = "rabbitmqctl add_user zstack %s" %  self.rabbit_password
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        command = "rabbitmqctl set_user_tags zstack administrator"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        command = "rabbitmqctl change_password zstack %s" % self.rabbit_password
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        command = 'rabbitmqctl set_permissions -p \/ zstack ".*" ".*" ".*"'
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        command = "rabbitmq-plugins enable rabbitmq_management"
        run_remote_command(command, self.host1_post_info)
        run_remote_command(command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(command, self.host3_post_info)
        service_status("rabbitmq-server","state=restarted enabled=yes", self.host1_post_info)
        service_status("rabbitmq-server", "state=restarted enabled=yes", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("rabbitmq-server", "state=restarted enabled=yes", self.host3_post_info)

class ResetRabbitCmd(Command):
    def __init__(self):
        super(ResetRabbitCmd, self).__init__()
        self.name = "reset_rabbitmq"
        self.description = "Reinstall RabbitMQ message broker on local machine based on current configuration in zstack.properties."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        pass

    def run(self, args):
        rabbitmq_ip = ctl.read_property('CloudBus.serverIp.0')
        rabbitmq_user = ctl.read_property('CloudBus.rabbitmqUsername')
        rabbitmq_passwd = ctl.read_property('CloudBus.rabbitmqPassword')
        shell("service rabbitmq-server stop; rpm -ev rabbitmq-server; rm -rf /var/lib/rabbitmq")
        ctl.internal_run('install_rabbitmq', "--host=%s --rabbit-username=%s --rabbit-password=%s" % (rabbitmq_ip, rabbitmq_user, rabbitmq_passwd))


class InstallRabbitCmd(Command):
    def __init__(self):
        super(InstallRabbitCmd, self).__init__()
        self.name = "install_rabbitmq"
        self.description = "install RabbitMQ message broker on local or remote machine."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='host IP, for example, 192.168.0.212, please specify the real IP rather than "localhost" or "127.0.0.1" when installing on local machine; otherwise management nodes on other machines cannot access the RabbitMQ.', required=True)
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--no-update', help="don't update the IP address to 'CloudBus.serverIp.0' in zstack.properties", action="store_true", default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)
        parser.add_argument('--rabbit-username', help="RabbitMQ username; if set, the username will be created on RabbitMQ. [DEFAULT] rabbitmq default username", default=None)
        parser.add_argument('--rabbit-password', help="RabbitMQ password; if set, the password will be created on RabbitMQ for username specified by --rabbit-username. [DEFAULT] rabbitmq default password", default=None)
        parser.add_argument('--yum', help="Use ZStack predefined yum repositories. The valid options include: alibase,aliepel,163base,ustcepel,zstack-local. NOTE: only use it when you know exactly what it does.", default=None)

    def run(self, args):
        if (args.rabbit_password is None and args.rabbit_username) or (args.rabbit_username and args.rabbit_password is None):
            raise CtlError('--rabbit-username and --rabbit-password must be both set or not set')

        if not args.yum:
            args.yum = get_yum_repo_from_property()

        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      yum_repo: "$yum_repo"

  tasks:
    - name: pre-install script
      script: $pre_install_script

    - name: install RabbitMQ on RedHat OS from user defined yum repo
      when: ansible_os_family == 'RedHat' and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y rabbitmq-server libselinux-python iptables-services

    - name: install RabbitMQ on RedHat OS from online
      when: ansible_os_family == 'RedHat' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y rabbitmq-server libselinux-python iptables-services

    - name: install RabbitMQ on Ubuntu OS
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - rabbitmq-server

    - name: open 5672 port
      when: ansible_os_family != 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5672 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5672 -j ACCEPT

    - name: open 5673 port
      when: ansible_os_family != 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5673 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5673 -j ACCEPT

    - name: open 15672 port
      when: ansible_os_family != 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 15672 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 15672 -j ACCEPT

    - name: open 5672 port
      when: ansible_os_family == 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5672 -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 5672 -j ACCEPT && service iptables save)

    - name: open 5673 port
      when: ansible_os_family == 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5673 -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 5673 -j ACCEPT && service iptables save)

    - name: open 15672 port
      when: ansible_os_family == 'RedHat'
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 15672 -j ACCEPT" > /dev/null || (iptables -I INPUT -p tcp -m tcp --dport 15672 -j ACCEPT && service iptables save)

    - name: install rabbitmq management plugin
      shell: rabbitmq-plugins enable rabbitmq_management

    - name: enable RabbitMQ
      service: name=rabbitmq-server state=restarted enabled=yes

    - name: post-install script
      script: $post_install_script
'''

        pre_script = '''
if [ -f /etc/redhat-release ] ; then

grep ' 7' /etc/redhat-release
if [ $? -eq 0 ]; then
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=\$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
else
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=\$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
fi

[ -d /etc/yum.repos.d/ ] && echo -e "#aliyun base\n[alibase]\nname=CentOS-\$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

[ -d /etc/yum.repos.d/ ] && echo -e "#163 base\n[163base]\nname=CentOS-\$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo
fi

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
DNS hijacking will cause MySQL and RabbitMQ not working."
exit 1
'''
        fd, pre_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(pre_script)

        def cleanup_prescript():
            os.remove(pre_script_path)

        self.install_cleanup_routine(cleanup_prescript)

        if args.rabbit_username and args.rabbit_password:
            post_script = '''set -x
rabbitmqctl list_users|grep 'zstack'
if [ $$? -ne 0 ]; then
    set -e
    rabbitmqctl add_user $username $password
    rabbitmqctl set_user_tags $username administrator
    rabbitmqctl set_permissions -p / $username ".*" ".*" ".*"
fi
'''
            t = string.Template(post_script)
            post_script = t.substitute({
                'username': args.rabbit_username,
                'password': args.rabbit_password
            })
        else:
            post_script = ''

        fd, post_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(post_script)

        def cleanup_postscript():
            os.remove(post_script_path)

        self.install_cleanup_routine(cleanup_postscript)

        t = string.Template(yaml)
        if args.yum:
            yum_repo = args.yum
        else:
            yum_repo = 'false'
        yaml = t.substitute({
            'host': args.host,
            'pre_install_script': pre_script_path,
            'yum_folder': ctl.zstack_home,
            'yum_repo': yum_repo,
            'post_install_script': post_script_path
        })

        ansible(yaml, args.host, args.debug, args.ssh_key)

        if not args.no_update:
            ctl.write_property('CloudBus.serverIp.0', args.host)
            info('updated CloudBus.serverIp.0=%s in %s' % (args.host, ctl.properties_file_path))

        if args.rabbit_username and args.rabbit_password:
            ctl.write_property('CloudBus.rabbitmqUsername', args.rabbit_username)
            info('updated CloudBus.rabbitmqUsername=%s in %s' % (args.rabbit_username, ctl.properties_file_path))
            ctl.write_property('CloudBus.rabbitmqPassword', args.rabbit_password)
            info('updated CloudBus.rabbitmqPassword=%s in %s' % (args.rabbit_password, ctl.properties_file_path))

class DumpMysqlCmd(Command):
    def __init__(self):
        super(DumpMysqlCmd, self).__init__()
        self.name = "dump_mysql"
        self.description = (
            "Dump mysql database for backup"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--file-name',
                            help="The filename you want to save the database, default is 'zstack-backup-db'",
                            default="zstack-backup-db")
        parser.add_argument('--keep-amount',type=int,
                            help="The amount of backup files you want to keep, older backup files will be deleted, default number is 60",
                            default=60)

    def run(self, args):
        (db_hostname, db_port, db_user, db_password) = ctl.get_live_mysql_portal()
        file_name = args.file_name
        keep_amount = args.keep_amount
        backup_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        db_backup_dir = "/var/lib/zstack/mysql-backup/"
        if os.path.exists(db_backup_dir) is False:
            os.mkdir(db_backup_dir)
        db_backup_name = db_backup_dir + file_name + "-" + backup_timestamp
        if db_hostname == "localhost" or db_hostname == "127.0.0.1":
            if db_password is None or db_password == "":
                db_connect_password = ""
            else:
                db_connect_password = "-p" + db_password
            command = "mysqldump --add-drop-database  --databases -u %s %s -P %s zstack zstack_rest | gzip > %s "\
                           % (db_user, db_connect_password, db_port, db_backup_name + ".gz")
            (status, output) = commands.getstatusoutput(command)
            if status != 0:
                error(output)
        else:
            if db_password is None or db_password == "":
                db_connect_password = ""
            else:
                db_connect_password = "-p" + db_password
            command = "mysqldump --add-drop-database  --databases -u %s %s --host %s -P %s zstack zstack_rest | gzip > %s " \
                           % (db_user, db_connect_password, db_hostname, db_port, db_backup_name + ".gz")
            (status, output) = commands.getstatusoutput(command)
            if status != 0:
                error(output)
        print "Backup mysql successful! You can check the file at %s.gz" % db_backup_name
        # remove old file
        if len(os.listdir(db_backup_dir)) > keep_amount:
            backup_files_list = [s for s in os.listdir(db_backup_dir) if os.path.isfile(os.path.join(db_backup_dir, s))]
            backup_files_list.sort(key=lambda s: os.path.getmtime(os.path.join(db_backup_dir, s)))
            for expired_file in backup_files_list:
                if expired_file not in backup_files_list[-keep_amount:]:
                    os.remove(db_backup_dir + expired_file)


class RestoreMysqlCmd(Command):
    def __init__(self):
        super(RestoreMysqlCmd, self).__init__()
        self.name = "restore_mysql"
        self.description = (
            "Restore mysql data from backup file"
        )
        self.hide = True
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--from-file', '-f',
                            help="The backup filename under /var/lib/zstack/mysql-backup/ ",
                            required=True)
        parser.add_argument('--mysql-root-password',
                            help="mysql root password",
                            default=None)

    def run(self, args):
        (db_hostname, db_port, db_user, db_password) = ctl.get_live_mysql_portal()
        # only root user can restore database
        db_password = args.mysql_root_password
        db_backup_name = args.from_file
        if os.path.exists(db_backup_name) is False:
            error("Didn't find file: %s ! Stop recover database! " % db_backup_name)
        error_if_tool_is_missing('gunzip')
        info("Backup mysql before restore data ...")
        shell_no_pipe('zstack-ctl dump_mysql')
        shell_no_pipe('zstack-ctl stop_node')
        info("Starting recover data ...")
        if db_hostname == "localhost" or db_hostname == "127.0.0.1":
            if db_password is None or db_password == "":
                db_connect_password = ""
            else:
                db_connect_password = "-p" + db_password
            for database in ['zstack','zstack_rest']:
                command = "gunzip < %s | mysql -uroot %s -P %s %s" \
                          % (db_backup_name, db_connect_password, db_port, database)
                shell_no_pipe(command)
        else:
            if db_password is None or db_password == "":
                db_connect_password = ""
            else:
                db_connect_password = "-p" + db_password
            for database in ['zstack','zstack_rest']:
                command = "gunzip < %s | mysql -uroot %s --host %s -P %s %s" \
                      % (db_backup_name, db_connect_password, db_hostname, db_port, database)
                shell_no_pipe(command)
        #shell_no_pipe('zstack-ctl start_node')
        info("Recover data successfully! You can start node by: zstack-ctl start")


class CollectLogCmd(Command):
    zstack_log_dir = "/var/log/zstack"
    host_log_list = ['zstack-sftpbackupstorage.log','zstack.log','zstack-kvmagent.log','ceph-backupstorage.log',
                     'ceph-primarystorage.log', 'zstack-iscsi-filesystem-agent.log', 'zstack-store/zstack-store.log',
                     'zstack-agent/collectd.log','zstack-agent/server.log']
    # management-server.log is not in the same dir, will collect separately
    mn_log_list = ['deploy.log', 'ha.log', 'zstack-console-proxy.log', 'zstack.log', 'zstack-cli', 'zstack-ui.log',
                   'zstack-dashboard.log']
    collect_lines = 100000

    def __init__(self):
        super(CollectLogCmd, self).__init__()
        self.name = "collect_log"
        self.description = (
            "Collect log for diagnose"
        )
        ctl.register_command(self)

    #def install_argparse_arguments(self, parser):
        #parser.add_argument('--simple-log', help='collect simple log on all hosts and management node ', default=False)
        #parser.add_argument('--host', help='collect full log on this host and management node ', default=False)

    def get_host_list(self):
        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        query = MySqlCommandLineQuery()
        query.host = db_hostname
        query.port = db_port
        query.user = db_user
        query.password = db_password
        query.table = 'zstack'
        query.sql = "select * from HostVO"
        host_vo = query.query()
        return host_vo

    def compress_and_fetch_log(self, local_collect_dir, tmp_log_dir, host_post_info):
        command = "cd %s && tar zcf collect-log.tar.gz *" % tmp_log_dir
        run_remote_command(command, host_post_info)
        fetch_arg = FetchArg()
        fetch_arg.src =  "%s/collect-log.tar.gz " % tmp_log_dir
        fetch_arg.dest = local_collect_dir
        fetch_arg.args = "fail_on_missing=yes flat=yes"
        fetch(fetch_arg, host_post_info)
        command = "rm -rf %s " % tmp_log_dir
        run_remote_command(command, host_post_info)
        (status, output) = commands.getstatusoutput("cd %s && tar zxf collect-log.tar.gz" % local_collect_dir)
        if status != 0:
            warn("Uncompress %s/collect-log.tar.gz meet problem: %s" % (local_collect_dir, output))
        else:
            (status, output) = commands.getstatusoutput("rm -f %s/collect-log.tar.gz" % local_collect_dir)

    def get_host_log(self, host_post_info, collect_dir):
        if check_host_reachable(host_post_info) is True:
            info("Collecting log from host: %s ..." % host_post_info.host)
            tmp_log_dir = "%s/tmp-log/" % CollectLogCmd.zstack_log_dir
            local_collect_dir = collect_dir + host_post_info.host + '/'
            command = "mkdir -p %s " % tmp_log_dir
            run_remote_command(command, host_post_info)
            for log in CollectLogCmd.host_log_list:
                if 'zstack-agent' in log:
                    command = "mkdir -p %s" % tmp_log_dir + '/zstack-agent/'
                    run_remote_command(command, host_post_info)
                host_log = CollectLogCmd.zstack_log_dir + '/' + log
                collect_log = tmp_log_dir + '/' + log
                if file_dir_exist("path=%s" % host_log, host_post_info):
                    command = "tail -n %d %s > %s 2>&1" % (CollectLogCmd.collect_lines, host_log, collect_log)
                    run_remote_command(command, host_post_info)
            command = 'test "$(ls -A "%s" 2>/dev/null)" || echo The directory is empty' % tmp_log_dir
            (status, output) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
            if "The directory is empty" in output:
                warn("The dir %s is empty on host: %s " % (tmp_log_dir, host_post_info.host))
                return 0
            #collect uptime and last reboot log and dmesg
            host_info_log = tmp_log_dir + "host_info"
            print host_info_log
            command = "uptime > %s && last reboot >> %s" % (host_info_log, host_info_log)
            run_remote_command(command, host_post_info)
            command = "cp /var/log/dmesg* %s" % tmp_log_dir
            run_remote_command(command, host_post_info)
            self.compress_and_fetch_log(local_collect_dir, tmp_log_dir, host_post_info)

        else:
            warn("Host %s is unreachable!" % host_post_info.host)

    def get_host_ssh_info(self, host_ip):
        db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
        query = MySqlCommandLineQuery()
        query.host = db_hostname
        query.port = db_port
        query.user = db_user
        query.password = db_password
        query.table = 'zstack'
        query.sql = "select * from HostVO where managementIp='%s'" % host_ip
        host_uuid = query.query()[0]['uuid']
        query.sql = "select * from KVMHostVO where uuid='%s'" % host_uuid
        ssh_info = query.query()[0]
        username = ssh_info['username']
        password = ssh_info['password']
        ssh_port = ssh_info['port']
        return (username, password, ssh_port)

    def get_mn_list(self):
        with open(InstallHACmd.conf_file, 'r') as fd:
            ha_conf_content = yaml.load(fd.read())
            mn_list = ha_conf_content['host_list'].split(',')
        return mn_list

    def get_management_node_log(self, collect_dir, host_post_info):
        if check_host_reachable(host_post_info) is True:
            mn_ip = host_post_info.host
            info("Collecting log from management node %s ..." % mn_ip)
            local_collect_dir = collect_dir + "/mn-%s/" % mn_ip + '/'
            if not os.path.exists(local_collect_dir):
                os.makedirs(local_collect_dir)

            tmp_log_dir = "%s/../../logs/tmp-log/" % ctl.zstack_home
            command = 'mkdir -p %s' % tmp_log_dir
            run_remote_command(command, host_post_info)

            command = "tail -n %d %s/../../logs/management-server.log > %s/management-server.log 2>&1 " % \
                      (CollectLogCmd.collect_lines, ctl.zstack_home, tmp_log_dir)
            run_remote_command(command, host_post_info)
            for log in CollectLogCmd.mn_log_list:
                if file_dir_exist("path=%s/%s" % (CollectLogCmd.zstack_log_dir, log), host_post_info):
                    command = "tail -n %d %s/%s > %s/%s 2>&1 " \
                              % (CollectLogCmd.collect_lines, CollectLogCmd.zstack_log_dir, log, tmp_log_dir, log)
                    run_remote_command(command, host_post_info)

            self.compress_and_fetch_log(local_collect_dir, tmp_log_dir, host_post_info)
        else:
            warn("Management %s is unreachable!" % host_post_info.host)

    def get_local_mn_log(self, collect_dir):
        info("Collecting log from this management node ...")
        if not os.path.exists(collect_dir + "/management-node"):
            os.makedirs(collect_dir + "/management-node")
        (status, output) = commands.getstatusoutput("tail -n 10000 %s/../../logs/management-server.log > "
                                                    "%s/management-node/management-server.log 2>&1 "
                                                    % (ctl.zstack_home, collect_dir))
        if status != 0:
            error("get management-server.log failed: %s" % output)
        for log in CollectLogCmd.mn_log_list:
            (status, output) = commands.getstatusoutput("tail -n 10000 %s/%s > %s/management-node/%s 2>&1 "
                                                        % (CollectLogCmd.zstack_log_dir, log, collect_dir, log))

    def generate_tar_ball(self, run_command_dir, detail_version, time_stamp):
        (status, output) = commands.getstatusoutput("cd %s && tar zcf collect-log-%s-%s.tar.gz collect-log-%s-%s"
                                                    % (run_command_dir, detail_version, time_stamp, detail_version, time_stamp))
        if status != 0:
            error("Generate tarball failed: %s " % output)

    def run(self, args):
        run_command_dir = os.getcwd()
        time_stamp =  datetime.now().strftime("%Y-%m-%d_%H-%M")
        if get_detail_version() is not None:
            detail_version = get_detail_version().replace(' ','_')
        else:
            hostname, port, user, password = ctl.get_live_mysql_portal()
            detail_version = get_zstack_version(hostname, port, user, password)
        # collect_dir used to store the collect-log
        collect_dir = run_command_dir + "/" + 'collect-log-' + detail_version + '-' + time_stamp + '/'
        if not os.path.exists(collect_dir):
            os.makedirs(collect_dir)
        if os.path.exists(InstallHACmd.conf_file) is not True:
            self.get_local_mn_log(collect_dir)
        else:
            # this only for HA due to db will lost mn info if mn offline
            mn_list = self.get_mn_list()
            for mn_ip in mn_list:
                host_post_info = HostPostInfo()
                host_post_info.remote_user = 'root'
                # this will be changed in the future
                host_post_info.remote_port = '22'
                host_post_info.host = mn_ip
                host_post_info.host_inventory = InstallHACmd.conf_dir + 'host'
                host_post_info.post_url = ""
                host_post_info.private_key = InstallHACmd.conf_dir + 'ha_key'
                self.get_management_node_log(collect_dir, host_post_info)


        host_vo = self.get_host_list()
        for host in host_vo:
            host_post_info = HostPostInfo()
            host_ip = host['managementIp']
            #update inventory
            with open(ctl.zstack_home + "/../../../ansible/hosts") as f:
                old_hosts = f.read()
                if host_ip not in old_hosts:
                    with open(ctl.zstack_home + "/../../../ansible/hosts","w") as f:
                        new_hosts = host_ip + "\n" + old_hosts
                        f.write(new_hosts)
            (host_user, host_password, host_port) = self.get_host_ssh_info(host_ip)
            if host_user != 'root' and host_password is not None:
                host_post_info.become = True
                host_post_info.remote_user = host_user
                host_post_info.remote_pass = host_password
            host_post_info.remote_port = host_port
            host_post_info.host = host_ip
            host_post_info.host_inventory = ctl.zstack_home + "/../../../ansible/hosts"
            host_post_info.private_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa"
            host_post_info.post_url = ""
            self.get_host_log(host_post_info, collect_dir)

        self.generate_tar_ball(run_command_dir, detail_version, time_stamp)
        info("The collect log generate at: %s/collect-log-%s-%s.tar.gz" % (run_command_dir, detail_version, time_stamp))


class ChangeIpCmd(Command):
    def __init__(self):
        super(ChangeIpCmd, self).__init__()
        self.name = "change_ip"
        self.description = (
            "update new management ip address to zstack property file and cassandra config file"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--ip', help='The new IP address of management node.'
                                         'This operation will update the new ip address to '
                                         'zstack and cassandra config file' , required=True)
        parser.add_argument('--cassandra_rpc_address', help='The new IP address of cassandra_rpc_address, default will use value from --ip', required=False)
        parser.add_argument('--cassandra_listen_address', help='The new IP address of cassandra_listen_address, default will use value from --ip', required=False)
        parser.add_argument('--cloudbus_server_ip', help='The new IP address of CloudBus.serverIp.0, default will use value from --ip', required=False)
        parser.add_argument('--mysql_ip', help='The new IP address of DB.url, default will use value from --ip', required=False)

    def run(self, args):
        if args.ip == '0.0.0.0':
            raise CtlError('for your data safety, please do NOT use 0.0.0.0 as the listen address')
        if args.cassandra_rpc_address is not None:
            cassandra_rpc_address = args.cassandra_rpc_address
        else:
            cassandra_rpc_address = args.ip
        if args.cassandra_listen_address is not None:
            cassandra_listen_address = args.cassandra_listen_address
        else:
            cassandra_listen_address = args.ip
        if args.cloudbus_server_ip is not None:
            cloudbus_server_ip = args.cloudbus_server_ip
        else:
            cloudbus_server_ip = args.ip
        if args.mysql_ip is not None:
            mysql_ip = args.mysql_ip
        else:
            mysql_ip = args.ip

        zstack_conf_file = ctl.properties_file_path
        ip_check = re.compile('^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
        for input_ip in [cassandra_rpc_address, cassandra_listen_address, cloudbus_server_ip, mysql_ip]:
            if not ip_check.match(input_ip):
                info("The ip address you input: %s seems not a valid ip" % input_ip)
                return 1

        # Update /etc/hosts
        if os.path.isfile(zstack_conf_file):
            old_ip = ctl.read_property('management.server.ip')
            if old_ip != None:
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
            db_url = ctl.read_property('DB.url')
            db_old_ip = re.findall(r'[0-9]+(?:\.[0-9]{1,3}){3}', db_url)
            db_new_url = db_url.split(db_old_ip[0])[0] + mysql_ip + db_url.split(db_old_ip[0])[1]
            ctl.write_properties([
              ('DB.url', db_new_url),
            ])
            info("Update mysql new url %s in %s " % (db_new_url, zstack_conf_file))
        else:
            info("Didn't find %s, skip update new ip" % zstack_conf_file  )
            return 1

        # Update cassandra config file
        cassandra_conf_file = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "apache-cassandra-2.2.3/conf/cassandra.yaml")
        if os.path.isfile(cassandra_conf_file):
            shell('yes | cp %s %s.bak' % (cassandra_conf_file, cassandra_conf_file))
            with open(cassandra_conf_file, 'r') as fd:
                c_conf = yaml.load(fd.read())
                c_conf['listen_address'] = cassandra_listen_address
                c_conf['rpc_address'] = cassandra_rpc_address
                with open(cassandra_conf_file, 'w') as fd:
                    fd.write(yaml.dump(c_conf, default_flow_style=False))
                    info('Update cassandra listen address: %s rpc_address: %s in %s' \
                         % (cassandra_listen_address, cassandra_rpc_address, cassandra_conf_file))
                    ctl.write_properties([
                        ('Cassandra.contactPoints', cassandra_rpc_address)
                    ])
                    info("Update cassandra rpc address: %s in %s" % (cassandra_rpc_address, zstack_conf_file))
        else:
            info("Didn't find %s, skip update cassandra ip" % cassandra_conf_file)

        # Reset RabbitMQ
        shell("zstack-ctl reset_rabbitmq")
        info("Reset RabbitMQ")

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
        parser.add_argument('--host', help='target host IP, for example, 192.168.0.212, to install ZStack management node to a remote machine', required=True)
        parser.add_argument('--install-path', help='the path on remote machine where Apache Tomcat will be installed, which must be an absolute path; [DEFAULT]: /usr/local/zstack', default='/usr/local/zstack')
        parser.add_argument('--source-dir', help='the source folder containing Apache Tomcat package and zstack.war, if omitted, it will default to a path related to $ZSTACK_HOME')
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--force-reinstall', help="delete existing Apache Tomcat and resinstall ZStack", action="store_true", default=False)
        parser.add_argument('--yum', help="Use ZStack predefined yum repositories. The valid options include: alibase,aliepel,163base,ustcepel,zstack-local. NOTE: only use it when you know exactly what it does.", default=None)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def run(self, args):
        if not os.path.isabs(args.install_path):
            raise CtlError('%s is not an absolute path' % args.install_path)

        if not args.source_dir:
            args.source_dir = os.path.join(ctl.zstack_home, "../../../")

        if not os.path.isdir(args.source_dir):
            raise CtlError('%s is not an directory' % args.source_dir)

        if not args.yum:
            args.yum = get_yum_repo_from_property()

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

    - name: install dependencies on RedHat OS from user defined repo
      when: ansible_os_family == 'RedHat' and yum_repo != 'false'
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y java-1.8.0-openjdk wget python-devel gcc autoconf tar gzip unzip python-pip openssh-clients sshpass bzip2 ntp ntpdate sudo libselinux-python python-setuptools

    - name: install dependencies on RedHat OS from system repos
      when: ansible_os_family == 'RedHat' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y java-1.8.0-openjdk wget python-devel gcc autoconf tar gzip unzip python-pip openssh-clients sshpass bzip2 ntp ntpdate sudo libselinux-python python-setuptools

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
        - ntp
        - ntpdate
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

    - name: install MySQL client for Ubuntu
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

    - name: setup zstack account
      script: $setup_account
'''

        pre_script = '''
if [ -f /etc/redhat-release ] ; then

grep ' 7' /etc/redhat-release
if [ $$? -eq 0 ]; then
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=\$$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
else
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=\$$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
fi

[ -d /etc/yum.repos.d/ ] && echo -e "#aliyun base\n[alibase]\nname=CentOS-\$$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$$releasever/os/\$$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$$releasever/updates/\$$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$$releasever/extras/\$$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$$releasever/\$$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

[ -d /etc/yum.repos.d/ ] && echo -e "#163 base\n[163base]\nname=CentOS-\$$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$$releasever/os/\$$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$$releasever/updates/\$$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$$releasever/extras/\$$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$$releasever/\$$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo
fi

whereis zstack-ctl
if [ $$? -eq 0 ]; then
   zstack-ctl stop_node
fi

apache_path=$install_path/apache-tomcat
if [[ -d $$apache_path ]] && [[ $force_resinstall -eq 0 ]]; then
   echo "found existing Apache Tomcat directory $$apache_path; please use --force-reinstall to delete it and re-install"
   exit 1
fi

rm -rf $install_path
mkdir -p $install_path
'''
        t = string.Template(pre_script)
        pre_script = t.substitute({
            'force_resinstall': int(args.force_reinstall),
            'install_path': args.install_path
        })

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

        t = string.Template(yaml)
        if args.yum:
            yum_repo = args.yum
        else:
            yum_repo = 'false'
        yaml = t.substitute({
            'host': args.host,
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
            'setup_account': setup_account_path
        })

        ansible(yaml, args.host, args.debug, args.ssh_key)
        info('successfully installed new management node on machine(%s)' % args.host)

class ShowConfiguration(Command):
    def __init__(self):
        super(ShowConfiguration, self).__init__()
        self.name = "show_configuration"
        self.description = "a shortcut that prints contents of zstack.properties to screen"
        ctl.register_command(self)

    def run(self, args):
        shell_no_pipe('cat %s' % ctl.properties_file_path)

class SetEnvironmentVariableCmd(Command):
    PATH = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "zstack-ctl/ctl-env")

    def __init__(self):
        super(SetEnvironmentVariableCmd, self).__init__()
        self.name = "setenv"
        self.description = "set variables to zstack-ctl variable file at %s" % self.PATH
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


class InstallWebUiCmd(Command):

    def __init__(self):
        super(InstallWebUiCmd, self).__init__()
        self.name = "install_ui"
        self.description = "install ZStack web UI"
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
      apt: pkg=python-pip update_cache=yes

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

        pre_script = '''
if [ -f /etc/redhat-release ] ; then

grep ' 7' /etc/redhat-release
if [ $? -eq 0 ]; then
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=\$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
else
[ -d /etc/yum.repos.d/ ] && [ ! -f /etc/yum.repos.d/epel.repo ] && echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nmirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=\$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo
fi

[ -d /etc/yum.repos.d/ ] && echo -e "#aliyun base\n[alibase]\nname=CentOS-\$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

[ -d /etc/yum.repos.d/ ] && echo -e "#163 base\n[163base]\nname=CentOS-\$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo
fi
'''
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
        parser.add_argument('--host', help='IP or DNS name of the machine to upgrade the management node', default=None)
        parser.add_argument('--war-file', help='path to zstack.war. A HTTP/HTTPS url or a path to a local zstack.war', required=True)
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def run(self, args):
        error_if_tool_is_missing('unzip')
        need_download = args.war_file.startswith('http')
        if need_download:
            error_if_tool_is_missing('wget')

        upgrade_tmp_dir = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'upgrade', time.strftime('%Y-%m-%d-%H-%M-%S', time.gmtime()))
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
                shell('rm -rf %s' % ctl.zstack_home)
                if ctl.zstack_home.endswith('/'):
                    webapp_dir = os.path.dirname(os.path.dirname(ctl.zstack_home))
                else:
                    webapp_dir = os.path.dirname(ctl.zstack_home)

                shell('cp %s %s' % (new_war.path, webapp_dir))
                ShellCmd('unzip %s -d zstack' % os.path.basename(new_war.path), workdir=webapp_dir)()
                #create local repo folder for possible zstack local yum repo
                zstack_dvd_repo = '%s/zstack/static/zstack-dvd' % webapp_dir
                shell('rm -f %s; ln -s /opt/zstack-dvd %s' % (zstack_dvd_repo, zstack_dvd_repo))

            def restore_config():
                info('restoring the zstack.properties ...')
                ctl.internal_run('restore_config', '--restore-from %s' % os.path.dirname(property_file_backup_path))

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
            ansible(yaml, args.host, args.debug, ssh_key=args.ssh_key)
            info('upgraded the remote management node successfully')


        if args.host:
            remote_upgrade()
        else:
            local_upgrade()


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

    def run(self, args):
        error_if_tool_is_missing('mysqldump')
        error_if_tool_is_missing('mysql')

        db_url = ctl.get_db_url()
        db_url_params = db_url.split('//')
        db_url = db_url_params[0] + '//' + db_url_params[1].split('/')[0]
        if 'zstack' not in db_url:
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

        def backup_current_database():
            if args.no_backup:
                return

            info('start to backup the database ...')

            db_backup_path = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'db_backup', time.strftime('%Y-%m-%d-%H-%M-%S', time.gmtime()), 'backup.sql')
            shell('mkdir -p %s' % os.path.dirname(db_backup_path))
            if db_password:
                shell('mysqldump -u %s -p%s --host %s --port %s zstack > %s' % (db_user, db_password, db_hostname, db_port, db_backup_path))
            else:
                shell('mysqldump -u %s --host %s --port %s zstack > %s' % (db_user, db_hostname, db_port, db_backup_path))

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

        def migrate():
            schema_path = 'filesystem:%s' % upgrading_schema_dir

            if db_password:
                shell_no_pipe('bash %s migrate -outOfOrder=true -user=%s -password=%s -url=%s -locations=%s' % (flyway_path, db_user, db_password, db_url, schema_path))
            else:
                shell_no_pipe('bash %s migrate -outOfOrder=true -user=%s -url=%s -locations=%s' % (flyway_path, db_user, db_url, schema_path))

            info('Successfully upgraded the database to the latest version.\n')

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

        rollback_tmp_dir = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'rollback', time.strftime('%Y-%m-%d-%H-%M-%S', time.gmtime()))
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
                shell('rm -rf %s' % ctl.zstack_home)
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

class StopUiCmd(Command):
    def __init__(self):
        super(StopUiCmd, self).__init__()
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
                shell('kill %s >/dev/null 2>&1' % pid, is_exception=False)

        def stop_all():
            pid = find_process_by_cmdline('zstack_dashboard')
            if pid:
                shell('kill -9 %s >/dev/null 2>&1' % pid)
                stop_all()
            else:
                return

        stop_all()
        info('successfully stopped the UI server')

class UiStatusCmd(Command):
    def __init__(self):
        super(UiStatusCmd, self).__init__()
        self.name = "ui_status"
        self.description = "check the UI server status on the local or remote host."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help="UI server IP. [DEFAULT] localhost", default='localhost')

    def _remote_status(self, host):
        cmd = '/etc/init.d/zstack-dashboard status'
        ssh_run_no_pipe(host, cmd)

    def run(self, args):
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

class InstallLicenseCmd(Command):
    def __init__(self):
        super(InstallLicenseCmd, self).__init__()
        self.name = "install_license"
        self.description = "install zstack license"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--license', '-f', help="path to the license file", required=True)
        parser.add_argument('--prikey', help="[OPTIONAL] the path to the private key used to generate license request")

    def run(self, args):
        lpath = expand_path(args.license)
        if not os.path.isfile(lpath):
            raise CtlError('cannot find the license file at %s' % args.license)

        ppath = None
        if args.prikey:
            ppath = expand_path(args.prikey)
            if not os.path.isfile(ppath):
                raise CtlError('cannot find the private key file at %s' % args.prikey)

        license_folder = '/var/lib/zstack/license'
        shell('''su - zstack -c "mkdir -p %s"''' % license_folder)
        shell('''yes | cp %s %s/license.txt''' % (lpath, license_folder))
        shell('''chown zstack:zstack %s/license.txt''' % license_folder)
        info("successfully installed the license file to %s/license.txt" % license_folder)
        if ppath:
            shell('''yes | cp %s %s/pri.key''' % (ppath, license_folder))
            shell('''chown zstack:zstack %s/pri.key''' % license_folder)
            info("successfully installed the private key file to %s/pri.key" % license_folder)


class StartUiCmd(Command):
    PID_FILE = '/var/run/zstack/zstack-dashboard.pid'

    def __init__(self):
        super(StartUiCmd, self).__init__()
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
            shell('kill -9 %s > /dev/null' % pid)

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

        shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport %s -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT' % args.port)

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

def main():
    AddManagementNodeCmd()
    BootstrapCmd()
    ChangeIpCmd()
    CollectLogCmd()
    ConfigureCmd()
    DumpMysqlCmd()
    DeployDBCmd()
    GetEnvironmentVariableCmd()
    InstallWebUiCmd()
    InstallHACmd()
    InstallDbCmd()
    InstallRabbitCmd()
    InstallManagementNodeCmd()
    InstallLicenseCmd()
    ShowConfiguration()
    SetEnvironmentVariableCmd()
    RollbackManagementNodeCmd()
    RollbackDatabaseCmd()
    ResetRabbitCmd()
    RestoreConfigCmd()
    RestartNodeCmd()
    RestoreMysqlCmd()
    ShowStatusCmd()
    StartCmd()
    StopCmd()
    SaveConfigCmd()
    StartUiCmd()
    StopUiCmd()
    StartAllCmd()
    StopAllCmd()
    TailLogCmd()
    UiStatusCmd()
    UnsetEnvironmentVariableCmd()
    UpgradeManagementNodeCmd()
    UpgradeDbCmd()
    UpgradeCtlCmd()
    UpgradeHACmd()

    try:
        ctl.run()
    except CtlError as e:
        if ctl.verbose:
            error_not_exit(traceback.format_exc())
        error(str(e))

if __name__ == '__main__':
    main()
