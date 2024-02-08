import os

import linux


def get_device_wwid(device_name):
    if not os.path.exists(os.path.join('/dev', device_name)):
        raise Exception('device name[%s] does not exist' % device_name)

    wwid_path = os.path.join('/sys/block/', device_name,  'device/wwid')
    if os.path.exists(wwid_path):
        return linux.read_file(wwid_path)

    slave_dir = os.path.join('/sys/block/', device_name,  'slaves')
    if not os.path.exists(slave_dir) or not os.listdir(slave_dir):
        raise Exception('device[%s] does not have wwid nor slaves' % device_name)

    for slave in os.listdir(slave_dir):
        return get_device_wwid(slave)


