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
import datetime

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
    sys.stdout.write('WARNING: %s\n' % msg)

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

class SpinnerInfo(object):
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
        while InstallHACmd.spinner_status[self.name]:
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

    def put_envs(self, vs):
        if not os.path.exists(SetEnvironmentVariableCmd.PATH):
            shell('su - zstack -c "mkdir -p %s"' % os.path.dirname(SetEnvironmentVariableCmd.PATH))
            shell('su - zstack -c "touch %s"' % SetEnvironmentVariableCmd.PATH)
        env = PropertyFile(SetEnvironmentVariableCmd.PATH)
        env.write_properties(vs)

    def run(self):
        if os.getuid() != 0:
            raise CtlError('zstack-ctl needs root privilege, please run with sudo')

        subparsers = self.main_parser.add_subparsers(help="All sub-commands", dest="sub_command_name")
        for cmd in self.command_list:
            cmd.install_argparse_arguments(subparsers.add_parser(cmd.name, help=cmd.description + '\n\n'))

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

def create_check_mgmt_node_command(timeout=10):
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
        return ShellCmd('''curl --noproxy --connect-timeout 1 --retry %s --retry-delay 0 --retry-max-time %s --max-time %s -H "Content-Type: application/json" -d '{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://127.0.0.1:8080/zstack/api''' % (timeout, timeout, timeout))
    elif what_tool == USE_WGET:
        return ShellCmd('''wget --no-proxy -O- --tries=%s --timeout=1  --header=Content-Type:application/json --post-data='{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://127.0.0.1:8080/zstack/api''' % timeout)
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
                info_list.append('status: %s' % status)

            if not cmd:
                write_status('cannot detect status, no wget and curl installed')
                return

            cmd(False)
            if cmd.return_code != 0:
                pid = get_management_node_pid()
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
                write_status(colored('Running', 'green'))
            else:
                write_status('Unknown')

        def show_version():
            db_hostname, db_port, db_user, db_password = ctl.get_live_mysql_portal()
            if db_password:
                cmd = ShellCmd('''mysql -u %s -p%s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_password, db_hostname, db_port))
            else:
                cmd = ShellCmd('''mysql -u %s --host %s --port %s -t zstack -e "show tables like 'schema_version'"''' %
                            (db_user, db_hostname, db_port))

            cmd(False)
            if cmd.return_code != 0:
                info_list.append('version: %s' % colored('unknown, MySQL is not running', 'yellow'))
                return

            out = cmd.stdout
            if 'schema_version' not in out:
                version = '0.6'
            else:
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

            detailed_version_file = os.path.join(ctl.DEFAULT_ZSTACK_HOME, "VERSION")
            if os.path.exists(detailed_version_file):
                with open(detailed_version_file, 'r') as fd:
                    detailed_version = fd.read()
                    info_list.append('version: %s (%s)' % (version, detailed_version))
            else:
                info_list.append('version: %s' % version)

        check_zstack_status()
        show_version()

        info('\n'.join(info_list))

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

    with open(pid_file_path, 'r') as fd:
        pid = fd.read()
        try:
            pid = int(pid)
            proc_pid = '/proc/%s' % pid
            if os.path.exists(proc_pid):
                return pid
        except Exception:
            return None

    return None

class StopAllCmd(Command):
    def __init__(self):
        super(StopAllCmd, self).__init__()
        self.name = 'stop'
        self.description = 'stop all ZStack related services including cassandra, kairosdb, zstack management node, web UI' \
                           ' if those services are installed'
        ctl.register_command(self)

    def run(self, args):
        def stop_cassandra():
            exe = ctl.get_env(InstallCassandraCmd.CASSANDRA_EXEC)
            if not exe or not os.path.exists(exe):
                info('skip stopping cassandra, it is not installed')
                return

            info(colored('Stopping cassandra, it may take a few minutes...', 'blue'))
            ctl.internal_run('cassandra', '--stop')

        def stop_kairosdb():
            exe = ctl.get_env(InstallKairosdbCmd.KAIROSDB_EXEC)
            if not exe or not os.path.exists(exe):
                info('skip stopping kairosdb, it is not installed')
                return

            info(colored('Stopping kairosdb, it may take a few minutes...', 'blue'))
            ctl.internal_run('kairosdb', '--stop')

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
        stop_kairosdb()
        stop_cassandra()

class StartAllCmd(Command):

    def __init__(self):
        super(StartAllCmd, self).__init__()
        self.name = 'start'
        self.description = 'start all ZStack related services including cassandra, kairosdb, zstack management node, web UI' \
                           ' if those services are installed'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--daemon', help='Start ZStack in daemon mode. Only used with systemd.', action='store_true', default=False)

    def run(self, args):
        def start_cassandra():
            exe = ctl.get_env(InstallCassandraCmd.CASSANDRA_EXEC)
            if not exe or not os.path.exists(exe):
                info('skip starting cassandra, it is not installed')
                return

            info(colored('Starting cassandra, it may take a few minutes...', 'blue'))
            ctl.internal_run('cassandra', '--start --wait-timeout 120')

        def start_kairosdb():
            exe = ctl.get_env(InstallKairosdbCmd.KAIROSDB_EXEC)
            if not exe or not os.path.exists(exe):
                info('skip starting kairosdb, it is not installed')
                return

            info(colored('Starting kairosdb, it may take a few minutes...', 'blue'))
            ctl.internal_run('kairosdb', '--start --wait-timeout 120')

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

        start_cassandra()
        start_kairosdb()
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

        default_pid_file_path = os.path.join(os.path.expanduser('~zstack'), "management-server.pid")
        if os.path.exists(default_pid_file_path):
            with open(default_pid_file_path, 'r') as fd:
                pid = fd.read()
                pid = pid.strip(' \n\t\r')

            proc_cmdline = os.path.join('/proc/%s/cmdline', pid)
            if os.path.exists(proc_cmdline):
                with open(proc_cmdline, 'r') as fd:
                    cmdline = fd.read()
                    if 'appName=zstack' in cmdline:
                        info('the management node[pid:%s] is already running' % pid)
                        return

        pid = get_management_node_pid()
        if pid:
            info('the management node[pid:%s] is already running' % pid)
            return

        def check_ip_port(host, port):
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((host, int(port)))
            return result == 0

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

            with on_error('unable to get RabbitMQ server IPs from %s, please check CloudBus.serverIp.0'):
                ips = ctl.read_property_list('CloudBus.serverIp.')
                if not ips:
                    raise CtlError('no RabbitMQ IPs defined in %s, please specify it use CloudBus.serverIp.0=the_ip' % ctl.properties_file_path)

                success = False
                for key, ip in ips:
                    if check_ip_port(ip, RABBIT_PORT):
                        success = True
                    else:
                        warn('cannot connect to the RabbitMQ server[ip:%s, port:%s]' % (ip, RABBIT_PORT))

                if not success:
                    raise CtlError('cannot connect to all RabbitMQ servers[ip:%s, port:%s] defined in %s' %
                                    (ips, RABBIT_PORT, ctl.properties_file_path))

        def prepare_setenv():
            setenv_path = os.path.join(ctl.zstack_home, self.SET_ENV_SCRIPT)
            catalina_opts = [
                '-Djava.net.preferIPv4Stack=true',
                '-Dcom.sun.management.jmxremote=true',
                '-Djava.security.egd=file:/dev/./urandom'
            ]

            co = ctl.get_env('CATALINA_OPTS')
            if co:
                info('use CATALINA_OPTS[%s] set in environment zstack environment variables; check out them by "zstack-ctl getenv"' % co)
                catalina_opts.extend(co.split(' '))

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

        check_8080()
        check_msyql()
        check_rabbitmq()
        prepare_setenv()
        start_mgmt_node()
        #sleep a while, since zstack won't start up so quick
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
            args.yum = ctl.read_property('Ansible.var.yum_repo')

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
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y  mariadb mariadb-server
      register: install_result

    - name: install MySQL for RedHat 7 from local
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y  mariadb mariadb-server
      register: install_result

    - name: install MySQL for Ubuntu
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - mysql-client
        - mysql-server
      register: install_result

    - name: open 3306 port
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
            grant_access_cmd = '''/usr/bin/mysql -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '' WITH GRANT OPTION; FLUSH PRIVILEGES;"''' % args.host
        elif not args.root_password:
            args.root_password = args.login_password
            grant_access_cmd = '''/usr/bin/mysql -u root -p%s -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '%s' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION; FLUSH PRIVILEGES;"''' % (args.root_password, args.root_password, args.host, args.root_password)
        else:
            grant_access_cmd = '''/usr/bin/mysql -u root -p%s -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' IDENTIFIED BY '%s' WITH GRANT OPTION; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%s' IDENTIFIED BY '%s' WITH GRANT OPTION; FLUSH PRIVILEGES;"''' % (args.root_password, args.root_password, args.host, args.root_password)

        if args.login_password is not None:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root -p{{login_password}} password {{root_password}}'
        else:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root password {{root_password}}'

        pre_install_script = '''
echo -e "#aliyun base\n[alibase]\nname=CentOS-\$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

echo -e "#163 base\n[163base]\nname=CentOS-\$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo

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
if [ -f /etc/mysql/my.cnf ]; then
    # Ubuntu
    sed -i 's/^bind-address/#bind-address/' /etc/mysql/my.cnf
    sed -i 's/^skip-networking/#skip-networking/' /etc/mysql/my.cnf
    grep '^character-set-server' /etc/mysql/my.cnf >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        sed -i '/\[mysqld\]/a character-set-server=utf8\' /etc/mysql/my.cnf
    fi
    grep '^skip-name-resolve' /etc/mysql/my.cnf >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        sed -i '/\[mysqld\]/a skip-name-resolve\' /etc/mysql/my.cnf
    fi
fi

if [ -f /etc/my.cnf ]; then
    # CentOS
    sed -i 's/^bind-address/#bind-address/' /etc/my.cnf
    sed -i 's/^skip-networking/#skip-networking/' /etc/my.cnf
    grep '^character-set-server' /etc/my.cnf >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        sed -i '/\[mysqld\]/a character-set-server=utf8\' /etc/my.cnf
    fi
    grep '^skip-name-resolve' /etc/my.cnf >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        sed -i '/\[mysqld\]/a skip-name-resolve\' /etc/my.cnf
    fi
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

class InstallHACmd(Command):
    '''This feature only support zstack offline image currently'''
    host_post_info_list = []
    current_dir = ""
    logger_dir = ""
    spinner_status = {'mysql':False,'rabbitmq':False, 'haproxy_keepalived':False,'Cassandra':False,
                      'Kairosdb':False, 'Mevoco':False, 'check_init':False, 'recovery_cluster':False}
    def __init__(self):
        super(InstallHACmd, self).__init__()
        self.name = "install_ha"
        self.description =  "install high availability environment for Mevoco."
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host1-info',
                            help="The first host connect info follow below format: 'root:password@ip_address' ",
                            required=True)
        parser.add_argument('--host2-info',
                            help="The second host connect info follow below format: 'root:password@ip_address' ",
                            required=True)
        parser.add_argument('--host3-info',
                            help="The third host connect info follow below format: 'root:password@ip_address' ",
                            default=False)
        parser.add_argument('--vip',
                            help="The virtual IP address for HA setup",
                            required=True)
        parser.add_argument('--gateway',
                            help="The gateway IP address for HA setup",
                            default=None)
        parser.add_argument('--mysql-root-password',
                            help="Password of MySQL root user", default="zstack123")
        parser.add_argument('--mysql-user-password',
                            help="Password of MySQL user zstack", default="zstack123")
        parser.add_argument('--rabbit-password',
                            help="RabbitMQ password; if set, the password will be created on RabbitMQ for username "
                                 "specified by --rabbit-username. [DEFAULT] rabbitmq default password",
                            default="zstack123")
        parser.add_argument('--drop', action='store_true', default=False,
                            help="Force delete mysql data for re-deploy HA")
        parser.add_argument('--keep-db', action='store_true', default=False,
                            help='keep existing zstack database and not raise error.')
        parser.add_argument('--recovery-from-this-host', action='store_true', default=False,
                            help="This argument for admin to recovery mysql from the last shutdown mysql server")
        parser.add_argument('--perfect-mode', action='store_true', default=False,
                            help="This mode will re-connect mysql faster")

    def reset_dict_value(self, dict_name, value):
        return dict.fromkeys(dict_name, value)

    def get_default_gateway(self):
        '''This function will return default route gateway ip address'''
        with open("/proc/net/route") as gateway:
            try:
                for item in gateway:
                    self.fields = item.strip().split()
                    if self.fields[1] != '00000000' or not int(self.fields[3], 16) & 2:
                        continue
                    return socket.inet_ntoa(struct.pack("=L", int(self.fields[2], 16)))
            except ValueError:
                return None

    def get_formatted_netmask(self, device_name):
        '''This function will return formatted netmask. eg. 172.20.12.16/24 will return 24'''
        self.netmask = socket.inet_ntoa(fcntl.ioctl(socket.socket(socket.AF_INET, socket.SOCK_DGRAM),
                                                    35099, struct.pack('256s', device_name))[20:24])
        self.formatted_netmask = sum([bin(int(x)).count('1') for x in self.netmask.split('.')])
        return self.formatted_netmask

    def get_ip_by_interface(self, device_name):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x8915,
                struct.pack('256s', device_name[:15])
            )[20:24])

    def check_host_info_format(self, host_info):
        if '@' not in host_info:
            error("Host connect information should follow format: 'root:password@host_ip', please check your input!")
        else:
            # get user and password
            if ':' not in host_info.split('@')[0]:
                error("Host connect information should follow format: 'root:password@host_ip', please check your input!")
            else:
                self.user = host_info.split('@')[0].split(':')[0]
                self.password = host_info.split('@')[0].split(':')[1]
                if self.user != "" and self.user != "root":
                   print "Only root user can be supported, please change user to root"
                if self.user == "":
                    self.user = "root"
            # get ip and port
            if ':' not in host_info.split('@')[1]:
                self.ip = host_info.split('@')[1]
                self.port = '22'
            else:
                self.ip = host_info.split('@')[1].split(':')[0]
                self.port = host_info.split('@')[1].split(':')[1]
            return (self.user, self.password, self.ip, self.port)

    def run(self, args):
        self.spinner_info = SpinnerInfo()
        self.spinner_info.output = "Checking system and init environment"
        self.spinner_info.name = 'check_init'
        InstallHACmd.spinner_status['check_init'] = True
        ZstackSpinner(self.spinner_info)
        # check gw ip is available
        if args.gateway is None:
            if self.get_default_gateway() is None:
                error("Can't get the gateway IP address from system, please check your route table or pass specific " \
                      "gateway through \"--gateway\" argument")
            else:
                self.gateway_ip = self.get_default_gateway()
        else:
            self.gateway_ip = args.gateway
        (self.status, self.output) = commands.getstatusoutput('ping -c 1 %s' % self.gateway_ip)
        if self.status != 0:
            error("The gateway %s unreachable!" % self.gateway_ip)
        # check input host info
        self.host1_info = args.host1_info
        self.host1_connect_info_list = self.check_host_info_format(self.host1_info)
        args.host1 = self.host1_connect_info_list[2]
        args.host1_password = self.host1_connect_info_list[1]
        self.host2_info = args.host2_info
        self.host2_connect_info_list = self.check_host_info_format(self.host2_info)
        args.host2 = self.host2_connect_info_list[2]
        args.host2_password = self.host2_connect_info_list[1]
        if args.host3_info is not False:
            self.host3_info = args.host3_info
            self.host3_connect_info_list = self.check_host_info_format(self.host3_info)
            args.host3 = self.host3_connect_info_list[2]
            args.host3_password = self.host3_connect_info_list[1]


        # check root password is available
        if args.host1_password != args.host2_password:
            error("Host1 password and Host2 password must be the same, Please change one of them!")
        elif args.host3_info is not False:
            if not args.host1_password == args.host2_password == args.host3_password:
                error("All hosts root password must be the same. Please check your host password!")
        self.command ='timeout 10 sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o  PubkeyAuthentication=no -o ' \
                      'StrictHostKeyChecking=no  root@%s echo ""' % (args.host1_password, args.host1)
        (self.status, self.output) = commands.getstatusoutput(self.command)
        if self.status != 0:
            error("The host: '%s' password '%s' incorrect! please check it!" % (args.host1, args.host1_password))
        self.command ='timeout 10 sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o  PubkeyAuthentication=no -o ' \
                      'StrictHostKeyChecking=no  root@%s echo ""' % (args.host2_password, args.host2)
        (self.status, self.output) = commands.getstatusoutput(self.command)
        if self.status != 0:
            error("The host: '%s' password '%s' incorrect! please check it!" % (args.host2, args.host2_password))
        if args.host3_info is not False:
            self.command ='timeout 10 sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o  PubkeyAuthentication=no -o ' \
                          'StrictHostKeyChecking=no  root@%s echo ""' % (args.host3_password, args.host3)
            (self.status, self.output) = commands.getstatusoutput(self.command)
            if self.status != 0:
                error("The host: '%s' password '%s' incorrect! please check it!" % (args.host3, args.host3_password))

        # check image type
        self.zstack_local_repo = os.path.isfile("/etc/yum.repos.d/zstack-local.repo")
        self.galera_repo = os.path.isfile("/etc/yum.repos.d/galera.repo")
        if self.zstack_local_repo is False or self.galera_repo is False:
            error("This feature only support ZStack community CentOS 7 image")

        # check network configuration
        self.interface_list = os.listdir('/sys/class/net/')
        if 'br_eth0' not in self.interface_list:
            error("Make sure you have already run the 'zs-network-setting' to setup the network environment")

        # check user start this command on host1
        if args.recovery_from_this_host is False:
            self.local_ip = self.get_ip_by_interface("br_eth0")
            if args.host1 != self.local_ip:
                error("Please run this command at host1 %s, or change your host1 ip to local host ip" % args.host1)

        # check user input wrong host2 ip
        if args.host2 == args.host1:
            error("The host1 and host2 should not be the same ip address!")
        elif args.host3_info is not False:
            if args.host2 == args.host3 or args.host1 == args.host3:
                error("The host1, host2 and host3 should not be the same ip address!")



        #init variables
        self.yum_repo = ctl.read_property('Ansible.var.yum_repo')
        InstallHACmd.current_dir = os.path.dirname(os.path.realpath(__file__))
        self.private_key_name = InstallHACmd.current_dir + "/conf/ha_key"
        self.public_key_name = InstallHACmd.current_dir + "/conf/ha_key.pub"
        if os.path.isfile(self.public_key_name) is not True:
            self.command = "echo -e  'y\n'|ssh-keygen -q -t rsa -N \"\" -f %s" % self.private_key_name
            (self.status, self.output) = commands.getstatusoutput(self.command)
            if self.status != 0:
                error("Generate private key %s failed! Generate manually or rerun the process!" % self.private_key_name)
        with open(self.public_key_name) as self.public_key_file:
            self.public_key = self.public_key_file.read()
        # create log
        InstallHACmd.logger_dir = "/var/log/zstack/"
        create_log(InstallHACmd.logger_dir)
        # create inventory file
        with  open('%s/conf/host' % InstallHACmd.current_dir ,'w') as f:
            f.writelines([args.host1+'\n', args.host2+'\n'])
        if args.host3_info is not False:
            with  open('%s/conf/host' % InstallHACmd.current_dir ,'w') as f:
                f.writelines([args.host1+'\n', args.host2+'\n', args.host3+'\n'])

        #self.host_inventory = '%s,%s' % (args.host1, args.host2)
        self.host_inventory = InstallHACmd.current_dir + '/conf/host'

        # init host1 parameter
        self.host1_post_info = HostPostInfo()
        self.host1_post_info.host = args.host1
        self.host1_post_info.host_inventory = self.host_inventory
        self.host1_post_info.private_key = self.private_key_name
        self.host1_post_info.yum_repo = self.yum_repo
        self.host1_post_info.vip = args.vip
        self.host1_post_info.gateway_ip = self.gateway_ip
        self.host1_post_info.rabbit_password = args.rabbit_password
        self.host1_post_info.mysql_password = args.mysql_root_password
        self.host1_post_info.mysql_userpassword = args.mysql_user_password
        self.host1_post_info.post_url = ""

        # init host2 parameter
        self.host2_post_info = HostPostInfo()
        self.host2_post_info.host = args.host2
        self.host2_post_info.host_inventory = self.host_inventory
        self.host2_post_info.private_key = self.private_key_name
        self.host2_post_info.yum_repo = self.yum_repo
        self.host2_post_info.vip = args.vip
        self.host2_post_info.gateway_ip = self.gateway_ip
        self.host2_post_info.rabbit_password = args.rabbit_password
        self.host2_post_info.mysql_password = args.mysql_root_password
        self.host2_post_info.mysql_userpassword = args.mysql_user_password
        self.host2_post_info.post_url = ""

        if args.host3_info is not False:
            # init host3 parameter
            self.host3_post_info = HostPostInfo()
            self.host3_post_info.host = args.host3
            self.host3_post_info.host_inventory = self.host_inventory
            self.host3_post_info.private_key = self.private_key_name
            self.host3_post_info.yum_repo = self.yum_repo
            self.host3_post_info.vip = args.vip
            self.host3_post_info.gateway_ip = self.gateway_ip
            self.host3_post_info.rabbit_password = args.rabbit_password
            self.host3_post_info.mysql_password = args.mysql_root_password
            self.host3_post_info.mysql_userpassword = args.mysql_user_password
            self.host3_post_info.post_url = ""


        # init all variables in map
        self.local_map = {
            "mysql_connect_timeout" : 60000,
            "mysql_socket_timeout" : 60000
        }
        if args.perfect_mode is True:
            self.local_map['mysql_connect_timeout'] = 2000
            self.local_map['mysql_socket_timeout'] = 2000

        self.add_public_key_command = ' if [ ! -d ~/.ssh ]; then mkdir -p ~/.ssh; chmod 700 ~/.ssh; fi && if [ ! -f ~/.ssh/authorized_keys ]; ' \
                                      'then touch ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; fi && pub_key="%s";grep ' \
                                      '"%s" ~/.ssh/authorized_keys > /dev/null; if [ $? -eq 1 ]; ' \
                                      'then echo "%s" >> ~/.ssh/authorized_keys; fi  && exit 0;'\
                                      % (self.public_key.strip('\n'), self.public_key.strip('\n'), self.public_key.strip('\n'))

        # add ha public key to host1
        self.ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                  "PubkeyAuthentication=no -o StrictHostKeyChecking=no  root@%s '%s'" % \
                                  (args.host1_password, args.host1, self.add_public_key_command)
        (status, output) = commands.getstatusoutput(self.ssh_add_public_key_command)
        if status != 0:
            error(output)

        # add ha public key to host2
        self.ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                  "PubkeyAuthentication=no -o StrictHostKeyChecking=no  root@%s '%s' " % \
                                  (args.host2_password, args.host2, self.add_public_key_command)
        (status, output) = commands.getstatusoutput(self.ssh_add_public_key_command)
        if status != 0:
            error(output)

        # add ha public key to host3
        if args.host3_info is not False:
            self.ssh_add_public_key_command = "sshpass -p %s ssh -q -o UserKnownHostsFile=/dev/null -o " \
                                              "PubkeyAuthentication=no -o StrictHostKeyChecking=no  root@%s '%s' " % \
                                              (args.host3_password, args.host3, self.add_public_key_command)
            (status, output) = commands.getstatusoutput(self.ssh_add_public_key_command)
            if status != 0:
                error(output)


        # sync ansible key in two host
        self.copy_arg = CopyArg()
        self.copy_arg.src = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/"
        self.copy_arg.dest = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/"
        copy(self.copy_arg,self.host2_post_info)
        if args.host3_info is not False:
            copy(self.copy_arg,self.host3_post_info)

        # check whether to recovery the HA cluster
        if args.recovery_from_this_host is True:
            self.local_ip = self.get_ip_by_interface("br_eth0")
            self.spinner_info = SpinnerInfo()
            self.spinner_info.output = "Starting to recovery mysql from this host"
            self.spinner_info.name = "recovery_cluster"
            InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
            InstallHACmd.spinner_status['recovery_cluster'] = True
            ZstackSpinner(self.spinner_info)
            self.command = "service mysql bootstrap"
            (status, output) = commands.getstatusoutput(self.command)
            if status != 0:
                error(output)
            else:
                #self.command = "service mysql start"
                if self.local_ip == self.host1_post_info.host:
                    # make sure vip will be on this host, so start haproxy firstly
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    #run_remote_command(self.command, self.host2_post_info)
                    service_status("mysql","state=started", self.host2_post_info)
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    if args.host3_info is not False:
                        #run_remote_command(self.command, self.host3_post_info)
                        service_status("mysql","state=started", self.host3_post_info)
                        service_status("haproxy","state=started", self.host3_post_info)
                        service_status("keepalived","state=started", self.host3_post_info)
                    #self.command = "service mysql restart"
                    #run_remote_command(self.command, self.host1_post_info)
                    service_status("mysql","state=restarted", self.host1_post_info)

                elif self.local_ip == self.host2_post_info.host:
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    #run_remote_command(self.command, self.host1_post_info)
                    service_status("mysql","state=started", self.host1_post_info)
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    if args.host3_info is not False:
                        #run_remote_command(self.command, self.host3_post_info)
                        service_status("mysql","state=started", self.host3_post_info)
                        service_status("haproxy","state=started", self.host3_post_info)
                        service_status("keepalived","state=started", self.host3_post_info)
                    #self.command = "service mysql restart"
                    #run_remote_command(self.command, self.host2_post_info)
                    service_status("mysql","state=restarted", self.host2_post_info)
                else:
                    # localhost must be host3
                    service_status("haproxy","state=started", self.host3_post_info)
                    service_status("keepalived","state=started", self.host3_post_info)
                    #run_remote_command(self.command, self.host1_post_info)
                    service_status("mysql","state=started", self.host1_post_info)
                    service_status("haproxy","state=started", self.host1_post_info)
                    service_status("keepalived","state=started", self.host1_post_info)
                    service_status("mysql","state=started", self.host2_post_info)
                    service_status("haproxy","state=started", self.host2_post_info)
                    service_status("keepalived","state=started", self.host2_post_info)
                    #self.command = "service mysql restart"
                    #run_remote_command(self.command, self.host2_post_info)
                    service_status("mysql","state=restarted", self.host3_post_info)

                # start mevoco
                self.spinner_info.output = "Starting Mevoco"
                self.spinner_info.name = "mevoco"
                InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
                InstallHACmd.spinner_status['mevoco'] = True
                ZstackSpinner(self.spinner_info)
                self.command = "zstack-ctl start"
                (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s"
                                                                     % (self.private_key_name, args.host1, self.command))
                if self.status != 0:
                    error("Something wrong on host: %s\n %s" % (args.host1, self.output))
                (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s"
                                                                     % (self.private_key_name, args.host2, self.command))
                if self.status != 0:
                    error("Something wrong on host: %s\n %s" % (args.host2, self.output))
                if args.host3_info is not False:
                    (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s"
                                                                         % (self.private_key_name, args.host3, self.command))
                    if self.status != 0:
                        error("Something wrong on host: %s\n %s" % (args.host2, self.output))
                InstallHACmd.spinner_status['mevoco'] = False
                time.sleep(.2)
            info("The cluster has been recovery!")
            sys.exit(0)

        # get iptables from system config
        service_status("iptables","state=restarted",self.host1_post_info)
        service_status("iptables","state=restarted",self.host2_post_info)
        if args.host3_info is not False:
            service_status("iptables","state=restarted",self.host3_post_info)
        # remove mariadb for avoiding conflict with mevoco install process
        self.command = "rpm -q mariadb | grep 'not installed' || yum remove -y mariadb"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(self.command, self.host3_post_info)

        self.command = "hostnamectl set-hostname zstack-1"
        run_remote_command(self.command, self.host1_post_info)
        self.command = "hostnamectl set-hostname zstack-2"
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            self.command = "hostnamectl set-hostname zstack-3"
            run_remote_command(self.command, self.host3_post_info)

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

        self.command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                       " ; iptables-save > /dev/null 2>&1" % (self.host2_post_info.host, self.host2_post_info.host)
        run_remote_command(self.command, self.host1_post_info)
        if args.host3_info is not False:
            self.command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host3_post_info.host, self.host3_post_info.host)
            run_remote_command(self.command, self.host1_post_info)
        self.command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                       " ; iptables-save > /dev/null 2>&1" % (self.host1_post_info.host, self.host1_post_info.host)
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            self.command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host3_post_info.host, self.host3_post_info.host)
            run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            self.command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host1_post_info.host, self.host1_post_info.host)
            run_remote_command(self.command, self.host3_post_info)
            self.command = " ! iptables -C INPUT -s %s/32 -j ACCEPT >/dev/null 2>&1 && iptables -I INPUT -s %s/32 -j ACCEPT" \
                           " ; iptables-save > /dev/null 2>&1" % (self.host2_post_info.host, self.host2_post_info.host)
            run_remote_command(self.command, self.host3_post_info)

        # stop haproxy and keepalived service for avoiding terminal status  disturb
        self.command = "service keepalived stop && service haproxy stop || echo True"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(self.command, self.host3_post_info)

        #pass all the variables to other HA deploy process
        InstallHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info]
        if args.host3_info is not False:
            InstallHACmd.host_post_info_list = [self.host1_post_info, self.host2_post_info, self.host3_post_info]
        # setup mysql ha
        self.spinner_info = SpinnerInfo()
        self.spinner_info.output = "Starting to deploy Mysql HA"
        self.spinner_info.name = 'mysql'
        InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
        InstallHACmd.spinner_status['mysql'] = True
        ZstackSpinner(self.spinner_info)
        MysqlHA()()

        # setup rabbitmq ha
        self.spinner_info = SpinnerInfo()
        self.spinner_info.output ="Starting to deploy Rabbitmq HA"
        self.spinner_info.name = 'rabbitmq'
        InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
        InstallHACmd.spinner_status['rabbitmq'] = True
        ZstackSpinner(self.spinner_info)
        RabbitmqHA()()

        # setup haproxy and keepalived
        self.spinner_info = SpinnerInfo()
        self.spinner_info.output = "Starting to deploy Haproxy and Keepalived"
        self.spinner_info.name = 'haproxy_keepalived'
        InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
        InstallHACmd.spinner_status['haproxy_keepalived'] = True
        ZstackSpinner(self.spinner_info)
        HaproxyKeepalived()()

        #install database on local management node
        self.command = "zstack-ctl stop"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(self.command, self.host3_post_info)
        if args.keep_db is True:
            self.command = "zstack-ctl deploydb --keep-db --host=%s --port=3306 --zstack-password=%s --root-password=%s" \
                           % (args.host1, args.mysql_user_password, args.mysql_root_password)
            run_remote_command(self.command, self.host1_post_info)
        elif args.drop is True:
            self.command = "zstack-ctl deploydb --drop --host=%s --port=3306 --zstack-password=%s --root-password=%s" \
                           % (args.host1, args.mysql_user_password, args.mysql_root_password)
            run_remote_command(self.command, self.host1_post_info)
        else:
            self.command = "zstack-ctl deploydb --host=%s --port=3306 --zstack-password=%s --root-password=%s" \
                           % (args.host1, args.mysql_user_password, args.mysql_root_password)
            run_remote_command(self.command, self.host1_post_info)

        self.command = "zstack-ctl configure DB.url=jdbc:mysql://%s:53306/{database}?connectTimeout=%d\&socketTimeout=%d"\
                       % (args.vip, self.local_map['mysql_connect_timeout'], self.local_map['mysql_socket_timeout'])
        run_remote_command(self.command, self.host1_post_info)
        self.command = "zstack-ctl configure CloudBus.rabbitmqPassword=%s" % args.mysql_user_password
        run_remote_command(self.command, self.host1_post_info)

        # cassandra HA only need to change the config file, so unnecessary to wrap the process in a class
        self.spinner_info = SpinnerInfo()
        self.spinner_info.output = "Starting to deploy Cassandra HA"
        self.spinner_info.name = "Cassandra"
        InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
        InstallHACmd.spinner_status['Cassandra'] = True
        ZstackSpinner(self.spinner_info)
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

        # kaiosdb HA only need to change the config file, so unnecessary to wrap the process in a class
        update_file("%s/kairosdb/conf/kairosdb.properties" % ctl.USER_ZSTACK_HOME_DIR,
                    "regexp='kairosdb\.datastore\.cassandra\.host_list' line='kairosdb.datastore.cassandra.host_list="
                    "%s:9160,%s:9160'" % (args.host1, args.host2), self.host1_post_info)
        update_file("%s/kairosdb/conf/kairosdb.properties" % ctl.USER_ZSTACK_HOME_DIR,
                    "regexp='kairosdb\.datastore\.cassandra\.host_list' line='kairosdb.datastore.cassandra.host_list="
                    "%s:9160,%s:9160'" % (args.host1, args.host2), self.host2_post_info)
        if args.host3_info is not False:
            update_file("%s/kairosdb/conf/kairosdb.properties" % ctl.USER_ZSTACK_HOME_DIR,
                        "regexp='kairosdb\.datastore\.cassandra\.host_list' line='kairosdb.datastore.cassandra.host_list="
                        "%s:9160,%s:9160,%s:9160'" % (args.host1, args.host2, args.host3), self.host1_post_info)
            update_file("%s/kairosdb/conf/kairosdb.properties" % ctl.USER_ZSTACK_HOME_DIR,
                        "regexp='kairosdb\.datastore\.cassandra\.host_list' line='kairosdb.datastore.cassandra.host_list="
                        "%s:9160,%s:9160,%s:9160'" % (args.host1, args.host2, args.host3), self.host2_post_info)
            update_file("%s/kairosdb/conf/kairosdb.properties" % ctl.USER_ZSTACK_HOME_DIR,
                        "regexp='kairosdb\.datastore\.cassandra\.host_list' line='kairosdb.datastore.cassandra.host_list="
                        "%s:9160,%s:9160,%s:9160'" % (args.host1, args.host2, args.host3), self.host3_post_info)

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
                    "regexp='^Kairosdb.ip' line='Kairosdb.ip=%s'" % args.vip, self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='^Kairosdb.port' line='Kairosdb.port=58080'", self.host1_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='management\.server\.ip' line='management.server.ip = %s'" %
                    args.host1, self.host1_post_info)
        self.copy_arg = CopyArg()
        self.copy_arg.src = ctl.properties_file_path
        self.copy_arg.dest = ctl.properties_file_path
        copy(self.copy_arg, self.host2_post_info)
        update_file("%s" % ctl.properties_file_path,
                    "regexp='management\.server\.ip' line='management.server.ip = %s'"
                    % args.host2, self.host2_post_info)
        if args.host3_info is not False:
            copy(self.copy_arg, self.host3_post_info)
            update_file("%s" % ctl.properties_file_path,
                        "regexp='management\.server\.ip' line='management.server.ip = %s'"
                        % args.host3, self.host3_post_info)


        # start Cassadra and KairosDB
        # backup old cassandra dir avoid changing keyspace error
        self.command = "[ -d /var/lib/cassandra/ ] && mv /var/lib/cassandra/ /var/lib/cassandra-%s/ || echo '' " \
                       % datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_remote_command(self.command, self.host1_post_info)
        self.command = 'zstack-ctl cassandra --start --wait-timeout 120'
        (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                             (self.private_key_name, args.host1, self.command))
        if self.status != 0:
            error("Something wrong on host: %s\n %s" % (args.host1, self.output))
        (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                             (self.private_key_name, args.host2, self.command))
        if self.status != 0:
            error("Something wrong on host: %s\n %s" % (args.host2, self.output))
        if args.host3_info is not False:
            (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                                 (self.private_key_name, args.host3, self.command))
            if self.status != 0:
                error("Something wrong on host: %s\n %s" % (args.host3, self.output))

        self.spinner_info = SpinnerInfo()
        self.spinner_info.output = "Starting to deploy Kairosdb HA"
        self.spinner_info.name = "Kairosdb"
        InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
        InstallHACmd.spinner_status['Kairosdb'] = True
        ZstackSpinner(self.spinner_info)
        self.command = 'zstack-ctl kairosdb --start --wait-timeout 120'
        (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                             (self.private_key_name, args.host1, self.command))
        if self.status != 0:
            error("Something wrong on host: %s\n %s" % (args.host1, self.output))
        (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                             (self.private_key_name, args.host2, self.command))
        if self.status != 0:
            error("Something wrong on host: %s\n %s" % (args.host2, self.output))
        if args.host3_info is not False:
            (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                                 (self.private_key_name, args.host3, self.command))
            if self.status != 0:
                error("Something wrong on host: %s\n %s" % (args.host3, self.output))

        # deploy cassandra_db
        # self.command = 'zstack-ctl deploy_cassandra_db'
        # run_remote_command(self.command, self.host1_post_info)

        # change Cassadra duplication number
        #self.update_cassadra = "ALTER KEYSPACE kairosdb WITH REPLICATION = { 'class' : " \
        #                       "'SimpleStrategy','replication_factor' : 3 };CONSISTENCY ONE;"
        #self.command = "%s/../../../apache-cassandra-2.2.3/bin/cqlsh %s 9042 -e \"%s\"" % \
        #               (os.environ['ZSTACK_HOME'], args.host1, self.update_cassadra)
        #run_remote_command(self.command, self.host1_post_info)

        #finally, start zstack-1 and zstack-2
        self.spinner_info = SpinnerInfo()
        self.spinner_info.output = "Starting Mevoco"
        self.spinner_info.name = "mevoco"
        InstallHACmd.spinner_status = self.reset_dict_value(InstallHACmd.spinner_status,False)
        InstallHACmd.spinner_status['mevoco'] = True
        ZstackSpinner(self.spinner_info)
        # Add zstack-ctl start to rc.local for auto recovery when system reboot
        self.command = "service iptables save"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(self.command, self.host3_post_info)
        self.command = "zstack-ctl install_ui"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if args.host3_info is not False:
            run_remote_command(self.command, self.host3_post_info)
        self.command = "zstack-ctl start"
        (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                             (self.private_key_name, args.host1, self.command))
        if self.status != 0:
            error("Something wrong on host: %s\n %s" % (args.host1, self.output))
        (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                             (self.private_key_name, args.host2, self.command))
        if self.status != 0:
            error("Something wrong on host: %s\n %s" % (args.host2, self.output))
        if args.host3_info is not False:
            (self.status, self.output)= commands.getstatusoutput("ssh -i %s root@%s %s" %
                                                                 (self.private_key_name, args.host3, self.command))
            if self.status != 0:
                error("Something wrong on host: %s\n %s" % (args.host3, self.output))
        InstallHACmd.spinner_status['mevoco'] = False
        time.sleep(0.2)


        print '''HA deploy finished!
Mysql user 'root' password: %s
Mysql user 'zstack' password: %s
Rabbitmq user 'zstack' password: %s
Mevoco is running, visit %s in Chrome or Firefox with default user/password : %s
You can check the cluster status at %s with user/passwd : %s
       ''' % (args.mysql_root_password, args.mysql_user_password, args.rabbit_password,
              colored('http://%s:8888' % args.vip, 'blue'), colored('admin/password', 'yellow'),
              colored('http://%s:9132/zstack' % args.host1, 'blue'), colored('zstack/zstack123', 'yellow'))

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
        self.command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q haproxy keepalived"
                        " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                        "--disablerepo=* --enablerepo=%s install -y $pkg; done;") % self.yum_repo
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
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
        self.command = "touch /var/log/haproxy.log"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
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

listen  proxy-kairosdb 0.0.0.0:58080
    mode tcp
    balance source
    server zstack-1 {{ host1 }}:18080 weight 10 check inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:18080 backup weight 10 check inter 3s rise 2 fall 2
    option tcpka
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

listen  proxy-kairosdb 0.0.0.0:58080
    mode tcp
    balance source
    server zstack-1 {{ host1 }}:18080 weight 10 check inter 3s rise 2 fall 2
    server zstack-2 {{ host2 }}:18080 backup weight 10 check inter 3s rise 2 fall 2
    server zstack-3 {{ host3 }}:18080 backup weight 10 check inter 3s rise 2 fall 2
    option tcpka
        '''

        self.haproxy_conf_template = jinja2.Template(haproxy_raw_conf)
        self.haproxy_host1_conf = self.haproxy_conf_template.render({
            'host1' : self.host1_post_info.host,
            'host2' : self.host2_post_info.host
        })
        if len(self.host_post_info_list) == 3:
            self.haproxy_host1_conf = self.haproxy_conf_template.render({
                'host1' : self.host1_post_info.host,
                'host2' : self.host2_post_info.host,
                'host3' : self.host3_post_info.host
            })

        # The host1 and host2 and host3 use the same config file
        self.host1_config, self.haproxy_host1_conf_file = tempfile.mkstemp()
        self.f1 = os.fdopen(self.host1_config, 'w')
        self.f1.write(self.haproxy_host1_conf)
        self.f1.close()

        def cleanup_haproxy_config_file():
            os.remove(self.haproxy_host1_conf_file)
        self.install_cleanup_routine(cleanup_haproxy_config_file)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.haproxy_host1_conf_file
        self.copy_arg.dest = "/etc/haproxy/haproxy.cfg"
        copy(self.copy_arg,self.host1_post_info)
        copy(self.copy_arg,self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(self.copy_arg,self.host3_post_info)

        #config haproxy firewall
        self.command = "! iptables -C INPUT -p tcp -m tcp --dport 53306 -j ACCEPT > /dev/null 2>&1 && iptables -I INPUT -p tcp -m tcp --dport 53306 -j ACCEPT; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 55672 -j ACCEPT > /dev/null 2>&1  &&  iptables -I INPUT -p tcp -m tcp --dport 55672 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 80 -j ACCEPT > /dev/null 2>&1  && iptables -I INPUT -p tcp -m tcp --dport 80 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 9132 -j ACCEPT > /dev/null 2>&1 &&  iptables -I INPUT -p tcp -m tcp --dport 9132 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 8888 -j ACCEPT > /dev/null 2>&1 &&  iptables -I INPUT -p tcp -m tcp --dport 8888 -j ACCEPT ; " \
                       "! iptables -C INPUT -p tcp -m tcp --dport 6033 -j ACCEPT > /dev/null 2>&1 && iptables -I INPUT -p tcp -m tcp --dport 6033 -j ACCEPT; iptables-save "
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)

        #config keepalived
        self.keepalived_raw_config = '''
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
   interface br_eth0
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
      {{ vip }}/{{ netmask }} label br_eth0:0
 }
}
        '''

        self.virtual_router_id = random.randint(1, 255)
        self.auth_pass = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(15))
        self.master_priority = 100
        self.slave_priority = 90
        self.second_slave_priority = 80
        self.keepalived_template = jinja2.Template(self.keepalived_raw_config)
        self.keepalived_host1_config = self.keepalived_template.render({
            'vrouter_id': self.virtual_router_id,
            'priority': self.master_priority,
            'auth_passwd': self.auth_pass,
            'vip': self.vip,
            'netmask': self.get_formatted_netmask('br_eth0')
        })

        self.keepalived_host2_config = self.keepalived_template.render({
            'vrouter_id': self.virtual_router_id,
            'priority': self.slave_priority,
            'auth_passwd': self.auth_pass,
            'vip': self.vip,
            'netmask': self.get_formatted_netmask('br_eth0')
        })

        if len(self.host_post_info_list) == 3:
            self.keepalived_host3_config = self.keepalived_template.render({
                'vrouter_id': self.virtual_router_id,
                'priority': self.second_slave_priority,
                'auth_passwd': self.auth_pass,
                'vip': self.vip,
                'netmask': self.get_formatted_netmask('br_eth0')
            })

        self.host1_config, self.keepalived_host1_config_file = tempfile.mkstemp()
        self.f1 = os.fdopen(self.host1_config, 'w')
        self.f1.write(self.keepalived_host1_config)
        self.f1.close()
        self.host2_config, self.keepalived_host2_config_file = tempfile.mkstemp()
        self.f2 = os.fdopen(self.host1_config, 'w')
        self.f2.write(self.keepalived_host2_config)
        self.f2.close()
        if len(self.host_post_info_list) == 3:
            self.host3_config, self.keepalived_host3_config_file = tempfile.mkstemp()
            self.f3 = os.fdopen(self.host3_config, 'w')
            self.f3.write(self.keepalived_host3_config)
            self.f3.close()

        def cleanup_keepalived_config_file():
            os.remove(self.keepalived_host1_config_file)
            os.remove(self.keepalived_host2_config_file)
            if len(self.host_post_info_list) == 3:
                os.remove(self.keepalived_host3_config_file)
            self.install_cleanup_routine(cleanup_keepalived_config_file)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.keepalived_host1_config_file
        self.copy_arg.dest = "/etc/keepalived/keepalived.conf"
        copy(self.copy_arg, self.host1_post_info)
        self.copy_arg = CopyArg()
        self.copy_arg.src = self.keepalived_host2_config_file
        self.copy_arg.dest = "/etc/keepalived/keepalived.conf"
        copy(self.copy_arg, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            self.copy_arg = CopyArg()
            self.copy_arg.src = self.keepalived_host3_config_file
            self.copy_arg.dest = "/etc/keepalived/keepalived.conf"
            copy(self.copy_arg, self.host3_post_info)

        # copy keepalived-kill.sh to host
        self.copy_arg = CopyArg()
        self.copy_arg.src = "%s/conf/keepalived-kill.sh" % InstallHACmd.current_dir
        self.copy_arg.dest = "/usr/local/bin/keepalived-kill.sh"
        self.copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(self.copy_arg, self.host1_post_info)
        copy(self.copy_arg, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(self.copy_arg, self.host3_post_info)

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
        self.command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q MariaDB-Galera-server xinetd rsync openssl-libs "
                   " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
                   "--disablerepo=* --enablerepo=%s,mariadb install -y $pkg; done;") % self.yum_repo
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
        # Generate galera config file and copy to host1 host2
        self.galera_raw_config= '''[mysqld]
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
            self.galera_raw_config= '''[mysqld]
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
        self.galera_config_template = jinja2.Template(self.galera_raw_config)

        self.galera_config_host1 = self.galera_config_template.render({
            'host1' : self.host1_post_info.host,
            'host2' : self.host2_post_info.host
        })
        if len(self.host_post_info_list) == 3:
            self.galera_config_host1 = self.galera_config_template.render({
                'host1' : self.host1_post_info.host,
                'host2' : self.host2_post_info.host,
                'host3' : self.host3_post_info.host
            })

        self.galera_config_host2 = self.galera_config_template.render({
            'host1' : self.host2_post_info.host,
            'host2' : self.host1_post_info.host
        })
        if len(self.host_post_info_list) == 3:
            self.galera_config_host2 = self.galera_config_template.render({
                'host1' : self.host2_post_info.host,
                'host2' : self.host3_post_info.host,
                'host3' : self.host1_post_info.host
            })

        if len(self.host_post_info_list) == 3:
            self.galera_config_host3 = self.galera_config_template.render({
                'host1' : self.host3_post_info.host,
                'host2' : self.host1_post_info.host,
                'host3' : self.host2_post_info.host
            })

        self.host1_config, self.galera_config_host1_file = tempfile.mkstemp()
        self.f1 = os.fdopen(self.host1_config, 'w')
        self.f1.write(self.galera_config_host1)
        self.f1.close()

        self.host2_config, self.galera_config_host2_file = tempfile.mkstemp()
        self.f2 = os.fdopen(self.host2_config, 'w')
        self.f2.write(self.galera_config_host2)
        self.f2.close()

        if len(self.host_post_info_list) == 3:
            self.host3_config, self.galera_config_host3_file = tempfile.mkstemp()
            self.f3 = os.fdopen(self.host3_config, 'w')
            self.f3.write(self.galera_config_host3)
            self.f3.close()

        def cleanup_galera_config_file():
            os.remove(self.galera_config_host1_file)
            os.remove(self.galera_config_host2_file)
            if len(self.host_post_info_list) == 3:
                os.remove(self.galera_config_host3_file)
        self.install_cleanup_routine(cleanup_galera_config_file)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.galera_config_host1_file
        self.copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
        copy(self.copy_arg, self.host1_post_info)
        self.copy_arg = CopyArg()
        self.copy_arg.src = self.galera_config_host2_file
        self.copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
        copy(self.copy_arg, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            self.copy_arg = CopyArg()
            self.copy_arg.src = self.galera_config_host3_file
            self.copy_arg.dest = "/etc/my.cnf.d/galera.cnf"
            copy(self.copy_arg, self.host3_post_info)

        # restart mysql service to enable galera config
        self.command = "service mysql stop || echo True"
        #service_status("mysql", "state=stopped", self.host1_post_info)
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
        self.command = "service mysql bootstrap"
        run_remote_command(self.command, self.host1_post_info)
        service_status("mysql","state=started enabled=yes", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("mysql","state=started enabled=yes", self.host3_post_info)
        service_status("mysql","state=restarted enabled=yes", self.host1_post_info)

        self.init_install = check_command_status("mysql -u root --password='' -e 'exit' ", self.host1_post_info)
        if self.init_install is True:
            #self.command = "mysql -u root --password='' -Bse \"show status like 'wsrep_%%';\""
            #galera_status = run_remote_command(self.command, self.host2_post_info)
            #create zstack user
            self.command =" mysql -u root --password='' -Bse 'grant ALL PRIVILEGES on *.* to zstack@\"localhost\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES on *.* to zstack@\"zstack-1\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES on *.* to zstack@\"%%\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES on *.* to root@\"%%\" Identified by \"%s\";" \
                          "grant ALL PRIVILEGES on *.* to root@\"localhost\" Identified by \"%s\"; " \
                          "grant ALL PRIVILEGES ON *.* TO root@\"%%\" IDENTIFIED BY \"%s\" WITH GRANT OPTION; " \
                          "flush privileges;'" % (self.host1_post_info.mysql_userpassword, self.host1_post_info.mysql_userpassword,
                                                 self.host1_post_info.mysql_userpassword,self.host1_post_info.mysql_password,
                                                 self.host1_post_info.mysql_password, self.host1_post_info.mysql_password)
            run_remote_command(self.command, self.host1_post_info)

        # config mysqlchk_status.sh on zstack-1 and zstack-2
        self.mysqlchk_raw_script = '''#!/bin/sh
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
        self.mysqlchk_template = jinja2.Template(self.mysqlchk_raw_script)
        self.mysqlchk_script_host1 = self.mysqlchk_template.render({
            'host1' : self.host1_post_info.host,
            'mysql_username' : "zstack",
            'mysql_password' : self.host1_post_info.mysql_userpassword
        })
        self.mysqlchk_script_host2 = self.mysqlchk_template.render({
            'host1' : self.host2_post_info.host,
            'mysql_username' : "zstack",
            'mysql_password' : self.host2_post_info.mysql_userpassword
        })
        if len(self.host_post_info_list) == 3:
            self.mysqlchk_script_host3 = self.mysqlchk_template.render({
                'host1' : self.host3_post_info.host,
                'mysql_username' : "zstack",
                'mysql_password' : self.host3_post_info.mysql_userpassword
            })


        self.host1_config, self.mysqlchk_script_host1_file = tempfile.mkstemp()
        self.f1 = os.fdopen(self.host1_config, 'w')
        self.f1.write(self.mysqlchk_script_host1)
        self.f1.close()

        self.host2_config, self.mysqlchk_script_host2_file = tempfile.mkstemp()
        self.f2 = os.fdopen(self.host2_config, 'w')
        self.f2.write(self.mysqlchk_script_host2)
        self.f2.close()

        if len(self.host_post_info_list) == 3:
            self.host3_config, self.mysqlchk_script_host3_file = tempfile.mkstemp()
            self.f3 = os.fdopen(self.host3_config, 'w')
            self.f3.write(self.mysqlchk_script_host3)
            self.f3.close()

        def cleanup_mysqlchk_script():
            os.remove(self.mysqlchk_script_host1_file)
            os.remove(self.mysqlchk_script_host2_file)
            if len(self.host_post_info_list) == 3:
                os.remove(self.mysqlchk_script_host3_file)
            self.install_cleanup_routine(cleanup_mysqlchk_script)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.mysqlchk_script_host1_file
        self.copy_arg.dest = "/usr/local/bin/mysqlchk_status.sh"
        self.copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(self.copy_arg,self.host1_post_info)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.mysqlchk_script_host2_file
        self.copy_arg.dest = "/usr/local/bin/mysqlchk_status.sh"
        self.copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(self.copy_arg,self.host2_post_info)

        if len(self.host_post_info_list) == 3:
            self.copy_arg = CopyArg()
            self.copy_arg.src = self.mysqlchk_script_host3_file
            self.copy_arg.dest = "/usr/local/bin/mysqlchk_status.sh"
            self.copy_arg.args = "mode='u+x,g+x,o+x'"
            copy(self.copy_arg,self.host3_post_info)

        #check network
        self.check_network_raw_script='''#!/bin/bash
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
        self.galera_check_network = jinja2.Template(self.check_network_raw_script)
        self.galera_check_network_host1 = self.galera_check_network.render({
            'host' : self.host1_post_info.host,
            'mysql_root_password' : self.host1_post_info.mysql_password
        })
        self.galera_check_network_host2 = self.galera_check_network.render({
            'host' : self.host2_post_info.host,
            'mysql_root_password' : self.host1_post_info.mysql_password
        })

        self.host1_config, self.galera_check_network_host1_file = tempfile.mkstemp()
        self.f1 = os.fdopen(self.host1_config, 'w')
        self.f1.write(self.galera_check_network_host1)
        self.f1.close()

        self.host2_config, self.galera_check_network_host2_file = tempfile.mkstemp()
        self.f2 = os.fdopen(self.host2_config, 'w')
        self.f2.write(self.galera_check_network_host2)
        self.f2.close()

        def cleanup_gelerachk_script():
            os.remove(self.galera_check_network_host1_file)
            os.remove(self.galera_check_network_host2_file)
            if len(self.host_post_info_list) == 3:
                os.remove(self.galera_check_network_host3_file)
            self.install_cleanup_routine(cleanup_gelerachk_script)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.galera_check_network_host1_file
        self.copy_arg.dest = "/usr/local/zstack/check-network.sh"
        self.copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(self.copy_arg,self.host1_post_info)

        self.copy_arg = CopyArg()
        self.copy_arg.src = self.galera_check_network_host2_file
        self.copy_arg.dest = "/usr/local/zstack/check-network.sh"
        self.copy_arg.args = "mode='u+x,g+x,o+x'"
        copy(self.copy_arg,self.host2_post_info)

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
        self.copy_arg = CopyArg()
        self.copy_arg.src = "%s/conf/mysql-check" % InstallHACmd.current_dir
        self.copy_arg.dest = "/etc/xinetd.d/mysql-check"
        copy(self.copy_arg,self.host1_post_info)
        copy(self.copy_arg,self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            copy(self.copy_arg,self.host3_post_info)

        # add service name
        update_file("/etc/services", "line='mysqlcheck      6033/tcp     #MYSQL status check'", self.host1_post_info)
        update_file("/etc/services", "line='mysqlcheck      6033/tcp     #MYSQL status check'", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            update_file("/etc/services", "line='mysqlcheck      6033/tcp     #MYSQL status check'", self.host3_post_info)

        # start service
        self.command = "systemctl daemon-reload"
        run_remote_command(self.command,self.host1_post_info)
        run_remote_command(self.command,self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command,self.host3_post_info)
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
        self.command = ("yum clean --enablerepo=zstack-local metadata && pkg_list=`rpm -q rabbitmq-server"
               " | grep \"not installed\" | awk '{ print $2 }'` && for pkg in $pkg_list; do yum "
               "--disablerepo=* --enablerepo=%s,mariadb install -y $pkg; done;") % self.yum_repo
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
        # clear erlang process for new deploy
        self.command = "echo True || pkill -f .*erlang.*  > /dev/null 2>&1 && rm -rf /var/lib/rabbitmq/* && service rabbitmq-server stop "
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)

        # to start rabbitmq-server
        service_status("rabbitmq-server","state=started enabled=yes", self.host1_post_info)
        service_status("rabbitmq-server", "state=started enabled=yes", self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            service_status("rabbitmq-server", "state=started enabled=yes", self.host3_post_info)
        # add zstack user in this cluster
        self.command = "rabbitmqctl add_user zstack %s" %  self.rabbit_password
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
        self.command = "rabbitmqctl set_user_tags zstack administrator"
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
        self.command = "rabbitmqctl change_password zstack %s" % self.rabbit_password
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)
        self.command = 'rabbitmqctl set_permissions -p \/ zstack ".*" ".*" ".*"'
        run_remote_command(self.command, self.host1_post_info)
        run_remote_command(self.command, self.host2_post_info)
        if len(self.host_post_info_list) == 3:
            run_remote_command(self.command, self.host3_post_info)


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
            args.yum = ctl.read_property('Ansible.var.yum_repo')

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
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y rabbitmq-server libselinux-python

    - name: install RabbitMQ on RedHat OS from online
      when: ansible_os_family == 'RedHat' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y rabbitmq-server libselinux-python

    - name: install RabbitMQ on Ubuntu OS
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - rabbitmq-server


    - name: open 5672 port
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5672 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5672 -j ACCEPT

    - name: open 5673 port
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5673 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5673 -j ACCEPT

    - name: open 15672 port
      shell: iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 15672 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 15672 -j ACCEPT

    - name: enable RabbitMQ
      service: name=rabbitmq-server state=started enabled=yes

    - name: post-install script
      script: $post_install_script
'''

        pre_script = '''
echo -e "#aliyun base\n[alibase]\nname=CentOS-\$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

echo -e "#163 base\n[163base]\nname=CentOS-\$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo

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
            post_script = '''set -e
rabbitmqctl add_user $username $password
rabbitmqctl set_user_tags $username administrator
rabbitmqctl set_permissions -p / $username ".*" ".*" ".*"
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

class InstallKairosdbCmd(Command):
    PACKAGE_NAME = "kairosdb-1.1.1-1.tar.gz"
    KAIROSDB_EXEC = 'KAIROSDB_EXEC'
    KAIROSDB_CONF = 'KAIROSDB_CONF'
    KAIROSDB_LOG = 'KAIROSDB_LOG'

    def __init__(self):
        super(InstallKairosdbCmd, self).__init__()
        self.name = "install_kairosdb"
        self.description = (
            "install kairosdb"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--file', help='path to the %s' % self.PACKAGE_NAME, required=False)
        parser.add_argument('--listen-address', help='the IP kairosdb listens to, which cannot be 0.0.0.0', required=True)
        parser.add_argument('--cassandra-rpc-address', help='the RPC address of cassandra, which must be in the format of'
                                                            '\nIP:port, for example, 192.168.0.199:9160. If omitted, the'
                                                            '\naddress will be retrieved from local cassandra YAML config,'
                                                            '\nor an error will be raised if the YAML config cannot be found', required=False)
        parser.add_argument('--listen-port', help='the port kairosdb listens to, default to 18080', default=18080, required=False)
        parser.add_argument('--update-zstack-config', action='store_true', default=True, help='update kairosdb config to zstack.properties', required=False)

    def run(self, args):
        if not args.file:
            args.file = os.path.join(ctl.USER_ZSTACK_HOME_DIR, self.PACKAGE_NAME)

        if not os.path.exists(args.file):
            raise CtlError('cannot find %s, you may need to specify the option[--file]' % args.file)

        if not args.file.endswith(self.PACKAGE_NAME):
            raise CtlError('at this version, zstack only supports %s' % self.PACKAGE_NAME)

        shell('su - zstack -c "tar xzf %s -C %s"' % (args.file, ctl.USER_ZSTACK_HOME_DIR))
        kairosdb_dir = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "kairosdb")
        info("successfully installed %s to %s" % (args.file, os.path.join(ctl.USER_ZSTACK_HOME_DIR, kairosdb_dir)))

        if args.listen_address == '0.0.0.0':
            raise CtlError('for your data safety, please do NOT use 0.0.0.0 as the listen address')

        original_conf_path = os.path.join(kairosdb_dir, "conf/kairosdb.properties")
        shell("yes | cp %s %s.bak" % (original_conf_path, original_conf_path))

        all_configs = []
        if ctl.extra_arguments:
            configs = [l.split('=', 1) for l in ctl.extra_arguments]
            for l in configs:
                if len(l) != 2:
                    raise CtlError('invalid config[%s]. The config must be in the format of key=value without spaces around the =' % l)
                all_configs.append(l)

        if args.cassandra_rpc_address and ':' not in args.cassandra_rpc_address:
            raise CtlError('invalid --cassandra-rpc-address[%s]. It must be in the format of IP:port' % args.cassandra_rpc_address)
        elif not args.cassandra_rpc_address:
            cassandra_conf = ctl.get_env(InstallCassandraCmd.CASSANDRA_CONF)
            if not cassandra_conf:
                raise CtlError('cannot find cassandra conf[%s] in %s, have you installed cassandra? or'
                               ' you can use --cassandra-rpc-address to set the address explicitly' % (InstallCassandraCmd.CASSANDRA_CONF, SetEnvironmentVariableCmd.PATH))

            with open(cassandra_conf, 'r') as fd:
                with on_error('cannot YAML load %s, it seems corrupted' % InstallCassandraCmd.CASSANDRA_CONF):
                    c_conf = yaml.load(fd.read())

            addr = c_conf['rpc_address']
            if not addr:
                raise CtlError('rpc_address is not set in %s. Please fix it otherwise kairosdb cannot boot later' % InstallCassandraCmd.CASSANDRA_CONF)

            port = c_conf['rpc_port']
            if not port:
                raise CtlError('rpc_port is not set in %s. Please fix it otherwise kairosdb cannot boot later' % InstallCassandraCmd.CASSANDRA_CONF)

            args.cassandra_rpc_address = '%s:%s' % (addr, port)

        all_configs.extend([
          ('kairosdb.service.datastore', 'org.kairosdb.datastore.cassandra.CassandraModule'),
          ('kairosdb.jetty.address', args.listen_address),
          ('kairosdb.jetty.port', args.listen_port),
          ('kairosdb.datastore.cassandra.host_list', args.cassandra_rpc_address)
        ])
        prop = PropertyFile(original_conf_path)
        prop.write_properties(all_configs)

        if args.update_zstack_config:
            ctl.write_properties([
              ('Kairosdb.ip', args.listen_address),
              ('Kairosdb.port', args.listen_port),
            ])
            info('successfully wrote kairosdb properties to %s' % ctl.properties_file_path)

        ctl.put_envs([
            (self.KAIROSDB_EXEC, os.path.normpath('%s/bin/kairosdb.sh' % kairosdb_dir)),
            (self.KAIROSDB_CONF, original_conf_path),
            (self.KAIROSDB_LOG, os.path.join(kairosdb_dir, 'log')),
        ])

        log_conf = os.path.normpath('%s/conf/logging/logback.xml' % kairosdb_dir)
        shell('''sed -i 's/<root level="DEBUG">/<root level="INFO">/g' %s''' % log_conf)

        info('successfully installed kairosdb, the config file is written to %s' % original_conf_path)


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
        (self.db_hostname, self.db_port, self.db_user, self.db_password) = ctl.get_live_mysql_portal()
        self.file_name = args.file_name
        self.keep_amount = args.keep_amount
        self.backup_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.db_backup_dir = "/var/lib/zstack/mysql-backup/"
        if os.path.exists(self.db_backup_dir) is False:
            os.mkdir(self.db_backup_dir)
        self.db_backup_name = self.db_backup_dir + self.file_name + "-" + self.backup_timestamp
        if self.db_hostname == "localhost" or self.db_hostname == "127.0.0.1":
            if self.db_password is None or self.db_password == "":
                self.db_connect_password = ""
            else:
                self.db_connect_password = "-p" + self.db_password
            self.command = "mysqldump --add-drop-database  --databases -u %s %s -P %s zstack zstack_rest | gzip > %s "\
                           % (self.db_user, self.db_connect_password, self.db_port, self.db_backup_name + ".gz")
            (self.status, self.output) = commands.getstatusoutput(self.command)
            if self.status != 0:
                error(self.output)
        else:
            if self.db_password is None or self.db_password == "":
                self.db_connect_password = ""
            else:
                self.db_connect_password = "-p" + self.db_password
            self.command = "mysqldump --add-drop-database  --databases -u %s %s --host %s -P %s zstack zstack_rest | gzip > %s " \
                           % (self.db_user, self.db_connect_password, self.db_hostname, self.db_port, self.db_backup_name + ".gz")
            (self.status, self.output) = commands.getstatusoutput(self.command)
            if self.status != 0:
                error(self.output)
        print "Backup mysql successful! You can check the file at %s.gz" % self.db_backup_name
        # remove old file
        if len(os.listdir(self.db_backup_dir)) > self.keep_amount:
            self.backup_files_list = [s for s in os.listdir(self.db_backup_dir) if os.path.isfile(os.path.join(self.db_backup_dir, s))]
            self.backup_files_list.sort(key=lambda s: os.path.getmtime(os.path.join(self.db_backup_dir, s)))
            for self.expired_file in self.backup_files_list:
                if self.expired_file not in self.backup_files_list[-self.keep_amount:]:
                    os.remove(self.db_backup_dir + self.expired_file)


class CollectLogCmd(Command):
    zstack_log_dir = "/var/log/zstack"
    host_log_list = ['zstack-sftpbackupstorage.log','zstack.log','zstack-kvmagent.log','ceph-backupstorage.log',
                     'ceph-primarystorage.log', 'zstack-iscsi-filesystem-agent.log']
    mn_log_list = ['deploy.log', 'ha.log', 'zstack-console-proxy.log', 'zstack.log', 'zstack-cli', 'zstack-ui.log',
                   'zstack-dashboard.log']

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

    def get_host_log(self, host_post_info, collect_dir):
        info("Collecting log from host: %s ..." % host_post_info.host)
        tmp_collect_log_dir = "%s/tmp-collect-log/" % CollectLogCmd.zstack_log_dir
        command = "mkdir -p %s " % tmp_collect_log_dir
        run_remote_command(command, host_post_info)
        for log in CollectLogCmd.host_log_list:
            command = "tail -n 10000 %s/%s > %s/%s-collect 2>&1 || true" \
                      % (CollectLogCmd.zstack_log_dir, log, tmp_collect_log_dir, log)
            run_remote_command(command, host_post_info)
        command = "tar zcf %s/collect-log.tar.gz %s" % (CollectLogCmd.zstack_log_dir, tmp_collect_log_dir)
        run_remote_command(command, host_post_info)
        fetch_arg = FetchArg()
        fetch_arg.src =  "%s/collect-log.tar.gz " % CollectLogCmd.zstack_log_dir
        fetch_arg.dest = "%s/%s/" % (collect_dir, host_post_info.host)
        fetch_arg.args = "fail_on_missing=yes flat=yes"
        fetch(fetch_arg, host_post_info)
        command = "rm -rf %s %s/collect-log.tar.gz " % (tmp_collect_log_dir, CollectLogCmd.zstack_log_dir)
        run_remote_command(command, host_post_info)

    def get_management_node_log(self, collect_dir):
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

    def generate_tar_ball(self, collect_dir):
        (status, output) = commands.getstatusoutput("tar zcf collect-log.tar.gz %s" % collect_dir)
        if status != 0:
            error("Generate tarball failed: %s " % output)

    def run(self, args):
        run_command_dir = os.getcwd()
        collect_dir = run_command_dir + "/" + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        if not os.path.exists(collect_dir):
            os.makedirs(collect_dir)
        host_vo = self.get_host_list()
        for host in host_vo:
            host_ip = host['managementIp']
            host_post_info = HostPostInfo()
            host_post_info.host = host_ip
            host_post_info.host_inventory = ctl.zstack_home + "/../../../ansible/hosts"
            host_post_info.private_key = ctl.zstack_home + "/WEB-INF/classes/ansible/rsaKeys/id_rsa"
            host_post_info.post_url = ""
            self.get_host_log(host_post_info, collect_dir)

        self.get_management_node_log(collect_dir)
        self.generate_tar_ball(collect_dir)
        info("The collect log generate at: %s/collect-log.tar.gz" % run_command_dir)


class ChangeIpCmd(Command):
    def __init__(self):
        super(ChangeIpCmd, self).__init__()
        self.name = "change_ip"
        self.description = (
            "update new management ip address to zstack property file, kairosdb and cassandra config file"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--ip', help='The new IP address of management node.'
                                         'This operation will update the new ip address to '
                                         'zstack, kairosdb and cassandra config file' , required=True)
        parser.add_argument('--kairosdb_ip', help='The new IP address of kairosdb, default will use value from --ip', required=False)
        parser.add_argument('--cassandra_rpc_address', help='The new IP address of cassandra_rpc_address, default will use value from --ip', required=False)
        parser.add_argument('--cassandra_listen_address', help='The new IP address of cassandra_listen_address, default will use value from --ip', required=False)
        parser.add_argument('--cloudbus_server_ip', help='The new IP address of CloudBus.serverIp.0, default will use value from --ip', required=False)
        parser.add_argument('--mysql_ip', help='The new IP address of DB.url, default will use value from --ip', required=False)

    def run(self, args):
        if args.ip == '0.0.0.0':
            raise CtlError('for your data safety, please do NOT use 0.0.0.0 as the listen address')
        if args.kairosdb_ip is not None:
            kairosdb_ip = args.kairosdb_ip
        else:
            kairosdb_ip = args.ip
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
        for input_ip in [kairosdb_ip, cassandra_rpc_address, cassandra_listen_address, cloudbus_server_ip, mysql_ip]:
            if not ip_check.match(input_ip):
                info("The ip address you input: %s seems not a valid ip" % input_ip)
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

        # Update kairosdb config file
        kairosdb_conf_file = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "kairosdb/conf/kairosdb.properties")
        if os.path.isfile(kairosdb_conf_file):
            shell("yes | cp %s %s.bak" % (kairosdb_conf_file, kairosdb_conf_file))
            new_kairosdb_config = []
            new_kairosdb_config.extend([
              ('kairosdb.jetty.address', kairosdb_ip),
              ('kairosdb.datastore.cassandra.host_list', kairosdb_ip)
            ])
            prop = PropertyFile(kairosdb_conf_file)
            prop.write_properties(new_kairosdb_config)
            info("Update new ip address %s in %s " % (kairosdb_ip, kairosdb_conf_file))
            ctl.write_properties([
              ('Kairosdb.ip', kairosdb_ip),
            ])
            info("Update kairosdb ip %s in %s " % (kairosdb_ip, zstack_conf_file))
        else:
            info("Didn't find %s, skip update kairosdb ip" % kairosdb_conf_file)


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


class InstallCassandraCmd(Command):
    CASSANDRA_EXEC = 'CASSANDRA_EXEC'
    CASSANDRA_CONF = 'CASSANDRA_CONF'
    CASSANDRA_LOG = 'CASSANDRA_LOG'

    def __init__(self):
        super(InstallCassandraCmd, self).__init__()
        self.name = "install_cassandra"
        self.description = (
            "install cassandra nosql database."
            "\nNOTE: you can pass an extra JSON string that will be converted to the cassandra YAML config. The string must"
            "\nbe quoted by a single quote('), and the content must be the valid JSON format, for example:"
            "\n\nzstack-ctl  install_cassandra --file /tmp/apache-cassandra-2.2.3-bin.tar.gz '{\"rpc_address\":\"192.168.0.199\", \"listen_address\":\"192.168.0.199\"}'"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--file', help='path to the apache-cassandra-2.2.3-bin.tar.gz', required=False)
        parser.add_argument('--user-zstack', help='do all operations with user zstack', default=True, action='store_true', required=False)
        parser.add_argument('--listen-address', help='the IP used for both rpc_address and listen_address.'
                                                     'This option is overridden if rpc_address or listen_address'
                                                     ' is specified in the JSON body', required=False)

    def run(self, args):
        if not args.file:
            args.file = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "apache-cassandra-2.2.3-bin.tar.gz")

        if not os.path.exists(args.file):
            raise CtlError('cannot find %s, you may need to specify the option[--file]' % args.file)

        if not args.file.endswith("apache-cassandra-2.2.3-bin.tar.gz"):
            raise CtlError('at this version, zstack only support apache-cassandra-2.2.3-bin.tar.gz')

        shell('su - zstack -c "tar xzf %s -C %s"' % (args.file, ctl.USER_ZSTACK_HOME_DIR))
        cassandra_dir = os.path.join(ctl.USER_ZSTACK_HOME_DIR, "apache-cassandra-2.2.3")
        info("successfully installed %s to %s" % (args.file, os.path.join(ctl.USER_ZSTACK_HOME_DIR, cassandra_dir)))

        yaml_conf = os.path.join(cassandra_dir, "conf/cassandra.yaml")
        shell('yes | cp %s %s.bak' % (yaml_conf, yaml_conf))

        if ctl.extra_arguments:
            extra = ' '.join(ctl.extra_arguments)
            with on_error("%s is not a valid JSON string" % extra):
                conf = simplejson.loads(extra)
        else:
            conf = {}

        if args.listen_address:
            if 'rpc_address' not in conf:
                conf['rpc_address'] = args.listen_address
            if 'listen_address' not in conf:
                conf['listen_address'] = args.listen_address

        if 'commitlog_directory' not in conf:
            conf['commitlog_directory'] = ['/var/lib/cassandra/commitlog']
        if 'data_file_directories' not in conf:
            conf['data_file_directories'] = ['/var/lib/cassandra/data']
        if 'commitlog_directory' not in conf:
            conf['saved_caches_directory'] = ['/var/lib/cassandra/saved_caches']
        conf['start_rpc'] = True

        if args.user_zstack:
            with use_user_zstack():
                with open(yaml_conf, 'r') as fd:
                    c_conf = yaml.load(fd.read())
        else:
            with open(yaml_conf, 'r') as fd:
                c_conf = yaml.load(fd.read())

        for k, v in conf.items():
            c_conf[k] = v

        listen_address = c_conf['listen_address']
        rpc_address = c_conf['rpc_address']
        if listen_address != rpc_address:
            raise CtlError('listen_address[%s] and rpc_address[%s] do not match' % (listen_address, rpc_address))

        seed_provider = c_conf['seed_provider']
        with on_error("cannot find parameter[seeds] in %s" % yaml_conf):
            # check if the parameter is in the YAML conf
            _ = seed_provider[0]['parameters'][0]['seeds']

        seed_provider[0]['parameters'][0]['seeds'] = listen_address
        info("change parameter['seeds'] to listen_address[%s], otherwise cassandra may fail to get seeds" % listen_address)

        if args.user_zstack:
            with use_user_zstack():
                with open(yaml_conf, 'w') as fd:
                    fd.write(yaml.dump(c_conf, default_flow_style=False))
        else:
            with open(yaml_conf, 'w') as fd:
                fd.write(yaml.dump(c_conf, default_flow_style=False))


        ctl.put_envs([
          (self.CASSANDRA_EXEC, os.path.join(cassandra_dir, 'bin/cassandra')),
          (self.CASSANDRA_CONF, yaml_conf),
          (self.CASSANDRA_LOG, os.path.join(cassandra_dir, 'log')),
        ])
        info('configs are written into %s' % yaml_conf)

        ctl.write_properties([
            ('Cassandra.contactPoints', rpc_address)
        ])

        # fix cassandra a bug of judging Java version
        cassandra_service_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'conf/cassandra-env.sh')
        if not os.path.exists(cassandra_service_file):
            raise Exception('cannot find %s' % cassandra_service_file)

        shell('yes | cp %s %s' % (cassandra_service_file, os.path.join(cassandra_dir, 'conf/cassandra-env.sh')))

        info("set Cassandra.contactPoints = %s in zstack.properties" % rpc_address)

class KairosdbCmd(Command):
    NAME = 'kairosdb'

    def __init__(self):
        super(KairosdbCmd, self).__init__()
        self.name = self.NAME
        self.description = (
            'control kairosdb life cycle'
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--start', help='start kairosdb', action="store_true", required=False)
        parser.add_argument('--stop', help='stop kairosdb', action="store_true", required=False)
        parser.add_argument('--status', help='show kairosdb status', action="store_true", required=False)
        parser.add_argument('--wait-timeout', type=int, help='wait timeout(in seconds) until kairosdb web port is available. This is normally used'
                                                           ' with --start option to make sure cassandra successfully starts.',
                            default=-1, required=False)

    def _status(self, args):
        return find_process_by_cmdline('org.kairosdb.core.Main')

    def start(self, args):
        shell("iptables-save | grep -- '-A INPUT -p tcp -m state --state NEW -m tcp --dport 18080 -j ACCEPT' > /dev/null || iptables -w -I INPUT -p tcp -m state --state NEW -m tcp --dport 18080 -j ACCEPT")

        pid = self._status(args)
        if pid:
            info('kairosdb[PID:%s] is already running' % pid)
            return

        exe = ctl.get_env(InstallKairosdbCmd.KAIROSDB_EXEC)
        if not os.path.exists(exe):
            raise CtlError('cannot find the variable[%s] in %s. Have you installed kairosdb?' %
                           (InstallKairosdbCmd.KAIROSDB_EXEC, SetEnvironmentVariableCmd.PATH))

        shell('bash %s start' % exe)
        info('successfully starts kairosdb')

        if args.wait_timeout < 0:
            return

        info('waiting for kairosdb to listen on web port until %s seconds timeout' % args.wait_timeout)
        conf = ctl.get_env(InstallKairosdbCmd.KAIROSDB_CONF)
        if not conf:
            warn('cannot find the variable[%s] in %s, ignore --wait-timeout' %
                (InstallKairosdbCmd.KAIROSDB_CONF, SetEnvironmentVariableCmd.PATH))
            return

        if not os.path.exists(conf):
            warn('cannot find kairosdb conf at %s, ignore --wait-timeout' % conf)
            return

        prop = PropertyFile(conf)
        port = prop.read_property('kairosdb.jetty.port')
        if not port:
            raise CtlError('kairosdb.jetty.port is not set in %s' % InstallKairosdbCmd.KAIROSDB_CONF)

        timeout = args.wait_timeout
        while args.wait_timeout > 0:
            ret = shell_return('netstat -nap | grep %s > /dev/null' % port)
            if ret == 0:
                info('kairosdb is listening on the web port[%s] now' % port)
                return
            time.sleep(1)
            args.wait_timeout -= 1

        raise CtlError("kairosdb is not listening on the web port[%s] after %s seconds, it may not successfully start,"
                        "please check the log file in %s" % (port, timeout, ctl.get_env(InstallKairosdbCmd.KAIROSDB_LOG)))

    def stop(self, args):
        pid = self._status(args)
        if not pid:
            info('kairosdb is already stopped')
            return

        exe = ctl.get_env(InstallKairosdbCmd.KAIROSDB_EXEC)
        if not os.path.exists(exe):
            shell('kill %s' % pid)
        else:
            shell('bash %s stop' % exe)

        count = 30
        while count > 0:
            pid = self._status(args)
            if not pid:
                info('successfully stopped kairosdb')
                return
            time.sleep(1)
            count -= 1

        info('kairosdb is still running after %s seconds, kill -9 it' % count)
        shell('kill -9 %s' % pid)

    def status(self, args):
        pid = self._status(args)
        if pid:
            info('kairosdb[PID:%s] is running' % pid)
        else:
            info('kairosdb is stopped')

    def run(self, args):
        if args.start:
            self.start(args)
        elif args.stop:
            self.stop(args)
        elif args.status:
            self.status(args)
        else:
            self.status(args)

class DeployCassandraDbCmd(Command):

    def __init__(self):
        super(DeployCassandraDbCmd, self).__init__()
        self.name = "deploy_cassandra_db"
        self.description = "deploy or upgrade Cassandra database"
        ctl.register_command(self)

    def run(self, args):
        exe = ctl.get_env(InstallCassandraCmd.CASSANDRA_EXEC)
        if not exe:
            raise CtlError('cannot find the variable[%s] in %s. Have you installed cassandra?' %
                           (InstallCassandraCmd.CASSANDRA_EXEC, SetEnvironmentVariableCmd.PATH))

        cqlsh = os.path.join(os.path.dirname(exe), 'cqlsh')
        if not os.path.isfile(cqlsh):
            raise CtlError('cannot find the cqlsh at %s, cassandra corrupted!???' % cqlsh)

        cips = ctl.read_property('Cassandra.contactPoints')
        if not cips:
            raise CtlError('cannot find Cassandra IP address in zstack.properties, have you installed Cassandra?'
                           'If you have installed Cassandra, please configure Cassandra.contactPoints in the zstack.properties')

        if isinstance(cips, list):
            cip = cips[0]
        else:
            cip = cips

        cport = ctl.read_property('Cassandra.port')
        if not cport:
            cport = 9042
        else:
            cport = int(cport)

        ret = shell_return('%s %s %s -e "DESC KEYSPACES"' % (cqlsh, cip, cport))
        if ret != 0:
            raise CtlError('Cassandra seems not running, please start it using "zstack-ctl cassandra --start"')

        root_home = os.path.expanduser('~root')
        cassandra_setting_folder = os.path.join(root_home, '.cassandra')
        if not os.path.exists(cassandra_setting_folder):
            shell('mkdir -p %s' % cassandra_setting_folder)

        cqlrc = os.path.join(cassandra_setting_folder, 'cqlshrc')
        if not os.path.exists(cqlrc):
            with open(cqlrc, 'w') as fd:
                fd.write('''[connection]
client_timeout = 1800
''')

        deployer_path = os.path.join(ctl.zstack_home, 'WEB-INF/classes/deploy_cassandra_db.py')
        if not os.path.isfile(deployer_path):
            raise CtlError('cannot find %s, your ZStack setup seems corrupted' % deployer_path)

        schema_folder = os.path.join(ctl.zstack_home, 'WEB-INF/classes/mevoco/cassandra/db/')
        if not os.path.isdir(schema_folder):
            raise CtlError('cannot find %s, you do not have any Cassandra database to deploy' % schema_folder)

        shell_no_pipe('python %s -v --schema-folder %s --cqlsh %s --ip %s --port %s' % (deployer_path, schema_folder,
                                                                                     cqlsh, cip, cport))

class CassandraCmd(Command):
    def __init__(self):
        super(CassandraCmd, self).__init__()
        self.name = "cassandra"
        self.description = (
            "control cassandra's life cycle"
        )
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--start', help='start cassandra', action="store_true", required=False)
        parser.add_argument('--stop', help='stop cassandra', action="store_true", required=False)
        parser.add_argument('--status', help='show cassandra status', action="store_true", required=False)
        parser.add_argument('--wait-timeout', type=int, help='wait timeout(in seconds) until cassandra RPC port is available. This is normally used'
                                           ' with --start option to make sure cassandra successfully starts.',
                            default=-1, required=False)

    def start(self, args):
        shell("iptables-save | grep -- '-A INPUT -p tcp -m state --state NEW -m tcp --dport 9042 -j ACCEPT' > /dev/null || iptables -w -I INPUT -p tcp -m state --state NEW -m tcp --dport 9042 -j ACCEPT")

        pid = self._status(args)
        if pid:
            info('cassandra[PID:%s] is already running' % pid)
            return

        exe = ctl.get_env(InstallCassandraCmd.CASSANDRA_EXEC)
        if not exe:
            raise CtlError('cannot find the variable[%s] in %s. Have you installed cassandra?' %
                           (InstallCassandraCmd.CASSANDRA_EXEC, SetEnvironmentVariableCmd.PATH))

        # cd to the /bin folder to start cassandra, otherwise the command line
        # will be too long to be truncated by the linux /proc/[pid]/cmdline, which
        # leads _status() not working
        shell('cd %s && bash %s' % (os.path.dirname(exe), os.path.basename(exe)))
        info('successfully starts cassandra')

        if args.wait_timeout <= 0:
            return

        info('waiting for cassandra to listen on the RPC port until timeout after %s seconds' % args.wait_timeout)
        conf = ctl.get_env(InstallCassandraCmd.CASSANDRA_CONF)
        if not conf:
            warn('cannot find the variable[%s] in %s, ignore --wait-timeout' %
                (InstallCassandraCmd.CASSANDRA_CONF, SetEnvironmentVariableCmd.PATH))
            return

        if not os.path.exists(conf):
            warn('cannot find cassandra conf at %s, ignore --wait-timeout' % conf)
            return

        timeout = args.wait_timeout
        with open(conf, 'r') as fd:
            m = yaml.load(fd.read())
            ip = m['listen_address']
            port = m['native_transport_port']
            if not ip:
                warn('cannot find parameter[listen_address] in %s, ignore --wait-timeout' % conf)
                return

            if not port:
                warn('cannot find parameter[native_transport_port] in %s, ignore --wait-timeout' % conf)
                return

            cqlsh = os.path.join(os.path.dirname(exe), 'cqlsh')
            while args.wait_timeout > 0:
                ret = shell_return('%s %s %s -e "describe keyspaces" > /dev/null' % (cqlsh, ip, port))
                if ret == 0:
                    info('cassandra is listening on RPC port[%s] now' % port)
                    return

                time.sleep(1)
                args.wait_timeout -= 1

            raise CtlError("cannot execute cassandra shell[%s] after %s seconds, it may not successfully start,"
                           "please check the log file in %s" % (cqlsh, timeout, ctl.get_env(InstallCassandraCmd.CASSANDRA_LOG)))

    def stop(self, args):
        pid = self._status(args)
        if not pid:
            info('cassandra is already stopped')
            return

        shell('kill %s' % pid)

        count = 30
        while count > 0:
            pid = self._status(args)
            if not pid:
                info('successfully stopped cassandra')
                return
            time.sleep(1)
            count -= 1

        info('cassandra is still running after %s seconds, kill -9 it' % count)
        shell('kill -9 %s' % pid)

    def _status(self, args):
        return find_process_by_cmdline('org.apache.cassandra.service.CassandraDaemon')

    def status(self, args):
        pid = self._status(args)
        if not pid:
            info('cassandra is stopped')
        else:
            info('cassandra[PID:%s] is running' % pid)

    def run(self, args):
        if args.start:
            self.start(args)
        elif args.stop:
            self.stop(args)
        elif args.status:
            self.status(args)
        else:
            self.status(args)

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
            args.yum = ctl.read_property('Ansible.var.yum_repo')

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
      shell: yum clean metadata; yum --disablerepo=* --enablerepo={{yum_repo}} --nogpgcheck install -y java-1.7.0-openjdk wget python-devel gcc autoconf tar gzip unzip python-pip openssh-clients sshpass bzip2 ntp ntpdate sudo libselinux-python python-setuptools

    - name: install dependencies on RedHat OS from system repos
      when: ansible_os_family == 'RedHat' and yum_repo == 'false'
      shell: yum clean metadata; yum --nogpgcheck install -y java-1.7.0-openjdk wget python-devel gcc autoconf tar gzip unzip python-pip openssh-clients sshpass bzip2 ntp ntpdate sudo libselinux-python python-setuptools

    - name: install dependencies Debian OS
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}} update_cache=yes
      with_items:
        - openjdk-7-jdk
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
      shell: "cd $pypi_path; pip install --ignore-installed pip*.tar.gz"

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
[ -f /etc/yum.repos.d/epel.repo ] || echo -e "[epel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$$releasever/\$$basearch\nfailovermethod=priority\nenabled=1\ngpgcheck=0\n" > /etc/yum.repos.d/epel.repo

echo -e "#aliyun base\n[alibase]\nname=CentOS-\$$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$$releasever/os/\$$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$$releasever/updates/\$$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$$releasever/extras/\$$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$$releasever/\$$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

echo -e "#163 base\n[163base]\nname=CentOS-\$$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$$releasever/os/\$$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$$releasever/updates/\$$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$$releasever/extras/\$$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$$releasever - \$$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$$releasever/\$$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo

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

        setup_account = '''id -u zstack >/dev/null 2>&1 || (useradd -d $install_path zstack && mkdir -p $install_path && chown -R zstack.zstack $install_path)
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

    def _install_to_local(self):
        install_script = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/install.sh")
        if not os.path.isfile(install_script):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % install_script)

        info('found installation script at %s, start installing ZStack web UI' % install_script)
        shell('bash %s zstack-dashboard' % install_script)

    def run(self, args):
        if not args.host:
            self._install_to_local()
            return

        if not args.yum:
            args.yum = ctl.read_property('Ansible.var.yum_repo')

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
      shell: "cd $pypi_path; pip install --ignore-installed pip*.tar.gz"

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
echo -e "#aliyun base\n[alibase]\nname=CentOS-\$releasever - Base - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[aliupdates]\nname=CentOS-\$releasever - Updates - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliextras]\nname=CentOS-\$releasever - Extras - mirrors.aliyun.com\nfailovermethod=priority\nbaseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[aliepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com\nbaseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-aliyun-yum.repo

echo -e "#163 base\n[163base]\nname=CentOS-\$releasever - Base - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/\ngpgcheck=0\nenabled=0\n \n#released updates \n[163updates]\nname=CentOS-\$releasever - Updates - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/\nenabled=0\ngpgcheck=0\n \n#additional packages that may be useful\n[163extras]\nname=CentOS-\$releasever - Extras - mirrors.163.com\nfailovermethod=priority\nbaseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/\nenabled=0\ngpgcheck=0\n \n[ustcepel]\nname=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc \nbaseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch\nfailovermethod=priority\nenabled=0\ngpgcheck=0\n" > /etc/yum.repos.d/zstack-163-yum.repo
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
        db_url = db_url.replace('{database}', 'zstack')
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
                shell_no_pipe('bash %s migrate -user=%s -password=%s -url=%s -locations=%s' % (flyway_path, db_user, db_password, db_url, schema_path))
            else:
                shell_no_pipe('bash %s migrate -user=%s -url=%s -locations=%s' % (flyway_path, db_user, db_url, schema_path))

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

        pidfile = '/var/run/zstack/zstack-dashboard.pid'
        if os.path.exists(pidfile):
            with open(pidfile, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                check_pid_cmd = ShellCmd('ps -p %s > /dev/null' % pid)
                check_pid_cmd(is_exception=False)
                if check_pid_cmd.return_code == 0:
                    info('%s: [PID:%s]' % (colored('Running', 'green'), pid))
                    return

        pid = find_process_by_cmdline('zstack_dashboard')
        if pid:
            info('%s: [PID: %s]' % (colored('Zombie', 'yellow'), pid))
        else:
            info('%s: [PID: %s]' % (colored('Stopped', 'red'), pid))

class InstallLicenseCmd(Command):
    def __init__(self):
        super(InstallLicenseCmd, self).__init__()
        self.name = "install_license"
        self.description = "install zstack license"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--license', '-l', help="path to the license file", required=True)
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

        license_folder = os.path.join(ctl.USER_ZSTACK_HOME_DIR, 'license')
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

    def _remote_start(self, host, params):
        cmd = '/etc/init.d/zstack-dashboard start --rabbitmq %s' % params
        ssh_run_no_pipe(host, cmd)
        info('successfully start the UI server on the remote host[%s]' % host)

    def _check_status(self):
        if os.path.exists(self.PID_FILE):
            with open(self.PID_FILE, 'r') as fd:
                pid = fd.readline()
                pid = pid.strip(' \t\n\r')
                check_pid_cmd = ShellCmd('ps -p %s > /dev/null' % pid)
                check_pid_cmd(is_exception=False)
                if check_pid_cmd.return_code == 0:
                    info('UI server is still running[PID:%s]' % pid)
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

        if not self._check_status():
            return

        shell('iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 5000 -j ACCEPT" > /dev/null || iptables -I INPUT -p tcp -m tcp --dport 5000 -j ACCEPT')

        scmd = '. %s/bin/activate\nnohup python -c "from zstack_dashboard import web; web.main()" --rabbitmq %s >/var/log/zstack/zstack-dashboard.log 2>&1 </dev/null &' % (virtualenv, param)
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
        info('successfully started UI server on the local host, PID[%s]' % pid)

def main():
    BootstrapCmd()
    DeployDBCmd()
    ShowStatusCmd()
    TailLogCmd()
    StartCmd()
    StopCmd()
    SaveConfigCmd()
    RestoreConfigCmd()
    ConfigureCmd()
    InstallDbCmd()
    InstallRabbitCmd()
    InstallManagementNodeCmd()
    ShowConfiguration()
    SetEnvironmentVariableCmd()
    GetEnvironmentVariableCmd()
    InstallWebUiCmd()
    UpgradeManagementNodeCmd()
    UpgradeDbCmd()
    UpgradeCtlCmd()
    RollbackManagementNodeCmd()
    RollbackDatabaseCmd()
    StartUiCmd()
    StopUiCmd()
    UiStatusCmd()
    InstallCassandraCmd()
    InstallKairosdbCmd()
    CassandraCmd()
    KairosdbCmd()
    StartAllCmd()
    StopAllCmd()
    InstallLicenseCmd()
    UnsetEnvironmentVariableCmd()
    RestartNodeCmd()
    DeployCassandraDbCmd()
    ChangeIpCmd()
    InstallHACmd()
    DumpMysqlCmd()
    CollectLogCmd()

    try:
        ctl.run()
    except CtlError as e:
        if ctl.verbose:
            error_not_exit(traceback.format_exc())
        error(str(e))

if __name__ == '__main__':
    main()
