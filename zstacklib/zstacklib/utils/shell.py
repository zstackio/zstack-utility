'''

@author: frank
'''
import subprocess
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

class ShellError(Exception):
    '''shell error'''
    
class ShellCmd(object):
    '''
    classdocs
    '''
    
    def __init__(self, cmd, workdir=None, pipe=True):
        '''
        Constructor
        '''
        self.cmd = cmd
        if pipe:
            self.process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, executable='/bin/sh', cwd=workdir)
        else:
            self.process = subprocess.Popen(cmd, shell=True, executable='/bin/sh', cwd=workdir)
            
        self.stdout = None
        self.stderr = None
        self.return_code = None
        
    def __call__(self, is_exception=True):
        if logcmd:
            logger.debug(self.cmd)
            
        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            err = []
            err.append('failed to execute shell command: %s' % self.cmd)
            err.append('return code: %s' % self.process.returncode)
            err.append('stdout: %s' % self.stdout)
            err.append('stderr: %s' % self.stderr)
            raise ShellError('\n'.join(err))
            
        self.return_code = self.process.returncode
        return self.stdout

def call(cmd, exception=True, workdir=None):
    return ShellCmd(cmd, workdir)(exception)

def run(cmd, workdir=None):
    s = ShellCmd(cmd, workdir)
    s(False)
    return s.return_code
