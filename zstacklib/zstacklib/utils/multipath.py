
import json
from future.backports import ChainMap
from zstacklib.utils import bash
from zstacklib.utils import log


logger = log.get_logger(__name__)
MULTIPATH_PATH = "/etc/multipath.conf"


def parse_multipath_conf(conf_lines):
    config = []
    for line in conf_lines:
        line = line.rstrip().strip()
        if line.startswith('#'):
            continue
        elif line.endswith('{'):
            config.append({line.replace(' ', '').split("{")[0]: parse_multipath_conf(conf_lines)})
        else:
            if line.endswith('}'):
                break
            else:
                line = line.split()
                if len(line) > 1:
                    config.append({line[0]: " ".join(line[1:])})
    return config


def write_multipath_conf(path):
    device = {'device': [{'features': '0'}, {'no_path_retry': 'fail'}, {'product': '*'}, {'vendor': '*'}]}
    devices = {
        'devices': [{'device': [{'vendor': '*'}, {'product': '*'}, {'features': '0'}, {'no_path_retry': 'fail'}]}]}
    skipWrite = False
    with open(path, 'r+') as fd:
        config = parse_multipath_conf(fd)
        isAddDevices = True
        for item in config:
            if 'devices' in item:
                for devices_k, devices_v in item.items():
                    for device_dict in devices_v:
                        if cmp(device, device_dict) == 0:
                            skipWrite = True
                            break
                    if skipWrite is True:
                        break

                isAddDevices = False

                if skipWrite is False:
                    item['devices'].append(device)

        if isAddDevices is True:
            config.append(devices)
        logger.info(config)
        if skipWrite is False:
            fd.seek(0)
            fd.truncate()

            for parent_dict in config:
                for parent_k, parent_v in parent_dict.items():
                    fd.write(parent_k + " ")
                    if len(parent_v) > 0 and type(parent_v[0].values()[0]) == str:
                        fd.write(
                            json.dumps(dict(ChainMap(*parent_v)), sort_keys=True, indent=4, separators=(' ', ' ')))
                        fd.write("\n")
                    else:
                        fd.write("{\n")
                        for child_dict in parent_v:
                            for child_k, child_v in child_dict.items():
                                fd.write(child_k + " ")
                                fd.write(
                                    json.dumps(dict(ChainMap(*child_v)), sort_keys=True, indent=4,
                                               separators=(' ', ' ')))
                                fd.write("\n")

                        fd.write("\n}\n")
    if skipWrite is False:
        bash.bash_roe("sed -i -e 's/\"//g' -e 's/\\\//g' %s" % path)

    return skipWrite