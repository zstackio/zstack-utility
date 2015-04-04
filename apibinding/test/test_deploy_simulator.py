'''

@author: frank
'''
import unittest
from apibinding import deployer
from apibinding import inventory
from zstacklib.utils import sizeunit
from zstacklib.utils import uuidhelper

class Test(unittest.TestCase):

    def testName(self):
        dc = deployer.DataCenterPlan()
        zone = deployer.ZonePlan()
        zone.name = "Zone1"
        zone.description = "Zone1"
        dc.add_zone(zone)
        
        cluster = deployer.ClusterPlan()
        cluster.name = "Cluster1"
        cluster.description = "Cluster1"
        cluster.hypervisorType = inventory.HYPERVISOR_TYPE_SIMULATOR
        cluster.type = inventory.ZSTACK_CLUSTER_TYPE
        zone.add_cluster(cluster)
        
        host = deployer.SimulatorHostPlan()
        host.cpuCapacity = 2600 * 4
        host.hypervisorType = inventory.HYPERVISOR_TYPE_SIMULATOR
        host.description = "Host1"
        host.name = "Host1"
        host.managementIp = "10.1.1.11"
        host.hostTags = ['large', 'test']
        host.memoryCapacity = sizeunit.GigaByte.toByte(36)
        cluster.add_host(host)
        
        primary_storage = deployer.PrimaryStoragePlan()
        primary_storage.name = "primaryStorage1"
        primary_storage.description = "primaryStorage1"
        primary_storage.totalCapacity = sizeunit.GigaByte.toByte(500)
        primary_storage.usedCapacity = 0
        primary_storage.url = "nfs://test.primary.storage/nfs/%s" % uuidhelper.uuid()
        primary_storage.type = inventory.PRIMARY_STORAGE_TYPE_SIMULATORPRIMARYSTORAGE
        primary_storage.add_cluster(cluster)
        dc.add_primary_storage(primary_storage)
        
        backup_storage = deployer.BackupStoragePlan()
        backup_storage.name = "backupstorage"
        backup_storage.description = "backup_storage"
        backup_storage.totalCapacity = sizeunit.GigaByte.toByte(1000)
        backup_storage.usedCapacity = 0
        backup_storage.url = "nfs://test.backup.storage/nfs/%s" % uuidhelper.uuid()
        backup_storage.type = inventory.BACKUP_STORAGE_TYPE_SIMULATORBACKUPSTORAGE
        backup_storage.add_zone(zone)
        
        image = deployer.ImagePlan()
        image.accountUuid = inventory.INITIAL_SYSTEM_ADMIN_UUID
        image.bits = 64
        image.description = "image"
        #TODO: auto generated from java
        image.format = "template"
        image.hypervisorType = inventory.HYPERVISOR_TYPE_SIMULATOR
        image.type = inventory.ZSTACK_IMAGE_TYPE
        image.guestOsType = "Linux"
        image.url = "http://download.zstack.org/download/test.qcow2"
        image.add_backup_storage(backup_storage)
        
        l2network = deployer.L2NetworkPlan()
        l2network.name = "l2network"
        l2network.description = "l2network"
        l2network.physicalInterface = "eth0"
        l2network.type = inventory.L2_NO_VLAN_NETWORK_TYPE
        l2network.add_cluster(cluster)
        zone.add_l2network(l2network)
        
        l3network = deployer.L3NetworkPlan()
        l3network.name = "l3network"
        l3network.description = "l3network"
        l3network.type = inventory.L3_BASIC_NETWORK_TYPE
        l2network.add_l3network(l3network)
        
        iprange = inventory.IpRangeInventory()
        iprange.name = "iprange"
        iprange.startIp = "10.1.1.100"
        iprange.endIp = "10.1.1.150"
        iprange.gateway = "10.1.1.1"
        iprange.netmask = "255.255.255.0"
        #TODO: auto generated iprange type from java
        iprange.type = "Guest"
        l3network.add_iprange(iprange)
        
        dns = deployer.DnsPlan()
        dns.name = "dns"
        dns.description = "dns"
        dns.address = "10.1.1.254"
        dns.add_l3network(l3network)
        dc.add_dns(dns)
        
        dc.deploy()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()