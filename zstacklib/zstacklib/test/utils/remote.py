import os
import tempfile
import paramiko
import jinja2
import env
from zstacklib.utils import log

logger = log.get_logger(__name__)


class SetupRemoteMachine(object):
    VENV_DIR = os.path.join('/root', 'setup_venv')

    def __init__(self, remote_ip, pkg_name='', entrypoint_name='', port=22, username="root", password="password"):
        self.port = port
        self.username = username
        self.password = password
        self.remote_ip = remote_ip
        self.entrypoint_name = entrypoint_name
        self.pkg_name = pkg_name
        self.src_venv_tar_path = None
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(hostname=self.remote_ip, port=self.port, username=self.username, password=self.password)

    def put_file(self, local_path, remote_path):
        sftp = self.client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()

    def close(self):
        self.client.close()

    def execute_command(self, command):
        stdin, stdout, stderr = self.client.exec_command(command)
        return stdout, stderr

    def _copy_venv_to_remote(self):
        dst_path = os.path.join('/root', self.VENV_TAR_NAME)
        self.put_file(self.src_venv_tar_path, dst_path)
        self.execute_command('mkdir -p %s && tar xzf %s -C %s' % (self.VENV_DIR, dst_path, self.VENV_DIR))

    def _install_self(self):
        dirs = env.CASE_PATH.split(os.sep)

        paths = []
        for d in dirs:
            paths.append(d)
            ps = paths[:]
            ps.append('install.sh')
            p = os.sep.join(ps)
            if os.path.isfile(p):
                break

    def _collect_ztest_env_vars(self):
        env_vars = {}
        for k, v in os.environ.iteritems():
            if k.startswith('ZTEST_'):
                env_vars[k] = v

        return env_vars

    def _execute(self):
        script_tmpt = """
import os

from {{pkg}} import {{entry_point}}

{{entry_point}}()
"""
        script = jinja2.Template(script_tmpt).render({
            # 'env_vars': str(self._collect_ztest_env_vars()),
            'pkg': self.pkg_name,
            'entry_point': self.entrypoint_name
        })

        fd, filename = tempfile.mkstemp()
        os.write(fd, script)
        os.close(fd)

        self.put_file(filename, '/root/setup_env.py')

        stdout, stderr = self.execute_command('python /root/setup_env.py ')
        return stdout, stderr

    def setup(self):
        # self._install_self()
        # self._generate_venv_tar()
        # self._copy_venv_to_remote()
        stdout, stderr = self._execute()
        return stdout, stderr


def setup_remote_machine(remote_ip, pkg_name, entrypoint_name):
    s = SetupRemoteMachine(remote_ip=remote_ip, pkg_name=pkg_name, entrypoint_name=entrypoint_name)
    s.setup()
    s.close()


def ssh_run(ip, cmd, user='root', port=22, password='password', pri_key_text=None, print_to_screen=False, ret_code=0,
            err_out=False):
    # type: (str, str, str, int, str, bool, typing.Union[int, list[int]], bool) -> (int, str, str)

    """
    return ret_code, stdout, stderr
    """
    s = SetupRemoteMachine(remote_ip=ip, port=port, password=password, username=user)
    out, err = s.execute_command(cmd)
    exited = out.channel.recv_exit_status()
    return exited, out, err
