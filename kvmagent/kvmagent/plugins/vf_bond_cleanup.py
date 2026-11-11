"""Read-only evidence for releasing quarantined VF devices; no guest tools required."""
import errno
import libvirt
import os
import re
import xml.etree.ElementTree as ET

from kvmagent.plugins import vm_plugin
from zstacklib.utils import linux


@vm_plugin.LibvirtAutoReconnect
def domain_devices(conn):
    used = set()
    # Include inactive persistent definitions: a later start must not reclaim a VF.
    for domain in conn.listAllDomains(0):
        definitions = [domain.XMLDesc(0)]
        if domain.isPersistent():
            definitions.append(domain.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE))
        for xml in definitions:
            root = ET.fromstring(xml)
            devices = [d for d in root.findall('./devices/hostdev') if d.get('type') == 'pci'] + [
                d for d in root.findall('./devices/interface') if d.get('type') == 'hostdev']
            for device in devices:
                address = device.find('./source/address')
                if address is not None and address.get('type', 'pci') == 'pci':
                    used.add('%04x:%02x:%02x.%x' % tuple(
                        int(address.get(k, '0'), 0) for k in ('domain', 'bus', 'slot', 'function')))
    return used


def open_vfio_groups():
    opened = set()
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        directory = '/proc/' + pid + '/fd'
        try:
            for fd in os.listdir(directory):
                try:
                    opened.add(os.readlink(directory + '/' + fd))
                except OSError as error:
                    if error.errno != errno.ENOENT:
                        raise
        except OSError as error:
            if error.errno != errno.ENOENT:
                raise
    return opened


def check_devices(devices):
    result = dict(success=True, protocolVersion=1, safeDevices={}, blockedDevices={})
    # Any inability to inspect the host fails the entire observation closed.
    used = domain_devices()
    opened = open_vfio_groups()
    for device in devices:
        key, address, owner = device['uuid'], device['pciAddress'], device.get('vmUuid')
        if not re.fullmatch(r'[a-f0-9]{32}', key) or not re.fullmatch(
                r'(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', address):
            raise ValueError('invalid VF cleanup identity')
        if owner and not re.fullmatch(r'[a-f0-9]{32}', owner):
            raise ValueError('invalid VF cleanup owner')
        bdf = (address if address.count(':') == 2 else '0000:' + address).lower()
        group_path = '/sys/bus/pci/devices/' + bdf + '/iommu_group'
        if owner and linux.find_vm_process_by_uuid(owner):
            reason = 'OwnerProcessPresent'
        elif bdf in used:
            reason = 'DomainReferencesDevice'
        elif not os.path.islink(group_path):
            reason = 'IommuGroupUnavailable'
        elif any(path.startswith('/dev/vfio/devices/') or path == '/dev/iommu' for path in opened):
            reason = 'UnsupportedVfioDescriptor'
        elif '/dev/vfio/' + os.path.basename(os.path.realpath(group_path)) in opened:
            reason = 'VfioGroupInUse'
        else:
            result['safeDevices'][key] = address
            continue
        result['blockedDevices'][key] = reason
    return result
