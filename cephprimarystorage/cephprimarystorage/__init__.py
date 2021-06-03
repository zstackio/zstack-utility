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
    is_tp_ceph = hasattr(token_object, "token") and token_object.token

    # if gateway do not have xdc.conf, pass another step
    # gateway has xdc.conf,  judge the config xdc_proxy_feature
    cfg_path = '/etc/xdc/xdc.conf'
    dirname = os.path.dirname(cfg_path)
    if not os.path.exists(dirname):
        return is_tp_ceph

    if shell.run("grep -c '^xdc_proxy_feature = true$' /etc/xdc/xdc.conf") != 0:
        return is_tp_ceph

    if is_tp_ceph:
        # /etc/modules-load.d/target.conf example:
        # '''
        # iscsi_target_mod
        # target_core_user
        # target_core_iblock
        # '''
        shell.call(
            "sed -i '/^xdc_proxy_feature = true$/d' /etc/xdc/xdc.conf;"
            "sed -i '/iscsi_target_mod/,+2d' /etc/modules-load.d/target.conf;systemctl disable target")
        raise Exception(
            "The gateway node has LIO configurations. Reboot the gateway node and perform this operation again.")
    return is_tp_ceph

