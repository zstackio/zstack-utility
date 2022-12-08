from kvmagent.plugins import network_plugin
from kvmagent.plugins import vm_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from kvmagent.plugins import ovsdpdk_network
from zstacklib.utils import linux
from zstacklib.utils import jsonobject
from zstacklib.utils import bash
from unittest import TestCase

class BaseCase():
    @classmethod
    def setUpClass(self):
        self.NET_PLUGIN = network_plugin.NetworkPlugin()
        self.NET_PLUGIN.configure()

        self.DPDK_PLUGIN = ovsdpdk_network.OvsDpdkNetworkPlugin()
        self.DPDK_PLUGIN.configure()
        self.DPDK_PLUGIN.start()


class vHostAddOn():
    def __init__(self):
        self.queueNum = None

class Volume():

    def __init__(self):
        self.installPath = None
        self.deviceType = None
        self.volumeUuid = None
        self.useVirtio = None
        self.useVirtioSCSI = None
        self.shareable = None
        self.cacheMode = None
        self.wwn = None
        self.bootOrder = None
        self.physicalBlockSize = None

class Addon():
    def __init__(self):
        self.channel = None
        self.numaNodes = None


class PriorityConfigStruct():
    def __init__(self):
        self.vmUuid = None
        self.cpuShares = None
        self.oomScoreAdj = None