import os
import sys
import subprocess

verbose = False

class CtlError(Exception):
    pass

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
        if verbose:
            print('executing shell command[%s]:' % self.cmd)

        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            self.raise_error()

        self.return_code = self.process.returncode

        if verbose:
            print(simplejson.dumps({
                "shell" : self.cmd,
                "return_code" : self.return_code,
                "stdout": self.stdout,
                "stderr": self.stderr
            }, ensure_ascii=True, sort_keys=True, indent=4))

        return self.stdout

def shell(cmd, is_exception=True):
    return ShellCmd(cmd)(is_exception)

def parse_positional_arguments(cmd):
    pa_key = 'positional arguments:'
    output = shell('%s -h' % cmd).split('\n')
    next_line = False
    for line in output:
        if next_line:
            positional_arguments_line = line.strip()
            break
        if line.startswith(pa_key):
            next_line = True

    if positional_arguments_line:
        positional_arguments_line = positional_arguments_line[1:-1]
        return positional_arguments_line.split(',')

def parse_sub_arguments(cmd, positional_arguments):
    sa_key = 'optional arguments:'
    arg_key = '  -'

    output = shell('%s %s -h' % (cmd, positional_arguments)).split('\n')
    next_line = False
    sub_args = []
    for line in output:
        if next_line:
            if line.startswith(arg_key):
                line_list = line.strip().split(',')
                for item in line_list:
                    item = item.strip()
                    if item.startswith('-'):
                        sub_args.append(item.split()[0])

        if line.startswith(sa_key):
            next_line = True

    return sub_args

def parse_arguements():
    positional_arguments = parse_positional_arguments('zstack-ctl')
    string = """
_zstack-ctl() 
{
    local cur prev opts base
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
"""
    string = string + '\n    opts="%s"' % ' '.join(positional_arguments)

    string = string + '\n    case "${prev}" in'

    for positional_argument in positional_arguments:
        sub_args = parse_sub_arguments('zstack-ctl', positional_argument)
        string = string + """
        %s)
            local sub_args="%s"
            COMPREPLY=( $(compgen -W "${sub_args}" -- ${cur}) )
            return 0
            ;;
""" % (positional_argument, ' '.join(sub_args))

    string = string + """
        -f)
            _filedir
            return 0
            ;;
        --license)
            _filedir
            return 0
            ;;
        --file)
            _filedir
            return 0
            ;;

        *)
            ;;
    esac

    COMPREPLY=($(compgen -W "${opts}" -- ${cur}))  
    return 0
}
complete -F _zstack-ctl zstack-ctl
"""

    if os.path.exists('/etc/bash_completion.d/'):
        open('/etc/bash_completion.d/zstack-ctl-bash-completion.sh', 'w').write(string)

if __name__ == '__main__':
    parse_arguements()
