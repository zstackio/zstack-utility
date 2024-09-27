from zstacklib.utils import shell
import log
from zstacklib.utils.singleflight import Group

logger = log.get_logger(__name__)

sft = Group()


def get_sensor_info_from_ipmi():
    ipmi_sensor_cmd = "ipmitool sdr elist"

    def ipmi_sensor_call():
        try:
            return shell.call(ipmi_sensor_cmd), None
        except Exception as e:
            return None, str(e)

    result = sft.do(ipmi_sensor_cmd, ipmi_sensor_call)
    if result.error:
        logger.warn("failed to get ipmi sensor info: %s" % result.error)
        return ''

    return result.value[0]
