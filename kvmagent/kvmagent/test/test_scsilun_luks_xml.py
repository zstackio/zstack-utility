import unittest
import xml.etree.ElementTree as etree

from kvmagent.plugins import luks_xml


def e(parent, tag, value=None, attrib=None):
    if attrib is None:
        attrib = {}
    el = etree.SubElement(parent, tag, attrib)
    if value:
        el.text = value
    return el


class AttrVolume(object):
    pass


class TestScsiLunLuksXml(unittest.TestCase):
    def test_scsilun_volume_adds_luks_secret(self):
        volume = AttrVolume()
        volume.deviceType = 'scsilun'
        volume.installPath = '/dev/disk/by-id/scsi-test'
        volume.cacheMode = 'none'
        volume.luksSecretUuid = 'secret-uuid'

        disk = etree.Element('disk', attrib={'type': 'block', 'device': 'lun', 'sgio': 'filtered'})
        e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': volume.cacheMode})
        e(disk, 'source', None, {'dev': volume.installPath})
        luks_xml.add_luks_encryption(e, disk, volume)
        e(disk, 'target', None, {'dev': 'sdb', 'bus': 'scsi'})

        xml = etree.tostring(disk, encoding='unicode')
        self.assertIn('device="lun"', xml)
        self.assertIn('format="luks"', xml)
        self.assertIn('uuid="secret-uuid"', xml)


if __name__ == "__main__":
    unittest.main()
