try:
    import Queue
except ImportError:
    import queue as Queue
from zstacklib.utils import singleton

@singleton.singleton
class VmPluginQueueSingleton(object):
    queue = Queue.Queue()
