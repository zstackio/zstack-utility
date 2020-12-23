class SystemDriverBase(object):

    driver_name = 'base'

    def ping(self, *args, **kwargs):
        raise NotImplementedError()

    def reboot(self, *args, **kwargs):
        raise NotImplementedError()

    def stop(self, *args, **kwargs):
        raise NotImplementedError()

    def attach_volume(self, *args, **kwargs):
        raise NotImplementedError()

    def detach_volume(self, *args, **kwargs):
        raise NotImplementedError()

    def attach_port(self, *args, **kwargs):
        raise NotImplementedError()

    def detach_port(self, *args, **kwargs):
        raise NotImplementedError()

    def update_default_route(self, *args, **kwargs):
        raise NotImplementedError()

    def update_password(self, *args, **kwargs):
        raise NotImplementedError()

    def console(self, *args, **kwargs):
        raise NotImplementedError()
