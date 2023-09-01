'''

@author: frank
'''

import abc
import functools
import os
import os.path
import imp
import inspect
import threading
import traceback

import log
import ConfigParser

import time

from zstacklib.utils import jsonobject, http
from zstacklib.utils.report import get_api_id, AutoReporter, get_timeout, get_task_stage
from zstacklib.utils import traceable_shell

PLUGIN_CONFIG_SECTION_NAME = 'plugins'

logger = log.get_logger(__name__)

class CancelJobResponse(object):
    def __init__(self):
        self.success = True
        self.error = None

class TaskProgressInfo(object):
    def __init__(self, key, req, rsp):
        self.key = key
        self.rsp = rsp
        self.req = req
        self.agent_pid = os.getpid()
        self.completed = False
        self.current_pid = None
        self.current_process_cmd = None
        self.current_process_name = None
        self.current_process_return_code = None


def completetask(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        err = None
        task_manager = args[0]
        req = args[1]
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err = str(e)
            raise
        finally:
            task_manager.complete_task(req=req, err=err)
    return wrap


class TaskDaemon(object):
    __metaclass__ = abc.ABCMeta

    '''
    A daemon to track a long task, task will be canceled automatically when timeout or canceled by api.
    '''

    def __init__(self, task_spec, task_name, timeout=0):
        self.api_id = get_api_id(task_spec)
        self.task_name = task_name
        self.stage = get_task_stage(task_spec)
        self.timeout = get_timeout(task_spec) if timeout == 0 else timeout
        report_progress = type(self)._get_percent != TaskDaemon._get_percent
        self.progress_reporter = AutoReporter.from_spec(task_spec, task_name, self._get_percent, self._get_detail) if report_progress else None
        self.cancel_thread = threading.Timer(self.timeout, self._timeout_cancel) if self.timeout > 0 else None
        self.closed = False
        self.start_time = None
        self.deadline = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.close()
        except:
            pass

    def start(self):
        if self.api_id:
            TaskManager.add_task(self.api_id, self)

        if self.cancel_thread:
            self.cancel_thread.start()

        if self.progress_reporter:
            self.progress_reporter.start()

        self.start_time = time.time()
        self.deadline = self.start_time + self.timeout
        logger.debug("[task=%s] (name=%s) task started. timeout %d, deadline %d" % (self.api_id, self.task_name, self.timeout, self.deadline))

    def get_remaining_timeout(self):
        now = time.time()
        return self.deadline - now

    def close(self):
        if self.closed:
            return

        if self.api_id:
            TaskManager.remove_task(self.api_id, self)

        if self.progress_reporter:
            self.progress_reporter.close()

        if self.cancel_thread:
            self.cancel_thread.cancel()

        self.closed = True

    def _timeout_cancel(self):
        logger.debug('[task=%s] (name=%s) timeout after %d seconds, cancelling %s.' % (self.api_id, self.task_name, self.timeout, self.task_name))
        self._cancel()

    def cancel(self):
        logger.debug('It is going to cancel %s.' % self.task_name)
        self._cancel()

    @abc.abstractmethod
    def _cancel(self):
        pass

    def _get_percent(self):
        # type: () -> int
        pass

    def _get_detail(self):
        # type: () -> jsonobject
        pass


task_daemons = {}  # type: dict[str, list[TaskDaemon]]
task_operator_lock = threading.RLock()


def cancel_job(cmd, rsp):
    if cmd.times and cmd.interval:
        return _cancel_job(cmd, rsp, cmd.times, cmd.interval)
    else:
        return _cancel_job(cmd, rsp)


def _cancel_job(cmd, rsp, times=1, interval=3):
    for i in range(times):
        process_canceled = traceable_shell.cancel_job(cmd)
        canceled_task_count = TaskManager.cancel_task(cmd.cancellationApiId)
        if process_canceled or canceled_task_count:
            return rsp

        if times > i:
            time.sleep(interval)

    rsp.success = False
    rsp.error = "no matched job to cancel"
    return rsp

class TaskManager(object):
    CANCEL_JOB = "/job/cancel"
    global task_daemons
    global task_operator_lock

    def __init__(self):
        '''
        Constructor
        '''
        self.mapper_lock = threading.RLock()
        self.longjob_progress_mapper = {}

    # TODO(MJ): use task daemon instead
    def load_task(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if cmd.identificationCode in self.longjob_progress_mapper.keys():
            return self.longjob_progress_mapper[cmd.identificationCode]
        return None

    # todo : load task when agent restart
    def load_and_save_task(self, req, rsp, validate_task_result_existing, args):
        assert validate_task_result_existing, "you must validate task result has not been clean"
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if not cmd.identificationCode:
            return None
        with self.mapper_lock:
            if validate_task_result_existing(args) and cmd.identificationCode in self.longjob_progress_mapper.keys():
                return self.longjob_progress_mapper[cmd.identificationCode]
            else:
                self.longjob_progress_mapper[cmd.identificationCode] = TaskProgressInfo(req=req, rsp=rsp, key=cmd.identificationCode)
                return None

    def complete_task(self, req, err=None):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if not cmd.identificationCode:
            return

        assert self.longjob_progress_mapper[cmd.identificationCode], "you must save task before complete it."
        task_info = self.longjob_progress_mapper[cmd.identificationCode]

        with self.mapper_lock:
            if err:
                task_info.rsp.success = False
                task_info.rsp.error = err

            task_info.completed = True
        # threading.Timer(300, self.longjob_progress_mapper.pop, args=[cmd.identificationCode]).start()

    def wait_task_complete(self, task_info, timeout=259200):
        interval = 60
        key = task_info.key
        assert self.longjob_progress_mapper[key].completed is not None, "last task must be existing"

        def do_wait():
            waited_time = 0
            while not self.longjob_progress_mapper[key].completed:
                time.sleep(interval)
                waited_time += interval
                if timeout < waited_time:
                    return None

            return self.longjob_progress_mapper[key]

        completed_task = do_wait()
        if completed_task:
            return completed_task.rsp
        else:
            rsp = task_info.rsp
            rsp.success = False
            rsp.error = "timeout to wait other task"
            return rsp

    @staticmethod
    def add_task(api_id, task):
        with task_operator_lock:
            if api_id in task_daemons:
                task_daemons[api_id].append(task)
            else:
                task_daemons[api_id] = [task]

    @staticmethod
    def remove_task(api_id, task):
        with task_operator_lock:
            if api_id in task_daemons:
                tasks = task_daemons[api_id]
                if task in tasks:
                    tasks.remove(task)
                if len(tasks) == 0:
                    task_daemons.pop(api_id)

    @staticmethod
    def cancel_task(api_id):
        with task_operator_lock:
            to_cancel_tasks = task_daemons.pop(api_id, [])

        for task in to_cancel_tasks:
            task.cancel()

        return len(to_cancel_tasks)

class Plugin(TaskManager):
    __metaclass__  = abc.ABCMeta

    def __init__(self):
        super(Plugin, self).__init__()
        self.config = None

    def configure(self, config=None):
        if not config: config = {}
        self.config = config

    @abc.abstractmethod
    def start(self):
        pass

    @abc.abstractmethod
    def stop(self):
        pass

class PluginRegistry(object):
    '''
    classdocs
    '''

    def _parse_plugins(self, mobj):
        members = inspect.getmembers(mobj)
        for (name, member) in members:
            if inspect.isclass(member) and issubclass(member, Plugin):
                logger.debug('Adding plugin[%s] to PluginRegistry' % name)
                name = member.__name__
                self.plugins[name] = member()

    def _load_module(self, mpath, mname=None):
        module_name = inspect.getmodulename(mpath) if not mname else mname
        search_path = [os.path.dirname(mpath)] if os.path.isfile(mpath) else [mpath]
        logger.debug('Loading module[name:%s, path:%s]' % (module_name, search_path))
        base_module_name = module_name.split('.')[-1]
        (mfile, mpname, mdesc) = imp.find_module(base_module_name, search_path)
        try:
            mobj = imp.load_module(module_name, mfile, mpname, mdesc)
            self._parse_plugins(mobj)
        finally:
            mfile.close()

    def _scan_folder(self):
        for root, dirs, files in os.walk(self.plugin_folder):
            for f in files:
                if f.endswith('.py'): self._load_module(os.path.join(root, f))

    def _parse_config(self):
        config = ConfigParser.SafeConfigParser()
        config.read(self.plugin_config)
        for (module_name, path) in config.items(PLUGIN_CONFIG_SECTION_NAME):
            if config.has_option('DEFAULT', module_name): continue
            self._load_module(os.path.abspath(path), module_name)

    def configure_plugins(self, config={}):
        for p in self.plugins.values():
            p.configure(config)

    def start_plugins(self):
        for p in self.plugins.values():
            p.start()

    def stop_plugins(self):
        for p in self.plugins.values():
            p.stop()

    def get_plugin(self, name):
        return self.plugins[name]

    def get_plugins(self):
        return self.plugins.values()

    def __init__(self, path):
        '''
        Constructor
        '''
        path = os.path.abspath(path)
        if os.path.isdir(path):
            self.plugin_folder = path
            self.use_config = False
        elif os.path.isfile(path):
            self.plugin_config = path
            self.use_config = True
        else:
            raise Exception("the constructor parameter's absolute path[%s] must be either a file or a directory" % path)

        self.plugins = {}
        if not self.use_config:
            logger.debug('Loading plugins from folder[%s]' % self.plugin_folder)
            self._scan_folder()
        else:
            logger.debug('Loading plugins from configuration file[%s]' % self.plugin_config)
            self._parse_config()
