'''

@author: frank
'''
import logging
import sys
import os.path
import gzip
from cloghandler import ConcurrentRotatingFileHandler
from random import randint

class ZstackRotatingFileHandler(ConcurrentRotatingFileHandler):
    def __init__(self, filename, **kws):
        backupCount = kws.get('backupCount', 0)
        self.backup_count = backupCount
        ConcurrentRotatingFileHandler.__init__(self, filename, **kws)

    def doArchive(self, old_log):
        with open(old_log) as log:
            with gzip.open(old_log + '.gz', 'wb') as comp_log:
                comp_log.writelines(log)
        os.remove(old_log)

    def doRollover(self):
        """
        Do a rollover, as described in __init__().
        """
        self._close()
        if self.backupCount <= 0:
            # Don't keep any backups, just overwrite the existing backup file
            # Locking doesn't much matter here; since we are overwriting it anyway
            self.stream = self._open("w")
            return
        try:
            # Determine if we can rename the log file or not. Windows refuses to
            # rename an open file, Unix is inode base so it doesn't care.

            # Attempt to rename logfile to tempname:  There is a slight race-condition here, but it seems unavoidable
            tmpname = None
            while not tmpname or os.path.exists(tmpname):
                tmpname = "%s.rotate.%08d" % (self.baseFilename, randint(0, 99999999))
            try:
                # Do a rename test to determine if we can successfully rename the log file
                os.rename(self.baseFilename, tmpname)
            except (IOError, OSError):
                exc_value = sys.exc_info()[1]
                self._degrade(True, "rename failed.  File in use?  "
                                    "exception=%s", exc_value)
                return

            # Q: Is there some way to protect this code from a KeboardInterupt?
            # This isn't necessarily a data loss issue, but it certainly does
            # break the rotation process during stress testing.

            # There is currently no mechanism in place to handle the situation
            # where one of these log files cannot be renamed. (Example, user
            # opens "logfile.3" in notepad); we could test rename each file, but
            # nobody's complained about this being an issue; so the additional
            # code complexity isn't warranted.
            for i in range(self.backupCount - 1, 0, -1):
                sfn = "%s.%d.gz" % (self.baseFilename, i)
                dfn = "%s.%d.gz" % (self.baseFilename, i + 1)
                if os.path.exists(sfn):
                    # print "%s -> %s" % (sfn, dfn)
                    if os.path.exists(dfn):
                        os.remove(dfn)
                    os.rename(sfn, dfn)
            dfn = self.baseFilename + ".1"
            if os.path.exists(dfn):
                os.remove(dfn)
            os.rename(tmpname, dfn)
            self.doArchive(dfn)
            # print "%s -> %s" % (self.baseFilename, dfn)
            self._degrade(False, "Rotation completed")
        finally:
            # Re-open the output stream, but if "delay" is enabled then wait
            # until the next emit() call. This could reduce rename contention in
            # some usage patterns.
            if not self.delay:
                self.stream = self._open()

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
        max_rotate_handler = ZstackRotatingFileHandler(self.log_path, maxBytes=10*1024*1024, backupCount=30)
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
