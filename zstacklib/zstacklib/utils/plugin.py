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

import log
import ConfigParser

import time
from zstacklib.utils import jsonobject, http

PLUGIN_CONFIG_SECTION_NAME = 'plugins'

logger = log.get_logger(__name__)


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

class TaskManager(object):
    def __init__(self):
        '''
        Constructor
        '''
        self.mapper_lock = threading.RLock()
        self.longjob_progress_mapper = {}
        pass

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
        