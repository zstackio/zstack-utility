'''
Hygon Device Plugin - standalone Hygon CCP device management plugin

@author: malin
@date: 2025
'''

from kvmagent import kvmagent
from zstacklib.utils import bash, http, linux
from zstacklib.utils.jsonobject import JsonObject
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils.bash import *
import os
import functools

logger = log.get_logger(__name__)


def require_hygon_tools(response_class):
    """
    Decorator to check if Hygon tools are available before executing endpoint methods.

    This decorator eliminates the need for manual "if not self.tools_available" checks
    in each endpoint method.

    Args:
        response_class: The response class to instantiate if tools are unavailable

    Usage:
        @require_hygon_tools(GetHygonCcpDevicesResponse)
        @kvmagent.replyerror
        @in_bash
        def get_hygon_ccp_devices(self, req):
            # Method implementation without manual tool checking
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            tools_status = self._get_tools_status()
            if not tools_status['available']:
                rsp = response_class()
                rsp.success = False
                rsp.error = "Hygon tools not available. Missing tools: %s" % (
                    ", ".join(tools_status['missing'])
                )
                return jsonobject.dumps(rsp)
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


class GetHygonCcpDevicesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetHygonCcpDevicesResponse, self).__init__()
        self.devices = []


class GenerateHygonMdevDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GenerateHygonMdevDevicesRsp, self).__init__()
        self.mdevBindings = []
        self.generated = False


class UngenerateHygonMdevDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UngenerateHygonMdevDevicesRsp, self).__init__()


class CheckHygonToolsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckHygonToolsResponse, self).__init__()
        self.available = False
        self.tools = {}
        self.missingTools = []


class HygonDevicePlugin(kvmagent.KvmAgent):
    """
    Hygon CCP Device Plugin

    Manages Hygon CCP (Cryptographic Co-Processor) devices and their mdev virtualization.
    This plugin is loaded independently and only activates if Hygon tools are available.
    """

    # Hygon tool paths (hardcoded, following project style)
    HCT_CCP_BIND_SCRIPT = "/opt/hygon/hct/hct/script/hct_ccp_bind.py"
    HCTCONFIG_SCRIPT = "/opt/hygon/hct/hct/script/hctconfig"
    HCT_START_QEMU_SCRIPT = "/opt/hygon/hct/hct/script/start_qemu.py"

    # HTTP endpoints
    GET_HYGON_CCP_DEVICES = "/hygonccpdevice/get"
    GENERATE_HYGON_MDEV_DEVICES = "/hygonmdevdevice/generate"
    UNGENERATE_HYGON_MDEV_DEVICES = "/hygonmdevdevice/ungenerate"
    CHECK_HYGON_TOOLS = "/hygontools/check"

    # Hygon CCP Device IDs (from hct_ccp_bind.py output)
    # These IDs are used to verify we're detecting genuine Hygon CCP devices
    HYGON_VENDOR_NAME = "Chengdu Haiguang IC Design Co., Ltd."
    HYGON_CCP_DEVICE_IDS = {
        "1456": "PSPCCP Command DMA Processor",
        "1468": "NTBCCP"
    }

    # Mdev use flag constants (from sysfs vendor/use attribute)
    MDEV_USED_BY_VM = 1  # Passthrough to vm

    def __init__(self):
        self.config = None
        self.tools_available = False

    def configure(self, config):
        self.config = config

    def start(self):
        """Initialize plugin and register HTTP routes if tools are available"""
        self.tools_available = self._check_tools_availability()

        if not self.tools_available:
            logger.warning("Hygon tools not available, plugin will not handle requests")
            return

        # Register HTTP routes
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.GET_HYGON_CCP_DEVICES, self.get_hygon_ccp_devices)
        http_server.register_async_uri(self.GENERATE_HYGON_MDEV_DEVICES, self.generate_hygon_mdev_devices)
        http_server.register_async_uri(self.UNGENERATE_HYGON_MDEV_DEVICES, self.ungenerate_hygon_mdev_devices)
        http_server.register_async_uri(self.CHECK_HYGON_TOOLS, self.check_hygon_tools)

        logger.info("Hygon device plugin started successfully")

    def stop(self):
        """Cleanup when plugin stops"""
        pass

    def _get_tools_status(self):
        """
        Get detailed Hygon tools availability status

        Returns:
            dict: {
                'available': bool,      # True if all tools are available
                'tools': {              # Tool paths and their existence status
                    'hct_ccp_bind': {'path': str, 'exists': bool},
                    'hctconfig': {'path': str, 'exists': bool},
                    'start_qemu': {'path': str, 'exists': bool}
                },
                'missing': [str],       # List of missing tool paths
            }
        """
        hct_exists = os.path.exists(self.HCT_CCP_BIND_SCRIPT)
        hctconfig_exists = os.path.exists(self.HCTCONFIG_SCRIPT)
        start_qemu_exists = os.path.exists(self.HCT_START_QEMU_SCRIPT)

        tools = {
            'hct_ccp_bind': {
                'path': self.HCT_CCP_BIND_SCRIPT,
                'exists': hct_exists
            },
            'hctconfig': {
                'path': self.HCTCONFIG_SCRIPT,
                'exists': hctconfig_exists
            },
            'start_qemu': {
                'path': self.HCT_START_QEMU_SCRIPT,
                'exists': start_qemu_exists
            }
        }

        missing = []
        if not hct_exists:
            missing.append(self.HCT_CCP_BIND_SCRIPT)
        if not hctconfig_exists:
            missing.append(self.HCTCONFIG_SCRIPT)
        if not start_qemu_exists:
            missing.append(self.HCT_START_QEMU_SCRIPT)

        available = hct_exists and hctconfig_exists and start_qemu_exists

        if available:
            logger.debug("Hygon tools are available: %s, %s and %s" % (
                self.HCT_CCP_BIND_SCRIPT, self.HCTCONFIG_SCRIPT, self.HCT_START_QEMU_SCRIPT))
        else:
            logger.debug("Hygon tools not available. Missing: %s" % ", ".join(missing))

        return {
            'available': available,
            'tools': tools,
            'missing': missing
        }

    def _check_tools_availability(self):
        """
        Check if Hygon tools (hct_ccp_bind.py and hctconfig) are available

        This is a simple wrapper for backward compatibility.
        For detailed status, use _get_tools_status() instead.

        Returns:
            bool: True if all tools are available, False otherwise
        """
        return self._get_tools_status()['available']

    def _check_hygon_ccp_devices_exist(self):
        """
        Check if genuine Hygon CCP devices exist on the system

        This method performs a more rigorous check than simple grep to avoid false positives.
        It validates both vendor name and device IDs to ensure we only detect Hygon CCP devices.

        Checks performed:
            1. Search for Hygon vendor name in lspci output
            2. Verify device IDs match known Hygon CCP device types (PSPCCP/NTBCCP)

        lspci Output Format:
            05:00.2 Encryption controller: Chengdu Haiguang IC Design Co., Ltd. PSPCCP Command DMA Processor
            06:00.1 Encryption controller: Chengdu Haiguang IC Design Co., Ltd. NTBCCP

        Returns:
            bool: True if Hygon CCP devices found, False otherwise
        """
        # First, check if there are any devices from Hygon vendor
        r, o, e = bash_roe("timeout 60 lspci | grep '%s'" % self.HYGON_VENDOR_NAME)
        if r == 124:
            logger.warn("lspci command timeout after 60s when checking vendor: %s" % self.HYGON_VENDOR_NAME)
            return False
        if r != 0 or not o.strip():
            logger.debug("No devices found from vendor: %s" % self.HYGON_VENDOR_NAME)
            return False

        # Second, verify that these devices are CCP devices by checking device IDs
        # Use lspci -nn to get numeric device IDs
        r, o, e = bash_roe("timeout 60 lspci -nn | grep '%s'" % self.HYGON_VENDOR_NAME)
        if r == 124:
            logger.warn("lspci -nn command timeout after 60s when checking vendor: %s" % self.HYGON_VENDOR_NAME)
            return False
        if r != 0:
            logger.debug("Failed to get detailed device info via lspci -nn for vendor: %s" % self.HYGON_VENDOR_NAME)
            return False

        # Check if any line contains known CCP device IDs
        lines = o.strip().split('\n')
        for line in lines:
            for device_id in self.HYGON_CCP_DEVICE_IDS.keys():
                if device_id in line:
                    logger.debug("Found Hygon CCP device (ID: %s) in: %s" % (device_id, line))
                    return True

        logger.debug("Found vendor devices but none match known CCP device IDs: %s" % list(self.HYGON_CCP_DEVICE_IDS.keys()))
        return False

    def _parse_ccp_devices(self):
        """
        Parse CCP devices from hct_ccp_bind.py -s output

        Script Command:
            python /opt/hygon/hct/hct/script/hct_ccp_bind.py -s

        Expected Output Format:
            The script outputs device information grouped by categories.
            We focus on "Crypto devices" sections (all types).

            Example output:
            -----------------------------------------------------------------------
            Crypto devices using DPDK-compatible driver
            ===========================================
            0000:06:00.1 'NTBCCP 1468' drv=hct unused=vfio-pci
            0000:23:00.2 'PSPCCP Command DMA Processor 1456' drv=hct unused=vfio-pci
            0000:24:00.1 'NTBCCP 1468' drv=hct unused=vfio-pci

            Crypto devices using kernel driver
            ==================================
            0000:05:00.2 'PSPCCP Command DMA Processor 1456' drv=ccp unused=vfio-pci,hct

            Other Crypto devices
            ====================
            0000:06:00.1 'NTBCCP 1468' unused=vfio-pci
            0000:42:00.2 'PSPCCP Command DMA Processor 1456' unused=vfio-pci
            -----------------------------------------------------------------------

        Parsing Logic:
            Each device line format: <PCI_BDF> '<Device_Name>' [drv=<driver>] unused=<unused>
            - Device name is enclosed in single quotes and may contain spaces
            - Device ID is the last word in the device name (e.g., "1468", "1456")
            - drv= field may be absent (in "Other Crypto devices" section)
            - Uses regex to handle spaces in device names correctly

        Returns:
            list: List of CCP device dictionaries with keys:
                - pciBdf (str): PCI address (e.g., "0000:06:00.1")
                - deviceType (str): Device type - first word only (e.g., "NTBCCP" or "PSPCCP")
                - deviceId (str): Device ID without quotes (e.g., "1468", "1456")
                - driverStatus (str): Current driver binding (e.g., "drv=hct", "drv=ccp", "drv=none")

        Raises:
            Exception: If failed to execute hct_ccp_bind.py or parse output
        """
        import re

        r, o, e = bash_roe("timeout 60 python %s -s" % self.HCT_CCP_BIND_SCRIPT)
        if r == 124:
            raise Exception("hct_ccp_bind.py -s timeout after 60s")
        if r != 0:
            raise Exception("failed to get CCP devices: %s" % e)

        devices = []
        lines = o.strip().split('\n')

        # Regex pattern to match device lines:
        # Example 1: 0000:06:00.1 'NTBCCP 1468' drv=hct unused=vfio-pci
        # Example 2: 0000:05:00.2 'PSPCCP Command DMA Processor 1456' drv=ccp unused=vfio-pci
        # Example 3: 0000:06:00.1 'NTBCCP 1468' unused=vfio-pci (no drv= field)
        # Pattern: PCI_BDF 'DEVICE_NAME DEVICE_ID' [drv=DRIVER] unused=...
        pattern = r"^([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9])\s+'([^']+\s+(\w+))'\s+(?:drv=(\S+)\s+)?unused="

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line, re.IGNORECASE)
            if not match:
                logger.debug("skip non-device line from script output: %s" % line)
                continue

            pci_bdf = match.group(1)
            device_name_with_id = match.group(2)  # e.g., "NTBCCP 1468" or "PSPCCP Command DMA Processor 1456"
            device_id = match.group(3)  # Last word is the device ID
            driver = match.group(4) if match.group(4) else "none"  # drv= field may be absent

            # Extract device type: only take the first word (e.g., "PSPCCP" or "NTBCCP")
            device_type = device_name_with_id.split()[0]

            devices.append({
                'pciBdf': pci_bdf,
                'deviceType': device_type,
                'deviceId': device_id,
                'driverStatus': 'drv=' + driver
            })
            logger.debug("Parsed CCP device: pciBdf=%s, deviceType=%s, deviceId=%s, driverStatus=%s" %
                        (pci_bdf, device_type, device_id, 'drv=' + driver))

        return devices

    @require_hygon_tools(GetHygonCcpDevicesResponse)
    @kvmagent.replyerror
    @in_bash
    def get_hygon_ccp_devices(self, req):
        """
        Get Hygon CCP devices list

        This endpoint queries the host for available Hygon CCP devices using hct_ccp_bind.py.

        Scripts Used:
            1. lspci | grep 'Chengdu Haiguang IC Design Co., Ltd.'
               - Check for Hygon vendor devices
               - Prevents false positives from devices with "CCP" in other names

            2. lspci -nn | grep 'Chengdu Haiguang IC Design Co., Ltd.'
               - Get numeric device IDs: [1d94:1456] or [1d94:1468]
               - Validates device IDs against known CCP types:
                 * 1456: PSPCCP Command DMA Processor
                 * 1468: NTBCCP
               - Only proceed if genuine Hygon CCP devices found

            3. python /opt/hygon/hct/hct/script/hct_ccp_bind.py -s
               - Lists all CCP devices with detailed information
               - See _parse_ccp_devices() for output format details

            4. python /opt/hygon/hct/hct/script/hct_ccp_bind.py --get_master_pspccp
               - Returns the PCI address of the master PSP device
               - Output format: Single line with PCI BDF (e.g., "0000:05:00.2")
               - Used to mark which device is the master PSP

        Response Format:
            {
                "success": true,
                "error": "",
                "devices": [
                    {
                        "pciBdf": "0000:06:00.1",
                        "deviceType": "NTBCCP",
                        "deviceId": "1468",
                        "driverStatus": "drv=hct",
                        "isMasterPsp": false,
                        "vendorIdx": null,
                        "state": "Enabled"
                    },
                    {
                        "pciBdf": "0000:05:00.2",
                        "deviceType": "PSPCCP",
                        "deviceId": "1456",
                        "driverStatus": "drv=ccp",
                        "isMasterPsp": true,
                        "vendorIdx": null,
                        "state": "Enabled"
                    },
                    ...
                ]
            }
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetHygonCcpDevicesResponse()

        # Check if there are genuine Hygon CCP devices
        # This performs vendor and device ID validation to avoid false positives
        if not self._check_hygon_ccp_devices_exist():
            # No Hygon CCP devices found
            rsp.devices = []
            return jsonobject.dumps(rsp)

        # Parse CCP devices using helper method
        try:
            ccp_device_list = self._parse_ccp_devices()
        except Exception as e:
            rsp.success = False
            rsp.error = str(e)
            return jsonobject.dumps(rsp)

        # Check if parsing returned any devices (TOCTOU protection)
        if not ccp_device_list:
            rsp.devices = []
            return jsonobject.dumps(rsp)

        # Convert to JsonObject format
        logger.info("ccp_device_list = %s", ccp_device_list)
        devices = []
        for device_info in ccp_device_list:
            device = jsonobject.JsonObject()
            device.pciBdf = device_info['pciBdf']
            device.deviceType = device_info['deviceType']
            device.deviceId = device_info['deviceId']
            device.driverStatus = device_info['driverStatus']
            device.isMasterPsp = False
            device.vendorIdx = None
            device.state = "Enabled"
            devices.append(device)

        # Get Master PSP via hct_ccp_bind.py --get_master_pspccp
        r, o, e = bash_roe("timeout 60 python %s --get_master_pspccp" % self.HCT_CCP_BIND_SCRIPT)
        if r == 124:
            logger.warning("hct_ccp_bind.py --get_master_pspccp timeout after 60s")
        elif r == 0 and o.strip():
            master_psp = o.strip()
            for device in devices:
                if device.pciBdf == master_psp:
                    device.isMasterPsp = True
                    break
        else:
            logger.warning("failed to get master PSP: %s" % e)

        rsp.devices = devices
        return jsonobject.dumps(rsp)

    @require_hygon_tools(GenerateHygonMdevDevicesRsp)
    @kvmagent.replyerror
    @in_bash
    def generate_hygon_mdev_devices(self, req):
        """
        Generate Hygon mdev devices (idempotent)

        This endpoint calls hctconfig to generate mdev (mediated device) instances
        from Hygon CCP physical devices for VM assignment.

        Idempotency:
            This method is idempotent. If the required number of mdev devices already
            exist, it will skip the generation step and return the existing bindings.
            This allows safe re-execution during host reconnection without destroying
            existing mdev devices.

        Script Command:
            bash /opt/hygon/hct/hct/script/hctconfig start -p <maxProgress> -q <maxQemuNum>

            Parameters:
                -p <maxProgress>: Max host processes per CCP device (default: 128)
                    - Creates (CCP_NUM * maxProgress) mdev devices for host processes
                    - These mdev devices have vendor/use=0 (host process usage)
                    - Example: 3 CCP devices * 128 = 384 mdev devices for host

                -q <maxQemuNum>: Max VMs per CCP device (default: 0)
                    - Creates (CCP_NUM * maxQemuNum) mdev devices for VMs
                    - These mdev devices have vendor/use=1 (VM usage)
                    - Example: 3 CCP devices * 64 = 192 mdev devices for VMs

            This command creates mdev devices under /sys/bus/mdev/devices/

        Mdev Device Sysfs Structure:
            /sys/bus/mdev/devices/<mdev_uuid>/
                vendor/
                    use    - Device usage flag (0: host process, 1: VM, 2: reserved)
                    idx    - Vendor index mapping to physical CCP device

            Hygon hct driver creates mdev devices under a virtual device layer:
                /sys/devices/virtual/hct/hct/<mdev_uuid>/

            Example:
                /sys/bus/mdev/devices/87bb66cc-390b-48c2-86f4-2da3ee78f581/
                    vendor/use  -> contains "1" (VM device)
                    vendor/idx  -> contains "65" (maps to a CCP device)

        Vendor Index Mapping Logic:
            The vendor_idx is calculated differently based on device usage:

            For host process devices (use=0):
                vendor_idx 0-15 maps directly to device_idx 0-15

            For VM devices (use=1):
                vendor_idx starts from 16, and every 4 consecutive indices map to one device
                Formula: device_idx = (vendor_idx - 16) / 4

            Example with 16 CCP devices and maxQemuNum=64:
                Device 0 (0000:05:00.2): vendor_idx 16-19 (4 indices * 15 mdev each = 60 mdev)
                Device 1 (0000:06:00.1): vendor_idx 20-23 (4 indices * 15 mdev each = 60 mdev)
                Device 2 (0000:23:00.2): vendor_idx 24-27
                ...
                Device 15 (0000:e2:00.1): vendor_idx 76-79

            Total VM mdev devices: 16 devices * 4 indices * 15 mdev = 960 mdev devices

        Response Format:
            {
                "success": true,
                "error": "",
                "mdevBindings": [
                    {
                        "mdevUuid": "12345678-1234-1234-1234-123456789abc",
                        "ccpDeviceUuid": null,  // Set by backend based on pciBdf
                        "pciBdf": "0000:42:00.2",
                        "vendorIdx": 65,
                        "useFlag": 1
                    },
                    ...
                ]
            }
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateHygonMdevDevicesRsp()

        max_progress = cmd.maxProgress if hasattr(cmd, 'maxProgress') else 0
        max_qemu_num = cmd.maxQemuNum if hasattr(cmd, 'maxQemuNum') else 64

        # Parse CCP devices first to build device_idx mapping
        try:
            ccp_devices = self._parse_ccp_devices()
        except Exception as e:
            logger.error("Failed to parse CCP devices list: %s" % e)
            rsp.success = False
            rsp.error = str(e)
            return jsonobject.dumps(rsp)

        if not ccp_devices:
            logger.info("No CCP devices found, skip mdev generation")
            rsp.mdevBindings = []
            return jsonobject.dumps(rsp)

        # Build device_index to pciBdf mapping
        # Sort by pciBdf to ensure stable mapping
        all_devices_sorted = sorted(ccp_devices, key=lambda x: x['pciBdf'])
        device_idx_to_pci_bdf = {}
        for idx, device_info in enumerate(all_devices_sorted):
            device_idx_to_pci_bdf[idx] = device_info['pciBdf']

        logger.debug("Built device_idx to pciBdf mapping: %s" % device_idx_to_pci_bdf)

        num_ccp_devices = len(ccp_devices)

        # Check existing mdev devices for idempotency
        # Only generate mdev devices if NO mdev exists on host
        # This prevents unnecessary regeneration when some mdevs are accidentally deleted
        existing_mdev_bindings = self._collect_mdev_bindings(device_idx_to_pci_bdf)
        existing_vm_mdev_count = len(existing_mdev_bindings)

        logger.info("Idempotency check: existing VM mdev count=%d (maxQemuNum=%d)" %
                   (existing_vm_mdev_count, max_qemu_num))

        if existing_vm_mdev_count > 0:
            # Mdev devices already exist, skip generation regardless of count
            # This avoids disrupting existing mdevs that may be in use
            logger.info("Mdev devices already exist (count=%d), skip regeneration" % existing_vm_mdev_count)
            rsp.mdevBindings = existing_mdev_bindings
            rsp.generated = False
            return jsonobject.dumps(rsp)

        # No mdev exists, generate new ones
        logger.info("No mdev devices found, generating with maxQemuNum=%d" % max_qemu_num)

        # Call hctconfig start -p {maxProgress} -q {maxQemuNum}
        r, o, e = bash_roe("timeout 60 bash %s start -p %d -q %d" % (self.HCTCONFIG_SCRIPT, max_progress, max_qemu_num))
        if r == 124:
            rsp.success = False
            rsp.error = "hctconfig start timeout after 60s"
            return jsonobject.dumps(rsp)
        if r != 0:
            rsp.success = False
            rsp.error = "failed to start hctconfig: %s" % e
            return jsonobject.dumps(rsp)

        # Collect mdev bindings after generation
        mdev_bindings = self._collect_mdev_bindings(device_idx_to_pci_bdf)
        rsp.mdevBindings = mdev_bindings
        rsp.generated = True

        logger.info("Generated %d mdev bindings from %d CCP devices" % (len(mdev_bindings), num_ccp_devices))

        # Note: qemu.conf cgroup_device_acl configuration and libvirtd restart
        # are now handled by ansible (kvm.py) during host reconnection.
        # The MN will trigger a host reconnect after this API returns,
        # which will collect vfio devices and update qemu.conf automatically.

        return jsonobject.dumps(rsp)

    def _collect_mdev_bindings(self, device_idx_to_pci_bdf):
        """
        Collect mdev device bindings from /sys/bus/mdev/devices/

        Only processes mdev devices that belong to Hygon CCP devices based on vendor_idx mapping.
        Other mdev devices (GPU, SR-IOV, etc.) in /sys/bus/mdev/devices/ are silently skipped.

        Vendor Index Mapping:
            - use=0 (host process): vendor_idx 0-15 maps directly to device_idx 0-15
            - use=1 (VM): vendor_idx 16+ maps to devices using formula:
              device_idx = (vendor_idx - 16) / 4

              Example with 16 CCP devices:
                vendor_idx 16-19 -> device 0
                vendor_idx 20-23 -> device 1
                vendor_idx 24-27 -> device 2
                ...
                vendor_idx 76-79 -> device 15

        Args:
            device_idx_to_pci_bdf: Mapping from device_idx (0-15) to PCI BDF

        Returns:
            list: List of mdev binding JsonObjects for Hygon CCP devices only
        """
        mdev_devices_path = "/sys/bus/mdev/devices"
        mdev_bindings = []

        if not os.path.exists(mdev_devices_path):
            return mdev_bindings

        num_devices = len(device_idx_to_pci_bdf)
        logger.debug("Number of CCP devices: %d" % num_devices)

        for mdev_uuid in os.listdir(mdev_devices_path):
            mdev_path = os.path.join(mdev_devices_path, mdev_uuid)
            vendor_use_path = os.path.join(mdev_path, "vendor", "use")
            vendor_idx_path = os.path.join(mdev_path, "vendor", "idx")

            if not os.path.exists(vendor_use_path) or not os.path.exists(vendor_idx_path):
                # This mdev device doesn't have vendor-specific attributes
                # (not a Hygon CCP device), skip silently
                continue

            try:
                with open(vendor_use_path, 'r') as f:
                    use_flag = int(f.read().strip())
                if use_flag != self.MDEV_USED_BY_VM:  # Only VM devices (use=1)
                    continue

                with open(vendor_idx_path, 'r') as f:
                    vendor_idx = int(f.read().strip())

                # Calculate device_idx from vendor_idx
                # For VM devices: vendor_idx starts from 16, every 4 consecutive indices map to one device
                if vendor_idx < 16:
                    # This shouldn't happen for use=1 devices, but handle gracefully
                    logger.debug("skip mdev device[uuid:%s] vendor_idx=%d (< 16 for VM device)" %
                               (mdev_uuid, vendor_idx))
                    continue

                device_idx = (vendor_idx - 16) // 4

                if device_idx not in device_idx_to_pci_bdf:
                    logger.debug("skip mdev device[uuid:%s] vendor_idx=%d -> device_idx=%d (out of range, num_devices=%d)" %
                               (mdev_uuid, vendor_idx, device_idx, num_devices))
                    continue

                # Map device_idx to PCI BDF
                pci_bdf = device_idx_to_pci_bdf[device_idx]

                binding = jsonobject.JsonObject()
                binding.mdevUuid = mdev_uuid
                binding.ccpDeviceUuid = None  # Will be set by backend based on pciBdf
                binding.pciBdf = pci_bdf
                binding.vendorIdx = vendor_idx
                binding.useFlag = use_flag
                mdev_bindings.append(binding)

            except IOError as e:
                logger.warn("failed to read mdev device[uuid:%s] info, IO error: %s" % (mdev_uuid, str(e)))
                continue
            except ValueError as e:
                logger.warn("failed to parse mdev device[uuid:%s] info, value error: %s" % (mdev_uuid, str(e)))
                continue
            except Exception as e:
                logger.warn("failed to process mdev device[uuid:%s], unexpected error: %s" % (mdev_uuid, str(e)))
                continue

        logger.info("Collected %d mdev bindings from %d CCP devices" % (len(mdev_bindings), num_devices))
        return mdev_bindings

    @require_hygon_tools(UngenerateHygonMdevDevicesRsp)
    @kvmagent.replyerror
    @in_bash
    def ungenerate_hygon_mdev_devices(self, req):
        """
        Ungenerate (remove) Hygon mdev devices

        This endpoint calls hctconfig stop to remove all mdev instances.

        Script Command:
            bash /opt/hygon/hct/hct/script/hctconfig stop

            This command:
                - Removes all mdev devices created under /sys/bus/mdev/devices/
                - Cleans up CCP device virtualization resources
                - Should be called before detaching or reconfiguring CCP devices

        Response Format:
            {
                "success": true,
                "error": ""
            }
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UngenerateHygonMdevDevicesRsp()

        # Call hctconfig stop
        r, o, e = bash_roe("timeout 60 bash %s stop" % self.HCTCONFIG_SCRIPT)
        if r == 124:
            rsp.success = False
            rsp.error = "hctconfig stop timeout after 60s"
            return jsonobject.dumps(rsp)
        if r != 0:
            rsp.success = False
            rsp.error = "failed to stop hctconfig: %s" % e
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_hygon_tools(self, req):
        """
        Check Hygon tools availability

        This endpoint provides detailed information about Hygon tools installation status.
        It can be used by the management system to verify that the host is properly configured
        before attempting to use Hygon CCP features.

        Unlike other endpoints, this one does NOT require tools to be available - it will
        report the current status regardless.

        Request Format:
            {} (empty request body or any valid JSON)

        Response Format:
            {
                "success": true,
                "available": true/false,
                "tools": {
                    "hct_ccp_bind": {
                        "path": "/opt/hygon/hct/hct/script/hct_ccp_bind.py",
                        "exists": true/false
                    },
                    "hctconfig": {
                        "path": "/opt/hygon/hct/hct/script/hctconfig",
                        "exists": true/false
                    }
                },
                "missingTools": ["/path/to/missing/tool", ...]
            }

        Usage Example:
            curl -X POST 'http://host:7070/hygontools/check' \\
              -H 'Content-Type: application/json' \\
              -d '{}'
        """
        rsp = CheckHygonToolsResponse()

        # Get detailed tools status
        tools_status = self._get_tools_status()

        # Populate response
        rsp.available = tools_status['available']
        rsp.tools = tools_status['tools']
        rsp.missingTools = tools_status['missing']

        return jsonobject.dumps(rsp)
