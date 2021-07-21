'''

@author: frank
'''
import subprocess
from zstacklib.utils import log
from zstacklib.utils import lock


@lock.lock("subprocess.popen")
def get_process(cmd, shell=None, workdir=None, pipe=None, executable=None):
    if pipe:
        return subprocess.Popen(cmd, shell=shell, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                close_fds=True, executable=executable, cwd=workdir)
    else:
        return subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                close_fds=True, executable=executable, cwd=workdir)


class ShellError(Exception):
    '''shell error'''
    
class ShellCmd(object):
    '''
    classdocs
    '''
    stdout = None  # type: str

    def __init__(self, cmd, workdir=None, pipe=True):
        '''
        Constructor
        '''
        self.cmd = cmd
        self.process = get_process(cmd, True, workdir, pipe, "/bin/bash")

        self.stdout = None
        self.stderr = None
        self.return_code = None

    def raise_error(self):
        err = []
        err.append('failed to execute shell command: %s' % self.cmd.split(' ', 1)[0])
        err.append('return code: %s' % self.process.returncode)
        err.append('stdout: %s' % self.stdout)
        err.append('stderr: %s' % self.stderr)
        raise ShellError('\n'.join(err))
        
    def __call__(self, is_exception=True, logcmd=True):
        if logcmd:
            log.get_logger(__name__).debug(self.cmd)
            
        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            self.raise_error()

        self.return_code = self.process.returncode
        return self.stdout

def call(cmd, exception=True, workdir=None):
    # type: (str, bool, bool) -> str
    return ShellCmd(cmd, workdir)(exception)

def run(cmd, workdir=None):
    s = ShellCmd(cmd, workdir, False)
    s(False)
    return s.return_code

def check_run(cmd, workdir=None):
    s = ShellCmd(cmd, workdir, False)
    s(True)
    return s.return_code
