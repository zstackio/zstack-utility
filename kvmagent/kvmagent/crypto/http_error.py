import os.path
import subprocess
import traceback

from zstacklib.utils import log


logger = log.get_logger(__name__)

_TOOL_ACTIONS = {
    'qemu-img': ('info', 'map', 'create', 'convert', 'rebase', 'commit', 'resize', 'check'),
    'qemu-io': (),
    'qemu-storage-daemon': (),
    'rbd': ('info', 'du', 'mv', 'rm'),
    'cryptsetup': ('luksFormat',),
    'zstcli': (),
}


class CryptoCommandError(subprocess.CalledProcessError):
    @classmethod
    def from_error(cls, error):
        tool, action = _tool_action(error.cmd)
        command = [tool] if action == 'unknown' else [tool, action]
        return cls(error.returncode, command)

    def __str__(self):
        status = ('signal %s' % -self.returncode if self.returncode < 0
                  else 'exit code %s' % self.returncode)
        return '%s failed (%s)' % (' '.join(self.cmd), status)


def run_checked(command, **kwargs):
    try:
        subprocess.run(command, check=True, stderr=subprocess.DEVNULL, **kwargs)
    except subprocess.CalledProcessError as error:
        raise CryptoCommandError.from_error(error) from None


def check_output(command):
    try:
        return subprocess.check_output(command, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as error:
        raise CryptoCommandError.from_error(error) from None


def response_error(stage, error, safe_error_types):
    if isinstance(error, CryptoCommandError):
        return '%s: %s' % (stage, error)
    if isinstance(error, subprocess.CalledProcessError):
        return '%s: %s' % (stage, CryptoCommandError.from_error(error))
    if isinstance(error, safe_error_types):
        return str(error)
    return '%s: %s' % (stage, type(error).__name__)


def _tool_action(command):
    if not isinstance(command, (list, tuple)) or not command or not isinstance(command[0], str):
        return 'unknown', 'unknown'
    tool = os.path.basename(command[0])
    if tool not in _TOOL_ACTIONS:
        return 'unknown', 'unknown'
    action_index = 1
    if tool == 'rbd':
        while action_index < len(command) and command[action_index] in ('--conf', '--id'):
            action_index += 2
    if tool == 'cryptsetup' and len(command) > 1 and command[1] == '-q':
        action_index += 1
    action = command[action_index] if action_index < len(command) else None
    return tool, action if action in _TOOL_ACTIONS[tool] else 'unknown'


def log_failure(operation, stage, error):
    # Exception text and subprocess arguments can contain secret channel paths.
    stack = '\n'.join('%s:%s in %s' % (frame.f_code.co_filename, lineno, frame.f_code.co_name)
                      for frame, lineno in traceback.walk_tb(error.__traceback__))
    failed_process = isinstance(error, subprocess.CalledProcessError)
    returncode = error.returncode if failed_process else None
    tool, action = _tool_action(error.cmd) if failed_process else ('unknown', 'unknown')
    logger.error('crypto operation=%s stage=%s exception=%s returncode=%s tool=%s action=%s\n%s',
                 operation, stage, type(error).__name__, returncode, tool, action, stack)
