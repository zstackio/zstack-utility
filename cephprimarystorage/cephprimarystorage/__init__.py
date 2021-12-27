from zstacklib.utils import log

log.configure_log('/var/log/zstack/ceph-primarystorage.log')
logger = log.get_logger(__name__)

from cephprimarystorage import cephdriver
from cephprimarystorage import thirdpartycephdriver

mapping = {
    'ceph': cephdriver.CephDriver,
    'thirdpartyCeph': thirdpartycephdriver.ThirdpartyCephDriver
}


def get_driver(cmd):
    if is_third_party_ceph(cmd):
        ps_type = 'thirdpartyCeph'
    else:
        ps_type = 'ceph'

    return mapping.get(ps_type)(cmd)


def is_third_party_ceph(token_object):
    return hasattr(token_object, "token") and token_object.token

