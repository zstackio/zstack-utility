import bash
import shell
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class TraceableShell(object):
    def __init__(self, id):
        self.id = id

    def call(self, cmd, exception=True, workdir=None):
        cmd = self.wrap_cmd(cmd)
        # type: (str, bool, bool) -> str
        return shell.ShellCmd(cmd, workdir)(exception)

    def run(self, cmd, workdir=None):
        cmd = self.wrap_cmd(cmd)
        s = shell.ShellCmd(cmd, workdir, False)
        s(False)
        return s.return_code

    def check_run(self, cmd, workdir=None):
        cmd = self.wrap_cmd(cmd)
        s = shell.ShellCmd(cmd, workdir, False)
        s(True)
        return s.return_code

    def bash_progress_1(self, cmd, func, errorout=True):
        cmd = self.wrap_cmd(cmd)
        return bash.bash_progress_1(cmd, func, errorout)

    def wrap_cmd(self, cmd):
        return _build_id_cmd(self.id) + "; " + cmd


def _build_id_cmd(id):
    return "echo %s > /dev/null" % id


def get_shell(cmd):
    if cmd.threadContext and cmd.threadContext.api:
        return TraceableShell(cmd.threadContext.api)
    else:
        return shell


def cancel_job(cmd):
    keywords = _build_id_cmd(cmd.cancellationApiId)
    pids = linux.get_pids_by_process_fullname(keywords)
    if not pids:
        return False

    logger.debug("it is going to kill process %s to cancel job[api:%s].", pids, cmd.cancellationApiId)
    for pid in pids:
        linux.kill_process(pid)
    return True


