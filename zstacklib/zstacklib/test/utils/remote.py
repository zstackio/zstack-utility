import os
import tempfile

import jinja2
import typing
from fabric import Connection

import env
from zstacklib.utils import bash, defer
from zstacklib.utils import log

logger = log.get_logger(__name__)


class SSHError(Exception):
    def __init__(self, ip, cmd, ret, stdout, stderr):
        self.ip = ip
        self.cmd = cmd
        self.ret_code = ret
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return 'SSH command[%s] failed on machine[%s], ret_code=%s, stderr=%s, stdout=%s' % (self.cmd, self.ip,
                                                                                             self.ret_code, self.stderr,
                                                                                             self.stdout)


@defer.protect
def ssh_run(ip, cmd, user='root', port=22, pri_key_text=None, print_to_screen=False, ret_code=0, err_out=False):
    # type: (str, str, str, int, str, bool, typing.Union[int, list[int]], bool) -> (int, str, str)

    """
    return ret_code, stdout, stderr
    """

    fd, filename = tempfile.mkstemp()
    os.write(fd, pri_key_text if pri_key_text is not None else env.SSH_PRIVATE_KEY)
    os.close(fd)

    defer.defer(lambda: os.remove(filename))

    logger.debug('[SSH Start %s@%s:%s] %s' % (user, ip, port, cmd))

    with Connection(ip, user=user, port=port, connect_kwargs={'key_filename': filename}) as conn:
        hide = 'both' if not print_to_screen else None
        logger.debug("Command is: ", cmd, " hide flag is:", hide)
        res = conn.run(cmd, hide=hide)
        logger.debug('[SSH End %s@%s:%s] %s, result: [ret_code=%s, stdout=%s, stderr=%s]' % (
            user, ip, port, cmd, res.exited, res.stdout, res.stderr))
        if err_out:
            if isinstance(ret_code, int):
                if res.exited != ret_code:
                    raise SSHError(ip=ip, cmd=cmd, ret=res.exited, stderr=res.stderr, stdout=res.stdout)
            elif isinstance(ret_code, list):
                if res.exited not in ret_code:
                    raise SSHError(ip=ip, cmd=cmd, ret=res.exited, stderr=res.stderr, stdout=res.stdout)

        return res.exited, res.stdout, res.stderr


def ssh_call(ip, cmd, user='root', port=22, pri_key_text=None, print_to_screen=False, ret_code=0):
    # type: (str, str, str, int, str, bool, typing.Union[int, list[int]]) -> str

    """
    return stdout, raise exception if return code not equal to @ret_code
    """

    _, stdout, _ = ssh_run(ip, cmd, user, port, pri_key_text, print_to_screen, ret_code, err_out=True)
    return stdout


@defer.protect
def rsync(ip, src, dst, user='root', pri_key_text=None, delete=True, excludes=None):
    # type: (str, str, str, str, str, bool, list[str]) -> None
    fd, filename = tempfile.mkstemp()
    os.write(fd, pri_key_text if pri_key_text is not None else env.SSH_PRIVATE_KEY)
    os.close(fd)
    with open(filename) as fd:
        print(fd.read())
    print("*" * 12)
    defer.defer(lambda: os.remove(filename))

    cmds = ['rsync -avz']
    if excludes is not None:
        for ex in excludes:
            cmds.append('--exclude "%s"' % ex)

    cmds.append('-e "ssh -i %s -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"' % filename)
    if delete:
        cmds.append('--delete')

    cmds.append('--progress %s' % src)
    cmds.append('%s@%s:%s' % (user, ip, dst))

    bash.bash_errorout(' '.join(cmds))


class SetupRemoteMachine(object):
    VENV_TAR_NAME = 'setup_venv.tar.gz'
    VENV_DIR = os.path.join('/root', 'setup_venv')
    VENV_ACTIVATE = os.path.join(VENV_DIR, 'bin/activate')

    def __init__(self, remote_ip, pkg_name, entrypoint_name):
        self.remote_ip = remote_ip
        self.entrypoint_name = entrypoint_name
        self.pkg_name = pkg_name
        self.src_venv_tar_path = None

    def _generate_venv_tar(self):
        tdir = tempfile.mkdtemp()
        tar_path = os.path.join(tdir, self.VENV_TAR_NAME)
        bash.call_with_screen_output('venv-pack -o %s' % tar_path)
        self.src_venv_tar_path = tar_path

    def _copy_venv_to_remote(self):
        dst_path = os.path.join('/root', self.VENV_TAR_NAME)
        rsync(self.remote_ip, self.src_venv_tar_path, dst_path)
        ssh_call(self.remote_ip, 'mkdir -p %s && tar xzf %s -C %s' % (self.VENV_DIR, dst_path, self.VENV_DIR),
                 print_to_screen=True)

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

        # if install_sh is None:
        #     raise Exception('cannot find install.sh for the case: %s' % env.CASE_PATH)

        # bash.call_with_screen_output('bash %s' % install_sh)

    def _collect_ztest_env_vars(self):
        env_vars = {}
        for k, v in os.environ.iteritems():
            if k.startswith('ZTEST_'):
                env_vars[k] = v

        return env_vars

    @defer.protect
    def _execute(self):
        script_tmpt = """
import os
        
env_vars = {{env_vars}}

for k, v in env_vars.iteritems():
    os.environ[k] = v
    
from {{pkg}} import {{entry_point}}

{{entry_point}}()
"""
        script = jinja2.Template(script_tmpt).render({
            'env_vars': str(self._collect_ztest_env_vars()),
            'pkg': self.pkg_name,
            'entry_point': self.entrypoint_name
        })

        fd, filename = tempfile.mkstemp()
        os.write(fd, script)
        os.close(fd)
        defer.defer(lambda: os.remove(filename))

        rsync(self.remote_ip, filename, '/root/setup_env.py')

        ssh_call(self.remote_ip, print_to_screen=True, cmd='python /root/setup_env.py ')

    @defer.protect
    def setup(self):
        self._install_self()
        # self._generate_venv_tar()
        # self._copy_venv_to_remote()
        self._execute()

        defer.defer(lambda: bash.call_with_screen_output('rm -rf %s' % os.path.dirname(self.src_venv_tar_path)))


def setup_remote_machine(remote_ip, pkg_name, entrypoint_name):
    # type: (str, str, str) -> None

    SetupRemoteMachine(remote_ip=remote_ip, pkg_name=pkg_name, entrypoint_name=entrypoint_name).setup()
