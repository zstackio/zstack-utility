import urlparse

from zstacklib.utils import log, linux

logger = log.get_logger(__name__)


class RemoteTarget(object):
    def __init__(self, uri):
        self.uri = uri

    def download(self, dst_path):
        pass

    def upload(self):
        pass


class NbdRemoteTarget(RemoteTarget):
    def __init__(self, uri):
        super(NbdRemoteTarget, self).__init__(uri)

    def _get_out_format(self, dst_path):
        if dst_path.startswith("rbd:"):
            return "raw"
        raise Exception('not implemented')

    def download(self, dst_path):
        out_format = self._get_out_format(dst_path)
        linux.nbd_qemu_img_convert(self.uri, out_format, dst_path)

    def upload(self):
        raise Exception('not implemented')


def get_remote_target_from_uri(uri):
    u = urlparse.urlparse(uri)
    if u.scheme == 'nbd':
        return NbdRemoteTarget(uri)

    raise Exception('not implement schema: %s' % u.scheme)
