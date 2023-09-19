'''

@author: frank
'''
import sys, os, os.path
from zstacklib.utils import log

pidfile = '/var/run/zstack/ceph-backupstorage.pid'
log.configure_log('/var/log/zstack/ceph-backupstorage.log')
logger = log.get_logger(__name__)

import cephagent
from zstacklib.utils import linux

def prepare_pid_dir(path):
    pdir = os.path.dirname(path)
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    
def main():
    usage = 'usage: python -c "from cephbackupstorage import cdaemon; cdaemon.main()" start|stop|restart'
    if len(sys.argv) != 2 or not sys.argv[1] in ['start', 'stop', 'restart']:
        print usage
        sys.exit(1)
    
    global pidfile
    prepare_pid_dir(pidfile)

    try:
        cmd = sys.argv[1]
        py_process_name = 'from cephbackupstorage import cdaemon'
        agentdaemon = cephagent.CephDaemon(pidfile, py_process_name)
        if cmd == 'start':
            logger.debug('zstack-ceph-backupstorage starts')
            agentdaemon.start()
        elif cmd == 'stop':
            logger.debug('zstack-ceph-backupstorage stops')
            agentdaemon.stop()
        elif cmd == 'restart':
            logger.debug('zstack-ceph-backupstorage restarts')
            agentdaemon.restart()
        sys.exit(0)    
    except Exception:
        logger.warning(linux.get_exception_stacktrace())
        sys.exit(1)
    
    
if __name__ == '__main__':
    main()
