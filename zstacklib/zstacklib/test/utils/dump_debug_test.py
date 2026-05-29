from zstacklib.utils import debug
debug.track_objects()

'''sample:
[root@172-26-52-160 ~]# PYTHONPATH=/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages python /var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/test/utils/dump_debug_test.py
2024-12-31 11:46:29,478 140662198007552 DEBUG [zstacklib.utils.debug] dumping threads
2024-12-31 11:46:29,510 140662198007552 DEBUG [zstacklib.utils.debug] There are 3 threads:
Thread: MainThread, ID: 140662444418880
  File "/usr/lib64/python2.7/threading.py", line 1109, in _exitfunc
    t.join()
  File "/usr/lib64/python2.7/threading.py", line 951, in join
    self.__block.wait()
  File "/usr/lib64/python2.7/threading.py", line 339, in wait
    waiter.acquire()

Locals: {'saved_state': 'None', 'waiter': '<thread.lock object at 0x7fee790a2430>', 'self': '<Condition(<thread.lock object at 0x7fee790a2470>, 1)>', 'balancing': 'True', 'timeout': 'None'}

Thread: dump_threads, ID: 140662198007552
  File "/usr/lib64/python2.7/threading.py", line 785, in __bootstrap
    self.__bootstrap_inner()
  File "/usr/lib64/python2.7/threading.py", line 812, in __bootstrap_inner
    self.run()
  File "/usr/lib64/python2.7/threading.py", line 765, in run
    self.__target(*self.__args, **self.__kwargs)
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/thread.py", line 30, in safe_run
    target(*sargs, **skwargs)
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/debug.py", line 74, in dump_threads
    stack = traceback.format_stack(current_frames[th.ident])

Locals: {'current_frames': '{140662189614848: <frame object at 0x7fee785b9050>, 140662198007552: <frame object at 0x7fee70000d70', 'simplified_locals': "{'saved_state': 'None', 'waiter': '<thread.lock object at 0x7fee790a2430>', 'self': '<Condition(<thr", 'threads': '2', 'th': '<Thread(dump_threads, started 140662198007552)>', 'output': '[\'Thread: MainThread, ID: 140662444418880\\n  File "/usr/lib64/python2.7/threading.py", line 1109, in', 'thread_info': '[\'Thread: dump_threads, ID: 140662198007552\', \'  File "/usr/lib64/python2.7/threading.py", line 785,', 'stack': '[\'  File "/usr/lib64/python2.7/threading.py", line 785, in __bootstrap\\n    self.__bootstrap_inner()', 'thread_locals': "{'saved_state': None, 'waiter': <thread.lock object at 0x7fee790a2430>, 'self': <Condition(<thread.l"}

Thread: track_objects, ID: 140662189614848
  File "/usr/lib64/python2.7/threading.py", line 785, in __bootstrap
    self.__bootstrap_inner()
  File "/usr/lib64/python2.7/threading.py", line 812, in __bootstrap_inner
    self.run()
  File "/usr/lib64/python2.7/threading.py", line 765, in run
    self.__target(*self.__args, **self.__kwargs)
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/thread.py", line 30, in safe_run
    target(*sargs, **skwargs)
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/lock.py", line 85, in inner
    retval = f(*args, **kwargs)
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/debug.py", line 192, in track_objects
    old_num_stats, old_size_stats, total_num, total_size = type_stats()
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/debug.py", line 168, in type_stats
    n = typename(o)
  File "/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/zstacklib/utils/debug.py", line 232, in _long_typename
    return '%s.%s' % (module, name)

Locals: {'objtype': "<type 'type'>", 'obj': "<class 'pyroute2.netlink.rtnl.rtmsg.rta_mfc_stats'>", 'name': "'type'", 'module': "'__builtin__'"}
2024-12-31 11:46:29,517 140662189614848 DEBUG [zstacklib.utils.debug] Total size = 17668 bytes. Total objects num = 141861.
Index Kind                                                  Size     %       Growth     %        Count     %       Growth     %
    0 abc.ABCMeta                                          24408   138           +0    +0           27     0           +0    +0
    1 _ctypes.PyCSimpleType                                23504   133           +0    +0           26     0           +0    +0
    2 _ctypes.PyCStructType                                12656    71           +0    +0           14     0           +0    +0
    3 _ctypes.CField                                       10608    60           +0    +0          102     0           +0    +0
    4 _ctypes.PyCPointerType                                9944    56           +0    +0           11     0           +0    +0
    5 _ctypes.PyCArrayType                                  9040    51           +0    +0           10     0           +0    +0
    6 _ctypes.PyCFuncPtrType                                7232    40           +0    +0            8     0           +0    +0
    7 pyroute2.ethtool.common.LinkModeBit                   5520    31           +0    +0           69     0           +0    +0
    8 operator.itemgetter                                   5440    30           +0    +0           85     0           +0    +0
    9 _weakrefset.WeakSet                                   5184    29           +0    +0           81     0           +0    +0
   10 random.Random                                         5064    28           +0    +0            1     0           +0    +0
   11 netaddr.ip.IPNetwork                                  2640    14           +0    +0           30     0           +0    +0
   12 logging.Logger                                        1664     9           +0    +0           26     0           +0    +0
   13 pyroute2.ndb.auth_manager.check_auth                  1536     8           +0    +0           24     0           +0    +0
   14 functools.partial                                     1496     8           +0    +0           17     0           +0    +0
   15 pyroute2.netlink.SQLSchema                            1344     7           +0    +0           21     0           +0    +0
   16 ctypes.CFunctionType                                  1040     5           +0    +0            5     0           +0    +0
   17 string._TemplateMetaclass                              904     5           +0    +0            1     0           +0    +0
   18 ctypes._endian._swapped_meta                           904     5           +0    +0            1     0           +0    +0
   19 pyroute2.netns.process.MetaPopen                       904     5           +0    +0            1     0           +0    +0
   20 _ctypes.UnionType                                      904     5           +0    +0            1     0           +0    +0
   21 threading._RLock                                       896     5           +0    +0           14     0           +0    +0
   22 logging.PlaceHolder                                    576     3           +0    +0            9     0           +0    +0
   23 __future__._Feature                                    504     2           +0    +0            7     0           +0    +0
   24 decimal.Decimal                                        480     2           +0    +0            6     0           +0    +0
   25 netaddr.ip.IPAddress                                   448     2           +0    +0            7     0           +0    +0
   26 abc.abstractproperty                                   416     2           +0    +0            4     0           +0    +0
   27 ctypes._FuncPtr                                        416     2           +0    +0            2     0           +0    +0
   28 logging.Formatter                                      384     2           +0    +0            6     0           +0    +0
   29 threading._Condition                                   384     2           +0    +0            6     0           +0    +0
   30 zstacklib.utils.log.ZstackRotatingFileHandler          320     1           +0    +0            5     0           +0    +0
   31 logging.StreamHandler                                  320     1           +0    +0            5     0           +0    +0
   32 netaddr.ip.IPRange                                     288     1           +0    +0            3     0           +0    +0
   33 collections.OrderedDict                                280     1           +0    +0            1     0           +0    +0
   34 codecs.CodecInfo                                       264     1           +0    +0            3     0           +0    +0
   35 uuid.UUID                                              256     1           +0    +0            4     0           +0    +0
   36 itertools.count                                        216     1           +0    +0            3     0           +0    +0
   37 weakref.WeakValueDictionary                            216     1           +0    +0            3     0           +0    +0
   38 decimal.Context                                        192     1           +0    +0            3     0           +0    +0
   39 thread._local                                          192     1           +0    +0            2     0           +0    +0
   40 threading._Event                                       192     1           +0    +0            3     0           +0    +0
   41 site._Printer                                          192     1           +0    +0            3     0           +0    +0
   42 zstacklib.utils.lock.Lockf                             128     0           +0    +0            2     0           +0    +0
   43 threading.Thread                                       128     0           +0    +0            2     0           +0    +0
   44 ctypes.LibraryLoader                                   128     0           +0    +0            2     0           +0    +0
   45 ctypes.CDLL                                            128     0           +0    +0            2     0           +0    +0
   46 site.Quitter                                           128     0           +0    +0            2     0           +0    +0
   47 simplejson._speedups.Scanner                           112     0           +0    +0            1     0           +0    +0
   48 _json.Scanner                                          104     0           +0    +0            1     0           +0    +0
   49 multiprocessing.process.AuthenticationString           101     0           +0    +0            1     0           +0    +0
   50 weakref.KeyedRef                                        96     0           +0    +0            1     0           +0    +0
   51 exceptions.MemoryError                                  72     0           +0    +0            1     0           +0    +0
   52 exceptions.RuntimeError                                 72     0           +0    +0            1     0           +0    +0
   53 os._Environ                                             72     0           +0    +0            1     0           +0    +0
   54 zipimport.zipimporter                                   72     0           +0    +0            1     0           +0    +0
   55 pyroute2.common.AddrPool                                64     0           +0    +0            1     0           +0    +0
   56 ctypes.PyDLL                                            64     0           +0    +0            1     0           +0    +0
   57 zstacklib.utils.log.LogConfig                           64     0           +0    +0            1     0           +0    +0
   58 site._Helper                                            64     0           +0    +0            1     0           +0    +0
   59 logging.RootLogger                                      64     0           +0    +0            1     0           +0    +0
   60 logging.Manager                                         64     0           +0    +0            1     0           +0    +0
   61 zstacklib.utils.thread.AsyncThread                      64     0           +0    +0            1     0           +0    +0
   62 multiprocessing.process._MainProcess                    64     0           +0    +0            1     0           +0    +0
   63 json.encoder.JSONEncoder                                64     0           +0    +0            1     0           +0    +0
   64 logging.LogRecord                                       64     0           +0    +0            1     0           +0    +0
   65 decimal._Log10Memoize                                   64     0           +0    +0            1     0           +0    +0
   66 zstacklib.utils.lock.NamedLock                          64     0           +0    +0            1     0           +0    +0
   67 logging.NullHandler                                     64     0           +0    +0            1     0           +0    +0
   68 json.decoder.JSONDecoder                                64     0           +0    +0            1     0           +0    +0
   69 simplejson.encoder.JSONEncoder                          64     0           +0    +0            1     0           +0    +0
   70 threading._MainThread                                   64     0           +0    +0            1     0           +0    +0
   71 zstacklib.utils.lock.FileLock                           64     0           +0    +0            1     0           +0    +0
   72 simplejson.decoder.JSONDecoder                          64     0           +0    +0            1     0           +0    +0
2024-12-31 11:46:29,517 140662189614848 DEBUG [zstacklib.utils.debug] tracking the growth of objects:(1/5)
2024-12-31 11:51:29,572 140662189614848 DEBUG [zstacklib.utils.debug] Total size = 141797 bytes. Total objects num = 17694.
......
2024-12-31 11:51:59,572 140662189614848 DEBUG [zstacklib.utils.debug] tracking the growth of objects:(2/5)
2024-12-31 11:56:29,629 140662189614848 DEBUG [zstacklib.utils.debug] Total size = 141797 bytes. Total objects num = 17694.
......
'''
