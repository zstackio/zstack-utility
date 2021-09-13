import os

from zstacklib.utils import shell
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

