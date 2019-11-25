import libvirt


class TemporaryPauseVmOperator(object):
    def __init__(self, domain):
        self.domain = domain  # type: libvirt.virDomain
        self.need_pause = self.domain.state() != libvirt.VIR_DOMAIN_PAUSED

    def __enter__(self):
        if self.need_pause:
            self.domain.suspend()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.need_pause:
            self.domain.resume()