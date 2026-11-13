import os.path
import subprocess
import traceback

from zstacklib.utils import log


logger = log.get_logger(__name__)

_TOOL_ACTIONS = {
    'qemu-img': ('info', 'map', 'create', 'convert', 'rebase', 'commit', 'resize'),
    'qemu-io': (),
    'qemu-storage-daemon': (),
    'rbd': ('info', 'du', 'mv', 'rm'),
    'cryptsetup': (),
    'zstcli': (),
}


def run_checked(command, **kwargs):
    subprocess.run(command, check=True, stderr=subprocess.PIPE, **kwargs)


def subprocess_failure_reason(stderr):
    if isinstance(stderr, bytes):
        stderr = stderr.decode('utf-8', errors='replace')
    output = (stderr or '').lower()
    for reason, markers in (
            ('luks_secret_required', ("key-secret' is required for cipher",)),
            ('luks_unlock_failed', ('cannot unlock any keyslot', 'invalid password')),
            ('nbd_connection_failed', ('failed to connect', 'connection refused')),
            ('qcow2_open_failed', ('not in qcow2 format', 'qcow2 header')),
            ('no_space', ('no space left on device',)),
            ('io_error', ('input/output error',)),
            ('permission_denied', ('permission denied', 'operation not permitted')),
            ('resource_busy', ('device or resource busy', 'image is busy', 'image is still being used')),
            ('config_error', ('error reading configuration file', 'error parsing config file',
                              'did not load config file', 'unable to parse config')),
            ('unsupported_option', ('unrecognized option', 'unknown option', 'invalid option', 'unsupported option')),
            ('file_not_found', ('no such file or directory',))):
        if any(marker in output for marker in markers):
            return reason
    return 'unrecognized_stderr' if output.strip() else 'no_stderr'


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
    action = command[action_index] if action_index < len(command) else None
    return tool, action if action in _TOOL_ACTIONS[tool] else 'unknown'


def log_failure(operation, stage, error):
    # Exception text and subprocess arguments can contain secret channel paths.
    stack = '\n'.join('%s:%s in %s' % (frame.f_code.co_filename, lineno, frame.f_code.co_name)
                      for frame, lineno in traceback.walk_tb(error.__traceback__))
    failed_process = isinstance(error, subprocess.CalledProcessError)
    returncode = error.returncode if failed_process else None
    tool, action = _tool_action(error.cmd) if failed_process else ('unknown', 'unknown')
    reason = subprocess_failure_reason(error.stderr) if failed_process else 'unknown'
    logger.error('crypto operation=%s stage=%s exception=%s returncode=%s reason=%s tool=%s action=%s\n%s',
                 operation, stage, type(error).__name__, returncode, reason, tool, action, stack)
