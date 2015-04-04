'''

@author: yyk
'''

import os
import sys
import imp
import log
import imp
import linux

PLUGIN_CONFIG_SECTION_NAME = 'plugins'

logger = log.get_logger(__name__)

class ComponentLoader(object):
    ''' Component Loader will load a given python file name as an module.
        The default search parent path depth is 2. It means loader will only 
        try to find the component in its parent folder and all sub folders in
        current path.

        If parent path depth is -1, the parent path will be up to '/' root 
        folder.

        The search sequence is current folder, all sub folders, +1 folder, 
        +2 folder, ... , '/' folder. 

        The first matched file will be loaded and return. '''
    def __init__(self, module_name, current_path, parent_path_depth=2):
        self.module_name = module_name
        self.module_file_name = '%s.py' % module_name 
        self.current_path = current_path
        if isinstance(parent_path_depth, int):
            self.parent_path_depth = parent_path_depth
        else:
            raise Exception('Parameter error: parent_path_depth should be a number')

        self.module_file_path = None
        self.module = None

    def load(self):
        '''
        import and return the module.
        '''
        self.module_file_path = linux.find_file(self.module_file_name, self.current_path, self.parent_path_depth)

        if not self.module_file_path:
            raise Exception('Did not find module file: %s in module path: %s with parent path depth: %s' % (self.module_file_name, self.module_file_path, self.parent_path_depth))
        sys.path.append(os.path.dirname(self.module_file_path))
        self.module = imp.load_source(self.module_name, self.module_file_path)
        return self.module

