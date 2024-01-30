import os

import linux
import lock

def do_config_iscsi_startup():
    conf_path = "/etc/iscsi/iscsid.conf"
    if not os.path.exists(conf_path):
        raise Exception(conf_path + " not found")

    if linux.filter_file_lines_by_regex(conf_path, '^\s*iscsid.startup'):
        return

    with open(conf_path, 'a') as file:
        file.write("\niscsid.startup = /bin/systemctl start iscsid.socket iscsiuio.socket\n")

    return None


config_iscsi_startup_needed = True


@lock.lock('config_iscsi_startup_if_needed')
def config_iscsi_startup_if_needed():
    global config_iscsi_startup_needed
    if config_iscsi_startup_needed:
        do_config_iscsi_startup()
        config_iscsi_startup_needed = False
