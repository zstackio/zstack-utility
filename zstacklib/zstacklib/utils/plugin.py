'''

@author: frank
'''

import abc
import os
import os.path
import imp
import inspect
import log
import ConfigParser

PLUGIN_CONFIG_SECTION_NAME = 'plugins'

logger = log.get_logger(__name__)

class Plugin(object):
    __metaclass__  = abc.ABCMeta
    
    def __init__(self):
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
        