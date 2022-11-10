import unittest
from kvmagent.plugins import network_plugin
from kvmagent.plugins import vm_plugin
from kvmagent.plugins import host_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from kvmagent.plugins import ovsdpdk_network
from zstacklib.utils import linux
from zstacklib.utils import jsonobject
from zstacklib.utils import bash
from zstacklib.utils import ovs
from kvmagent import kvmagent
import time
import pytest


class Test():
    ofed_not_exsit = True
    @classmethod
    def setup_class(self):
        self.HOST_PLUGIN = host_plugin.HostPlugin()

    def test_getHostNetworkFacts(self):
        cmd = kvmagent.AgentCommand()

        response = self.HOST_PLUGIN.get_host_network_facts(({"body": jsonobject.dumps(cmd)}))
        rsp = jsonobject.loads(response)

        if rsp.bondings is None or rsp.nics is None:
            print "rsp.bondings is None or rsp.nics is None"
            return

        bonds = rsp.bondings

        bondslavesInterfaces = []
        for bond in bonds:
            if bond.type == "LinuxBonding":
                continue
            for slave in bond.slaves:
                bondslavesInterfaces.append(slave.interfaceName)

        for nic in rsp.nics:
            if nic.interfaceName in bondslavesInterfaces:
                assert nic.interfaceType != "noMaster"

        return

    def test_getDpdpBond(self):
        bonds = ovs.getAllBondFromFile()
        for bond in bonds:
            print "bond name %s" % bond.name
        return