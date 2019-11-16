import Queue


class Singleton(object):
    _instance = None

    def __new__(cls, *args, **kw):
        if not cls._instance:
            cls._instance = super(Singleton, cls).__new__(cls, *args)
        return cls._instance


class VmPluginQueueSingleton(Singleton):
    queue = Queue.Queue()
