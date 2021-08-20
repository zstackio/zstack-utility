__author__ = 'frank'

import traceback
import signal
import sys
import threading
import operator
import gc
import beeprint
try:
    from types import InstanceType
except ImportError:
    # Python 3.x compatibility
    InstanceType = None

from zstacklib.utils import log
from zstacklib.utils import thread

logger = log.get_logger(__name__)


def dump(sig, frame):
    message = "Signal received : dump Traceback:\n"
    message += ''.join(traceback.format_stack(frame))
    print message


def install_runtime_tracedumper():
    signal.signal(signal.SIGUSR2, dump_debug_info)


def dump_stack():
    message = "Stack Traceback:\n"
    message += ''.join(traceback.format_stack())
    return message


def dump_debug_info(signum, fram, *argv):
    try:
        thread.ThreadFacade.run_in_thread(dump_threads)
        thread.ThreadFacade.run_in_thread(dump_objects)
    except Exception as e:
        logger.warn("get error when dump debug info %s" % e.message)


def dump_threads():
    logger.debug('dumping threads')
    output = ""
    threads = 0
    for th in threading.enumerate():
        threads += 1
        output = "%s\n%s\n" % (output, th)
        try:
            for stack in traceback.format_stack(sys._current_frames()[th.ident]):
                output = "%s%s" % (output, stack)
            thread_locals = sys._current_frames()[th.ident].f_locals
            output = "%s\n%s\n\n" % (output, beeprint.pp(thread_locals, output=False))

        except Exception as e:
            logger.warn("get error when dump thread %s: %s" % (th, e.message))
    output = "there are %s threads: \n%s" % (threads, output)
    logger.debug(output)
    return


def dump_objects():
    logger.debug('dumping objects')
    stats = sorted(
        typestats().items(), key=operator.itemgetter(1), reverse=True)
    logger.debug(stats)
    return


def typestats(objects=None, shortnames=False, filter=None):
    if objects is None:
        objects = gc.get_objects()
    try:
        if shortnames:
            typename = _short_typename
        else:
            typename = _long_typename
        stats = {}
        for o in objects:
            if filter and not filter(o):
                continue
            n = typename(o)
            stats[n] = stats.get(n, 0) + 1
        return stats
    finally:
        del objects  # clear cyclic references to frame


def _short_typename(obj):
    return _get_obj_type(obj).__name__


def _long_typename(obj):
    objtype = _get_obj_type(obj)
    name = objtype.__name__
    module = getattr(objtype, '__module__', None)
    if module:
        return '%s.%s' % (module, name)
    else:
        return name


def _get_obj_type(obj):
    objtype = type(obj)
    if type(obj) == InstanceType:
        objtype = obj.__class__
    return objtype
