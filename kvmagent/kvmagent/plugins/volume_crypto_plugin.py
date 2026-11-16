from kvmagent import kvmagent
from kvmagent.crypto import vm_xml, volume_request
from kvmagent.crypto.snapshots import LuksSnapshot
from kvmagent.crypto.ceph import http as ceph_http
from kvmagent.crypto.file_volume import http as file_volume_http
from kvmagent.crypto.file_volume.driver import LuksFileVolumeDriver
from kvmagent.crypto.imagestore_extension import ImageStoreEncryptionExtension
from kvmagent.crypto.shared_block import http as shared_block_http
from kvmagent.crypto.shared_block.driver import LuksSharedBlockVolumeDriver
from kvmagent.crypto.zbs import http as zbs_http
from kvmagent.volume import disk_xml, driver_registry, imagestore_commands, snapshots


class VolumeCryptoPlugin(kvmagent.KvmAgent):
    def configure(self, config=None):
        super(VolumeCryptoPlugin, self).configure(config)
        # Agent configures every plugin before starting HTTP request handling.
        driver_registry.register_driver(
            'file', 'luks', should_use_driver=volume_request.should_use_luks_driver,
            driver_class=LuksFileVolumeDriver)
        driver_registry.register_driver(
            'sharedblock', 'luks', should_use_driver=volume_request.should_use_luks_driver,
            driver_class=LuksSharedBlockVolumeDriver)
        snapshots.register_extension('luks', LuksSnapshot)
        disk_xml.register_extension('luks', vm_xml.apply_volume_encryption)
        imagestore_commands.register_extension('luks', ImageStoreEncryptionExtension)

    def start(self):
        http_server = kvmagent.get_http_server()
        file_volume_http.register_http_handlers(http_server)
        shared_block_http.register_http_handlers(http_server)
        ceph_http.register_http_handlers(http_server)
        zbs_http.register_http_handlers(http_server)

    def stop(self):
        pass
