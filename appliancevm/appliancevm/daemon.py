import sys,os,os.path
from zstacklib.utils import log
from zstacklib.utils import linux
import zstacklib.utils.iptables as iptables

log.configure_log('/var/log/zstack/zstack-appliancevm.log')
logger = log.get_logger(__name__)

import appliancevm

def main():
    usage = 'usage: python -c "from appliancevm import daemon; daemon.main()" start|stop|restart'
    if len(sys.argv) != 2 or not sys.argv[1] in ['start', 'stop', 'restart']:
        print usage
        sys.exit(1)
        
    pidfile = '/var/run/zstack/appliancevm.pid'
    dirname = os.path.dirname(pidfile)
    if not os.path.exists(dirname):
        os.makedirs(dirname, 0o755)
    
    try:
        iptables.insert_single_rule_to_filter_table('-A INPUT -i eth0 -p tcp -m tcp --dport 7759 -j ACCEPT')
        cmd = sys.argv[1]
        py_process_name = 'from appliancevm import daemon'
        agentdaemon = appliancevm.ApplianceVmDaemon(pidfile, py_process_name)
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
