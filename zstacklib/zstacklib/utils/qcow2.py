import log
import plugin
import traceable_shell
import report
import linux
import tempfile

logger = log.get_logger(__name__)

def create_template_with_task_daemon(src, dst, task_spec, dst_format='qcow2', opts=None, **daemonargs):
    t_shell = traceable_shell.get_shell(task_spec)
    p_file = tempfile.mktemp()

    class ConvertTaskDaemon(plugin.TaskDaemon):

        def __init__(self, dst_path, task_spec):
            super(ConvertTaskDaemon, self).__init__(task_spec, 'ConvertImage')
            self.task_spec = task_spec
            self.dst_path = dst_path
            self.__dict__.update(daemonargs)

        def __exit__(self, exc_type, exc_val, exc_tb):
            super(ConvertTaskDaemon, self).__exit__(exc_type, exc_val, exc_tb)
            linux.rm_file_force(p_file)

        def _cancel(self):
            traceable_shell.cancel_job_by_api(self.api_id)
            linux.rm_file_force(self.dst_path)

        # get percent from (75.65/100%)
        def _get_percent(self):
            p = linux.tail_1(p_file, split=b"\r")
            if not p or "%" not in p:
                return None

            percent = p.strip().lstrip("(").split("/")[0]
            return report.get_exact_percent(percent, self.stage)

    with ConvertTaskDaemon(dst, task_spec):
        linux.create_template(src, dst, dst_format=dst_format, shell=t_shell, progress_output=p_file, opts=opts)
