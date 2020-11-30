# flake8: noqa

HEADERS = {
    'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c',
    'callbackurl': 'http://127.0.0.1:8080',
    'Content-Type': 'application/json'
}


BM_INSTANCE1 = {
    'uuid': '7b432900-c0ad-47e7-b1c7-01b74961c235',
    'provisionIp': '192.168.101.10',
    'provisionMac': '52:54:00:3b:a5:1f'
}


BM_INSTANCE2 = {
    'uuid': 'f741cdbe-ed86-4188-badd-53cc697320af',
    'provisionIp': '192.168.101.20',
    'provisionMac': '52:54:00:ef:5c:1d'
}


VOLUME1 = {
    'uuid': '529c7537-3c94-499e-add7-551ab27205f2',
    'type': 'Root',
    'path': ('sharedblock://8e26d895-4c44-439e-8efe-cb2e3fc71b62/'
             '529c7537-3c94-499e-add7-551ab27205f2'),
    'format': 'qcow2',
    'deviceId': 1,
    'primaryStorageType': 'sharedblock'
}


PORT1 = {
    'mac': '52:54:00:23:f1:c0',
    'ipAddress': '10.0.120.10',
    'netmask': '255.255.255.0',
    'gateway': '10.0.120.1',
    'defaultRoute': False
}


PORT2 = {
    'mac': '52:54:00:4a:c0:1f',
    'ipAddress': '10.0.0.20',
    'netmask': '255.255.255.0',
    'gateway': '10.0.0.1',
    'defaultRoute': True
}

PORT3 = {
    'mac': '52:54:00:4a:c0:1f',
    'ipAddress': '10.0.10.20',
    'netmask': '255.255.255.0',
    'gateway': '10.0.10.1',
    'defaultRoute': True,
    'vlanId': 130
}


IFACE_PORT1 = {
    17: [{
        'addr': '52:54:00:23:f1:c0',
        'broadcast': 'ff:ff:ff:ff:ff:ff'
    }],
    2: [{
        'addr': '10.0.120.10',
        'netmask': '255.255.255.0'
    }]
}


IFACE_PORT1_NONE_IP = {
    17: [{
        'addr': '52:54:00:23:f1:c0',
        'broadcast': 'ff:ff:ff:ff:ff:ff'
    }]
}


IFACE_PORT2 = {
    17: [{
        'addr': '52:54:00:4a:c0:1f',
        'broadcast': 'ff:ff:ff:ff:ff:ff'
    }],
    2: [{
        'addr': '10.0.0.20',
        'netmask': '255.255.255.0',
    }]
}


IFACE_PORT2_NONE_IP = {
    17: [{
        'addr': '52:54:00:4a:c0:1f',
        'broadcast': 'ff:ff:ff:ff:ff:ff'
    }]
}


IFACE_PORT3 = {
    17: [{
        'addr': '52:54:00:4a:c0:1f',
        'broadcast': 'ff:ff:ff:ff:ff:ff'
    }],
    2: [{
        'addr': '10.0.10.20',
        'netmask': '255.255.255.0',
    }]
}


IFACE_PORT3_NONE_IP = {
    17: [{
        'addr': '52:54:00:4a:c0:1f',
        'broadcast': 'ff:ff:ff:ff:ff:ff'
    }]
}


IFACE_GATEWAYS = {
    'default': {
        2: ('10.0.120.1', 'enp4s0f0')
    },
    2: [
        ('10.0.120.1', 'enp4s0f0', True)
    ]
}


ISCSI_SESSION1 = '''
tcp: [5] 192.168.203.151:3260,1 iqn.2015-01.io.zstack:target.instance.7b432900-c0ad-47e7-b1c7-01b74961c235 (non-flash)
'''


ISCSI_SESSION2 = '''
tcp: [3] 192.168.203.151:3260,1 iqn.2015-01.io.zstack:target.instance.15d4b2b2-5cbe-47aa-93bc-7d29c902043d (non-flash)
'''


ISCSI_SESSION_DETAIL1 = '''
iSCSI Transport Class version 2.0-870
version 6.2.0.874-10
Target: iqn.2015-01.io.zstack:target.cda14fa9-c12b-401c-a085-31c7ada576c3 (non-flash)
        Current Portal: 172.25.12.55:3260,1
        Persistent Portal: 172.25.12.55:3260,1
                **********
                Interface:
                **********
                Iface Name: default
                Iface Transport: tcp
                Iface Initiatorname: InitiatorName=iqn.2015-01.io.zstack:initiator.instance.7b432900-c0ad-47e7-b1c7-01b74961c235
                Iface IPaddress: 172.30.5.1
                Iface HWaddress: <empty>
                Iface Netdev: <empty>
                SID: 5
                iSCSI Connection State: LOGGED IN
                iSCSI Session State: LOGGED_IN
                Internal iscsid Session State: NO CHANGE
                *********
                Timeouts:
                *********
                Recovery Timeout: 120
                Target Reset Timeout: 30
                LUN Reset Timeout: 30
                Abort Timeout: 15
                *****
                CHAP:
                *****
                username: <empty>
                password: ********
                username_in: <empty>
                password_in: ********
                ************************
                Negotiated iSCSI params:
                ************************
                HeaderDigest: None
                DataDigest: None
                MaxRecvDataSegmentLength: 262144
                MaxXmitDataSegmentLength: 262144
                FirstBurstLength: 65536
                MaxBurstLength: 262144
                ImmediateData: Yes
                InitialR2T: Yes
                MaxOutstandingR2T: 1
                ************************
                Attached SCSI devices:
                ************************
                Host Number: 11 State: running
                scsi11 Channel 00 Id 0 Lun: 0
                        Attached scsi disk sda          State: running
                scsi11 Channel 00 Id 0 Lun: 1
                        Attached scsi disk sdb          State: running
'''


ISCSI_SESSION_DETAIL2 = '''
iSCSI Transport Class version 2.0-870
version 6.2.0.874-10
Target: iqn.2015-01.io.zstack:target.cda14fa9-c12b-401c-a085-31c7ada576c3 (non-flash)
        Current Portal: 172.25.12.55:3260,1
        Persistent Portal: 172.25.12.55:3260,1
                **********
                Interface:
                **********
                Iface Name: default
                Iface Transport: tcp
                Iface Initiatorname: InitiatorName=iqn.2015-01.io.zstack:initiator.instance.7b432900-c0ad-47e7-b1c7-01b74961c235
                Iface IPaddress: 172.30.5.1
                Iface HWaddress: <empty>
                Iface Netdev: <empty>
                SID: 5
                iSCSI Connection State: LOGGED IN
                iSCSI Session State: LOGGED_IN
                Internal iscsid Session State: NO CHANGE
                *********
                Timeouts:
                *********
                Recovery Timeout: 120
                Target Reset Timeout: 30
                LUN Reset Timeout: 30
                Abort Timeout: 15
                *****
                CHAP:
                *****
                username: <empty>
                password: ********
                username_in: <empty>
                password_in: ********
                ************************
                Negotiated iSCSI params:
                ************************
                HeaderDigest: None
                DataDigest: None
                MaxRecvDataSegmentLength: 262144
                MaxXmitDataSegmentLength: 262144
                FirstBurstLength: 65536
                MaxBurstLength: 262144
                ImmediateData: Yes
                InitialR2T: Yes
                MaxOutstandingR2T: 1
                ************************
                Attached SCSI devices:
                ************************
                Host Number: 11 State: running
                scsi11 Channel 00 Id 0 Lun: 0
                        Attached scsi disk sda          State: running
'''


CPUINFO_X86 = {
    'arch': 'X86_64',
    'arch_string_raw': 'x86_64',
    'bits': 64,
    'brand_raw': 'AMD Ryzen 7 3700X 8-Core Processor',
    'count': 16,
    'cpuinfo_version': [7, 0, 0],
    'cpuinfo_version_string': '7.0.0',
    'family': 23,
    'flags': [
        '3dnowprefetch',
        'abm',
        'adx',
        'aes',
    ],
    'hz_actual': [3127553000, 0],
    'hz_actual_friendly': '3.1276 GHz',
    'hz_advertised': [3127553000, 0],
    'hz_advertised_friendly': '3.1276 GHz',
    'l1_data_cache_size': '256 KiB',
    'l1_instruction_cache_size': '256 KiB',
    'l2_cache_associativity': 6,
    'l2_cache_line_size': 512,
    'l2_cache_size': '4 MiB',
    'l3_cache_size': 524288,
    'model': 113,
    'python_version': '2.7.5.final.0 (64 bit)',
    'vendor_id_raw': 'AuthenticAMD'
}


CPUINFO_ARM = {
    'arch': 'ARM_8',
    'arch_string_raw': 'aarch64',
    'bits': 64,
    'count': 2,
    'cpuinfo_version': [7, 0, 0],
    'cpuinfo_version_string': '7.0.0',
    'flags': [
        'aes',
        'asimd',
        'asimddp',
        'asimdfhm',
        'asimdhp',
        'asimdrdm',
        'atomics',
        'cpuid',
        'crc32',
        'dcpop',
        'evtstrm',
        'fcma',
        'fp',
        'fphp',
        'jscvt',
        'pmull',
        'sha1',
        'sha2'
    ],
    'l1_data_cache_size': 65536,
    'l1_instruction_cache_size': 65536,
    'l2_cache_size': 524288,
    'l3_cache_size': 33554432,
    'python_version': '2.7.5.final.0 (64 bit)'
}
