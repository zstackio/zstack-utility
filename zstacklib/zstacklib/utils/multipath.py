
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


def write_multipath_conf(path, multipath_blacklist=None):
    device = {'device': [{'features': '"0"'}, {'no_path_retry': '"fail"'}, {'product': '"*"'}, {'vendor': '"*"'}]}
    devices = {
        'devices': [{'device': [{'vendor': '*'}, {'product': '*'}, {'features': '0'}, {'no_path_retry': 'fail'}]}]}
    feature = 'queue_if_no_path'
    skipWrite = False
    deleteFeature = False
    blacklist = parse_blacklist(multipath_blacklist)
    update_blacklist = blacklist is not None
    with open(path, 'r+') as fd:
        config = parse_multipath_conf(fd)
        isAddDevices = True
        for item in config:
            if 'devices' in item:
                for devices_k, devices_v in item.items():
                    for device_dict in devices_v:
                        for device_k, device_v in device_dict.items():
                            for device_feature in device_v:
                                if feature in str(device_feature):
                                    device_v.remove(device_feature)
                                    deleteFeature = True
                                    print config

                        if 'device' in device_dict and cmp(sorted(device['device']), sorted(device_dict['device'])) == 0:
                            skipWrite = True

                isAddDevices = False

                if skipWrite is False:
                    item['devices'].append(device)

            if 'blacklist' in item and update_blacklist and cmp(item['blacklist'], blacklist) == 0:
                update_blacklist = False

        if update_blacklist:
            config = filter(lambda cfg : 'blacklist' not in cfg, config)
            config.append({'blacklist' : blacklist})

        if isAddDevices is True:
            config.append(devices)
        logger.info(config)
        if skipWrite is False or deleteFeature is True or update_blacklist is True:
            fd.seek(0)
            fd.truncate()

            for parent_dict in config:
                for parent_k, parent_v in parent_dict.items():
                    fd.write(parent_k + " ")
                    fd.write("{\n")
                    for child_dict in parent_v:
                        if type(child_dict.values()[0]) == str:
                            fd.write('    %s "%s"\n' % (child_dict.keys()[0].replace('"', ''), child_dict.values()[0].replace('"', '')))
                            continue
                        for child_k, child_v in child_dict.items():
                            fd.write('    %s {\n' % child_k)
                            for leaf_dict in child_v:
                                fd.write('        %s "%s"\n' % (leaf_dict.keys()[0].replace('"', ''), leaf_dict.values()[0].replace('"', '')))
                            fd.write("    }\n")

                    fd.write("\n}\n")

    return not skipWrite or deleteFeature or update_blacklist


def parse_blacklist(blacklist):
    if blacklist is None:
        return

    return_list = []
    for item_obj in blacklist:
        item_dict = item_obj.__dict__
        if 'device' in item_dict:
            sub_item_list = []
            for sub_item_obj in item_dict['device']:
                sub_item_list.append(sub_item_obj.__dict__)
            item_dict['device'] = sub_item_list
        return_list.append(item_dict)

    return return_list