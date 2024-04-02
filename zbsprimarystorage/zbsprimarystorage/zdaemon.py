'''

@author: Xingwei YU
'''
import os
import sys

from zstacklib.utils import log
from zstacklib.utils import linux

pidfile = '/var/run/zstack/zbs-primarystorage.pid'
log.configure_log('/var/log/zstack/zbs-primarystorage.log')
logger = log.get_logger(__name__)
import zbsagent


def prepare_pid_dir(path):
    pdir = os.path.dirname(path)
    if not os.path.isdir(pdir):
        os.makedirs(pdir)


def main():
    usage = 'usage: python -c "from zbsprimarystorage import zdaemon; zdaemon.main()" start|stop|restart'
    if len(sys.argv) != 2 or not sys.argv[1] in ['start', 'stop', 'restart']:
        print
        usage
        sys.exit(1)

    global pidfile
    prepare_pid_dir(pidfile)

    try:
        cmd = sys.argv[1]
        py_process_name = 'from zbsprimarystorage import zdaemon'
        agentdaemon = zbsagent.ZbsDaemon(pidfile, py_process_name)
        if cmd == 'start':
            logger.debug('zstack-zbs-primarystorage starts')
            agentdaemon.start()
        elif cmd == 'stop':
            logger.debug('zstack-zbs-primarystorage stops')
            agentdaemon.stop()
        elif cmd == 'restart':
            logger.debug('zstack-zbs-primarystorage restarts')
            agentdaemon.restart()
        sys.exit(0)
    except Exception:
        logger.warning(linux.get_exception_stacktrace())
        sys.exit(1)


if __name__ == '__main__':
    main()
