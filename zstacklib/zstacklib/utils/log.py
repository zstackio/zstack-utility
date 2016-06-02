'''

@author: frank
'''
import logging
import logging.handlers
import sys
import os.path

class LogConfig(object):
    instance = None
    
    LOG_FOLER = '/var/log/zstack'
    
    def __init__(self):
        if not os.path.exists(self.LOG_FOLER):
            os.makedirs(self.LOG_FOLER, 0755)
        self.log_path = os.path.join(self.LOG_FOLER, 'zstack.log')
        self.log_level = logging.DEBUG
        self.log_to_console = True
    
    def set_log_to_console(self, to_console):
        self.log_to_console = to_console
        
    def get_log_path(self):
        return self.log_path
    
    def set_log_path(self, path):
        self.log_path = path
    
    def set_log_level(self, level):
        self.log_level = level
    
    def configure(self):
        dirname = os.path.dirname(self.log_path)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0755)
        logging.basicConfig(filename=self.log_path, level=self.log_level)
    
    def get_logger(self, name, logfd=None):
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        max_rotate_handler = logging.handlers.RotatingFileHandler(self.log_path, maxBytes=10*1024*1024, backupCount=30)
        formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
        max_rotate_handler.setFormatter(formatter)
        max_rotate_handler.setLevel(logging.DEBUG)
        logger.addHandler(max_rotate_handler)
        if self.log_to_console:
            formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
            if not logfd:
                logfd = sys.stdout
            ch = logging.StreamHandler(logfd)
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(formatter)
            logger.addHandler(ch)
        return logger 

    @staticmethod
    def get_log_config():
        if not LogConfig.instance:
            LogConfig.instance = LogConfig()
        return LogConfig.instance

def get_logfile_path():
    return LogConfig.get_log_config().get_log_path()

def set_logfile_path(path):
    LogConfig.get_log_config().set_log_path(path)

def configure_log(log_path, level=logging.DEBUG, log_to_console=False):
    cfg = LogConfig.get_log_config()
    log_dir = os.path.dirname(log_path)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    cfg.set_log_path(log_path)
    cfg.set_log_level(level)
    cfg.set_log_to_console(log_to_console)
    cfg.configure()

def get_logger(name, logfd=None):
    return LogConfig.get_log_config().get_logger(name, logfd)

def cleanup_log(hostname, username, password, port = 22):
    import ssh
    ssh.execute('''cd /var/log/zstack; tar --ignore-failed-read -zcf zstack-logs-`date +%y%m%d-%H%M%S`.tgz *.log.* *.log; find . -name "*.log"|while read file; do echo "" > $file; done''', hostname, username, password, port=port)

def cleanup_local_log():
    import shell
    shell.call('''cd /var/log/zstack; tar --ignore-failed-read -zcf zstack-logs-`date +%y%m%d-%H%M%S`.tgz *.log.* *.log; find . -name "*.log"|while read file; do echo "" > $file; done''')
