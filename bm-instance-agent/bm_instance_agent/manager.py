import json
import multiprocessing
import os
import platform
import re
import time
import yaml
from oslo_concurrency import processutils
from oslo_log import log as logging
from stevedore import driver
from zstacklib.utils import network_ipv6
from zstacklib.gpu_runtime_inventory import (
    RuntimeInventoryError,
    build_unsupported_runtime_inventory,
    build_nvidia_runtime_inventory,
    get_nvidia_runtime_inventory_cmd,
    get_nvidia_topology_cmd,
    parse_nvidia_runtime_query_output,
    runtime_inventory_to_legacy_pci_devices,
)

from .__init__ import __version__
from bm_instance_agent.common import utils as bm_utils
from bm_instance_agent.common import gpu
from bm_instance_agent.common.gpu import VendorEnum
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

GPU_RUNTIME_UNSUPPORTED_CLASSES = set([
    'VGA compatible controller',
    'Display controller',
    'Processing accelerators',
    'Co-processor',
    '3D controller',
])


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
        push_gateway_url = self.build_push_gateway_url(instance_obj.gateway_ip)
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

    @staticmethod
    def build_push_gateway_url(gateway_ip):
        return "http://%s:9092" % network_ipv6.format_url_host(gateway_ip)

    def ping(self, bm_instance, iqn_target_ip_map):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        global BM_INSTANCE_UUID
        if not BM_INSTANCE_UUID:
            BM_INSTANCE_UUID = instance_obj.uuid
        self._check_uuid_corrent(instance_obj.uuid)
        self.driver.ping(instance_obj)
        self.driver.discovery_target(instance_obj)
        if iqn_target_ip_map:
            for key, values in list(iqn_target_ip_map.items()):
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
        legacy_pci_devices = self._get_pci_info()
        gpu_inventory = self._get_gpu_inventory(ipmi_address, ipmi_port)
        if gpu_inventory:
            hardware_info['gpuInventory'] = gpu_inventory
            runtime_pci_devices = runtime_inventory_to_legacy_pci_devices(
                gpu_inventory)
            hardware_info['pciDevices'] = runtime_pci_devices or legacy_pci_devices
        else:
            hardware_info['pciDevices'] = legacy_pci_devices

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

            if not os.path.isdir(abspath):
                continue

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

    def _get_gpu_inventory(self, ipmi_address, ipmi_port):
        try:
            inventory = self._collect_nvidia_runtime_inventory(ipmi_address, ipmi_port)
            if inventory:
                return inventory
            return self._collect_unsupported_gpu_inventory(ipmi_address, ipmi_port)
        except RuntimeInventoryError as err:
            LOG.warning("failed to build runtime gpu inventory: %s", err)
        except Exception:
            LOG.exception("unexpected error while building runtime gpu inventory")
        return None

    def _collect_nvidia_runtime_inventory(self, ipmi_address, ipmi_port):
        r, _, _ = bm_utils.shell_cmd("which nvidia-smi", False)
        if r != 0:
            return None

        r, query_output, err = bm_utils.shell_cmd(
            get_nvidia_runtime_inventory_cmd(), False)
        if r != 0 or not query_output.strip():
            LOG.warning("nvidia runtime inventory query failed: %s", err)
            return None

        parsed_devices = parse_nvidia_runtime_query_output(query_output)
        pci_facts = self._get_nvidia_runtime_pci_facts(parsed_devices)
        if not pci_facts:
            return None

        r, topo_output, topo_err = bm_utils.shell_cmd(
            get_nvidia_topology_cmd(), False)
        if r != 0:
            LOG.warning("nvidia topology query failed: %s", topo_err)
            topo_output = ''

        now = int(time.time())
        observed_at = self._format_utc(now)
        valid_until = self._format_utc(now + 120)
        target_uuid = 'inspection:%s:%s' % (ipmi_address, ipmi_port)

        return build_nvidia_runtime_inventory(
            target_uuid=target_uuid,
            observation_generation=max(now, 1),
            observed_at=observed_at,
            valid_until=valid_until,
            collector_version=__version__,
            boot_id=self._get_boot_id(),
            query_output=query_output,
            topology_output=topo_output,
            pci_device_facts=pci_facts)

    def _collect_unsupported_gpu_inventory(self, ipmi_address, ipmi_port):
        vendor_names, detected_nvidia = self._detect_unsupported_gpu_vendors()
        if detected_nvidia or not vendor_names:
            return None

        vendor_names = sorted(set(vendor_names))
        reason = (
            'runtime inventory is unsupported for detected GPU vendors: %s'
            % ', '.join(vendor_names))
        now = int(time.time())
        return build_unsupported_runtime_inventory(
            target_uuid='inspection:%s:%s' % (ipmi_address, ipmi_port),
            observation_generation=max(now, 1),
            observed_at=self._format_utc(now),
            valid_until=self._format_utc(now + 120),
            collector_version=__version__,
            boot_id=self._get_boot_id(),
            vendor_names=vendor_names,
            reason=reason)

    def _detect_unsupported_gpu_vendors(self):
        vendor_names = []
        detected_nvidia = False
        r, output, err = bm_utils.shell_cmd("lspci -Dmmnn", False)
        if r != 0:
            LOG.warning("failed to probe pci devices for unsupported gpu vendors: %s", err)
            return vendor_names, detected_nvidia

        for part in output.split('\n\n'):
            pci_class = None
            vendor_id = None
            vendor_text = None
            for line in part.split('\n'):
                if len(line.split(':')) < 2:
                    continue
                title = line.split(':')[0].strip()
                content = line.split(':', 1)[1].strip()
                if title == 'Class':
                    pci_class = content.split('[')[0].strip()
                elif title == 'Vendor':
                    vendor_text = '['.join(content.split('[')[:-1]).strip()
                    vendor_id = content.split('[')[-1].strip(']').lower()

            if pci_class not in GPU_RUNTIME_UNSUPPORTED_CLASSES or not vendor_text:
                continue

            vendor_name = self._simplify_pci_device_name(vendor_text)
            if vendor_name == VendorEnum.NVIDIA or vendor_id == '10de':
                detected_nvidia = True
                continue
            vendor_names.append(vendor_name)

        return vendor_names, detected_nvidia

    def _get_nvidia_runtime_pci_facts(self, parsed_devices):
        pci_facts = {}
        shared_nodes = self._get_nvidia_shared_device_nodes()
        device_nodes_by_pci = {}
        for device in parsed_devices:
            dedicated_nodes = []
            if device.get('index') is not None:
                node = self._get_device_node_fact('/dev/nvidia%s' % device['index'])
                if node:
                    dedicated_nodes.append(node)
            device_nodes_by_pci[device['pciAddress']] = dedicated_nodes

        r, output, err = bm_utils.shell_cmd("lspci -Dmmnnv", False)
        if r != 0:
            LOG.warning("failed to read pci facts for runtime inventory: %s", err)
            return pci_facts

        for part in output.split('\n\n'):
            pci_address = None
            vendor_id = None
            device_id = None
            subsystem_vendor_id = None
            subsystem_device_id = None
            iommu_group = None
            for line in part.split('\n'):
                if len(line.split(':')) < 2:
                    continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title == 'Slot':
                    pci_address = line[5:].strip().lower()
                    group_path = os.path.join(
                        '/sys/bus/pci/devices/', pci_address, 'iommu_group')
                    group_realpath = os.path.realpath(group_path)
                    iommu_match = re.search(r'(\d+)$', group_realpath)
                    iommu_group = int(iommu_match.group(1)) if iommu_match else None
                elif title == 'Vendor':
                    vendor_id = content.split('[')[-1].strip(']').lower()
                elif title == 'Device':
                    device_id = content.split('[')[-1].strip(']').lower()
                elif title == 'SVendor':
                    subsystem_vendor_id = content.split('[')[-1].strip(']').lower()
                elif title == 'SDevice':
                    subsystem_device_id = content.split('[')[-1].strip(']').lower()

            if not pci_address or vendor_id != '10de':
                continue

            driver_loaded = bool(device_nodes_by_pci.get(pci_address))
            driver_ready = driver_loaded
            driver_reason = None if driver_ready else 'missing dedicated device node'
            pci_facts[pci_address] = {
                'vendorId': vendor_id,
                'deviceId': device_id,
                'subsystemVendorId': subsystem_vendor_id,
                'subsystemDeviceId': subsystem_device_id,
                'iommuGroup': iommu_group,
                'numaNode': self._get_numa_node(pci_address),
                'dedicatedDeviceNodes': device_nodes_by_pci.get(pci_address) or [],
                'sharedDeviceNodes': shared_nodes,
                'driverLoaded': driver_loaded,
                'driverReady': driver_ready,
                'driverReason': driver_reason,
                'extensions': {
                    'legacyInspectPath': 'bm-instance-agent'
                }
            }
        return pci_facts

    @staticmethod
    def _format_utc(timestamp):
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(timestamp))

    @staticmethod
    def _get_boot_id():
        boot_id_path = '/proc/sys/kernel/random/boot_id'
        if os.path.exists(boot_id_path):
            with open(boot_id_path, 'r') as stream:
                return stream.read().strip()
        return 'unknown-boot-id'

    @staticmethod
    def _get_numa_node(pci_address):
        numa_path = os.path.join('/sys/bus/pci/devices', pci_address, 'numa_node')
        try:
            with open(numa_path, 'r') as stream:
                value = int(stream.read().strip())
                return None if value < 0 else value
        except Exception:
            return None

    @staticmethod
    def _get_device_node_fact(path):
        if not os.path.exists(path):
            return None
        stat_result = os.stat(path)
        return {
            'path': path,
            'major': os.major(stat_result.st_rdev),
            'minor': os.minor(stat_result.st_rdev)
        }

    def _get_nvidia_shared_device_nodes(self):
        nodes = []
        for path in ['/dev/nvidiactl', '/dev/nvidia-uvm']:
            node = self._get_device_node_fact(path)
            if node:
                nodes.append(node)
        return nodes

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
                    vendor_name = self._simplify_pci_device_name(content.strip())
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
            elif "Processing accelerators" in gpu_type and gpu.is_valid_processing_accelerator(device):
                gpu_type = "GPU_Processing_Accelerators"
            else:
                gpu_type = "Generic"

            addonInfo = self._collect_gpu_addoninfo(gpu_type, pci_device_address.lower(), vendor_name)

            if addonInfo.get("device"):
                device = addonInfo["device"]
                del addonInfo["device"]

            if addonInfo.get("name"):
                name = addonInfo["name"]
                del addonInfo["name"]

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
        if gpu_type in ['GPU_3D_Controller', 'GPU_Video_Controller', 'GPU_Processing_Accelerators']:
            if vendor_name == VendorEnum.NVIDIA:
                return self._collect_nvidia_gpu_info(pci_device_address)
            if vendor_name == VendorEnum.AMD:
                return self._collect_amd_gpu_info(pci_device_address)
            if vendor_name == VendorEnum.HAIGUANG:
                return self._collect_hygon_gpu_info(pci_device_address)
            if vendor_name == VendorEnum.TIANSHU:
                return self._collect_tianshu_gpu_info(pci_device_address)
            if vendor_name == VendorEnum.HUAWEI:
                return self._collect_huawei_gpu_info(pci_device_address)
            if vendor_name == VendorEnum.ENFLAME:
                return self._collect_enflame_gpu_info(pci_device_address)

        return {}

    def _simplify_pci_device_name(self, name):
        if 'Intel Corporation' in name:
            return VendorEnum.INTEL
        elif 'Advanced Micro Devices' in name:
            return VendorEnum.AMD
        elif 'NVIDIA Corporation' in name:
            return VendorEnum.NVIDIA
        elif 'Haiguang' in name:
            return VendorEnum.HAIGUANG
        elif 'Huawei' in name:
            return VendorEnum.HUAWEI
        elif '1e3e' in name:
            return VendorEnum.TIANSHU
        elif 'Enflame' in name:
            return VendorEnum.ENFLAME
        else:
            return name.replace('Co., Ltd ', '')

    def _get_addon_info_from_gpu_infos(self, gpu_infos, pci_device_address):
        addon_info = {}
        for gpuinfo in gpu_infos:
            if pci_device_address not in gpuinfo.get("pciAddress"):
                continue
            addon_info["memory"] = gpuinfo.get("memory")
            addon_info["power"] = gpuinfo.get("power")
            addon_info["serialNumber"] = gpuinfo.get("serialNumber")
            addon_info["isDriverLoaded"] = True
        return addon_info

    def _collect_nvidia_gpu_info(self, pci_device_address):
        r, o, e = bm_utils.shell_cmd("which nvidia-smi", False)
        if r != 0:
            LOG.warning("no nvidia-smi")
            return

        r, o, e = bm_utils.shell_cmd(gpu.get_nvidia_gpu_basic_info_cmd(), False)
        if r != 0:
            LOG.error("nvidia query gpu is error, %s" % e)
            return

        return self._get_addon_info_from_gpu_infos(gpu.parse_nvidia_gpu_output(o),
                                                   pci_device_address)

    def _collect_amd_gpu_info(self, pci_device_address):
        r, o, e = bm_utils.shell_cmd("which rocm-smi", False)
        if r != 0:
            LOG.warning("no rocm-smi")
            return

        r, o, e = bm_utils.shell_cmd(gpu.get_amd_gpu_basic_info_cmd(), False)
        if r != 0:
            LOG.error("amd query gpu is error, %s" % e)
            return

        return self._get_addon_info_from_gpu_infos(gpu.parse_amd_gpu_output(o),
                                                   pci_device_address)

    def _collect_hygon_gpu_info(self, pci_device_address):
        r, o, e = bm_utils.shell_cmd("which hy-smi", False)
        if r != 0:
            LOG.warning("no hy-smi")
            return

        r, o, e = bm_utils.shell_cmd(gpu.get_hy_gpu_basic_info_cmd(), False)
        if r != 0:
            LOG.error("hy query gpu is error, %s" % e)
            return

        return self._get_addon_info_from_gpu_infos(gpu.parse_hy_gpu_output(o),
                                                   pci_device_address)

    def _collect_tianshu_gpu_info(self, pci_device_address):
        r, o, e = bm_utils.shell_cmd("which ixsmi", False)
        if r != 0:
            LOG.warning("no ixsmi")
            return

        r, o, e = bm_utils.shell_cmd(gpu.is_tianshu_v1(), False)
        if r == 0:
            cmd = gpu.get_tianshu_gpu_basic_info_cmd_v1()
        else:
            cmd = gpu.get_tianshu_gpu_basic_info_cmd_v2()
        r, o, e = bm_utils.shell_cmd(cmd, False)
        if r != 0:
            LOG.error("ixsmi query gpu is error, %s" % e)
            return

        return self._get_addon_info_from_gpu_infos(gpu.parse_tianshu_gpu_output(o),
                                                   pci_device_address)

    def _collect_huawei_gpu_info(self, pci_device_address):
        r, o, e = bm_utils.shell_cmd("which npu-smi", False)
        if r != 0:
            LOG.warning("no npu-smi")
            return

        r, npu_ids_out = bm_utils.shell_cmd(gpu.get_huawei_gpu_npu_id_cmd(), False)
        if r != 0:
            LOG.error("npu query gpu is error, %s" % npu_ids_out)
            return
        npu_ids = gpu.get_huawei_npu_id(npu_ids_out)
        if len(npu_ids) == 0:
            return

        npu_infos = []
        for npu_id in npu_ids:
            r, o, e = bm_utils.shell_cmd(gpu.get_huawei_gpu_basic_info_cmd(npu_id), False)
            if r != 0:
                LOG.error("npu query gpu board is error, %s" % e)
                return
            npu_infos.extend(gpu.parse_huawei_gpu_output_by_npu_id(o))

        device = None
        name = None
        for npu_info in npu_infos:
            if pci_device_address not in npu_info.get("pciAddress"):
                continue

            r, o, e = bm_utils.shell_cmd(gpu.get_huawei_gpu_product_name_cmd(npu_ids), False)
            if r != 0:
                LOG.error("npu-smi query gpu product type is error, %s " % e)
                return

            if "not support" in o:
                LOG.error("current gpu device not support query product")
                return

            product_type = gpu.get_huawei_product_type(o)
            if product_type:
                device = "-"
                name = product_type

        addon_info = self._get_addon_info_from_gpu_infos(npu_infos, pci_device_address)
        if device and name:
            addon_info["device"] = device
            addon_info["name"] = name

        return addon_info

    def _collect_enflame_gpu_info(self, pci_device_address):
        r, o, e = bm_utils.shell_cmd("which efsmi", False)
        if r != 0:
            LOG.warning("no efsmi, detail: %s " % o)
            return

        r, o, e = bm_utils.shell_cmd(gpu.get_enflame_gpu_info_cmd(), False)
        if r != 0:
            LOG.error("enflame query gcu is error, %s " % e)
            return

        addon_info = {}
        for info in gpu.parse_enflame_gpu_output(o):
            if pci_device_address not in info.get("pciAddress"):
                continue

            mem = info.get("memory", "")
            power = info.get("powerCap", "")
            serial = info.get("serialNumber", "")

            if mem and re.match(r"^\s*\d+\s*MiB\s*$", mem, re.IGNORECASE):
                addon_info["memory"] = mem.strip()

            if power and re.match(r"^\s*\d+(\.\d+)?\s*W\s*$", power, re.IGNORECASE):
                addon_info["power"] = power.strip()

            if serial.strip():
                addon_info["serialNumber"] = serial

            addon_info["isDriverLoaded"] = True
            break
        return addon_info
