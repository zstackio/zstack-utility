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

class CtlError(Exception):
    pass

def warn(msg):
    sys.stdout.write('WARNING: %s\n' % msg)

def error(msg):
    sys.stdout.write(colored('ERROR: %s\n' % msg, 'red'))
    sys.exit(1)

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
        if exc_type == CtlError:
            return

        if exc_val:
            error('%s\n%s' % (str(exc_val), self.msg))

def on_error(msg):
    return ExceptionWrapper(msg)

def error_if_tool_is_missing(tool):
    if shell_return('which %s' % tool) != 0:
        raise CtlError('cannot find tool "%s", please install it and re-run' % tool)

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
    def __init__(self, path):
        self.path = path
        if not os.path.isfile(self.path):
            raise CtlError('cannot find zstack.properties at %s' % self.path)

        with on_error("errors on reading %s" % self.path):
            self.config = ConfigObj(self.path, write_empty_values=True)

    def read_all_properties(self):
        with on_error("errors on reading %s" % self.path):
            return self.config.items()

    def read_property(self, key):
        with on_error("errors on reading %s" % self.path):
            return self.config.get(key, None)

    def write_property(self, key, value):
        with on_error("errors on writing (%s=%s) to %s" % (key, value, self.path)):
            with use_user_zstack():
                self.config[key] = value
                self.config.write()

    def write_properties(self, lst):
        with on_error("errors on writing list of key-value%s to %s" % (lst, self.path)):
            with use_user_zstack():
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

    def run(self):
        if os.getuid() != 0:
            raise CtlError('zstack-ctl needs root privilege, please run with sudo')

        def locate_zstack_home():
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
            if not os.path.isfile(self.properties_file_path):
                warn('cannot find %s, your ZStack installation may have crashed' % self.properties_file_path)

        def install_parsers():
            subparsers = self.main_parser.add_subparsers(help="All sub-commands", dest="sub_command_name")
            for cmd in self.command_list:
                cmd.install_argparse_arguments(subparsers.add_parser(cmd.name, help=cmd.description + '\n\n'))


        install_parsers()

        args, self.extra_arguments = self.main_parser.parse_known_args(sys.argv[1:])
        self.verbose = args.verbose

        cmd = self.commands[args.sub_command_name]

        if cmd.need_zstack_home():
            locate_zstack_home()

        if cmd.need_zstack_user():
            check_zstack_user()

        cmd(args)

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
        return prop.read_property(key)

    def write_properties(self, properties):
        prop = PropertyFile(self.properties_file_path)
        with on_error('property must be in format of "key=value", no space before and after "="'):
            prop.write_properties(properties)

    def write_property(self, key, value):
        prop = PropertyFile(self.properties_file_path)
        prop.write_property(key, value)

ctl = Ctl()

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
        return ShellCmd('''curl --noproxy --connect-timeout 1 --retry %s --retry-delay 0 --retry-max-time %s --max-time %s -H "Content-Type: application/json" -d '{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://localhost:8080/zstack/api''' % (timeout, timeout, timeout))
    elif what_tool == USE_WGET:
        return ShellCmd('''wget --no-proxy -O- --tries=%s --timeout=1  --header=Content-Type:application/json --post-data='{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://localhost:8080/zstack/api''' % timeout)
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

class ShowStatusCmd(Command):
    def __init__(self):
        super(ShowStatusCmd, self).__init__()
        self.name = 'status'
        self.description = 'show ZStack status and information.'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--remote', help='SSH URL, for example, root@192.168.0.10, to show the management node status on a remote machine')

    def _stop_remote(self, args):
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  %s "/usr/bin/zstack-ctl status"' % args.remote)

    def run(self, args):
        if args.remote:
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

        check_zstack_status()

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
        if cmd.return_code == 0 and not args.drop:
            if args.keep_db:
                info('detected existing zstack database and keep it; if you want to drop it, please append parameter --drop, instead of --keep-db')
            else:
                raise CtlError('detected existing zstack database; if you are sure to drop it, please append parameter --drop')
        else:
            if not args.root_password:
                args.root_password = "''"
            if not args.zstack_password:
                args.zstack_password = "''"

            cmd = ShellCmd('sh %s root %s %s %s %s' % (script_path, args.root_password, args.host, args.port, args.zstack_password))
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
                ("DbFacadeDataSource.user", "zstack"),
                ("DbFacadeDataSource.password", args.zstack_password),
                ("DbFacadeDataSource.jdbcUrl", 'jdbc:mysql://%s:%s/zstack' % (args.host, args.port)),
                ("RESTApiDataSource.jdbcUrl",'jdbc:mysql://%s:%s/zstack_rest' % (args.host, args.port))
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
        parser.add_argument('--remote', help='SSH URL, for example, root@192.168.0.10, to set properties in zstack.properties on the remote machine')
        parser.add_argument('--duplicate-to-remote', help='SSH URL, for example, root@192.168.0.10, to copy zstack.properties on this machine to the remote machine')
        parser.add_argument('--use-file', help='path to a file that will be used to as zstack.properties')

    def _configure_remote_node(self, args):
        shell_no_pipe('ssh %s "/usr/bin/zstack-ctl configure %s"' % (args.remote, ' '.join(ctl.extra_arguments)))

    def _duplicate_remote_node(self, args):
        tmp_file_name = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        tmp_file_name = os.path.join('/tmp/', tmp_file_name)
        with open(ctl.properties_file_path, 'r') as fd:
            txt = fd.read()
            cmd = '''ssh -T %s << EOF
cat <<EOT >> %s
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

        if args.remote:
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

class StartCmd(Command):
    START_SCRIPT = '../../bin/startup.sh'

    def __init__(self):
        super(StartCmd, self).__init__()
        self.name = 'start_node'
        self.description = 'start the ZStack management node on this machine'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--remote', help='SSH URL, for example, root@192.168.0.10, to start the management node on a remote machine')

    def _start_remote(self, args):
        info('it may take a while because zstack-ctl will wait for management node ready to serve API')
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  %s "/usr/bin/zstack-ctl start_node"' % args.remote)

    def run(self, args):
        if args.remote:
            self._start_remote(args)
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

        def check_msyql():
            with on_error('check "DbFacadeDataSource.jdbcUrl" in %s' % ctl.properties_file_path):
                db_url = ctl.read_property('DbFacadeDataSource.jdbcUrl')
                host_string = db_url.replace('jdbc:mysql://', '').replace('/zstack', '')
                host, port = host_string.split(':')

            if not check_ip_port(host, port):
                raise CtlError('unable to connect to %s, please check if the MySQL is running and the firewall rules' % host_string)

            with on_error('check "DbFacadeDataSource.user" in %s' % ctl.properties_file_path):
                username = ctl.read_property("DbFacadeDataSource.user")

            with on_error('check "DbFacadeDataSource.password" in %s' % ctl.properties_file_path):
                password = ctl.read_property("DbFacadeDataSource.password")

            with on_error('unable to connect to MySQL'):
                shell('mysql --host=%s --user=%s --password=%s --port=%s -e "select 1"' % (host, username, password, port))

        def check_rabbitmq():
            RABBIT_PORT = 5672

            with on_error('unable to get RabbitMQ server IPs from %s, please check CloudBus.serverIp.0'):
                ips = ctl.read_property_list('CloudBus.serverIp.')
                if not ips:
                    raise CtlError('no RabbitMQ IPs defined in %s, please specify it use CloudBus.serverIp.0=the_ip' % ctl.properties_file_path)

                for key, ip in ips:
                    if not check_ip_port(ip, RABBIT_PORT):
                        raise CtlError('cannot connect to RabbitMQ server[ip:%s, port:%s] defined by item[%s] in %s' % (ip, RABBIT_PORT, key, ctl.properties_file_path))

        def start_mgmt_node():
            shell('sudo -u zstack sh %s -DappName=zstack' % os.path.join(ctl.zstack_home, self.START_SCRIPT))
            info("successfully started Tomcat container; now it's waiting for the management node ready for serving APIs, which may take a few seconds")

        def wait_mgmt_node_start():
            timeout = 120
            @loop_until_timeout(timeout)
            def check():
                cmd = create_check_mgmt_node_command(1)
                cmd(False)
                return cmd.return_code == 0

            if not check():
                log_path = os.path.join(ctl.zstack_home, "../../logs/management-server.log")
                raise CtlError('no management-node-ready message received within %s seconds, please check error in log file %s' % (timeout, log_path))

        user = getpass.getuser()
        if user != 'root':
            raise CtlError('please use sudo or root user')

        check_msyql()
        check_rabbitmq()
        start_mgmt_node()
        wait_mgmt_node_start()

        info('successfully started management node')

class StopCmd(Command):
    STOP_SCRIPT = "../../bin/shutdown.sh"

    def __init__(self):
        super(StopCmd, self).__init__()
        self.name = 'stop_node'
        self.description = 'stop the ZStack management node on this machine'
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--remote', help='SSH URL, for example, root@192.168.0.10, to stop the management node on a remote machine')

    def _stop_remote(self, args):
        shell_no_pipe('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s "/usr/bin/zstack-ctl stop_node"' % args.remote)

    def run(self, args):
        if args.remote:
            self._stop_remote(args)
            return

        pid = get_management_node_pid()
        if not pid:
            info('the management node has been stopped')
            return

        timeout = 30
        @loop_until_timeout(timeout)
        def wait_stop():
            return get_management_node_pid() is None

        shell('sh %s' % os.path.join(ctl.zstack_home, self.STOP_SCRIPT))
        if wait_stop():
            info('successfully stopped management node')
            return

        pid = get_management_node_pid()
        if pid:
            info('unable to stop management node within %s seconds, kill it' % timeout)
            with on_error('unable to kill -9 %s' % pid):
                shell('kill -9 %s' % pid)

class SaveConfigCmd(Command):
    DEFAULT_PATH = '~/.zstack/'

    def __init__(self):
        super(SaveConfigCmd, self).__init__()
        self.name = 'save_config'
        self.description = 'save ZStack configuration from ZSTACK_HOME to specified file'
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
        properties_file_path = os.path.join(path, 'zstack.properties')
        if not os.path.exists(properties_file_path):
            raise CtlError('cannot find zstack.properties at %s' % properties_file_path)

        shell('yes | cp %s %s' % (properties_file_path, ctl.properties_file_path))
        info('successfully restored zstack.properties from %s to %s' % (properties_file_path, ctl.properties_file_path))

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
        parser.add_argument('--root-password', help="new password of MySQL root user; an empty password is used if this option is omitted")
        parser.add_argument('--login-password', help="login password of MySQL root user; an empty password is used if this option is omitted."
                            "\n[NOTE] this option is needed only when the machine has MySQL previously installed and removed; the old MySQL root password will be left in the system,"
                            "you need to input it in order to reset root password for the new installed MySQL.", default=None)
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def run(self, args):
        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      root_password: $root_password
      login_password: $login_password

  tasks:
    - name: pre-install script
      script: $pre_install_script

    - name: install MySQL for RedHat 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      yum: pkg={{item}}
      with_items:
        - mysql
        - mysql-server
      register: install_result

    - name: install MySQL for RedHat 7
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7'
      yum: pkg={{item}}
      with_items:
        - mariadb
        - mariadb-server
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
      yum: pkg={{item}} state=absent
      with_items:
        - mysql
        - mysql-server

    - name: rollback MySQL installation on RedHat 7
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7' and change_root_result.rc != 0 and install_result.changed == True
      yum: pkg={{item}} state=absent
      with_items:
        - mariadb
        - mariadb-server

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

        if not args.root_password:
            args.root_password = '''"''"'''
            grant_access_cmd = '''/usr/bin/mysql -u root -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' IDENTIFIED BY '' WITH GRANT OPTION; FLUSH PRIVILEGES;"'''
        else:
            grant_access_cmd = '''/usr/bin/mysql -u root -p%s -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%%' IDENTIFIED BY '%s' WITH GRANT OPTION; FLUSH PRIVILEGES;"''' % (args.root_password, args.root_password)

        if args.login_password is not None:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root -p{{login_password}} password {{root_password}}'
        else:
            change_root_password_cmd = '/usr/bin/mysqladmin -u root password {{root_password}}'

        pre_install_script = '''
###################
Check DNS hijacking
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
fi

if [ -f /etc/my.cnf ]; then
    # CentOS
    sed -i 's/^bind-address/#bind-address/' /etc/my.cnf
    sed -i 's/^skip-networking/#skip-networking/' /etc/my.cnf
fi
'''
        fd, post_install_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(post_install_script)

        def cleanup_post_install_script():
            os.remove(post_install_script_path)

        self.install_cleanup_routine(cleanup_post_install_script)

        t = string.Template(yaml)
        yaml = t.substitute({
            'host': args.host,
            'change_password_cmd': change_root_password_cmd,
            'root_password': args.root_password,
            'login_password': args.login_password,
            'grant_access_cmd': grant_access_cmd,
            'pre_install_script': pre_install_script_path,
            'post_install_script': post_install_script_path
        })

        ansible(yaml, args.host, args.debug, args.ssh_key)

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

    def run(self, args):
        yaml = '''---
- hosts: $host
  remote_user: root

  tasks:
    - name: pre-install script
      script: $pre_install_script

    - name: install libselinux-python for RedHat OS 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      yum: pkg=libselinux-python

    - name: install EPEL repo
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      copy: src=$epel_repo6
            dest=/etc/yum.repos.d/epel.repo
            owner=root group=root mode=0644

    - name: install RabbitMQ on RedHat OS
      when: ansible_os_family == 'RedHat'
      yum: pkg={{item}}
      with_items:
        - rabbitmq-server

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
'''

        fd, epel6_repo = tempfile.mkstemp()
        os.fdopen(fd, 'w').write('''[epel]
name=Extra Packages for Enterprise Linux 6 - $basearch
#baseurl=http://download.fedoraproject.org/pub/epel/6/$basearch
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=$basearch
failovermethod=priority
enabled=1
gpgcheck=0

[epel-debuginfo]
name=Extra Packages for Enterprise Linux 6 - $basearch - Debug
#baseurl=http://download.fedoraproject.org/pub/epel/6/$basearch/debug
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-debug-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0

[epel-source]
name=Extra Packages for Enterprise Linux 6 - $basearch - Source
#baseurl=http://download.fedoraproject.org/pub/epel/6/SRPMS
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-source-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0
        ''')

        def cleanup_temp_file():
            os.remove(epel6_repo)

        self.install_cleanup_routine(cleanup_temp_file)

        pre_script = '''
###################
Check DNS hijacking
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

        t = string.Template(yaml)
        yaml = t.substitute({
            'host': args.host,
            'epel_repo6': epel6_repo,
            'pre_install_script': pre_script_path
        })

        ansible(yaml, args.host, args.debug, args.ssh_key)

        if not args.no_update:
            ctl.write_property('CloudBus.serverIp.0', args.host)
            info('updated CloudBus.serverIp.0=%s in %s' % (args.host, ctl.properties_file_path))

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
        parser.add_argument('--remote', help='target host IP, for example, 192.168.0.212, to install ZStack management node to a remote machine', required=True)
        parser.add_argument('--install-path', help='the path on remote machine where Apache Tomcat will be installed, which must be an absolute path; [DEFAULT]: /usr/local/zstack', default='/usr/local/zstack')
        parser.add_argument('--source-dir', help='the source folder containing Apache Tomcat package and zstack.war, if omitted, it will default to a path related to $ZSTACK_HOME')
        parser.add_argument('--debug', help="open Ansible debug option", action="store_true", default=False)
        parser.add_argument('--force-reinstall', help="delete existing Apache Tomcat and resinstall ZStack", action="store_true", default=False)
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def run(self, args):
        if not os.path.isabs(args.install_path):
            raise CtlError('%s is not an absolute path' % args.install_path)

        if not args.source_dir:
            args.source_dir = os.path.join(ctl.zstack_home, "../../../")

        if not os.path.isdir(args.source_dir):
            raise CtlError('%s is not an directory' % args.source_dir)

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

        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      root: $install_path

  tasks:
    - name: prepare remote environment
      script: $pre_script

    - name: install libselinux-python for RedHat OS 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      yum: pkg=libselinux-python

    - name: install EPEL repo for RedHat OS 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      copy: src=$epel6_repo
            dest=/etc/yum.repos.d/epel.repo
            owner=root group=root mode=0644

    - name: install dependencies on RedHat OS
      when: ansible_os_family == 'RedHat'
      yum: pkg={{item}}
      with_items:
        - java-1.7.0-openjdk
        - wget
        - python-devel
        - gcc
        - autoconf
        - tar
        - gzip
        - unzip
        - python-pip
        - openssh-clients
        - sshpass
        - mysql

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

    - name: install MySQL client for RedHat 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      yum: pkg={{item}}
      with_items:
        - mysql

    - name: install MySQL client for RedHat 7
      when: ansible_os_family == 'RedHat' and ansible_distribution_version >= '7'
      yum: pkg={{item}}
      with_items:
        - mariadb

    - name: install MySQL client for Ubuntu
      when: ansible_os_family == 'Debian'
      apt: pkg={{item}}
      with_items:
        - mysql-client

    - name: install virtualenv
      pip: name=virtualenv

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

        def cleanup_pre_script():
            os.remove(pre_script_path)

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

eval "sh $$install_script zstack-ctl"
eval "sh $$install_script zstack-cli"

set +e
grep "ZSTACK_HOME" ~/.bashrc > /dev/null
if [ $$? -eq 0 ]; then
   sed -i "s#export ZSTACK_HOME=.*#export ZSTACK_HOME=$$apache_path/webapps/zstack#" ~/.bashrc
else
   echo "export ZSTACK_HOME=$$apache_path/webapps/zstack" >> ~/.bashrc
fi

which ansible-playbook &> /dev/null
if [ $$? -ne 0 ]; then
   pip install ansible==1.7.2
fi
'''
        t = string.Template(post_script)
        post_script = t.substitute({
            'install_path': args.install_path,
            'apache': os.path.join(args.install_path, apache_tomcat_zip_name),
            'zstack': os.path.join(args.install_path, 'zstack.war'),
            'apache_tomcat_zip_name': apache_tomcat_zip_name
        })

        fd, post_script_path = tempfile.mkstemp(suffix='.sh')
        os.fdopen(fd, 'w').write(post_script)

        def cleanup_post_script():
            os.remove(post_script_path)

        self.install_cleanup_routine(cleanup_post_script)

        fd, epel6_repo = tempfile.mkstemp()
        os.fdopen(fd, 'w').write('''[epel]
name=Extra Packages for Enterprise Linux 6 - $basearch
#baseurl=http://download.fedoraproject.org/pub/epel/6/$basearch
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=$basearch
failovermethod=priority
enabled=1
gpgcheck=0

[epel-debuginfo]
name=Extra Packages for Enterprise Linux 6 - $basearch - Debug
#baseurl=http://download.fedoraproject.org/pub/epel/6/$basearch/debug
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-debug-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0

[epel-source]
name=Extra Packages for Enterprise Linux 6 - $basearch - Source
#baseurl=http://download.fedoraproject.org/pub/epel/6/SRPMS
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-source-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0
        ''')

        def cleanup_temp_file():
            os.remove(epel6_repo)

        self.install_cleanup_routine(cleanup_temp_file)

        setup_account = '''id -u zstack >/dev/null 2>&1 || useradd -d $install_path zstack
grep 'zstack' /etc/sudoers >/dev/null || echo 'zstack        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
sed -i '/requiretty$$/d' /etc/sudoers
chown -R zstack.zstack $install_path

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
        yaml = t.substitute({
            'host': args.remote,
            'install_path': args.install_path,
            'apache_path': apache_tomcat,
            'zstack_path': zstack,
            'pre_script': pre_script_path,
            'post_script': post_script_path,
            'properties_file': ctl.properties_file_path,
            'apache_tomcat_zip_name': apache_tomcat_zip_name,
            'epel6_repo': epel6_repo,
            'setup_account': setup_account_path
        })

        ansible(yaml, args.remote, args.debug, args.ssh_key)
        info('successfully installed new management node on machine(%s)' % args.remote)

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
        vars = [l.split('=', 1) for l in ctl.extra_arguments]
        env.write_properties(vars)

class InstallWebUiCmd(Command):

    def __init__(self):
        super(InstallWebUiCmd, self).__init__()
        self.name = "install_ui"
        self.description = "install ZStack web UI"
        ctl.register_command(self)

    def install_argparse_arguments(self, parser):
        parser.add_argument('--host', help='target host IP, for example, 192.168.0.212, to install ZStack web UI; if omitted, it will be installed on local machine')
        parser.add_argument('--ssh-key', help="the path of private key for SSH login $host; if provided, Ansible will use the specified key as private key to SSH login the $host", default=None)

    def _install_to_local(self):
        install_script = os.path.join(ctl.zstack_home, "WEB-INF/classes/tools/install.sh")
        if not os.path.isfile(install_script):
            raise CtlError('cannot find %s, please make sure you have installed ZStack management node' % install_script)

        info('found installation script at %s, start installing ZStack web UI' % install_script)
        shell('sh %s zstack-dashboard' % install_script)

    def run(self, args):
        if not args.host:
            self._install_to_local()
            return

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

        fd, epel6_repo = tempfile.mkstemp()
        os.fdopen(fd, 'w').write('''[epel]
name=Extra Packages for Enterprise Linux 6 - $basearch
#baseurl=http://download.fedoraproject.org/pub/epel/6/$basearch
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-6&arch=$basearch
failovermethod=priority
enabled=1
gpgcheck=0

[epel-debuginfo]
name=Extra Packages for Enterprise Linux 6 - $basearch - Debug
#baseurl=http://download.fedoraproject.org/pub/epel/6/$basearch/debug
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-debug-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0

[epel-source]
name=Extra Packages for Enterprise Linux 6 - $basearch - Source
#baseurl=http://download.fedoraproject.org/pub/epel/6/SRPMS
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-source-6&arch=$basearch
failovermethod=priority
enabled=0
gpgcheck=0
        ''')

        def cleanup_temp_file():
            os.remove(epel6_repo)

        self.install_cleanup_routine(cleanup_temp_file)

        yaml = '''---
- hosts: $host
  remote_user: root

  vars:
      virtualenv_root: /var/lib/zstack/virtualenv/zstack-dashboard

  tasks:
    - name: install EPEL repo for RedHat OS 6
      when: ansible_os_family == 'RedHat' and ansible_distribution_version < '7'
      copy: src=$epel6_repo
            dest=/etc/yum.repos.d/epel.repo
            owner=root group=root mode=0644

    - name: copy zstack-dashboard package
      copy: src=$src dest=$dest

    - name: install Python pip for RedHat OS
      when: ansible_os_family == 'RedHat'
      yum: pkg=python-pip

    - name: install Python pip for Ubuntu
      when: ansible_os_family == 'Debian'
      apt: pkg=python-pip update_cache=yes

    - name: install virtualenv
      pip: name=virtualenv

    - name: create virtualenv directory
      shell: mkdir -p {{virtualenv_root}}

    - name: initialize virtualenv
      shell: "ls {{virtualenv_root}}/bin/activate > /dev/null || virtualenv {{virtualenv_root}}"

    - name: install zstack-dashboard
      pip: name=$dest extra_args="--ignore-installed" virtualenv="{{virtualenv_root}}"
'''

        t = string.Template(yaml)
        yaml = t.substitute({
            "src": ui_binary_path,
            "dest": os.path.join('/tmp', ui_binary),
            "host": args.host,
            "epel6_repo": epel6_repo
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
        shell('id -u zstack 2>/dev/null || useradd -d %s zstack -s /bin/false' % ctl.USER_ZSTACK_HOME_DIR)
        shell("grep 'zstack' /etc/sudoers || echo 'zstack        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers")
        shell('mkdir -p %s && chown zstack:zstack %s' % (ctl.USER_ZSTACK_HOME_DIR, ctl.USER_ZSTACK_HOME_DIR))

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
    InstallWebUiCmd()

    try:
        ctl.run()
    except CtlError as e:
        error(str(e))

if __name__ == '__main__':
    main()

