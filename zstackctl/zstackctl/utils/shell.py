import subprocess


class CtlError(Exception):
    pass
    
class ShellCmd(object):
    def __init__(self, cmd, workdir=None, pipe=True):
        self.cmd = cmd
        if pipe:
            self.process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                                            stderr=subprocess.PIPE, close_fds=True, executable='/bin/bash', cwd=workdir)
        else:
            self.process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            close_fds=True, executable='/bin/bash', cwd=workdir)
            
        self.stdout = None
        self.stderr = None
        self.return_code = None

    def raise_error(self):
        err = []
        err.append('failed to execute shell command: %s' % self.cmd)
        err.append('return code: %s' % self.process.returncode)
        err.append('stdout: %s' % self.stdout)
        err.append('stderr: %s' % self.stderr)
        raise CtlError('\n'.join(err))
        
    def __call__(self, is_exception=True):

        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            self.raise_error()

        self.return_code = self.process.returncode
        return self.stdout
