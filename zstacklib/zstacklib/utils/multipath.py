import os
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
        section_name, section_value = next(iter(section.items()))
        if type(section_value) is list:
            result.append({section_name: sorted_conf(section_value)})
        else:
            result.append({section_name: section_value})

    return result

class MultipathConfigUpdater:
    def __init__(self, config_path):
        self.path = config_path
        self.config = None
        self.old_config_str = None
        self.new_config_str = None
        self.modified = False

    def __enter__(self):
        with open(self.path, 'r') as fd:
            self.old_config_str = fd.read()
            fd.seek(0)
            self.config = parse_multipath_conf(fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and self.modified:
            logger.info(self.config)
            self.save()

    def set_default_config(self):
        default_device = {'device': [{'features': '0'}, {'no_path_retry': 'fail'}, {'product': '.*'}, {'vendor': '.*'}]}
        default_find_multipaths = {"find_multipaths": "yes"}
        feature_to_remove = 'queue_if_no_path'

        has_devices_section = False
        has_default_device = False
        has_defaults_section = False
        has_defaults_find_multipaths = False
        modified = False
        for section in self.config:
            if 'defaults' in section:
                has_defaults_section = True
                for attribute in section['defaults']:
                    name, value = next(iter(attribute.items()))
                    if name == "find_multipaths":
                        has_defaults_find_multipaths = True
                        if value.strip().strip('"') != 'yes':
                            attribute[name] = "yes"
                            modified = True

                if not has_defaults_find_multipaths:
                    section["defaults"].append(default_find_multipaths)
                    modified = True

            if 'devices' in section:
                has_devices_section = True
                for subsection in section['devices']:
                    for attribute in subsection['device'][:]:
                        name, value = next(iter(attribute.items()))
                        if value.strip().strip('"') == '*':
                            attribute[name] = '.*'
                            modified = True

                        if name == 'features' and feature_to_remove in value:
                            subsection['device'].remove(attribute)
                            modified = True

                        if sorted_conf(default_device['device']) == sorted_conf(subsection['device']):
                            has_default_device = True

                if not has_default_device:
                    section['devices'].append(default_device)
                    modified = True

        if not has_defaults_section:
            self.config.append({'defaults': [default_find_multipaths]})
            modified = True

        if not has_devices_section:
            self.config.append({'devices': [default_device]})
            modified = True

        self.modified |= modified
        return modified

    def config_section(self, name, cfg):
        for section in self.config:
            if name in section:
                if sorted_conf(section[name]) == sorted_conf(cfg):
                    return False
                section[name] = cfg
                self.modified = True
                return True

        self.config.append({name: cfg})
        self.modified = True
        return True

    def save(self):
        with open(self.path, 'w+') as fd:
            fd.seek(0)
            fd.truncate()

            for section in self.config:
                section_name, section_value = next(iter(section.items()))
                fd.write("%s {\n" % section_name)
                for child in sorted_conf(section_value):
                    child_name, child_value = next(iter(child.items()))
                    # child is attribute
                    if type(child_value) == str:
                        fd.write('\t%s "%s"\n' % (child_name.strip('"'), child_value.strip('"')))
                        continue

                    # child is subsection
                    fd.write('\t%s {\n' % child_name)
                    for attribute in child_value:
                        attrib_name, attrib_value = next(iter(attribute.items()))
                        fd.write('\t\t%s "%s"\n' % (attrib_name.strip('"'), attrib_value.strip('"')))
                    fd.write("\t}\n")
                fd.write("}\n")
            fd.flush()
            os.fsync(fd.fileno())
            fd.seek(0)
            self.new_config_str = fd.read()
