from bm_instance_agent.systems import base


class WindowsDriver(base.SystemDriverBase):

    driver_name = 'windows'

    def __init__(self):
        super(WindowsDriver, self).__init__()
