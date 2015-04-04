'''

@author: frank
'''

from kvmagent import kvmagent
from zstacklib.utils import log

logger = log.get_logger(__name__)

class HelloPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    def start(self):
        logger.debug('hello, I am in, my workspace is %s' % self.config[kvmagent.KvmRESTService.WORKSPACE])
    
    def stop(self):
        logger.debug('hello, I am out')
        
        