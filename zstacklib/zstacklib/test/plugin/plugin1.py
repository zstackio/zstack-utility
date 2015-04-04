'''

@author: frank
'''
from ...utils import plugin

class Plugin1(plugin.Plugin):
    '''
    classdocs
    '''


    def __init__(self):
        '''
        Constructor
        '''
        self.start_called = False
        self.stop_called = False
    
    def start(self):
        self.start_called = True
    
    def stop(self):
        self.stop_called = True
        