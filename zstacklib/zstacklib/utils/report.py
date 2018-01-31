from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import thread
from zstacklib.utils import linux

logger = log.get_logger(__name__)

class ProgressReportCmd(object):
    def __init__(self):
        self.progress = None
        self.processType = None
        self.resourceUuid = None
        self.serverUuid = None

def get_scale(stage=None):
    if not stage:
        return 0, 100
    stages = stage.split("-")
    start = int(stages[0])
    end = int(stages[1])
    return start, end

class Report(object):
    url = None
    serverUuid = None

    def __init__(self, ctxMap, ctxStack):
        self.resourceUuid = None
        self.progress = None
        self.header = None
        self.processType = None
        self.ctxMap = ctxMap
        self.ctxStack = ctxStack

    def progress_report(self, percent, flag):
        try:
            self.progress = percent
            header = {
                "start": "/progress/report",
                "finish": "/progress/report",
                "report": "/progress/report"
            }
            self.header = {'commandpath': header.get(flag, "/progress/report")}
            self.report()
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            logger.warn("report progress failed: %s" % e.message)

    @thread.AsyncThread
    def report(self):
        if not self.url:
            raise Exception('No url specified')

        cmd = ProgressReportCmd()
        cmd.serverUuid = Report.serverUuid
        cmd.processType = self.processType
        cmd.progress = self.progress
        cmd.resourceUuid = self.resourceUuid
        cmd.threadContextMap = self.ctxMap
        cmd.threadContextStack = self.ctxStack
        logger.debug("url: %s, progress: %s, header: %s", Report.url, cmd.progress, self.header)
        http.json_dump_post(Report.url, cmd, self.header)

