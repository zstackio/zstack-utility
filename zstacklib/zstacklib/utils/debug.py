__author__ = 'frank'

import random
import time

import linux
import traceback
import signal
import sys
import threading
import operator
import gc
import objgraph
import lock
import inspect
import datetime
import os
import functools
import psutil
from types import *
try:
    from types import InstanceType
except ImportError:
    # Python 3.x compatibility
    InstanceType = None

try:
    iteritems = dict.iteritems
except AttributeError:
    # Python 3.x compatibility
    iteritems = dict.items

from zstacklib.utils import log
from zstacklib.utils import thread

logger = log.get_logger(__name__)
CONFIG = None
SEND_COMMAND_URL = None
HOST_UUID = None

class DumpReporter(object):
    def __init__(self):
        self._lock = threading.Lock()
        self.dump_thread_count = 0
        self.report_thread = None

    @linux.retry(times=5, sleep_time=random.uniform(1, 2))
    def _send_to_mn(self):
        if not CONFIG or not SEND_COMMAND_URL or not CONFIG.get(SEND_COMMAND_URL):
            logger.warn("Cannot find SEND_COMMAND_URL, unable to send '/host/kvmagent/status' to management node ")
            return
        import http
        data = {"status": "busy" if self.dump_thread_count > 0 else "available",
                "hostUuid": CONFIG.get(HOST_UUID),
                "memoryUsage": long(psutil.Process().memory_info().rss)}
        http.json_dump_post(CONFIG.get(SEND_COMMAND_URL), data, {'commandpath': '/host/kvmagent/status'})

    def start_dump(self):
        def _report():
            while True:
                self._send_to_mn()
                with self._lock:
                    if self.dump_thread_count <= 0:
                        self.report_thread = None
                        break
                time.sleep(60)

        with self._lock:
            self.dump_thread_count += 1
            if self.report_thread is None:
                self.report_thread = thread.ThreadFacade.run_in_thread(_report)
            logger.debug("dump thread count inc: %s" % self.dump_thread_count)


    def end_dump(self):
        with self._lock:
            self.dump_thread_count -= 1
            logger.debug("dump thread count dec: %s" % self.dump_thread_count)


dump_reporter = DumpReporter()
def dump_track(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            dump_reporter.start_dump()
            return func(*args, **kwargs)
        finally:
            dump_reporter.end_dump()

    return wrap


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


def track_memory_growth():
    try:
        thread.ThreadFacade.run_in_thread(dump_threads)
        thread.ThreadFacade.run_in_thread(track_objects)
    except Exception as e:
        logger.warn("get error when track memory info %s" % e.message)


@dump_track
def dump_threads():
    logger.debug('dumping threads')
    output = []
    threads = 0
    current_frames = sys._current_frames()

    for th in threading.enumerate():
        threads += 1
        thread_info = []
        thread_info.append("Thread: {}, ID: {}, Alive: {}, Daemon: {}".format(th.name, th.ident, th.is_alive(), th.daemon))

        if th.ident in current_frames:
            try:
                stack = traceback.format_stack(current_frames[th.ident])
                thread_info.append("".join(stack))

                thread_locals = current_frames[th.ident].f_locals
                simplified_locals = {k: repr(v)[:100] for k, v in thread_locals.items()}
                thread_info.append("Locals: {}".format(simplified_locals))
            except Exception as e:
                logger.debug("Error dumping thread {}: {}".format(th.name, str(e)))

        output.append("\n".join(thread_info))

    full_output = "There are {} threads:\n{}".format(threads, "\n\n".join(output))
    logger.debug(full_output)
    return


class BufferWriter:
    def __init__(self, fd, buffer_size):
        self.fd = fd
        self.buffer_size = buffer_size
        self.buffer = bytearray()

    def write(self, context):
        self.buffer.extend(context)
        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        if self.buffer:
            self.fd.write(self.buffer)
            self.fd.flush()
            self.buffer = bytearray()

    def close(self):
        self.flush()

def by_types(typenames, objects=None, obj_num=3, shortname=False):
    if objects is None:
        objects = gc.get_objects()
    try:
        type_f = _short_typename if shortname else _long_typename
        type_objs = {}
        for obj in objects:
            t = type_f(obj)
            if t not in typenames:
                continue
            if t not in type_objs:
                type_objs[t] = []
            type_objs[t].append(obj)
            if len(type_objs[t]) >= obj_num:
                typenames.remove(t)
                if len(typenames) == 0:
                    break
        return type_objs
    finally:
        del objects  # clear cyclic references to frame


def show_backrefs(obj_types):
    if not obj_types:
        return
    # find back ref
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S').replace(" ", "-")
    ref_dir = "/var/log/zstack/obj_ref"
    if not os.path.exists(ref_dir):
        os.mkdir(ref_dir)

    def edge_filter(target):
        return not inspect.isfunction(target)

    obj_dict = by_types(obj_types, obj_num=3)
    for t, objs in obj_dict.items()[:50]:
        try:
            f = "%s/%s-%s.dot" % (ref_dir, now, t)
            with open(f, 'wb') as fd:
                writer = BufferWriter(fd, 1048576)
                objgraph.show_backrefs(objs, max_depth=5, filter=edge_filter, output=writer)
                writer.close()
            time.sleep(random.uniform(5, 10))
        except Exception as e:
            logger.debug("get an error on parsing objects back references: %s" % str(e))
    del obj_dict

def log_objs_statistics(total_num_stats, total_size_stats, num_deltas, size_deltas, all_total_size, all_total_num):
    res = []
    total_size_list = sorted(total_size_stats.items(), key=operator.itemgetter(1), reverse=True)
    width = max(len(name) for name, size in total_size_list)
    res.append("Total size = %s bytes. Total objects num = %s." % (all_total_size, all_total_num))
    res.append('%5s %-*s %12s %5s %12s %5s %12s %5s %12s %5s' % ("Index", width, "Kind", "Size", "%", "Growth", "%", "Count", "%", "Growth", "%"))
    idx = 0
    for name, total_size in total_size_list:
        total_num = total_num_stats.get(name, 0)
        size_delta = size_deltas.get(name, 0)
        num_delta = num_deltas.get(name, 0)
        res.append('%5d %-*s %12d %5d %+12d %+5d %12d %5d %+12d %+5d' % (idx, width, name, total_size, float(total_size)*100/all_total_size,
                                                                         size_delta, float(size_delta)*100/all_total_size, total_num, float(total_num)*100/all_total_num,
                                                                         num_delta, float(num_delta)*100/all_total_num))
        idx += 1

    logger.debug('\n'.join(res))


def type_stats(objects=None, shortname=False):
    if objects is None:
        objects = gc.get_objects()
    try:
        if shortname:
            typename = _short_typename
        else:
            typename = _long_typename
        num_stats = {}
        size_stats = {}
        total_num = len(objects)
        total_size = 0
        for o in objects:
            n = typename(o)
            if "__builtin__" in n:
                continue
            num_stats[n] = num_stats.get(n, 0) + 1
            obj_size = sys.getsizeof(o)
            size_stats[n] = size_stats.get(n, 0) + obj_size
            total_size += obj_size

        return num_stats, size_stats, total_num, total_size
    finally:
        del objects  # clear cyclic references to frame


@lock.file_lock("/var/run/zstack/mem_track.lock")
@dump_track
def track_objects(times=5, interval=300):
    """
    1. Traverse the objects tracked by gc and count the number and size of objects of the same type.
    2. Analyze object references and generate graph files
    :param times: number of tracking
    :param interval: interval of tracking
    :return:
    """
    gc.collect()
    logger.debug("start to track objects...")

    old_num_stats, old_size_stats, total_num, total_size = type_stats()
    log_objs_statistics(old_num_stats, old_size_stats, {}, {}, total_size, total_num)
    increasing_continuously_types = set(old_size_stats.keys())

    cnt = 1
    while cnt <= times:
        logger.debug("tracking the growth of objects:(%d/%d)" % (cnt, times))
        cnt += 1
        time.sleep(interval)

        cur_num_stats, cur_size_stats, total_num, total_size = type_stats()

        num_deltas = {}
        size_deltas = {}
        for name, size in iteritems(cur_size_stats):
            old_size = old_size_stats.get(name, 0)
            if size > old_size:
                size_deltas[name] = size - old_size
                num_deltas[name] = cur_num_stats[name] - old_num_stats.get(name, 0)
            old_num_stats[name] = cur_num_stats[name]
            old_size_stats[name] = cur_size_stats[name]

        log_objs_statistics(cur_num_stats, cur_size_stats, num_deltas, size_deltas, total_size, total_num)
        increasing_continuously_types = increasing_continuously_types & set(size_deltas.keys())

    logger.debug(increasing_continuously_types)
    show_backrefs(increasing_continuously_types)
    logger.debug("complete tracking objects")
    return


@dump_track
def dump_objects():
    old_num_stats, old_size_stats, total_num, total_size = type_stats()
    log_objs_statistics(old_num_stats, old_size_stats, {}, {}, total_size, total_num)


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
