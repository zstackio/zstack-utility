#!/usr/bin/env python
# encoding: utf-8


import os
import re
import sys
import copy
import time
from datetime import datetime
from termcolor import colored
from utils.shell import ShellCmd
from collections import OrderedDict
from threading import Thread, Lock

reload(sys)
sys.setdefaultencoding('utf8')

try:
    import simplejson as json
except ImportError:
    import json



DEBUG = os.getenv('DEBUG')
MAX_LOG_LINES = 2000

# set recursion limit for trait log tree
sys.setrecursionlimit(MAX_LOG_LINES)


class TraitErr(Exception):
    pass


curr_path = os.path.abspath(__file__)
zs_virtualenv, pysite, _ = curr_path.split('/zstackctl')
zstacklib_utils_path = os.path.join(zs_virtualenv, 'zstackcli', pysite.lstrip('/'), 'zstacklib', 'utils')


sys.path.append(zstacklib_utils_path)

try:
    from log_tree import LogTree as TraitLog
except ImportError as e:
    raise TraitErr(e)


trait_lock = Lock()

trait_conf_file = {
    "scsi": "sblk_dataplane_err_trait.json"
}





def warn(msg):
    sys.stdout.write(colored('WARNING: %s\n' % msg, 'yellow'))


def error(msg):
    sys.stderr.write(colored('ERROR: %s\n' % msg, 'red'))
    sys.exit(1)


def print_data(name, value):
    if DEBUG:
        print('%s:' % name)
        print(json.dumps(value, sort_keys=True, indent=4))


def parse_iscsi_info(iscsi_info):
    '''
    parse output of host cmd: iscsiadm -m session -P 3
    sample of return value:
    {
        "sdc": {
            "portal": "172.24.202.104",
            "sid": "20",
            "state": "running"
        }
    }
    '''
    iscsi_dict = {}
    with open(iscsi_info, 'r') as f:
        lns = f.readlines()
        for line in lns:
            if "Portal" in line:
                portal = line.split(':')[1].strip()
            elif "SID" in line:
                iscsi_dict.setdefault(portal, {})["sid"] = line.split(':')[1].strip()
            elif "Attached scsi" in line:
                scsi_line = line.split()
                dev_name = scsi_line[3]
                iscsi_dict.setdefault(portal, {}).setdefault("devices", {})[dev_name] = scsi_line[-1]

    dev_portal_map = {}
    for portl, info in iscsi_dict.items():
        if not info.has_key('devices'):
            continue
        for dev, state in info['devices'].items():
            dev_portal_map[dev] = {'portal': portl, 'sid': info['sid'], 'state': state}

    print_data('dev_portal_map', dev_portal_map)
    return dev_portal_map


def parse_mpath_info(mpath_info):
    '''
    parse output of host cmd: multipath -ll
    sample of return value:
    {
        "dm-5": {
            "devices": {
                "sdc": "running",
                "sdd": "running"
            },
            "mpath": "mpathb"
        }
    }
    '''
    mpath = {}
    with open(mpath_info, 'r') as f:
        lns = f.readlines()
        for line in lns:
            re_match = re.search("[A-Za-z0-9].*", line)
            if re_match is None:
                continue
            match_line = re_match.group(0)
            # device mapper
            if "dm" in match_line:
                dm_list = match_line.split()
                dmid_list = [dmid for dmid in dm_list if 'dm' in dmid]
                if len(dmid_list) > 0:
                    dm_id = dmid_list[0]
                    mpath[dm_id] = {"mpath": dm_list[0]}
            # disk
            elif "sd" in match_line:
                sd_line = match_line.split()
                state = sd_line[-1]
                dev_name = sd_line[1]
                mpath[dm_id].setdefault("devices", {}).setdefault(dev_name, state)
    print_data('mpath', mpath)
    return mpath


def parse_mpath_bindings(mpath_bindings):
    '''
    parse the content of host file: /etc/multipath/bindings
    sample of return value:
    {
        "mpatha": "32000000347006f9a",
        "mpathb": "32000202104006f9a"
    }
    '''
    mpath_map = {}
    with open(mpath_bindings, 'r') as f:
        lns = f.readlines()
        mpath_map = dict(l.split() for l in lns)
    print_data('mpath_map', mpath_map)
    return mpath_map


def parse_pvs_info(lvm_pvs_info):
    '''
    parse output of host cmd: pvs --nolocking | grep -v Fmt
    sample of return value:
    {
        "ce00338f878e42e79716ca47b7e1aace": [
            "/dev/mapper/mpathb"
        ],
        "e877b8787c4a4294af6ac6e9188b48b6": [
            "/dev/sdb"
        ]
    }
    '''
    vg_pv_map = {}
    with open(lvm_pvs_info, 'r') as f:
        lns = f.readlines()
        for l in lns:
            pv, vg = l.split()[:2]
            vg_pv_map.setdefault(vg, []).append(pv)
    print_data('vg_pv_map', vg_pv_map)
    return vg_pv_map


def parse_scsi_info(scsi_info):
    '''
    parse output of host cmd: lsscsi -i
    sample of return value:
    {
        "20:0:0:0": "INTEL AIO disk 0001 /dev/sdb",
        "23:0:0:0": "INTEL AIO disk 0001 /dev/sdc",
        "27:0:0:0": "INTEL AIO disk 0001 /dev/sdd"
    }
    '''
    scsi_dev_map = {}
    with open(scsi_info, 'r') as f:
        lns = f.readlines()
        for l in lns:
            ls = l.split()
            scsi_dev_map[ls[0][1:-1]] = ' '.join(ls[2:-1])
    print_data('scsi_dev_map', scsi_dev_map)
    return scsi_dev_map


def parse_mapdevs_info(mapdevs_info):
    '''
    the format of collected madevs log:
    6:*:*:*     qla2xxx            8 Gbit   Online   QLE2562 FW:v8.07.00 DVR:v10.01.00.25.08.3-k    NPort (fabric via point-to-point)
    15:*:*:*    qla2xxx            8 Gbit   Online   QLE2562 FW:v8.07.00 DVR:v10.01.00.25.08.3-k    NPort (fabric via point-to-point)
    sample of return value:
    {
        "15": "qla2xxx 8 Gbit Online QLE2562 FW:v8.07.00 DVR:v10.01.00.25.08.3-k", 
        "6": "qla2xxx 8 Gbit Online QLE2562 FW:v8.07.00 DVR:v10.01.00.25.08.3-k"
    }
    '''
    hba_map = {}
    with open(mapdevs_info, 'r') as f:
        lns = f.readlines()
        for l in lns:
            ll = l.split()
            hba_map[ll[0].split(':')[0]] = ' '.join(ll[1:-4])
    print_data('hba_map', hba_map)
    return hba_map


def get_trait_pattern(trait_type="scsi"):
    trait_dict = {}
    trait_pattern_dict = {}
    curr_dir = os.path.dirname(os.path.realpath(__file__))
    trait_file_path = os.path.join(curr_dir, "conf", trait_conf_file[trait_type]) 
    if not os.path.isfile(trait_file_path):
        TraitErr("trait file %s was not found!" % trait_file_path)

    with open(trait_file_path, 'r') as f:
        trait_dict = json.loads(f.read())

    for trait_cls, re_pattern in trait_dict.items():
        if not re_pattern:
            continue
        trait_pattern_dict[trait_cls] = re.compile('|'.join(re_pattern), flags=re.IGNORECASE)

    patterns = []
    for pattern_list in trait_dict.values():
        patterns.extend(pattern_list)

    trait_pattern = '|'.join(patterns)

    return (trait_pattern, trait_pattern_dict)


def update_log_flow(dev_map, dev_name, trait_class, log_msg, dtime, log_dict):
    if dev_name not in dev_map:
        dev_map[dev_name] = {}

    if 'errors' not in dev_map[dev_name]:
        dev_map[dev_name]['errors'] = {}

    if trait_class not in dev_map[dev_name]['errors']:
        # dev_map[dev_name]['errors'][trait_class] = {'count': 1}
        dev_map[dev_name]['errors'][trait_class] = 1
        # if 'start_time' not in dev_map[dev_name]['errors']:
        #     dev_map[dev_name]['errors'][trait_class]['start_time'] = dtime
    else:
        # dev_map[dev_name]['errors'][trait_class]['count'] += 1
        dev_map[dev_name]['errors'][trait_class] += 1

    log_dict.setdefault(dev_name, {}).setdefault(trait_class, {}).setdefault(log_msg, []).append(dtime)


def scsi_trait_match(host,
                     trait_pattern,
                     trait_pattern_dict,
                     log_file,
                     scsi_info,
                     dev_map, 
                     dev_log_map):
    search_trait = ShellCmd("grep -Ei '%s' %s" % (trait_pattern, log_file))
    search_trait(False)
    err_list = search_trait.stdout.splitlines()
    errs_count = len(err_list)
    if errs_count > MAX_LOG_LINES:
        warn("Too many errors, %s errors were found in %s/%s, check the storage's health/connection! The last %s errors will be analyzed.\n" % (
            errs_count, host, os.path.basename(log_file), MAX_LOG_LINES))
        err_list = err_list[errs_count - MAX_LOG_LINES:]

    log_dict = OrderedDict()
    for log in err_list:
        # skip empty line
        if len(log) == 0:
            continue

        log_list = log.split()
        dtime = ' '.join(log_list[:3])
        log_msg = ' '.join(log_list[4:])
        dev_name_list = [d for d in log_list if 'sd' in d or 'dm-' in d]

        for trait_class, re_pattern in trait_pattern_dict.items():
            if re_pattern.search(log) is None:
                continue

            if dev_name_list:
                dev_name = dev_name_list[0].strip('[').strip(']').strip(',')
                if dev_name != 'sd':
                    update_log_flow(dev_map, dev_name, trait_class, log_msg, dtime, log_dict)
                else:
                    # trait log: "kernel: sd 27:0:0:0: rejecting I/O to offline device", class: "io"
                    hbtl = log_msg.split()[2][:-1]
                    if hbtl in scsi_info:
                        scsi_brief_info = scsi_info[hbtl]
                        # log_msg += ' (%s)' % scsi_brief_info
                        dev_name = scsi_brief_info.split('/')[-1]
                        update_log_flow(dev_map, dev_name, trait_class, log_msg, dtime, log_dict)

            if trait_class != 'iscsi_connection':
                continue

            for dev_name, dev_info in dev_map.items():
                update_log = False
                # trait log: "kernel: connection18:0: detected conn error (1022)", class: "iscsi_connection"
                if 'detected conn error' in log:
                    sid = 0
                    sid_search = re.search('\d.*', log_msg.split(':')[1])
                    if sid_search is not None:
                        sid = sid_search.group()
                    if sid and 'sid' in dev_info and dev_info['sid'] == sid:
                        update_log = True

                # trait log2: "iscsid: connect to 10.0.202.100:3260 failed (Connection refused)", class: "iscsi_connection"
                elif 'connect to' in log:
                    iscsi_portal = re.search('\d.*', log_msg)
                    if iscsi_portal is not None:
                        portal, _ = iscsi_portal.group().split(':')
                        if dev_info.get('portal') == portal:
                            update_log = True

                if update_log:
                    update_log_flow(dev_map, dev_name, trait_class, log_msg, dtime, log_dict)
                    break

    # attach and merge repeated logs
    for dev_name, trait_cls_log_dict in log_dict.items():
        for trait_cls, log_dict in trait_cls_log_dict.items():
            for log_msg, datetime_list in log_dict.items():
                log_count = len(datetime_list)
                if log_count > 1:
                    log = '[%s -- %s]' % (datetime_list[0], datetime_list[-1]) + ' { %s } * %s' % (log_msg,  log_count)
                elif log_count == 1:
                    log = '[%s] %s' % (datetime_list[0], log_msg)

                dev_log_map.setdefault(dev_name, {}).setdefault(trait_cls, []).append(log)

    return dev_log_map

def add_dev_leaf(dev_name, dev_info, trait_log, dev_log_map):
    errs = {}
    if 'errors' in dev_info:
        errs = dev_info.pop('errors')
    if dev_info:
        trait_log.add(str(dev_info))
    # if errs:
    #     trait_log.add('error_statistics: %s' % errs, dev_name)

    for trait_cls, log_list in dev_log_map[dev_name].items():
        if errs:
            dev_trait = '%s:%s:error(%s)' % (dev_name, trait_cls, errs[trait_cls])
        else:
            dev_trait = '%s:%s:error' % (dev_name, trait_cls)
        trait_log.add(dev_trait, dev_name)
        for log in log_list:
            trait_log.add(log, dev_trait)


def do_scsi_diagnose(host,
                     log_dir,
                     log_path,
                     trait_pattern,
                     trait_pattern_dict,
                     blk_err_dict,
                     offline_dev):
        dev_log_map = OrderedDict()
        trait_log = TraitLog()
        msg_log_dir = os.path.join(log_dir, host, 'message-logs')
        if not os.path.exists(msg_log_dir):
            return

        # add trait log root
        trait_log.add(host)

        scsi_info_file = os.path.join(log_dir, host, 'scsi-info', 'scsi-info')
        scsi_info = parse_scsi_info(scsi_info_file)

        iscsi_session_info = os.path.join(log_dir, host, 'iscsi-session', 'iscsi-session')
        dev_map = parse_iscsi_info(iscsi_session_info)

        pvs_info = os.path.join(log_dir, host, 'pvs-info', 'pvs-info')
        vg_pv_map = parse_pvs_info(pvs_info)

        mpath_info = os.path.join(log_dir, host, 'multipath-info', 'multipath-info')
        mpath = parse_mpath_info(mpath_info)

        mpath_bindings = os.path.join(log_dir, host, 'multipath-bindings', 'multipath-bindings')
        mpath_map = parse_mpath_bindings(mpath_bindings)

        hba_info = os.path.join(log_dir, host, 'mapdevs-info', 'mapdevs-info')
        hba_map = parse_mapdevs_info(hba_info)

        for msg_log in os.listdir(msg_log_dir):
            scsi_trait_match(host,
                             trait_pattern, 
                             trait_pattern_dict, 
                             os.path.join(msg_log_dir, msg_log), 
                             scsi_info, 
                             dev_map, 
                             dev_log_map)

        if not dev_log_map:
            return

        dm_map = {}
        for dm_id, dm_info_dict in mpath.items():
            for mpathx, wwid in mpath_map.items():
                if dm_info_dict['mpath'] not in [mpathx, wwid]:
                    continue
                dm_map[(dm_info_dict['mpath'], dm_id)] = dm_info_dict['devices']

        new_dev_map = copy.deepcopy(dev_map)
        for dev_name, dev_info in dev_map.items():
            # skip healthy device
            if 'errors' not in dev_info:
                new_dev_map.pop(dev_name)
                continue

            # scsi dev hbtl/hba map
            for hbtl, scsi_vender_dev in scsi_info.items():
                if dev_name == scsi_vender_dev.split('/')[-1]:
                    new_dev_map[dev_name]['hbtl'] = hbtl
                    scsi_host = hbtl.split(':')[0]
                    if hba_map.has_key(scsi_host):
                        new_dev_map[dev_name]['hba'] = hba_map[scsi_host]

            # mpath dm dev map
            for mpathx_dm_set, devices in dm_map.items():
                if dev_name in devices or dev_name in mpathx_dm_set:
                    dm_alias = '%s:%s' % mpathx_dm_set
                    if dm_alias not in new_dev_map:
                        new_dev_map[dm_alias] = {}
                    new_dev_map[dm_alias][dev_name] = new_dev_map[dev_name]
                    new_dev_map[dm_alias]['paths'] = devices.keys()
                    new_dev_map.pop(dev_name)

        # dev_ps_dict = copy.deepcopy(new_dev_map)
        for dm_alias, dev_info_dict in new_dev_map.items():
            for vg_uuid, pv_list in vg_pv_map.items():
                sblk_uuid = 'SBLK:%s' % vg_uuid
                for pv in pv_list:
                    if dm_alias.split(':')[0] != pv.split('/')[-1]:
                        # record offline devices
                        for dev_name, dev_info in dev_info_dict.items():
                            if 'offline' in str(dev_info):
                                if not offline_dev.has_key(host):
                                    offline_dev[host] = {}
                                offline_dev[host][dev_name] = dev_info
                        continue

                    if sblk_uuid not in trait_log.child(trait_log.root):
                        trait_log.add(sblk_uuid, trait_log.root)

                    if 'dm' in dm_alias:
                        blk = 'mpath:' + dm_alias
                    else:
                        blk = dm_alias

                    trait_log.add(blk, sblk_uuid)
                    if 'paths' in dev_info_dict:
                        trait_log.add('paths: %s' % dev_info_dict['paths'], blk)
                    # dev_ps_dict[dm_alias]['sblk'] = vg_uuid

                    for dev_name, dev_info in dev_info_dict.items():
                        # skip none scsi device
                        if dev_name == 'paths':
                            continue

                        if 'sd' in dev_name or 'dm' in dev_name:
                            # multipath
                            trait_log.add(dev_name, blk)
                            add_dev_leaf(dev_name, copy.deepcopy(dev_info), trait_log, dev_log_map)
                            errors_str = str(dev_info.pop('errors'))
                            dev_info['errors'] = errors_str
                            blk_err_dict.setdefault(sblk_uuid, {}).setdefault(host, {}).setdefault(dev_name, dev_info)
                            blk_err_dict[sblk_uuid][host]['paths'] = dev_info_dict['paths']
                        else:
                            # disk
                            add_dev_leaf(blk, copy.deepcopy(dev_info_dict), trait_log, dev_log_map)
                            errors_str = str(dev_info_dict.pop('errors'))
                            dev_info_dict['errors'] = errors_str
                            blk_err_dict.setdefault(sblk_uuid, {}).setdefault(host, {}).setdefault(blk, dev_info_dict)
                            break

        # trait_log.dump_logs()
        with trait_lock:
            trait_log.write_log(log_path)
            # to stdout
            # trait_log.write_log()


def diagnose_scsi(log_dir, log_path, args):
    blk_err_dict = {}
    offline_dev = {}
    trait_pattern, trait_pattern_dict = get_trait_pattern()

    diagnose_thread_list = []
    host_log_list = os.listdir(log_dir)
    host_log_list.sort()
    for host in host_log_list:
        diagnose_thread_list.append(Thread(target=do_scsi_diagnose, args=(
            host, log_dir, log_path, trait_pattern, trait_pattern_dict, blk_err_dict, offline_dev
        )))

    for thrd in diagnose_thread_list:
        thrd.start()
        if os.getenv('DIAGNOSETEST'):
            time.sleep(0.5)

    for thrd in diagnose_thread_list:
        thrd.join()

    if args.since is not None:
        desc = "since " + args.since
    else:
        desc = "in recent %s days" % args.daytime

    if blk_err_dict:
        warn("SharedBlock storage errors were found %s, below is a summary, check details in %s\n" % (
            desc, os.path.join(os.getcwd(), log_path)))
        print(json.dumps(blk_err_dict, sort_keys=True, indent=4))
        if offline_dev:
            warn("Found offline devices:\n%s" % json.dumps(offline_dev, sort_keys=True, indent=4))
    else:
        print("SharedBlock storage error was not found %s, the storage access seems good.\n" % desc)


def diagnose(log_dir, log_path, args, trait_type='scsi'):
    if trait_type == 'scsi':
        diagnose_scsi(log_dir, log_path, args)