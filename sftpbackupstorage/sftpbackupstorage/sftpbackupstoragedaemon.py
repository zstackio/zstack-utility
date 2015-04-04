'''

@author: frank
'''
import sys, os, os.path
import sftpbackupstorage
from zstacklib.utils import log
from zstacklib.utils import linux
import zstacklib.utils.iptables as iptables

pidfile = '/var/run/zstack/sftpbackupstorageagent.pid'
log.configure_log('/var/log/zstack/zstack-sftpbackupstorage.log')
logger = log.get_logger(__name__)

def prepare_pid_dir(path):
    pdir = os.path.dirname(path)
    if not os.path.isdir(pdir):
        os.makedirs(pdir)
    
def main():
    usage = 'usage: python -c "from sftpbackupstorage import sftpbackupstoragedaemon; sftpbackupstoragedaemon.main()" start|stop|restart'
    if len(sys.argv) != 2 or not sys.argv[1] in ['start', 'stop', 'restart']:
        print usage
        sys.exit(1)
    
    global pidfile
    prepare_pid_dir(pidfile)
    
    try:
        iptables.insert_single_rule_to_filter_table('-A INPUT -p tcp -m tcp --dport 7171 -j ACCEPT')
        cmd = sys.argv[1]
        agentdaemon = sftpbackupstorage.SftpBackupStorageDaemon(pidfile)
        if cmd == 'start':
            agentdaemon.start()
        elif cmd == 'stop':
            agentdaemon.stop()
        elif cmd == 'restart':
            agentdaemon.restart()
        
        sys.exit(0)    
    except Exception:
        logger.warning(linux.get_exception_stacktrace())
        sys.exit(1)
