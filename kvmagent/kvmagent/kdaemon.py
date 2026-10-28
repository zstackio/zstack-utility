'''

@author: frank
'''
import sys, os, os.path
from zstacklib.utils import log

log.configure_log('/var/log/zstack/zstack-kvmagent.log')

from zstacklib.utils import linux
import zstacklib.utils.iptables as iptables

pidfile = '/var/run/zstack/kvmagent.pid'
logger = log.get_logger(__name__)

# dual-mode: bind the sibling agent module kvmagent.kvmagent (not the top-level
# package) identically on py2 and py3. bare "import kvmagent" binds the package
# on py3; "from kvmagent import kvmagent" fails when this file is not imported
# as a package submodule (or on py2's implicit-relative lookup). try both.
# the guard below re-raises if the fallback silently bound the package instead
# of the agent module (e.g. the module body itself raised ImportError).
try:
    from kvmagent import kvmagent
except ImportError:
    import kvmagent

if not hasattr(kvmagent, 'KvmDaemon'):
    raise ImportError('kvmagent resolved to the package, not the agent module')

def prepare_pid_dir(path):
    pdir = os.path.dirname(path)
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    
def main():
    usage = 'usage: python -c "from kvmagent import kdaemon; kdaemon.main()" start|stop|restart'
    if len(sys.argv) != 2 or not sys.argv[1] in ['start', 'stop', 'restart']:
        print(usage)
        sys.exit(1)
    
    global pidfile
    prepare_pid_dir(pidfile)

    try:
        cmd = sys.argv[1]
        py_process_name = 'from kvmagent import kdaemon'
        agentdaemon = kvmagent.KvmDaemon(pidfile, py_process_name)
        if cmd == 'start':
            logger.debug('zstack-kvmagent starts')
            agentdaemon.start()
        elif cmd == 'stop':
            logger.debug('zstack-kvmagent stops')
            agentdaemon.stop()
        elif cmd == 'restart':
            logger.debug('zstack-kvmagent restarts')
            agentdaemon.restart()
        sys.exit(0)    
    except Exception:
        logger.warning(linux.get_exception_stacktrace())
        sys.exit(1)
    
    
if __name__ == '__main__':
    main()
