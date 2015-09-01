'''
Deploy ZStack environment from template xml file.

@author: Youyk
'''
import sys
import traceback
import threading
import time

import zstacklib.utils.sizeunit as sizeunit
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.xmlobject as xmlobject
import zstacklib.utils.lock as lock
import apibinding.inventory as inventory
import apibinding.api_actions as api_actions

import account_operations
import resource_operations as res_ops

#global exception information for thread usage
exc_info = []
AddKVMHostTimeOut = 10*60*1000
IMAGE_THREAD_LIMIT = 2
DEPLOY_THREAD_LIMIT = 500

class DeployError(Exception):
    '''zstack deploy exception'''

def deploy_logger(msg):
    print '\n[Deploy Log:] %s\n' % msg

def get_first_item_from_list(list_obj, list_obj_name, list_obj_value, action_name):
    '''
    Judge if list is empty. If not, return the 1st item.
    list_obj: the list for judgment and return;
    list_obj_name: the list item type name;
    list_obj_value: the list item's value when do previous query;
    action_name: which action is calling this function
    '''
    if not isinstance(list_obj, list):
        raise DeployError("The first parameter is not a [list] type")

    if not list_obj:
        raise DeployError("Did not find %s: [%s], when adding %s" % (list_obj_name, list_obj_value, action_name))

    if len(list_obj) > 1:
        raise DeployError("Find more than 1 [%s] resource with name: [%s], when adding %s. Please check your deploy.xml and make sure resource do NOT have duplicated name " % (list_obj_name, list_obj_value, action_name))

    return list_obj[0]

#Add Backup Storage
def add_backup_storage(deployConfig, session_uuid):
    if xmlobject.has_element(deployConfig, 'backupStorages.sftpBackupStorage'):
        for bs in xmlobject.safe_list(deployConfig.backupStorages.sftpBackupStorage):
            action = api_actions.AddSftpBackupStorageAction()
            action.sessionUuid = session_uuid
            action.name = bs.name_
            action.description = bs.description__
            action.url = bs.url_
            action.username = bs.username_
            action.password = bs.password_
            action.hostname = bs.hostname_
            action.timeout = AddKVMHostTimeOut #for some platform slowly salt execution
            action.type = inventory.SFTP_BACKUP_STORAGE_TYPE
            if bs.uuid__:
                action.resourceUuid = bs.uuid__
            thread = threading.Thread(target = _thread_for_action, args = (action, ))
            wait_for_thread_queue()
            thread.start()

    if xmlobject.has_element(deployConfig, 'backupStorages.cephBackupStorage'):
        for bs in xmlobject.safe_list(deployConfig.backupStorages.cephBackupStorage):
            action = api_actions.AddCephBackupStorageAction()
            action.sessionUuid = session_uuid
            action.name = bs.name_
            action.description = bs.description__
            action.monUrls = bs.monUrls_.split(';')
            if bs.poolName__:
                action.poolName = bs.poolName_
            action.timeout = AddKVMHostTimeOut #for some platform slowly salt execution
            action.type = inventory.CEPH_BACKUP_STORAGE_TYPE
            thread = threading.Thread(target = _thread_for_action, args = (action, ))
            wait_for_thread_queue()
            thread.start()

    if xmlobject.has_element(deployConfig, 'backupStorages.simulatorBackupStorage'):
        for bs in xmlobject.safe_list(deployConfig.backupStorages.simulatorBackupStorage):
            action = api_actions.AddSimulatorBackupStorageAction()
            action.sessionUuid = session_uuid
            action.name = bs.name_
            action.description = bs.description__
            action.url = bs.url_
            action.type = inventory.SIMULATOR_BACKUP_STORAGE_TYPE
            action.totalCapacity = sizeunit.get_size(bs.totalCapacity_)
            action.availableCapacity = sizeunit.get_size(bs.availableCapacity_)
            thread = threading.Thread(target = _thread_for_action, args = (action, ))
            wait_for_thread_queue()
            thread.start()

    wait_for_thread_done()

#Add Zones
def add_zone(deployConfig, session_uuid, zone_name = None):
    def _add_zone(zone, zone_duplication):
        action = api_actions.CreateZoneAction()
        action.sessionUuid = session_uuid
        if zone_duplication == 0:
            action.name = zone.name_
            action.description = zone.description__
            if zone.uuid__:
                action.resourceUuid = zone.uuid__
        else:
            action.name = generate_dup_name(zone.name_, zone_duplication, 'z')
            action.description = generate_dup_name(zone.description__, zone_duplication, 'zone')

        try:
            evt = action.run()
            deploy_logger(jsonobject.dumps(evt))
            zinv = evt.inventory
        except:
            exc_info.append(sys.exc_info())
     
        if xmlobject.has_element(zone, 'backupStorageRef'):
            for ref in xmlobject.safe_list(zone.backupStorageRef):
                bss = res_ops.get_resource(res_ops.BACKUP_STORAGE, session_uuid, name=ref.text_)
                bs = get_first_item_from_list(bss, 'Backup Storage', ref.text_, 'attach backup storage to zone')

                action = api_actions.AttachBackupStorageToZoneAction()
                action.sessionUuid = session_uuid
                action.backupStorageUuid = bs.uuid
                action.zoneUuid = zinv.uuid
                try:
                    evt = action.run()
                    deploy_logger(jsonobject.dumps(evt))
                except:
                    exc_info.append(sys.exc_info())


    if not xmlobject.has_element(deployConfig, 'zones.zone'):
        return

    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone_name != zone.name_:
            continue 

        if zone.duplication__ == None:
            duplication = 1
        else:
            duplication = int(zone.duplication__)

        for i in range(duplication):
            thread = threading.Thread(target=_add_zone, args=(zone, i, ))
            wait_for_thread_queue()
            thread.start()

    wait_for_thread_done()

#Add L2 network
def add_l2_network(deployConfig, session_uuid, l2_name = None, zone_name = None):
    '''
    If providing name, it will only add L2 network with the same name.
    '''
    if not xmlobject.has_element(deployConfig, "zones.zone"):
        return

    def _deploy_l2_network(zone, is_vlan):
        if is_vlan:
            if not xmlobject.has_element(zone, "l2Networks.l2VlanNetwork"):
                return
            l2Network = zone.l2Networks.l2VlanNetwork
        else:
            if not xmlobject.has_element(zone, \
                    "l2Networks.l2NoVlanNetwork"):
                return
            l2Network = zone.l2Networks.l2NoVlanNetwork

        if zone.duplication__ == None:
            zone_dup = 1
        else:
            zone_dup = int(zone.duplication__)

        for zone_ref in range(zone_dup):
            zoneName = generate_dup_name(zone.name_, zone_ref, 'z')

            zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, name=zoneName)
            zinv = get_first_item_from_list(zinvs, 'Zone', zoneName, 'L2 network')

            #can only deal with single cluster duplication case.
            cluster = xmlobject.safe_list(zone.clusters.cluster)[0]
            
            if cluster.duplication__ == None:
                cluster_duplication = 1
            else:
                cluster_duplication = int(cluster.duplication__)

            for cluster_ref in range(cluster_duplication):
                for l2 in xmlobject.safe_list(l2Network):
                    if l2_name and l2_name != l2.name_:
                        continue 

                    if not is_vlan or l2.duplication__ == None:
                        l2_dup = 1
                    else:
                        l2_dup = int(l2.duplication__)

                    for j in range(l2_dup):
                        l2Name = generate_dup_name(\
                                generate_dup_name(\
                                generate_dup_name(\
                                l2.name_, zone_ref, 'z')\
                                , cluster_ref, 'c')\
                                , j, 'n')

                        if not l2.description__:
                            l2.description_ = 'l2'

                        l2Des = generate_dup_name(\
                                generate_dup_name(\
                                generate_dup_name(\
                                l2.description_, zone_ref, 'z')\
                                , cluster_ref, 'c')\
                                , j, 'n')

                        if is_vlan:
                            l2_vlan = int(l2.vlan_) + j

                        if is_vlan:
                            action = api_actions.CreateL2VlanNetworkAction()
                        else:
                            action = api_actions.CreateL2NoVlanNetworkAction()

                        action.sessionUuid = session_uuid
                        action.name = l2Name
                        action.description = l2Des

                        action.physicalInterface = l2.physicalInterface_
                        action.zoneUuid = zinv.uuid
                        if is_vlan:
                            action.vlan = l2_vlan

                        if l2.uuid__:
                            action.resourceUuid = l2.uuid__

                        thread = threading.Thread(\
                                target=_thread_for_action, \
                                args=(action,))
                        wait_for_thread_queue()
                        thread.start()

    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone.name_ != zone_name:
            continue

        _deploy_l2_network(zone, False)
        _deploy_l2_network(zone, True)

    wait_for_thread_done()

#Add Primary Storage
def add_primary_storage(deployConfig, session_uuid, ps_name = None, \
        zone_name = None):
    if not xmlobject.has_element(deployConfig, 'zones.zone'):
        deploy_logger('Not find zones.zone in config, skip primary storage deployment')
        return

    def _generate_sim_ps_action(zone, pr, zone_ref, cluster_ref):
        if zone_ref == 0:
            zone_name = zone.name_
        else:
            zone_name = generate_dup_name(zone.name_, zone_ref, 'z')

        zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, name=zone_name)
        zinv = get_first_item_from_list(zinvs, 'Zone', zone_name, 'primary storage')

        action = api_actions.AddSimulatorPrimaryStorageAction()
        action.sessionUuid = session_uuid
        action.name = generate_dup_name(generate_dup_name(pr.name_, zone_ref, 'z'), cluster_ref, 'c') 
        action.description = generate_dup_name(generate_dup_name(pr.description__, zone_ref, 'zone'), cluster_ref, 'cluster')
        action.url = generate_dup_name(generate_dup_name(pr.url_, zone_ref, 'z'), cluster_ref, 'c')

        action.type = inventory.SIMULATOR_PRIMARY_STORAGE_TYPE
        action.zoneUuid = zinv.uuid
        action.totalCapacity = sizeunit.get_size(pr.totalCapacity_)
        action.availableCapacity = sizeunit.get_size(pr.availableCapacity_)
        if pr.uuid__:
            action.resourceUuid = pr.uuid__
        return action

    def _deploy_primary_storage(zone):
        if xmlobject.has_element(zone, 'primaryStorages.nfsPrimaryStorage'):
            zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, \
                    name=zone.name_)
            zinv = get_first_item_from_list(zinvs, 'Zone', zone.name_, 'primary storage')

            for pr in xmlobject.safe_list(zone.primaryStorages.nfsPrimaryStorage):
                if ps_name and ps_name != pr.name_:
                    continue

                action = api_actions.AddNfsPrimaryStorageAction()
                action.sessionUuid = session_uuid
                action.name = pr.name_
                action.description = pr.description__
                action.type = inventory.NFS_PRIMARY_STORAGE_TYPE
                action.url = pr.url_
                action.zoneUuid = zinv.uuid
                if pr.uuid__:
                    action.resourceUuid = pr.uuid__
                thread = threading.Thread(target=_thread_for_action, args=(action,))
                wait_for_thread_queue()
                thread.start()

        if xmlobject.has_element(zone, 'primaryStorages.localPrimaryStorage'):
            zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, \
                    name=zone.name_)
            zinv = get_first_item_from_list(zinvs, 'Zone', zone.name_, 'primary storage')

            for pr in xmlobject.safe_list(zone.primaryStorages.localPrimaryStorage):
                if ps_name and ps_name != pr.name_:
                    continue

                action = api_actions.AddLocalPrimaryStorageAction()
                action.sessionUuid = session_uuid
                action.name = pr.name_
                action.description = pr.description__
                action.type = inventory.LOCAL_STORAGE_TYPE
                action.url = pr.url_
                action.zoneUuid = zinv.uuid
                thread = threading.Thread(target=_thread_for_action, args=(action,))
                wait_for_thread_queue()
                thread.start()

        if xmlobject.has_element(zone, 'primaryStorages.cephPrimaryStorage'):
            zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, \
                    name=zone.name_)
            zinv = get_first_item_from_list(zinvs, 'Zone', zone.name_, 'primary storage')

            for pr in xmlobject.safe_list(zone.primaryStorages.cephPrimaryStorage):
                if ps_name and ps_name != pr.name_:
                    continue

                action = api_actions.AddCephPrimaryStorageAction()
                action.sessionUuid = session_uuid
                action.name = pr.name_
                action.description = pr.description__
                action.type = inventory.CEPH_PRIMARY_STORAGE_TYPE
                action.monUrls = pr.monUrls_.split(';')
                if pr.dataVolumePoolName__:
                    action.dataVolumePoolName = pr.dataVolumePoolName__
                if pr.rootVolumePoolName__:
                    action.rootVolumePoolName = pr.rootVolumePoolName__
                if pr.imageCachePoolName__:
                    action.imageCachePoolName = pr.imageCachePoolName__
                action.zoneUuid = zinv.uuid
                thread = threading.Thread(target=_thread_for_action, args=(action,))
                wait_for_thread_queue()
                thread.start()

        if xmlobject.has_element(zone, 'primaryStorages.simulatorPrimaryStorage'):
            if zone.duplication__ == None:
                duplication = 1
            else:
                duplication = int(zone.duplication__)

            for pr in xmlobject.safe_list(zone.primaryStorages.simulatorPrimaryStorage):
                for zone_ref in range(duplication):
                    for cluster in xmlobject.safe_list(zone.clusters.cluster):
                        for pref in xmlobject.safe_list(cluster.primaryStorageRef):
                            if pref.text_ == pr.name_:
                                if cluster.duplication__ == None:
                                    cluster_duplication = 1
                                else:
                                    cluster_duplication = int(cluster.duplication__)

                                for cluster_ref in range(cluster_duplication):
                                    action = _generate_sim_ps_action(zone, pr, zone_ref, cluster_ref)
                                    thread = threading.Thread(target=_thread_for_action, args=(action,))
                                    wait_for_thread_queue()
                                    thread.start()

    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone.name_ != zone_name:
            continue
        _deploy_primary_storage(zone)

    wait_for_thread_done()

#Add Cluster
def add_cluster(deployConfig, session_uuid, cluster_name = None, \
        zone_name = None):
    if not xmlobject.has_element(deployConfig, "zones.zone"):
        return

    def _add_cluster(action, zone_ref, cluster, cluster_ref):
        evt = action.run()
        deploy_logger(jsonobject.dumps(evt))
        cinv = evt.inventory

        try:
            if xmlobject.has_element(cluster, 'primaryStorageRef'):
                for pref in xmlobject.safe_list(cluster.primaryStorageRef):
                    ps_name = generate_dup_name(generate_dup_name(pref.text_, zone_ref, 'z'), cluster_ref, 'c')

                    pinvs = res_ops.get_resource(res_ops.PRIMARY_STORAGE, session_uuid, name=ps_name)
                    pinv = get_first_item_from_list(pinvs, 'Primary Storage', ps_name, 'Cluster')

                    action_ps = api_actions.AttachPrimaryStorageToClusterAction()
                    action_ps.sessionUuid = session_uuid
                    action_ps.clusterUuid = cinv.uuid
                    action_ps.primaryStorageUuid = pinv.uuid
                    evt = action_ps.run()
                    deploy_logger(jsonobject.dumps(evt))
        except:
            exc_info.append(sys.exc_info())

        if cluster.allL2NetworkRef__ == 'true':
            #find all L2 network in zone and attach to cluster
            cond = res_ops.gen_query_conditions('zoneUuid', '=', \
                    action.zoneUuid)
            l2_count = res_ops.query_resource_count(res_ops.L2_NETWORK, \
                    cond, session_uuid)
            l2invs = res_ops.query_resource_fields(res_ops.L2_NETWORK, \
                    [{'name':'zoneUuid', 'op':'=', 'value':action.zoneUuid}], \
                    session_uuid, ['uuid'], 0, l2_count)
        else:
            l2invs = []
            if xmlobject.has_element(cluster, 'l2NetworkRef'):
                for l2ref in xmlobject.safe_list(cluster.l2NetworkRef):
                    l2_name = generate_dup_name(generate_dup_name(l2ref.text_, zone_ref, 'z'), cluster_ref, 'c')

                    cond = res_ops.gen_query_conditions('zoneUuid', '=', \
                            action.zoneUuid)
                    cond = res_ops.gen_query_conditions('name', '=', l2_name, \
                            cond)
                            
                    l2inv = res_ops.query_resource_fields(res_ops.L2_NETWORK, \
                            cond, session_uuid, ['uuid'])
                    if not l2inv:
                        raise DeployError("Can't find l2 network [%s] in database." % l2_name)
                    l2invs.extend(l2inv)

        for l2inv in l2invs:
            action = api_actions.AttachL2NetworkToClusterAction()
            action.sessionUuid = session_uuid
            action.clusterUuid = cinv.uuid
            action.l2NetworkUuid = l2inv.uuid
            thread = threading.Thread(target=_thread_for_action, args=(action,))
            wait_for_thread_queue()
            thread.start()

    def _deploy_cluster(zone):
        if not xmlobject.has_element(zone, "clusters.cluster"):
            return

        if zone.duplication__ == None:
            zone_duplication = 1
        else:
            zone_duplication = int(zone.duplication__)

        for zone_ref in range(zone_duplication):
            for cluster in xmlobject.safe_list(zone.clusters.cluster):
                if cluster_name and cluster_name != cluster.name_:
                    continue

                if cluster.duplication__ == None:
                    cluster_duplication = 1
                else:
                    cluster_duplication = int(cluster.duplication__)
    
                for cluster_ref in range(cluster_duplication):
                    action = api_actions.CreateClusterAction()
                    action.sessionUuid = session_uuid
                    action.name = generate_dup_name(generate_dup_name(cluster.name_, zone_ref, 'z'), cluster_ref, 'c')
                    action.description = generate_dup_name(generate_dup_name(cluster.description__, zone_ref, 'z'), cluster_ref, 'c')
        
                    action.hypervisorType = cluster.hypervisorType_
                    zone_name = generate_dup_name(zone.name_, zone_ref, 'z')
        
                    zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, name=zone_name)
                    zinv = get_first_item_from_list(zinvs, 'Zone', zone_name, 'Cluster')
                    action.zoneUuid = zinv.uuid
                    if cluster.uuid__:
                        action.resourceUuid = cluster.uuid__
                    thread = threading.Thread(target=_add_cluster, args=(action, zone_ref, cluster, cluster_ref, ))
                    wait_for_thread_queue()
                    thread.start()

    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone_name != zone.name_:
            continue 

        _deploy_cluster(zone)

    wait_for_thread_done()

#Add Host
def add_host(deployConfig, session_uuid, host_ip = None, zone_name = None, \
        cluster_name = None):
    '''
    Base on an xml deploy config object to add hosts. 
    If providing giving zone_name, cluster_name or host_ip, this function will
    only add related hosts. 
    '''
    if not xmlobject.has_element(deployConfig, "zones.zone"):
        return

    def _deploy_host(cluster, zone_ref, cluster_ref):
        if not xmlobject.has_element(cluster, "hosts.host"):
            return

        if zone_ref == 0 and cluster_ref == 0:
            cluster_name = cluster.name_
        else:
            cluster_name = generate_dup_name(generate_dup_name(cluster.name_, zone_ref, 'z'), cluster_ref, 'c')
        
        cinvs = res_ops.get_resource(res_ops.CLUSTER, session_uuid, name=cluster_name)
        cinv = get_first_item_from_list(cinvs, 'Cluster', cluster_name, 'L3 network')
        for host in xmlobject.safe_list(cluster.hosts.host):
            if host_ip and host_ip != host.managementIp_:
                continue

            if host.duplication__ == None:
                host_duplication = 1
            else:
                host_duplication = int(host.duplication__)

            for i in range(host_duplication):
                if cluster.hypervisorType_ == inventory.KVM_HYPERVISOR_TYPE:
                    action = api_actions.AddKVMHostAction()
                    action.username = host.username_
                    action.password = host.password_
                    action.timeout = AddKVMHostTimeOut
                elif cluster.hypervisorType_ == inventory.SIMULATOR_HYPERVISOR_TYPE:
                    action = api_actions.AddSimulatorHostAction()
                    if host.cpuCapacity__:
                        action.cpuCapacity = host.cpuCapacity_
                    else:
                        action.cpuCapacity = 416000
                    if host.memoryCapacity__:
                        action.memoryCapacity = sizeunit.get_size(host.memoryCapacity_)
                    else:
                        action.memoryCapacity = sizeunit.get_size('1024G')
    
                action.sessionUuid = session_uuid
                action.clusterUuid = cinv.uuid
                action.hostTags = host.hostTags__
                if zone_ref == 0 and cluster_ref == 0 and i == 0:
                    action.name = host.name_
                    action.description = host.description__
                    action.managementIp = host.managementIp_
                    if host.uuid__:
                        action.resourceUuid = host.uuid__
                else:
                    action.name = generate_dup_name(generate_dup_name(generate_dup_name(host.name_, zone_ref, 'z'), cluster_ref, 'c'), i, 'h')
                    action.description = generate_dup_name(generate_dup_name(generate_dup_name(host.description__, zone_ref, 'z'), cluster_ref, 'c'), i, 'h')
                    action.managementIp = generate_dup_host_ip(host.managementIp_, zone_ref, cluster_ref, i)

                thread = threading.Thread(target=_thread_for_action, args = (action, ))
                wait_for_thread_queue()
                thread.start()

    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone_name != zone.name_:
            continue

        if not xmlobject.has_element(zone, 'clusters.cluster'):
            continue

        if zone.duplication__ == None:
            zone_duplication = 1
        else:
            zone_duplication = int(zone.duplication__)

        for zone_ref in range(zone_duplication):
            for cluster in xmlobject.safe_list(zone.clusters.cluster):
                if cluster_name and cluster_name != cluster.name_:
                    continue

                if cluster.duplication__ == None:
                    cluster_duplication = 1
                else:
                    cluster_duplication = int(cluster.duplication__)

                for cluster_ref in range(cluster_duplication):
                    _deploy_host(cluster, zone_ref, cluster_ref)

    wait_for_thread_done()
    deploy_logger('All add KVM host actions are done.')

#Add L3 network
def add_l3_network(deployConfig, session_uuid, l3_name = None, l2_name = None, \
        zone_name = None):
    '''
    add_l3_network will add L3 network and also add related DNS, IpRange and 
    network services. 
    '''
    if not xmlobject.has_element(deployConfig, "zones.zone"):
        return


    def _deploy_l3_network(l2, zone_ref, cluster_ref):
        if not xmlobject.has_element(l2, "l3Networks.l3BasicNetwork"):
            return

        if not l2.duplication__:
            l2_dup = 1
        else:
            l2_dup = int(l2.duplication__)

        for l2_num in range(l2_dup):
            for l3 in xmlobject.safe_list(l2.l3Networks.l3BasicNetwork):
                if l3_name and l3_name != l3.name_:
                    continue 
    
                l2Name = generate_dup_name(generate_dup_name(generate_dup_name(l2.name_, zone_ref, 'z'), cluster_ref, 'c'), l2_num, 'n')
                l3Name = generate_dup_name(generate_dup_name(generate_dup_name(l3.name_, zone_ref, 'z'), cluster_ref, 'c'), l2_num, 'n')

                l2invs = res_ops.get_resource(res_ops.L2_NETWORK, \
                        session_uuid, \
                        name=l2Name)
                l2inv = get_first_item_from_list(l2invs, \
                        'L2 Network', l2Name, 'L3 Network')

                thread = threading.Thread(target=_do_l3_deploy, \
                        args=(l3, l2inv.uuid, l3Name, session_uuid, ))
                wait_for_thread_queue()
                thread.start()

    def _do_l3_deploy(l3, l2inv_uuid, l3Name, session_uuid):
        action = api_actions.CreateL3NetworkAction()
        action.sessionUuid = session_uuid
        action.description = l3.description__
        if l3.system__ and l3.system__ != 'False':
            action.system = 'true'
        action.l2NetworkUuid = l2inv_uuid
        action.name = l3Name
        if l3.uuid__:
            action.resourceUuid = l3.uuid__
        action.type = inventory.L3_BASIC_NETWORK_TYPE
        if l3.domain_name__:
            action.dnsDomain = l3.domain_name__

        try:
            evt = action.run()
        except:
            exc_info.append(sys.exc_info())

        deploy_logger(jsonobject.dumps(evt))
        l3_inv = evt.inventory

        #add dns
        if xmlobject.has_element(l3, 'dns'):
            for dns in xmlobject.safe_list(l3.dns):
                action = api_actions.AddDnsToL3NetworkAction()
                action.sessionUuid = session_uuid
                action.dns = dns.text_
                action.l3NetworkUuid = l3_inv.uuid
                try:
                    evt = action.run()
                except:
                    exc_info.append(sys.exc_info())
                deploy_logger(jsonobject.dumps(evt))

        #add ip range. 
        if xmlobject.has_element(l3, 'ipRange'):
            do_add_ip_range(l3.ipRange, l3_inv.uuid, session_uuid)

        #add network service.
        providers = {}
        action = api_actions.QueryNetworkServiceProviderAction()
        action.sessionUuid = session_uuid
        action.conditions = []
        try:
            reply = action.run()
        except:
            exc_info.append(sys.exc_info())
        for pinv in reply:
            providers[pinv.name] = pinv.uuid

        if xmlobject.has_element(l3, 'networkService'):
            do_add_network_service(l3.networkService, l3_inv.uuid, \
                    providers, session_uuid)

    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone_name != zone.name_:
            continue 

        l2networks = []

        if xmlobject.has_element(zone, 'l2Networks.l2NoVlanNetwork'):
            l2networks.extend(xmlobject.safe_list(zone.l2Networks.l2NoVlanNetwork))

        if xmlobject.has_element(zone, 'l2Networks.l2VlanNetwork'):
            l2networks.extend(xmlobject.safe_list(zone.l2Networks.l2VlanNetwork))

        for l2 in l2networks:
            if l2_name and l2_name != l2.name_:
                continue

            if zone.duplication__ == None:
                duplication = 1
            else:
                duplication = int(zone.duplication__)

            if duplication == 1:
                 _deploy_l3_network(l2, 0, 0)
            else:
                for zone_ref in range(duplication):
                    for cluster in xmlobject.safe_list(zone.clusters.cluster):
                        if cluster.duplication__ == None:
                            cluster_duplication = 1
                        else:
                            cluster_duplication = int(cluster.duplication__)
    
                        for cluster_ref in range(cluster_duplication):
                            _deploy_l3_network(l2, zone_ref, cluster_ref)

    wait_for_thread_done()
    deploy_logger('All add L3 Network actions are done.')

#Add Iprange
def add_ip_range(deployConfig, session_uuid, ip_range_name = None, \
        zone_name= None, l3_name = None):
    '''
    Call by only adding an IP range. If the IP range is in L3 config, 
    add_l3_network will add ip range direclty. 

    deployConfig is a xmlobject. If using standard net_operation, please 
    check net_operations.add_ip_range(test_util.IpRangeOption())
    '''
    if not xmlobject.has_element(deployConfig, "zones.zone"):
        return

    l3networks = []
    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        if zone_name and zone_name != zone.name_:
            continue

        l2networks = []

        if xmlobject.has_element(zone, 'l2Networks.l2NoVlanNetwork'):
            l2networks.extend(xmlobject.safe_list(zone.l2Networks.l2NoVlanNetwork))

        if xmlobject.has_element(zone, 'l2Networks.l2VlanNetwork'):
            l2networks.extend(xmlobject.safe_list(zone.l2Networks.l2VlanNetwork))

        for l2 in l2networks:
            if xmlobject.has_element(l2, 'l3Networks.l3BasicNetwork'):
                l3networks.extend(xmlobject.safe_list(l2.l3Networks.l3BasicNetwork))

    if zone.duplication__ == None:
        duplication = 1
    else:
        duplication = int(zone.duplication__)

    for zone_duplication in range(duplication):
        for l3 in l3networks:
            if l3_name and l3_name != l3.name_:
                continue

            if not xmlobject.has_element(l3, 'ipRange'):
                continue

            if zone_duplication == 0:
                l3Name = l3.name_
            else:
                l3Name = generate_dup_name(l3.name_, zone_duplication, 'z')

            l3_invs = res_ops.get_resource(res_ops.L3_NETWORK, session_uuid, name = l3Name)
            l3_inv = get_first_item_from_list(l3_invs, 'L3 Network', l3Name, 'IP range')
            do_add_ip_range(l3.ipRange, l3_inv.uuid, session_uuid, \
                    ip_range_name)

def do_add_ip_range(ip_range_xml_obj, l3_uuid, session_uuid, \
        ip_range_name = None):

    for ir in xmlobject.safe_list(ip_range_xml_obj):
        if ip_range_name and ip_range_name != ir.name_:
            continue

        action = api_actions.AddIpRangeAction()
        action.sessionUuid = session_uuid
        action.description = ir.description__
        action.endIp = ir.endIp_
        action.gateway = ir.gateway_
        action.l3NetworkUuid = l3_uuid
        action.name = ir.name_
        action.netmask = ir.netmask_
        action.startIp = ir.startIp_
        if ir.uuid__:
            action.resourceUuid = ir.uuid__
        try:
            evt = action.run()
        except Exception as e:
            exc_info.append(sys.exc_info())
            raise e
        deploy_logger(jsonobject.dumps(evt))

#Add Network Service
def add_network_service(deployConfig, session_uuid):
    if not xmlobject.has_element(deployConfig, "zones.zone"):
        return

    l3networks = []
    for zone in xmlobject.safe_list(deployConfig.zones.zone):
        l2networks = []

        if xmlobject.has_element(zone, 'l2Networks.l2NoVlanNetwork'):
            l2networks.extend(xmlobject.safe_list(zone.l2Networks.l2NoVlanNetwork))

        if xmlobject.has_element(zone, 'l2Networks.l2VlanNetwork'):
            l2networks.extend(xmlobject.safe_list(zone.l2Networks.l2VlanNetwork))

        for l2 in l2networks:
            if xmlobject.has_element(l2, 'l3Networks.l3BasicNetwork'):
                l3networks.extend(xmlobject.safe_list(l2.l3Networks.l3BasicNetwork))

    providers = {}
    action = api_actions.QueryNetworkServiceProviderAction()
    action.sessionUuid = session_uuid
    action.conditions = []
    try:
       reply = action.run()
    except Exception as e:
        exc_info.append(sys.exc_info())
        raise e
    for pinv in reply:
        providers[pinv.name] = pinv.uuid

    if zone.duplication__ == None:
        duplication = 1
    else:
        duplication = int(zone.duplication__)

    for zone_duplication in range(duplication):
        for l3 in l3networks:
            if not xmlobject.has_element(l3, 'networkService'):
                continue

            if zone_duplication == 0:
                l3_name = l3.name_
            else:
                l3_name = generate_dup_name(l3.name_, zone_duplication, 'z')

            l3_invs = res_ops.get_resource(res_ops.L3_NETWORK, session_uuid, name = l3_name)
            l3_inv = get_first_item_from_list(l3_invs, 'L3 Network', l3_name, 'Network Service')
            do_add_network_service(l3.networkService, l3_inv.uuid, \
                    providers, session_uuid)

def do_add_network_service(net_service_xml_obj, l3_uuid, providers, \
        session_uuid): 
    allservices = {}
    for ns in xmlobject.safe_list(net_service_xml_obj):
        puuid = providers.get(ns.provider_)
        if not puuid:
            raise DeployError('cannot find network service provider[%s], it may not have been added' % ns.provider_)

        servs = []
        for nst in xmlobject.safe_list(ns.serviceType):
            servs.append(nst.text_)
        allservices[puuid] = servs

    action = api_actions.AttachNetworkServiceToL3NetworkAction()
    action.sessionUuid = session_uuid
    action.l3NetworkUuid = l3_uuid
    action.networkServices = allservices
    try:
        evt = action.run()
    except Exception as e:
        exc_info.append(sys.exc_info())
        raise e
    deploy_logger(jsonobject.dumps(evt))

#Add Image
def add_image(deployConfig, session_uuid):
    def _add_image(action):
        increase_image_thread()
        try:
            evt = action.run()
            deploy_logger(jsonobject.dumps(evt))
        except:
            exc_info.append(sys.exc_info())
        finally:
            decrease_image_thread()

    if not xmlobject.has_element(deployConfig, 'images.image'):
        return

    for i in xmlobject.safe_list(deployConfig.images.image):
        for bsref in xmlobject.safe_list(i.backupStorageRef):
            bss = res_ops.get_resource(res_ops.BACKUP_STORAGE, session_uuid, name=bsref.text_)
            bs = get_first_item_from_list(bss, 'backup storage', bsref.text_, 'image')
            action = api_actions.AddImageAction()
            action.sessionUuid = session_uuid
            #TODO: account uuid will be removed later.
            action.accountUuid = inventory.INITIAL_SYSTEM_ADMIN_UUID
            action.backupStorageUuids = [bs.uuid]
            action.bits = i.bits__
            if not action.bits:
                action.bits = 64
            action.description = i.description__
            action.format = i.format_
            action.mediaType = i.mediaType_
            action.guestOsType = i.guestOsType__
            if not action.guestOsType:
                action.guestOsType = 'unknown'
            action.hypervisorType = i.hypervisorType__
            action.name = i.name_
            action.url = i.url_
            action.timeout = 1800000
            if i.uuid__:
                action.resourceUuid = i.uuid__
            thread = threading.Thread(target = _add_image, args = (action, ))
            print 'before add image1: %s' % i.url_
            wait_for_image_thread_queue()
            print 'before add image2: %s' % i.url_
            thread.start()
            print 'add image: %s' % i.url_

    print 'all images add command are executed'
    wait_for_thread_done(True)
    print 'all images have been added'

#Add Disk Offering
def add_disk_offering(deployConfig, session_uuid):
    def _add_disk_offering(disk_offering_xml_obj, session_uuid):
        action = api_actions.CreateDiskOfferingAction()
        action.sessionUuid = session_uuid
        action.name = disk_offering_xml_obj.name_
        action.description = disk_offering_xml_obj.description_
        action.diskSize = sizeunit.get_size(disk_offering_xml_obj.diskSize_)
        if disk_offering_xml_obj.uuid__:
            action.resourceUuid = disk_offering_xml_obj.uuid__
        evt = action.run()
        dinv = evt.inventory
        deploy_logger(jsonobject.dumps(evt))

    if not xmlobject.has_element(deployConfig, 'diskOfferings.diskOffering'):
        return

    for disk_offering_xml_obj in \
            xmlobject.safe_list(deployConfig.diskOfferings.diskOffering):
        thread = threading.Thread(target = _add_disk_offering, \
                args = (disk_offering_xml_obj, session_uuid))
        wait_for_thread_queue()
        thread.start()

    wait_for_thread_done()

#Add Instance Offering
def add_instance_offering(deployConfig, session_uuid):
    def _add_io(instance_offering_xml_obj, session_uuid):
        action = api_actions.CreateInstanceOfferingAction()
        action.sessionUuid = session_uuid
        action.name = instance_offering_xml_obj.name_
        action.description = instance_offering_xml_obj.description__
        action.cpuNum = instance_offering_xml_obj.cpuNum_
        action.cpuSpeed = instance_offering_xml_obj.cpuSpeed_
        action.memorySize = sizeunit.get_size(instance_offering_xml_obj.memorySize_)
        if instance_offering_xml_obj.uuid__:
            action.resourceUuid = instance_offering_xml_obj.uuid__
        evt = action.run()
        deploy_logger(jsonobject.dumps(evt))

    if not xmlobject.has_element(deployConfig, \
            'instanceOfferings.instanceOffering'):
        return

    for instance_offering_xml_obj in \
            xmlobject.safe_list(deployConfig.instanceOfferings.instanceOffering):
        thread = threading.Thread(target = _add_io, \
                args = (instance_offering_xml_obj, session_uuid, ))
        wait_for_thread_queue()
        thread.start()

    wait_for_thread_done()

    #Add VM -- Pass

def _thread_for_action(action):
    try:
        evt = action.run()
        deploy_logger(jsonobject.dumps(evt))
    except:
        exc_info.append(sys.exc_info())

#Add Virtual Router Offering
def add_virtual_router(deployConfig, session_uuid, l3_name = None, \
        zone_name = None):

    if not xmlobject.has_element(deployConfig, 'instanceOfferings.virtualRouterOffering'):
        return

    for i in xmlobject.safe_list(deployConfig.instanceOfferings.virtualRouterOffering):
        if l3_name and l3_name != i.managementL3NetworkRef.text_:
            continue 

        if zone_name and zone_name != i.zoneRef.text_:
            continue 

        action = api_actions.CreateVirtualRouterOfferingAction()
        action.sessionUuid = session_uuid
        action.name = i.name_
        action.description = i.description__
        action.cpuNum = i.cpuNum_
        action.cpuSpeed = i.cpuSpeed_
        action.memorySize = sizeunit.get_size(i.memorySize_)
        action.isDefault = i.isDefault__
        action.type = 'VirtualRouter'
        if i.uuid__:
            action.resourceUuid = i.uuid__

        zinvs = res_ops.get_resource(res_ops.ZONE, session_uuid, name=i.zoneRef.text_)
        zinv = get_first_item_from_list(zinvs, 'zone', i.zoneRef.text_, 'virtual router offering')
        action.zoneUuid = zinv.uuid
        cond = res_ops.gen_query_conditions('zoneUuid', '=', zinv.uuid)
        cond1 = res_ops.gen_query_conditions('name', '=', \
                i.managementL3NetworkRef.text_, cond)
        minvs = res_ops.query_resource(res_ops.L3_NETWORK, cond1, \
                session_uuid)

        minv = get_first_item_from_list(minvs, 'Management L3 Network', i.managementL3NetworkRef.text_, 'virtualRouterOffering')

        action.managementNetworkUuid = minv.uuid
        if xmlobject.has_element(i, 'publicL3NetworkRef'):
            cond1 = res_ops.gen_query_conditions('name', '=', \
                    i.publicL3NetworkRef.text_, cond)
            pinvs = res_ops.query_resource(res_ops.L3_NETWORK, cond1, \
                    session_uuid)
            pinv = get_first_item_from_list(pinvs, 'Public L3 Network', i.publicL3NetworkRef.text_, 'virtualRouterOffering')

            action.publicNetworkUuid = pinv.uuid

        iinvs = res_ops.get_resource(res_ops.IMAGE, session_uuid, \
                name=i.imageRef.text_)
        iinv = get_first_item_from_list(iinvs, 'Image', i.imageRef.text_, 'virtualRouterOffering')

        action.imageUuid = iinv.uuid

        thread = threading.Thread(target = _thread_for_action, args = (action, ))
        wait_for_thread_queue()
        thread.start()

    wait_for_thread_done()

def deploy_initial_database(deploy_config, admin_passwd = None):
    operations = [
            add_backup_storage,
            add_zone,
            add_l2_network,
            add_primary_storage,
            add_cluster,
            add_host,
            add_l3_network,
            add_image,
            add_disk_offering,
            add_instance_offering,
            add_virtual_router
            ]
    for operation in operations:
        session_uuid = account_operations.login_as_admin(admin_passwd)
        try:
            operation(deploy_config, session_uuid)
        except Exception as e:
            deploy_logger('[Error] zstack deployment meets exception when doing: %s . The real exception are:.' % operation.__name__)
            print('----------------------Exception Reason------------------------')
            traceback.print_exc(file=sys.stdout)
            print('-------------------------Reason End---------------------------\n')
            raise e
        finally:
            account_operations.logout(session_uuid)

    deploy_logger('[Done] zstack initial database was created successfully.')

def generate_dup_name(origin_name, num, prefix=None):
    if num == 0:
        return origin_name

    if prefix:
        return str(origin_name) + '-' + str(prefix) + str(num)
    else:
        return str(origin_name) + '-' + str(num)

def generate_dup_host_ip(origin_ip, zone_ref, cluster_ref, host_ref):
    ip_fields = origin_ip.split('.')
    ip_fields[1] = str(int(ip_fields[1]) + zone_ref)
    ip_fields[2] = str(int(ip_fields[2]) + cluster_ref)
    ip_fields[3] = str(int(ip_fields[3]) + host_ref)
    return '.'.join(ip_fields)

image_thread_queue = 0

@lock.lock('image_thread')
def increase_image_thread():
    global image_thread_queue
    image_thread_queue += 1

@lock.lock('image_thread')
def decrease_image_thread():
    global image_thread_queue
    image_thread_queue -= 1

def wait_for_image_thread_queue():
    while image_thread_queue >= IMAGE_THREAD_LIMIT:
        time.sleep(1)
        print 'image_thread_queue: %d' % image_thread_queue

def wait_for_thread_queue():
    while threading.active_count() > DEPLOY_THREAD_LIMIT:
        check_thread_exception()
        time.sleep(1)

def cleanup_exc_info():
    exc_info = []

def check_thread_exception():
    if exc_info:
        info1 = exc_info[0][1]
        info2 = exc_info[0][2]
        cleanup_exc_info()
        raise info1, None, info2

def wait_for_thread_done(report = False):
    while threading.active_count() > 1:
        check_thread_exception()
        time.sleep(1)
        if report:
            print 'thread workers: %d' % (threading.active_count() - 1)
    check_thread_exception()
