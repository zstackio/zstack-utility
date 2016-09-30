'''

@author: frank
'''
import unittest
from apibinding import deployer
from apibinding import inventory


class TestDeployZone(unittest.TestCase):


    def testName(self):
        dc = deployer.DataCenterPlan()
        zone = deployer.ZonePlan()
        zone.name = "Zone1"
        zone.description = "Zone1"
        dc.add_zone(zone)
        
        cluster = deployer.ClusterPlan()
        cluster.name = "Cluster1"
        cluster.description = "Cluster1"
        cluster.hypervisorType = inventory.KVM_HYPERVISOR_TYPE
        cluster.type = inventory.ZSTACK_CLUSTER_TYPE
        zone.add_cluster(cluster)
        
        dc.deploy()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()