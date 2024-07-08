import json
import multiprocessing
import os
import platform
import yaml
from oslo_concurrency import processutils
from oslo_log import log as logging
from stevedore import driver

from __init__ import __version__
from bm_instance_agent.common import utils as bm_utils
from bm_instance_agent import exception
from bm_instance_agent.objects import BmInstanceObj, PortObj
from bm_instance_agent.objects import NetworkObj
from bm_instance_agent.objects import VolumeObj

LOG = logging.getLogger(__name__)

BM_INSTANCE_UUID = None
DRIVER = None
ZWATCH_AGENT_CONF_PATH = "/usr/local/zstack/zwatch-vm-agent/conf.yaml"

pxe_iface_mac = ''

units_mapping = {
    'kb': 1024,
    'mb': 1024 * 1024,
    'gb': 1024 * 1024 * 1024
}


class AgentManager(object):

    def __init__(self):
        global DRIVER
        if not DRIVER:
            DRIVER = self._load_driver()
        self.driver = DRIVER

    def _load_driver(self):
        return driver.DriverManager(
            namespace='bm_instance_agent.systems.driver',
            name=bm_utils.get_distro(),
            invoke_on_load=True).driver

    def _check_uuid_corrent(self, bm_uuid):
        global BM_INSTANCE_UUID
        if not BM_INSTANCE_UUID == bm_uuid:
            raise exception.BmInstanceUuidConflict(
                req_instance_uuid=bm_uuid,
                exist_instance_uuid=BM_INSTANCE_UUID)

    def _check_gateway_ip(self, instance_obj):
        push_gateway_url = "http://%s:9092" % instance_obj.gateway_ip
        with open(ZWATCH_AGENT_CONF_PATH) as f:
            doc = yaml.load(f)

        old_url = doc.get('pushGatewayUrl')
        old_uuid = doc.get('bm2InstanceUuid')
        if old_url is not None and old_url == push_gateway_url \
                and old_uuid is not None and old_uuid == instance_obj.uuid:
            return

        LOG.info("pushGatewayUrl and bmInstanceUuid changed from %s to %s, %s to %s" %
                 (old_url, push_gateway_url, old_uuid, instance_obj.uuid))
        doc['pushGatewayUrl'] = push_gateway_url
        doc['bm2InstanceUuid'] = instance_obj.uuid

        with open(ZWATCH_AGENT_CONF_PATH, 'w') as f:
            yaml.safe_dump(doc, f, encoding='utf-8', allow_unicode=True)
            # f.write("\npushGatewayUrl: %s\nbm2InstanceUuid: %s\n" % (push_gateway_url, instance_obj.uuid))

        cmd = 'service zwatch-vm-agent restart'
        processutils.execute(cmd, shell=True)

    def ping(self, bm_instance, iqn_target_ip_map):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        global BM_INSTANCE_UUID
        if not BM_INSTANCE_UUID:
            BM_INSTANCE_UUID = instance_obj.uuid
        self._check_uuid_corrent(instance_obj.uuid)
        self.driver.ping(instance_obj)
        self.driver.discovery_target(instance_obj)
        if iqn_target_ip_map:
            for key, values in iqn_target_ip_map.items():
                self.driver.discovery_target_through_access_path_gateway_ips(key, values)
        self._check_gateway_ip(instance_obj)
        return {'version': __version__, 'ping': {'bmInstanceUuid': BM_INSTANCE_UUID}}

    def reboot(self, bm_instance):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to reboot the system: '
               '{bm_uuid}').format(bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.reboot(instance_obj)

    def stop(self, bm_instance):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to stop the system: '
               '{bm_uuid}').format(bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.stop(instance_obj)

    def attach_volume(self, bm_instance, volume, volume_access_path_gateway_ips):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        volume_obj = VolumeObj.from_json(volume)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to attach the volume: {volume_uuid} '
               'to the system: {bm_uuid}').format(
            volume_uuid=volume_obj.uuid, bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.attach_volume(instance_obj, volume_obj, volume_access_path_gateway_ips)

    def detach_volume(self, bm_instance, volume, volume_access_path_gateway_ips):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        volume_obj = VolumeObj.from_json(volume)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to detach the volume: {volume_uuid} '
               'from the system: {bm_uuid}').format(
            volume_uuid=volume_obj.uuid, bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.detach_volume(instance_obj, volume_obj, volume_access_path_gateway_ips)

    def attach_port(self, bm_instance, port):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        network_obj = NetworkObj.from_json(port)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to attach port: {port_mac} '
               'to the system: {bm_uuid}').format(
            bm_uuid=instance_obj.uuid,
            port_mac=[x.mac for x in network_obj.ports])
        LOG.info(msg)
        self.driver.attach_port(instance_obj, network_obj)

    def detach_port(self, bm_instance, port):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        network_obj = NetworkObj.from_json(port)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to detach port: {port_mac} '
               'from the system: {bm_uuid}').format(
            bm_uuid=instance_obj.uuid,
            port_mac=[x.mac for x in network_obj.ports])
        LOG.info(msg)
        self.driver.detach_port(instance_obj, network_obj)
        # provision nic detached from bond, config static ip for provision nic
        if instance_obj.provision_mac == network_obj.ports[0].mac:
            port = network_obj.ports[0]
            port.type = PortObj.PORT_TYPE_PHY
            port.iface_name = bm_utils.get_interface_by_mac(instance_obj.provision_mac)
            self.driver.attach_port(instance_obj, network_obj)

    def update_default_route(
            self, bm_instance, old_default_port, new_default_port):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        old_network_obj = NetworkObj.from_json(old_default_port)
        new_network_obj = NetworkObj.from_json(new_default_port)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to update the gateway from the system: '
               '{bm_uuid}').format(bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.update_default_route(
            instance_obj, old_network_obj, new_network_obj)

    def update_password(self, bm_instance, username, password):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to update user password')
        LOG.info(msg)
        self.driver.update_password(instance_obj, username, password)

    def console(self):
        msg = ('Call the driver to start console')
        LOG.info(msg)
        return self.driver.console()

    def inspect(self, provision_network, ipmi_address, ipmi_port):
        LOG.info("start to inspect hardwardinfo for baremetal chassis")
        result = {'ipmiAddress': ipmi_address, 'ipmiPort': ipmi_port}

        hardware_info = {}
        hardware_info.update(self._get_basic_info())
        hardware_info['nics'] = self._get_nic_info(provision_network)
        hardware_info['disks'] = self._get_disk_info()
        hardware_info['pciDevices'] = self._get_pci_info()

        result['hardwareInfo'] = json.dumps(hardware_info)
        LOG.info("inspect baremetal chassis hardwardinfo: %s successfully", result)
        return result

    def _get_basic_info(self):
        arch = os.uname()[-1]
        cpu_model_name = ''
        cpu_num = multiprocessing.cpu_count()
        memory_bytes = 0

        # Get memory total
        if platform.machine() == 'aarch64':
            with open('/proc/meminfo', 'r') as f:
                for line in f.readlines():
                    if 'MemTotal' in line:
                        _, size, unit = line.lower().split()
                        memory_bytes = int(size) * units_mapping[unit]
                        break
        else:
            _, stdout, _ = bm_utils.shell_cmd('dmidecode --type memory')
            for line in stdout.split('\n'):
                line = line.lower().strip()
                if line.startswith('size') and 'no module' not in line:
                    _, size, unit = line.split()
                    memory_bytes += int(size) * units_mapping[unit]

        with open('/proc/cpuinfo', 'r') as f:
            for line in f.readlines():
                if 'model name' in line:
                    cpu_model_name = line.split(':')[1].strip()
                    break

        return {
            'architecture': arch,
            'cpuModelName': cpu_model_name,
            'cpuNum': str(cpu_num),
            'memorySize': str(memory_bytes),
            'bootMode': self._get_boot_mode()
        }

    def _get_nic_info(self, provision_net):
        # Get the pxe interface from /proc/cmdline
        # NOTE: Need to point that the mac addr should start with '01', because
        # the arp type of ethernet is 1.
        global pxe_iface_mac
        with open('/proc/cmdline', 'r') as f:
            for param in f.read().strip().split():
                if 'BOOTIF' in param:
                    pxe_iface_mac = param.split('=')[-1].replace('-', ':')

        net_devs = []
        for net_dev in os.listdir('/sys/class/net'):
            abspath = os.path.join('/sys/class/net', net_dev)

            realpath = os.path.realpath(abspath)
            if 'virtual' in realpath or (net_dev == 'lo'):
                continue

            try:
                with open(os.path.join(abspath, 'speed'), 'r') as f:
                    speed = '%sMb/s' % f.read().strip()
            except Exception:
                speed = 'UNKNOWN'
            with open(os.path.join(abspath, 'address'), 'r') as f:
                mac_address = f.read().strip()

            if len(mac_address) > 32:
                continue
            rc, _, _ = bm_utils.shell_cmd("""arping -c 5 -I {} {}""".format(net_dev, provision_net), False)
            if rc == 0 and not pxe_iface_mac:
                is_provision_nic = True
                pxe_iface_mac = mac_address

            is_provision_nic = True if mac_address in pxe_iface_mac else False

            net_devs.append({
                'nicName': net_dev,
                'nicMac': mac_address,
                'nicSpeed': speed,
                'isProvisionNic': is_provision_nic
            })
        return net_devs

    def _get_disk_info(self):
        block_devs = []

        cmd = 'lsblk --nodeps --byte --output name,size,rota,type,wwn'
        _, stdout, _ = bm_utils.shell_cmd(cmd)
        for line in stdout.split('\n')[1:]:
            if len(line.split()) != 5:
                continue
            name, size, rotation, blk_type, wwn = line.split()

            if blk_type.lower() != 'disk':
                continue

            disk_type = 'SSD' if rotation == '0' else 'HDD'
            # get longest wwn
            _, output, _ = bm_utils.shell_cmd(
                "ls -l /dev/disk/by-id | grep -e wwn -e nvme-eui | grep %s | awk 'NR==1 {print $9}'" % name)
            if output != '':
                wwn = output.split("-")[1]
            block_devs.append({
                'diskType': disk_type,
                'diskSize': size,
                'wwn': wwn
            })

        return block_devs

    def _get_boot_mode(self):
        if os.path.exists('/sys/firmware/efi'):
            return 'UEFI'
        return 'Legacy'

    def _get_pci_info(self):
        pci_device_address = ""
        vendor_id = ""
        device_id = ""
        vendor = ""
        device = ""
        sub_vendor_id = ""
        sub_device_id = ""
        iommu_group = ""
        description = ""
        gpu_type = ""
        gpu_devs = []
        r, o, e = bm_utils.shell_cmd("lspci -Dmmnnv", False)
        if r != 0:
            return
        # parse lspci output
        for part in o.split('\n\n'):
            vendor_name = ""
            device_name = ""
            sub_vendor_name = ""
            for line in part.split('\n'):
                if len(line.split(':')) < 2: continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title == 'Slot':
                    content = line[5:].strip()
                    pci_device_address = content
                    group_path = os.path.join('/sys/bus/pci/devices/', pci_device_address, 'iommu_group')
                    iommu_group = os.path.realpath(group_path)
                elif title == 'Class':
                    _class = content.split('[')[0].strip()
                    gpu_type = _class
                    description = _class + ": "
                elif title == 'Vendor':
                    vendor_name = self._simplify_pci_device_name('['.join(content.split('[')[:-1]).strip())
                    vendor = vendor_name
                    vendor_id = content.split('[')[-1].strip(']')
                    description += vendor_name + " "
                elif title == "Device":
                    device = content
                    device_name = self._simplify_pci_device_name('['.join(content.split('[')[:-1]).strip())
                    device_id = content.split('[')[-1].strip(']')
                    description += device_name
                elif title == "SVendor":
                    sub_vendor_name = self._simplify_pci_device_name('['.join(content.split('[')[:-1]).strip())
                    sub_vendor_id = content.split('[')[-1].strip(']')
                elif title == "SDevice":
                    sub_device_id = content.split('[')[-1].strip(']')
            name = "%s_%s" % (sub_vendor_name if sub_vendor_name else vendor_name, device_name)

            gpu_vendors = ["NVIDIA", "AMD", "Haiguang"]
            if any(vendor in description for vendor in gpu_vendors) \
                    and ('VGA compatible controller' in gpu_type or 'Display controller' in gpu_type):
                gpu_type = "GPU_Video_Controller"
            elif any(vendor in description for vendor in gpu_vendors) \
                    and ('3D controller' in gpu_type):
                gpu_type = "GPU_3D_Controller"
            else:
                gpu_type = "Generic"

            addonInfo = self._collect_gpu_addoninfo(gpu_type, pci_device_address, vendor_name)

            if vendor_id != '' and device_id != '' and gpu_type != 'Generic':
                gpu_devs.append({
                    'name': name,
                    'description': description,
                    'vendorId': vendor_id,
                    'vendor': vendor,
                    'deviceId': device_id,
                    'device': device,
                    'subVendorId': sub_vendor_id,
                    'subDeviceId': sub_device_id,
                    'pciDeviceAddress': pci_device_address,
                    'iommuGroup': iommu_group,
                    'type': gpu_type,
                    'addonInfo': addonInfo
                })
        return gpu_devs

    def _collect_gpu_addoninfo(self, gpu_type, pci_device_address, vendor_name):
        addonInfo = {}
        if gpu_type in ['GPU_3D_Controller', 'GPU_Video_Controller']:
            if vendor_name == 'NVIDIA':
                return self._collect_nvidia_gpu_info(pci_device_address, addonInfo)
            if vendor_name == 'AMD':
                return self._collect_amd_gpu_info(pci_device_address, addonInfo)
            if vendor_name == 'Haiguang':
                return self._collect_hygon_gpu_info(pci_device_address, addonInfo)
        return addonInfo

    def _simplify_pci_device_name(self, name):
        if 'Intel Corporation' in name:
            return 'Intel'
        elif 'Advanced Micro Devices' in name:
            return 'AMD'
        elif 'NVIDIA Corporation' in name:
            return 'NVIDIA'
        elif 'Haiguang' in name:
            return 'Haiguang'
        else:
            return name.replace('Co., Ltd ', '')

    def _collect_nvidia_gpu_info(self, pci_device_address, addon_info):
        r, o, e = bm_utils.shell_cmd("which nvidia-smi", False)
        if r != 0:
            return

        r, o, e = bm_utils.shell_cmd("nvidia-smi --query-gpu=gpu_bus_id,memory.total,power.limit,gpu_serial"
                                     " --format=csv,noheader", False)
        if r != 0:
            return

        for part in o.split('\n'):
            if len(part.strip()) == 0:
                continue
            gpuinfo = part.split(',')
            if pci_device_address in gpuinfo[0].strip():
                addon_info["memory"] = gpuinfo[1].strip()
                addon_info["power"] = gpuinfo[2].strip()
                addon_info["serialNumber"] = gpuinfo[3].strip()
        return addon_info

    def _collect_amd_gpu_info(self, pci_device_address, addon_info):
        r, o, e = bm_utils.shell_cmd("which rocm-smi", False)
        if r != 0:
            return

        r, o, e = bm_utils.shell_cmd("rocm-smi --showbus --showmeminfo vram --showpower --showserial --json",
                                     False)
        if r != 0:
            return

        gpu_info_json = json.loads(o.strip())
        for card_name, card_data in gpu_info_json.items():
            if pci_device_address.lower() in card_data['PCI Bus'].lower():
                addon_info["memory"] = card_data['VRAM Total Memory (B)']
                addon_info["power"] = card_data['Average Graphics Package Power (W)']
                addon_info["serialNumber"] = card_data['Serial Number']
        return addon_info

    def _collect_hygon_gpu_info(self, pci_device_address, addon_info):
        r, o, e = bm_utils.shell_cmd("which hy-smi", False)
        if r != 0:
            return

        r, o, e = bm_utils.shell_cmd("hy-smi --showbus --showmeminfo vram --showpower --showserial --json",
                                     False)
        if r != 0:
            return

        gpu_info_json = json.loads(o.strip())
        for card_name, card_data in gpu_info_json.items():
            if pci_device_address.lower() in card_data['PCI Bus'].lower():
                addon_info["memory"] = card_data['vram Total Memory (MiB)']
                addon_info["power"] = card_data['Average Graphics Package Power (W)']
                addon_info["serialNumber"] = card_data['Serial Number']
        return addon_info
