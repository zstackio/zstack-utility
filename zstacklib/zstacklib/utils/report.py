import time
from zstacklib.utils import http, jsonobject
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
        self.detail = None

def get_scale(stage=None):
    if not stage:
        return 0, 100
    stages = stage.split("-")
    start = int(stages[0])
    end = int(stages[1])
    return start, end


def get_exact_percent(percent, stage):
    start, end = get_scale(stage)
    return get_exact_percent_from_scale(percent, start, end)


def get_exact_percent_from_scale(percent, start, end):
    return int(float(percent)/100 * (end - start) + start)


def get_task_stage(spec, default=None):
    stage = default
    if spec.threadContext:
        if spec.threadContext['task-stage']:
            stage = spec.threadContext['task-stage']
    return stage


def get_api_id(spec):
    if spec.threadContext and spec.threadContext.api:
        return spec.threadContext.api
    else:
        return None

def get_timeout(spec):
    if spec.taskContext and spec.taskContext.__messagetimeout__ and spec.taskContext.__messagedeadline__:
        timeout = min(long(spec.taskContext.__messagetimeout__) / 1000, long(spec.taskContext.__messagedeadline__) / 1000 - linux.get_current_timestamp())
        if timeout <= 60:
            raise Exception("timeout[%s] is too short" % timeout)
        return int(timeout)
    else:
        return 0

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
        self.taskStage = None
        self.detail = None

    @staticmethod
    def from_spec(cmd, progress_type):
        if cmd.sendCommandUrl:
            Report.url = cmd.sendCommandUrl

        report = Report(cmd.threadContext, cmd.threadContextStack)
        report.processType = progress_type
        report.taskStage = get_task_stage(cmd)
        return report

    def progress_report(self, percent, flag="report", detail=None):
        try:
            self.progress = percent
            self.detail = detail
            header = {
                "start": "/progress/report",
                "finish": "/progress/report",
                "report": "/progress/report"
            }
            self.header = {'commandpath': header.get(flag, "/progress/report")}
            self.report()
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            logger.warn("{api: %s} report progress failed: %s" % (e.message, self.ctxMap["api"]))

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
        cmd.detail = self.detail
        logger.debug("{api: %s} url: %s, progress: %s, header: %s, detail: %s", cmd.threadContextMap["api"], Report.url, cmd.progress, self.header, None if not cmd.detail else jsonobject.dumps(cmd.detail))
        http.json_dump_post(Report.url, cmd, self.header)


class AutoReporter(object):
    def __init__(self, report, progress_getter, detail_getter, timeout=259200):
        # type: (Report, callable, callable, int) -> None
        self.report = report
        self.progress_getter = progress_getter
        self.over = False
        self.timeout = timeout
        self.detail_getter = detail_getter

    @staticmethod
    def from_spec(spec, progress_type, progress_getter, detail_getter):
        report = Report.from_spec(spec, progress_type)
        return AutoReporter(report, progress_getter, detail_getter)

    @thread.AsyncThread
    def start(self):
        def report(_):
            if self.over:
                return True

            percent = self.progress_getter()
            if str(percent).isdigit():
                self.report.progress_report(str(percent), "report", self.detail_getter())

        linux.wait_callback_success(report, callback_data=None, timeout=self.timeout)

    def close(self):
        self.over = True
