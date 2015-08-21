'''
This file must be self-contained

@author: Frank
'''

import os
import subprocess
import sys
import logging
import traceback
import json
import time
import platform

log_path = '/var/log/zstack/appliancevm-bootstrap.log'
DEBIAN = 'debian'
CENTOS = 'CentOS'
SUPPORTED_OS = [DEBIAN, CENTOS]

dirname = os.path.dirname(log_path)
if not os.path.exists(dirname):
    os.makedirs(dirname, 0755)

logging.basicConfig(filename=log_path, level=logging.DEBUG)

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

logger = get_logger(__name__)

class BootStrapError(Exception):
    '''shell error'''
    
class ShellCmd(object):
    '''
    classdocs
    '''
    def __init__(self, cmd, workdir=None, pipe=True):
        '''
        Constructor
        '''
        self.cmd = cmd
        if pipe:
            self.process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, executable='/bin/sh', cwd=workdir)
        else:
            self.process = subprocess.Popen(cmd, shell=True, executable='/bin/sh', cwd=workdir)
            
        self.stdout = None
        self.stderr = None
        self.return_code = None
        
    def __call__(self, is_exception=True):
        logger.debug('start executing shell: %s', self.cmd)

        (self.stdout, self.stderr) = self.process.communicate()
        if is_exception and self.process.returncode != 0:
            err = []
            err.append('failed to execute shell command: %s' % self.cmd)
            err.append('return code: %s' % self.process.returncode)
            err.append('stdout: %s' % self.stdout)
            err.append('stderr: %s' % self.stderr)
            raise BootStrapError('\n'.join(err))
            
        self.return_code = self.process.returncode
        logger.debug("shell done[cmd :%s, return code: %s, stdout: %s, stderr:%s" % (self.cmd, self.return_code, self.stdout, self.stderr))
        return self.stdout

def shell(cmd, is_exception=True):
    return ShellCmd(cmd)(is_exception)

def wait_callback_success(callback, callback_data=None, timeout=60, interval=1):
    count = 0
    while count <= timeout:
        if callback(callback_data):
            return True
        time.sleep(interval)
        count += interval
    
    return False
    
def check_vr_os():
    '''
    Currently VR OS only support centos or debian
    '''
    os_dist = platform.linux_distribution()
    #Centos 7.0 will reply 'CentOS Linux'. So need to do split.
    os_name = os_dist[0].split()[0]
    return os_name

class VRBootStrap(object):
    UDEV_PERSISTENT_70_NET = '/etc/udev/rules.d/70-persistent-net.rules'
    VIRTIO_PORT_PATH = '/dev/virtio-ports/applianceVm.vport'
    BOOTSTRAP_INFO_CACHE = '/var/lib/zstack/bootstrap-info.json'
    ERROR_LOG = '/var/lib/zstack/error.log'
    
    def __init__(self):
        self.os = check_vr_os()
        if not self.os in SUPPORTED_OS:
            raise BootStrapError('VR did not support [OS:] %s' % self.os)
        
    def get_nicname_by_mac(self, nicmac):
        info = shell('ip link')
        infos = info.split('\n')
        lines = []
        for i in infos:
            i = i.strip().strip('\t').strip('\r').strip('\n')
            if i == '':
                continue
            lines.append(i)
            
        i = 0
        while(i < len(lines)):
            l1 = lines[i]
            dev_name = l1.split(':')[1].strip()
            i += 1
            l2 = lines[i]
            mac = l2.split()[1].strip()
            i += 1
            if nicmac == mac:
                return dev_name
            
        return None

    def do_centos_configure_nic(self, nicinfo):
        cfg = []
        cfg.append('DEVICE="{0}"'.format(nicinfo['name']))
        cfg.append('BOOTPROTO="static"')
        cfg.append('HWADDR="{0}"'.format(nicinfo['mac']))
        cfg.append('ONBOOT="yes"')
        cfg.append('TYPE="Ethernet"')
        cfg.append('IPADDR="{0}"'.format(nicinfo['ip']))
        cfg.append('NETMASK="{0}"'.format(nicinfo['netmask']))
        if nicinfo.has_key('gateway'):
            cfg.append('GATEWAY="{0}"'.format(nicinfo['gateway']))
         
        cfg_path = '/etc/sysconfig/network-scripts/ifcfg-%s' % nicinfo['name']
        with open(cfg_path, 'w') as fd:
            fd.write('\n'.join(cfg))
             
        shell('/sbin/ifdown {0} ; /sbin/ifup {0}'.format(nicinfo['name']))
        #TODO: calculate gateway for each device and ping its gateway
        if nicinfo.has_key('gateway'):
            self.ping(nicinfo['gateway'])
    
    def do_debian_configure_nic(self, nicinfo):
        cfg_path = '/etc/network/interfaces'

        def get_interfaces():
            with open(cfg_path, 'r') as fd:
                all_lines = fd.readlines()
            
            net_flag = 0
            interfaces = {}
            for line in all_lines:
                if line.startswith('auto'):
                    device_name = line.split()[1]
                    interfaces[device_name] = ['\n']
                    interfaces[device_name].append(line.strip('\n'))
                    net_flag = 1
                elif net_flag:
                    if line.strip() == '':
                        continue
                    interfaces[device_name].append(line.strip('\n'))

            return interfaces

        cfg = ['\n']
        cfg.append('auto {0}'.format(nicinfo['name']))
        cfg.append('iface {0} inet static'.format(nicinfo['name']))
        cfg.append('\thwaddress {0}'.format(nicinfo['mac']))
        cfg.append('\taddress {0}'.format(nicinfo['ip']))
        cfg.append('\tnetmask {0}'.format(nicinfo['netmask']))
        if nicinfo.has_key('gateway'):
            cfg.append('\tgateway {0}'.format(nicinfo['gateway']))

        interfaces = get_interfaces()
        interfaces[nicinfo['name']] = cfg

        cfg = []
        for interface in interfaces.values():
            cfg.extend(interface)

        with open(cfg_path, 'w') as fd:
            fd.write('\n'.join(cfg))
             
        shell('/sbin/ifdown {0} ; /sbin/ifup {0}'.format(nicinfo['name']))

    def ping(self, target):
        cmd = ShellCmd('ping %s -c 3 -W 1' % target)
        cmd(is_exception=False)
        if cmd.return_code != 0:
            logger.warn("failed to ping target: %s" % target)
        else:
            logger.debug("ping %s successfully" % target)

    def configure_nic(self, nic):
        nicname = self.get_nicname_by_mac(nic['mac'])
        if not nicname:
            raise BootStrapError('unable to find nic matching mac[%s]' % nic['mac'])

        nicinfo = {}
        nicinfo['name'] = nic['deviceName']
        nicinfo['ip'] = nic['ip']
        nicinfo['mac'] = nic['mac']
        nicinfo['netmask'] = nic['netmask']
        if nic['isDefaultRoute']:
            nicinfo['gateway'] = nic['gateway']

        if self.os == CENTOS:
            self.do_centos_configure_nic(nicinfo)
        elif self.os == DEBIAN:
            self.do_debian_configure_nic(nicinfo)

        try:
            shell('arping -A -U -c 1 -I %s -s %s %s' % (nic['deviceName'], nic['ip'], nic['gateway']))
        except Exception as e:
            logger.warn(str(e))

    def marshal_udev(self, nics):
        def mkdirs():
            dirname = os.path.dirname(self.UDEV_PERSISTENT_70_NET)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0755)
                
        def write_udev_persistent_70_net():
            info = []
            for nic in nics:
                i = 'SUBSYSTEM=="net", ACTION=="add", DRIVERS=="?*", ATTR{{address}}=="{0[mac]}", NAME="{0[deviceName]}"'.format(nic)
                info.append(i)
            
            with open(self.UDEV_PERSISTENT_70_NET, 'w') as fd:
                fd.write('\n'.join(info))
                
        def check_and_rewrite_nic_script():
            ret = False
            for nic in nics:
                nic_name = self.get_nicname_by_mac(nic['mac'])
                if nic_name != nic['deviceName']:
                    if self.os == CENTOS:
                        old = '/etc/sysconfig/network-scripts/ifcfg-%s' % nic_name
                        dst = '/etc/sysconfig/network-scripts/ifcfg-%s' % nic['deviceName']
                        if os.path.exists(old):
                            shell('mv {0} {1}'.format(old, dst))
                    ret = True
                    
            return ret
        
        mkdirs()
        if check_and_rewrite_nic_script():
            write_udev_persistent_70_net()
            shell('/usr/bin/reboot')
    
    def read_bootstrap_info(self):
        ret = {}

        with open(self.VIRTIO_PORT_PATH, 'r') as fd:
            def read_info(data):
                text = fd.read()
                if not text:
                    return False
                
                bootstrap_obj = json.loads(text)
                data['ret'] = bootstrap_obj
                shell('mkdir -p %s' % os.path.dirname(self.BOOTSTRAP_INFO_CACHE))
                with open(self.BOOTSTRAP_INFO_CACHE, 'w') as bd:
                    bd.write(text)

                return True

            #when zstack send vr boot command, it will ask host to set virio
            #data. If the network is very busy, the virio data setting might be
            #blocked for a while.
            if wait_callback_success(read_info, ret, 300, 1):
                return ret['ret']
            
            raise Exception('Cannot read bootstrap info from[%s] in 60 seconds' % self.VIRTIO_PORT_PATH)
    
    def configure_public_key(self, pub_key):
        ssh_path = '/root/.ssh'
        if not os.path.exists(ssh_path):
            os.makedirs(ssh_path, 0700)
        
        auth_file = os.path.join(ssh_path, 'authorized_keys')
        with open(auth_file, 'w') as fd:
            fd.write(pub_key)

        shell('chmod 0600 {0}'.format(auth_file))

    def wait_for_iptables_come_up(self):
        def test_iptables(variable):
            cmd = ShellCmd('iptables-save')
            cmd(False)
            return cmd.return_code == 0

        if not wait_callback_success(test_iptables, None, 120, 0.5):
            raise Exception('iptables service does not come up after 120 secs')

    def wait_for_virtio_port_come_up(self):
        def test_file(_):
            return os.path.exists(self.VIRTIO_PORT_PATH)

        if not wait_callback_success(test_file, None, 120, 0.5):
            raise Exception('%s does not exist after 120 secs' % self.VIRTIO_PORT_PATH)

    def main(self):
        mgmt_nic_info = None
        public_key_info = None
        try:
            self.wait_for_iptables_come_up()
            logger.debug("iptables is ready")
            self.wait_for_virtio_port_come_up()
            logger.debug("virtio-channel is ready")

            bootstrap_info = self.read_bootstrap_info()
            logger.debug("bootstrap info is loaded")
            public_key_info = bootstrap_info['publicKey']

            nics = []
            mgmt_nic_info = bootstrap_info['managementNic']
            nics.append(mgmt_nic_info)
            nics.extend(bootstrap_info['additionalNics'])

            self.marshal_udev(nics)
            logger.debug("udev is ready")
            for nic in nics:
                self.configure_nic(nic)
                logger.debug("configured nic[name: %s, ip:%s]" % (nic['deviceName'], nic['ip']))


            shell('grep "^ListenAddress" /etc/ssh/sshd_config >/dev/null || echo "ListenAddress 0.0.0.0" >> /etc/ssh/sshd_config')
            shell('sed -i "s/ListenAddress.*/ListenAddress %s/g" /etc/ssh/sshd_config' % mgmt_nic_info['ip'])
            shell('service sshd restart')

            self.configure_public_key(public_key_info)
            logger.debug("configured public ssh-key")
            shell('rm -f %s' % self.ERROR_LOG)
            logger.debug("the appliance vm initialized successfully")
        except Exception as e:
            logger.warn(traceback.format_exc())

            # try best to configure mgmt nic and write down error info
            # so mgmt server doesn't need to wait for VR startup timeout
            if mgmt_nic_info and public_key_info:
                with open(self.ERROR_LOG, 'w') as fd:
                    fd.write(str(e))

                self.configure_nic(mgmt_nic_info)
                self.configure_public_key(public_key_info)

            raise e


if __name__ == '__main__':
    try:
        VRBootStrap().main()
    except:
        logger.warn(traceback.format_exc())
        logger.warn('unable to bootstrap appliance vm')
        sys.exit(1)
        
    sys.exit(0)
