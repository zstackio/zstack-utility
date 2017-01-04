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

class Progress(object):
    def __init__(self):
        self.total = 0
        self.stage = 1
        self.stages = {1: "0:100"}
        self.processType = None
        self.resourceUuid = None
        self.pfile = None
        self.func = None
        self.written = 0

    def getScale(self):
        stages = self.stages.get(self.stage) if self.stages.get(self.stage) else "0:100"
        start = int(stages.split(":")[0]) if int(stages.split(":")[0]) > 0 else 0
        end = int(stages.split(":")[1]) if int(stages.split(":")[1]) < 100 else 100
        assert start < end
        return start, end

    def getStart(self):
        self.stages.keys().sort()
        if self.stage == self.stages.keys()[0]:
            return "start"
        return self.getReport()

    def getEnd(self):
        self.stages.keys().sort()
        if self.stage == self.stages.keys()[-1]:
            return "finish"
        return self.getReport()

    def getReport(self):
        return "report"


class Report(object):
    url = None
    serverUuid = None

    def __init__(self):
        self.resourceUuid = None
        self.progress = None
        self.header = None
        self.processType = None

    def progress_report(self, percent, flag):
        try:
            self.progress = percent
            header = {
                "start": "/progress/start",
                "finish": "/progress/finish",
                "report": "/progress/report"
            }
            self.header = {'commandpath': header.get(flag, "/progress/report")}
            self.report()
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            logger.warn("report progress failed: %s" % e.message)

    @thread.AsyncThread
    def report(self):
        cmd = ProgressReportCmd()
        cmd.serverUuid = Report.serverUuid
        cmd.processType = self.processType
        cmd.progress = self.progress
        cmd.resourceUuid = self.resourceUuid
        logger.debug("url: %s, progress: %s, header: %s", Report.url, cmd.progress, self.header)
        http.json_dump_post(Report.url, cmd, self.header)

