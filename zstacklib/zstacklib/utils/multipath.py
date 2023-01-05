
from zstacklib.utils import log


logger = log.get_logger(__name__)
MULTIPATH_PATH = "/etc/multipath.conf"


def parse_multipath_conf(conf_lines):
    # type: (iter) -> list[dict[str, list]]

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
                    config.append({line[0]: (" ".join(line[1:])).strip('"')})
    return config


def sorted_conf(sections):
    # type: (list) -> list

    result = []
    if not sections:
        return result

    for section in sorted(sections, key=lambda s: s.keys()[0]):
        section_name, section_value = section.items()[0]
        if type(section_value) is list:
            result.append({section_name: sorted_conf(section_value)})
        else:
            result.append({section_name: section_value})

    return result


def write_multipath_conf(path, blacklist=None):
    # type: (str, list[dict[str, object]]) -> bool

    default_device = {'device': [{'features': '0'}, {'no_path_retry': 'fail'}, {'product': '.*'}, {'vendor': '.*'}]}
    feature_to_remove = 'queue_if_no_path'
    modified = False
    with open(path, 'r+') as fd:
        config = parse_multipath_conf(fd)
        has_devices_section = False
        has_default_device = False
        blacklist_changed = False
        for section in config:
            if 'blacklist' in section:
                blacklist_changed = cmp(sorted_conf(section['blacklist']), sorted_conf(blacklist)) != 0

            if 'devices' in section:
                has_devices_section = True
                for subsection in section['devices']:
                    for attribute in subsection['device'][:]:
                        name, value = attribute.items()[0]
                        if value.strip().strip('"') == '*':
                            attribute[name] = '.*'
                            modified = True

                        if name == 'features' and feature_to_remove in value:
                            subsection['device'].remove(attribute)
                            modified = True

                        if cmp(sorted(default_device['device']), sorted(subsection['device'])) == 0:
                            has_default_device = True

                if not has_default_device:
                    section['devices'].append(default_device)
                    modified = True

        if blacklist is not None and blacklist_changed:  # None blacklist means ignore
            config = filter(lambda cfg : 'blacklist' not in cfg, config)
            config.append({'blacklist' : blacklist})
            modified = True

        if not has_devices_section:
            config.append({'devices': [default_device]})
            modified = True

        logger.info(config)
        if modified:
            fd.seek(0)
            fd.truncate()

            for section in config:
                section_name, section_value = section.items()[0]
                fd.write("%s {\n" % section_name)
                for child in sorted_conf(section_value):
                    child_name, child_value = child.items()[0]
                    # child is attribute
                    if type(child_value) == str:
                        fd.write('\t%s "%s"\n' % (child_name.strip('"'), child_value.strip('"')))
                        continue

                    # child is subsection
                    fd.write('\t%s {\n' % child_name)
                    for attribute in child_value:
                        attrib_name, attrib_value = attribute.items()[0]
                        fd.write('\t\t%s "%s"\n' % (attrib_name.strip('"'), attrib_value.strip('"')))
                    fd.write("\t}\n")
                fd.write("}\n")

    return modified
