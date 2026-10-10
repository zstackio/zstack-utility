from __future__ import annotations
import time

from . import bash
from . import shell
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils.report import get_api_id, get_deadline

logger = log.get_logger(__name__)

class TraceableShell(object):
    def __init__(self, id, deadline):
        # type: (str, int) -> None
        self.id = id
        self.deadline = deadline

    def call(self, cmd, exception=True, workdir=None):
        # type: (str, bool, str) -> str
        s = shell.ShellCmd(self.wrap_cmd(cmd), workdir)
        s(False)
        if s.return_code == 0 or not exception:
            return s.stdout
        self.raise_error(s, cmd)


    def run(self, cmd, workdir=None):
        cmd = self.wrap_cmd(cmd)
        s = shell.ShellCmd(cmd, workdir, False)
        s(False)
        return s.return_code

    def check_run(self, cmd, workdir=None):
        s = shell.ShellCmd(self.wrap_cmd(cmd), workdir, False)
        s(False)
        if s.return_code == 0:
            return s.return_code
        self.raise_error(s, cmd)

    def bash_progress_1(self, cmd, func, errorout=True, pipe_fail=False):
        cmd = self.wrap_bash_cmd(cmd)
        return bash.bash_progress_1(cmd, func=func, errorout=errorout, pipe_fail=pipe_fail)

    def bash_roe(self, cmd, errorout=False, ret_code=0, pipe_fail=False):
        cmd = self.wrap_bash_cmd(cmd)
        return bash.bash_roe(cmd, errorout=errorout, ret_code=ret_code, pipe_fail=pipe_fail)

    def bash_errorout(self, cmd, code=0, pipe_fail=False):
        cmd = self.wrap_bash_cmd(cmd)
        _, o, _ = bash.bash_roe(cmd, errorout=True, ret_code=code, pipe_fail=pipe_fail)
        return o

    def wrap_cmd(self, cmd):
        if self.deadline:
            if self.deadline <= int(time.time()):
                raise Exception("deadline[%d] has been exceeded" % self.deadline)
            cmd = "timeout " + str(self.deadline - int(time.time())) + "s " + cmd
        if self.id:
            cmd = _build_id_cmd(self.id) + "; " + cmd
        return cmd

    def wrap_bash_cmd(self, cmd):
        cmd = cmd.replace("'", "'\\''")
        return "bash -c '%s'" % self.wrap_cmd(cmd) if self.id else cmd

    def raise_error(self, s, origin_cmd):
        # type: (shell.ShellCmd, str) -> None
        err = []
        if s.return_code == 124 and self.deadline:
            err.append('execution timeout, exceeded the deadline: %d' % self.deadline)
        s.cmd = origin_cmd
        s.raise_error(err)


def _build_id_cmd(id):
    return "echo %s > /dev/null" % id


def get_shell(task_spec):
    return TraceableShell(get_api_id(task_spec), get_deadline(task_spec))


def cancel_job(task_spec):
    return cancel_job_by_api(task_spec.cancellationApiId)


def cancel_job_by_api(api_id):
    if not api_id:
        raise Exception("missing api_id")

    keywords = _build_id_cmd(api_id)
    pids = linux.get_pids_by_process_fullname(keywords)
    if not pids:
        return False

    logger.debug("it is going to kill process %s to cancel job[api:%s].", pids, api_id)
    for pid in pids:
        linux.kill_all_child_process(pid)
    return True

