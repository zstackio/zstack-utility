import time
import threading
from zstacklib.utils import shell
import subprocess
import os
from zstacklib.utils import log
from zstacklib.utils.report import Report
from zstacklib.utils.report import Progress
from zstacklib.utils import linux


logger = log.get_logger(__name__)

class WatchThread_1(threading.Thread):
    def __init__(self, func):
        threading.Thread.__init__(self)
        self.func = func
        self.keepRunning = True

    def run(self):
        logger.debug("watch_thread_1: %s start" % self.__class__)
        try:
            synced = 0
            while self.keepRunning:
                time.sleep(1)
                synced = self.func(synced)
        except:
            logger.warning(linux.get_exception_stacktrace())

    def stop(self):
        self.keepRunning = False

class WatchThread(threading.Thread):
    def __init__(self, popen, progress=None):
        threading.Thread.__init__(self)
        self.popen = popen
        self.keepRunning = True
        self.progress = progress if progress else Progress()

    def setProgress(self, progress):
        self.progress = progress

    def run(self):
        logger.debug("watch thread start...")
        start, end = self.progress.getScale()
        try:
            self._progress_report(start, self.progress.getStart())
            synced = self.progress.written
            while self.keepRunning and self.popen and self.popen.poll() is None:
                time.sleep(1)
                synced, percent = self.progress.func(self.progress, synced)
                logger.debug("synced: %s, percent: %s" % (synced, percent))
                if percent:
                    self._progress_report(percent, self.progress.getReport())
        except:
            logger.warning(linux.get_exception_stacktrace())
        finally:
            self._progress_report(end, self.progress.getEnd())

    def stop(self):
        self.keepRunning = False

    def _report(self, percent):
        self._progress_report(percent, self.progress.getReport())

    def _progress_report(self, percent, flag):
        logger.debug("progress is: %s" % percent)
        try:
            reports = Report()
            reports.progress = percent
            reports.processType = self.progress.processType
            header = {
                "start": "/progress/start",
                "finish": "/progress/finish",
                "report": "/progress/report"
            }
            reports.header = {'commandpath': header.get(flag, "/progress/report")}
            reports.resourceUuid = self.progress.resourceUuid
            reports.report()
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            logger.warn("report progress failed: %s" % e.message)


def main():
    test_out = shell.call('mktemp /tmp/tmp-XXXXXX').strip()
    fpwrite = open(test_out, 'w')
    p = subprocess.Popen('/bin/bash', stdout=fpwrite, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    watch = WatchThread(p, open(test_out, 'r'))
    watch.start()
    _, e = p.communicate('ping -c 10 114.114.114.114')
    r = p.returncode
    watch.stop()
    fpwrite.close()
    os.remove(test_out)
    if r != 0:
        print "error return: %s" % r

if __name__ == "__main__":
    main()

