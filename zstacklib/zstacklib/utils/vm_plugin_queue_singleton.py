import Queue
from zstacklib.utils import singleton

@singleton.singleton
class VmPluginQueueSingleton(object):
    queue = Queue.Queue()
