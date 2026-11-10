import os

from zstacklib.utils import pci, sansec_utils, shell

SYSFS_DEVICES = sansec_utils.SYSFS_DEVICES
MODULE_DIR = '/sys/module/swcsm'


def converge_driver():
    if os.path.exists(sansec_utils.MODULE_CONFIG) and not os.path.isdir(MODULE_DIR):
        shell.call('modprobe swcsm')


def probe(device, context):
    return sansec_utils.supported_device(device.vendorId, device.deviceId)


def init(device, context):
    device.type = 'Crypto_Controller'
    device.vendor = 'Sansec'
    path = os.path.join(SYSFS_DEVICES, device.pciDeviceAddress)
    parent = os.path.realpath(os.path.join(path, 'physfn')) if os.path.exists(os.path.join(path, 'physfn')) else path
    if not os.path.isdir(os.path.join(path, 'iommu_group')):
        device.iommuGroup = ''
    loaded = sansec_utils.driver_loaded(parent)
    try:
        version = sansec_utils.driver_version(parent) if loaded else None
    except OSError:
        version = None
    device.addonInfo.update({
        'cryptoQualification': (sansec_utils.Qualification.UNVERIFIED if loaded
                                else sansec_utils.Qualification.DRIVER_UNAVAILABLE),
        'cryptoDriverVersion': version.strip() if version else None,
    })
    numvfs = os.path.join(path, 'sriov_numvfs')
    if parent == path and os.path.exists(numvfs):
        with open(numvfs) as source:
            device.addonInfo['sriovNumVfs'] = sansec_utils.parse_int(source.read().strip())
    return True


pci.pci_register_device_ops(pci.PciDeviceOps(probe=probe, init=init))
