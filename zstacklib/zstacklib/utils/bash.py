import subprocess
import functools
import json
from jinja2 import Template
from zstacklib.utils import log
import inspect
import time
import re
from zstacklib.utils import shell
from progress_report import WatchThread
from zstacklib.utils.rollback import rollback, rollbackable
from zstacklib.utils import linux
import os

logger = log.get_logger(__name__)

class BashError(Exception):
    '''bash error'''

def __collect_locals_on_stack():
    frames = []
    frame = inspect.currentframe()
    while frame:
        frames.insert(0, frame)
        frame = frame.f_back

    ctx = {}
    for f in frames:
        ctx.update(f.f_locals)

    return ctx


def bash_eval(raw_str, ctx=None):
    if not ctx:
        ctx = __collect_locals_on_stack()

    while True:
        unresolved = re.findall('{{(.+?)}}', raw_str)
        if not unresolved:
            break

        for u in unresolved:
            if u not in ctx:
                raise Exception('unresolved symbol {{%s}}' % u)

        tmpt = Template(raw_str)
        raw_str = tmpt.render(ctx)

    return raw_str

# @return: return code, stdout, stderr
def bash_roe(cmd, errorout=False, ret_code = 0, pipe_fail=False):
    ctx = __collect_locals_on_stack()

    cmd = bash_eval(cmd, ctx)
    p = subprocess.Popen('/bin/bash', stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    if pipe_fail:
        cmd = 'set -o pipefail; %s' % cmd
    o, e = p.communicate(cmd)
    r = p.returncode

    __BASH_DEBUG_INFO__ = ctx.get('__BASH_DEBUG_INFO__')
    if __BASH_DEBUG_INFO__ is not None:
        __BASH_DEBUG_INFO__.append({
            'cmd': cmd,
            'return_code': p.returncode,
            'stdout': o,
            'stderr': e
        })

    if r != ret_code and errorout:
        raise BashError('failed to execute bash[%s], return code: %s, stdout: %s, stderr: %s' % (cmd, r, o, e))

    return r, o, e

# @return: return code, stdout
def bash_ro(cmd, pipe_fail=False):
    ret, o, _ = bash_roe(cmd, pipe_fail=pipe_fail)
    return ret, o

# @return: stdout
def bash_o(cmd, pipe_fail=False):
    _, o, _ = bash_roe(cmd, pipe_fail=pipe_fail)
    return o

# @return: return code
def bash_r(cmd, pipe_fail=False):
    ret, _, _ = bash_roe(cmd, pipe_fail=pipe_fail)
    return ret

# @return: stdout
def bash_errorout(cmd, code=0, pipe_fail=False):
    _, o, _ = bash_roe(cmd, errorout=True, ret_code=code, pipe_fail=pipe_fail)
    return o

def bash_progress(cmd, progress):
    ctx = __collect_locals_on_stack()
    cmd = bash_eval(cmd, ctx)
    logger.debug(cmd)
    fpwrite = None

    if not progress.pfile:
        progress_report = shell.call('mktemp /tmp/tmp-XXXXXX').strip()
        fpwrite = open(progress_report, 'w')
        p = subprocess.Popen('/bin/bash', stdout=fpwrite, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        progress.pfile = progress_report
    else:
        progress_report = progress.pfile
        p = subprocess.Popen('/bin/bash', stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    watch_thread = WatchThread(p, progress)

    try:
        watch_thread.start()
        o, e = p.communicate(cmd)
        r = p.returncode
    except:
        linux.get_exception_stacktrace()
    finally:
        watch_thread.stop()
        if fpwrite:
            fpwrite.close()
        os.remove(progress_report)
        return r, o, e



    __BASH_DEBUG_INFO__ = ctx.get('__BASH_DEBUG_INFO__')
    if __BASH_DEBUG_INFO__ is not None:
        __BASH_DEBUG_INFO__.append({
            'cmd': cmd,
            'return_code': p.returncode,
            'stderr': e
        })

    if r != 0:
        raise BashError('failed to execute bash[%s], return code: %s, stderr: %s' % (cmd, r, e))
    return r, o, e

def in_bash(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        __BASH_DEBUG_INFO__ = []

        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            end_time = time.time()
            logger.debug('BASH COMMAND DETAILS IN %s [cost %s ms]: %s' % (func.__name__, (end_time - start_time) * 1000, json.dumps(__BASH_DEBUG_INFO__)))
            del __BASH_DEBUG_INFO__

    return wrap
