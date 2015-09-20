'''
Read ZStack Config from ZStack 

@author: Youyk
'''
import sys
import traceback
import threading
import time
import xml.etree.cElementTree as etree
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ElementTree

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

NOT_SAVED_DATA = 'createDate lastOpDate'
XML_INDENT='  '

class ReadConfigError(Exception):
    '''zstack deploy exception'''

class JsonToXml(object):
    def __init__(self, json_object, xml_name, xml_parent_element, not_save=''):
        self.json_object = json_object
        self.xml_name = xml_name
        self.xml_parent = xml_parent_element
        self.not_save = NOT_SAVED_DATA + ' ' + not_save

    def generate_xml(self):
        if not self.json_object:
            return None

        xml_item = etree.SubElement(self.xml_parent, self.xml_name)
        json_dict = vars(self.json_object)
        for key,value in json_dict.iteritems():
            if not key in self.not_save and not isinstance(value, list) and \
                    not isinstance(value, dict) and \
                    not isinstance(value, jsonobject.JsonObject):
                value = str(value)
                xml_item.set(key, value)

        return xml_item

def add_xml_items(json_object_list, xml_name, xml_parent_element, not_save=''):
    for json_object in json_object_list:
        json_to_xml = JsonToXml(json_object, xml_name, xml_parent_element, \
                not_save)
        json_to_xml.generate_xml()

def get_node(xml_root, session_uuid = None):
    nodes = res_ops.safely_get_resource(res_ops.MANAGEMENT_NODE, [], \
            session_uuid)
    if nodes:
        xml_nodes = etree.SubElement(xml_root, "nodes")
        add_xml_items(nodes, 'node', xml_nodes, 'heartBeat joinDate')
        return xml_nodes

def get_instance_offering(xml_root, session_uuid = None):
    cond = []
    vr_inst_offerings = res_ops.safely_get_resource(res_ops.VR_OFFERING, cond, \
            session_uuid)
    uuids = ''
    if vr_inst_offerings:
        vr_offering_uuids = res_ops.safely_get_resource(res_ops.VR_OFFERING, \
                [], session_uuid, ['uuid'])
        for vr_uuid in vr_offering_uuids:
            uuids += ' %s' % vr_uuid.uuid

    cond = res_ops.gen_query_conditions('uuid', 'not in', uuids)
    inst_offerings = res_ops.safely_get_resource(res_ops.INSTANCE_OFFERING, \
            cond, session_uuid)

    if vr_inst_offerings or inst_offerings:
        xml_item = etree.SubElement(xml_root, "instanceOfferings")
        add_xml_items(inst_offerings, 'instanceOffering', xml_item)
        for vr_offering in vr_inst_offerings:
            vr_offering_xml_obj = JsonToXml(vr_offering, 
                    'virtualRouterOffering', xml_item, 'managementNetworkUuid \
                    publicNetworkUuid zoneUuid imageUuid')
            vr_offering_xml = vr_offering_xml_obj.generate_xml()
            zone_uuid = vr_offering.zoneUuid
            cond = res_ops.gen_query_conditions('uuid', '=', zone_uuid)
            zone_name = res_ops.query_resource(res_ops.ZONE, cond, \
                    session_uuid)[0].name
            _set_res_ref(vr_offering_xml, 'zoneRef', zone_name)

            pub_l3_uuid = vr_offering.publicNetworkUuid
            cond = res_ops.gen_query_conditions('uuid', '=', pub_l3_uuid)
            l3_name = res_ops.query_resource(res_ops.L3_NETWORK, cond, \
                    session_uuid)[0].name
            _set_res_ref(vr_offering_xml, 'publicL3NetworkRef', l3_name)

            mgt_l3_uuid = vr_offering.managementNetworkUuid
            cond = res_ops.gen_query_conditions('uuid', '=', mgt_l3_uuid)
            l3_name = res_ops.query_resource(res_ops.L3_NETWORK, cond, \
                    session_uuid)[0].name
            _set_res_ref(vr_offering_xml, 'managementL3NetworkRef', l3_name)

            img_uuid = vr_offering.imageUuid
            cond = res_ops.gen_query_conditions('uuid', '=', img_uuid)
            img_name = res_ops.query_resource(res_ops.IMAGE, cond, \
                    session_uuid)[0].name
            _set_res_ref(vr_offering_xml, 'imageRef', img_name)

        return xml_item

def get_disk_offering(xml_root, session_uuid = None):
    cond = []
    disk_offerings = res_ops.safely_get_resource(res_ops.DISK_OFFERING, cond, \
            session_uuid)

    if disk_offerings:
        xml_item = etree.SubElement(xml_root, "diskOfferings")
    else:
        return None

    add_xml_items(disk_offerings, 'diskOffering', xml_item)
    return xml_item
    

def get_backup_storage(xml_root, session_uuid = None):
    cond = []
    bs_storages = res_ops.safely_get_resource(res_ops.BACKUP_STORAGE, cond, \
            session_uuid)

    if bs_storages:
        xml_item = etree.SubElement(xml_root, "backupStorages")
    else:
        return None
    
    bs_storages = res_ops.safely_get_resource(res_ops.BACKUP_STORAGE,\
            cond, session_uuid)

    for bs in bs_storages:
        if bs.type == inventory.SFTP_BACKUP_STORAGE_TYPE:
       	    json_to_xml = JsonToXml(bs, 'sftpBackupStorage', xml_item, \
                   'attachedZoneUuids availableCapacity totalCapacity')
            json_to_xml.generate_xml()
        elif bs.type == inventory.CEPH_BACKUP_STORAGE_TYPE:
       	    json_to_xml = JsonToXml(bs, 'cephBackupStorage', xml_item, \
                   'attachedZoneUuids availableCapacity totalCapacity')
            json_to_xml.generate_xml()

    cond = res_ops.gen_query_conditions('type', '=', 'SimulatorBackupStorage')
    simulator_bss = res_ops.safely_get_resource(res_ops.BACKUP_STORAGE, \
            cond, session_uuid)

    if simulator_bss:
        add_xml_items(simulator_bss, 'simulatorBackupStorage', xml_item, \
                'attachedZoneUuids')

    return xml_item

def _set_backup_strorage_ref(xml_obj, bs_name):
    bs_ref = etree.SubElement(xml_obj, 'backupStorageRef')
    bs_ref.text = bs_name

def _set_primary_strorage_ref(xml_obj, ps_name):
    ps_ref = etree.SubElement(xml_obj, 'primaryStorageRef')
    ps_ref.text = ps_name

def _set_l2_ref(xml_obj, l2_name):
    l2_ref = etree.SubElement(xml_obj, 'l2NetworkRef')
    l2_ref.text = l2_name

def _set_res_ref(xml_obj, res_key, res_name):
    res_ref = etree.SubElement(xml_obj, res_key)
    res_ref.text = res_name

def get_image(xml_root, session_uuid = None):
    cond = []
    images = res_ops.safely_get_resource(res_ops.IMAGE, cond, session_uuid)

    if images:
        xml_item = etree.SubElement(xml_root, "images")
    else:
        return None

    for image in images:
        json_to_xml = JsonToXml(image, 'image', xml_item, 'md5Sum, size')
        xml_image = json_to_xml.generate_xml()
        bss = image.backupStorageRefs
        for bs in bss:
            bs_uuid = bs.backupStorageUuid
            cond = res_ops.gen_query_conditions('uuid', '=', bs_uuid)
            bs_name = res_ops.query_resource(res_ops.BACKUP_STORAGE, cond, \
                    session_uuid)[0].name

            _set_backup_strorage_ref(xml_image, bs_name)

    return xml_item

def get_zone(xml_root, session_uuid = None):
    def _get_primary_storage(pss_xml, zone):
        cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
        pss = res_ops.safely_get_resource(res_ops.PRIMARY_STORAGE, cond, \
                session_uuid)
        for ps in pss:
            if ps.type == inventory.NFS_PRIMARY_STORAGE_TYPE:
       	        json_to_xml = JsonToXml(ps, 'nfsPrimaryStorage', pss_xml, \
                        'availableCapacity mountPath totalCapacity type zoneUuid totalPhysicalCapacity')
                json_to_xml.generate_xml()
            elif ps.type == inventory.CEPH_PRIMARY_STORAGE_TYPE:
       	        json_to_xml = JsonToXml(ps, 'cephPrimaryStorage', pss_xml, \
                        'availableCapacity mountPath totalCapacity type zoneUuid totalPhysicalCapacity')
                json_to_xml.generate_xml()
            elif ps.type == inventory.LOCAL_STORAGE_TYPE:
       	        json_to_xml = JsonToXml(ps, 'localPrimaryStorage', pss_xml, \
                        'availableCapacity mountPath totalCapacity type zoneUuid totalPhysicalCapacity')
                json_to_xml.generate_xml()

        cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
        cond = res_ops.gen_query_conditions('type', '=', \
                'SimulatorPrimaryStorage', cond)
        pss = res_ops.safely_get_resource(res_ops.PRIMARY_STORAGE, cond, \
                session_uuid)
        add_xml_items(pss, 'simulatorPrimaryStorage', pss_xml, \
                'mountPath type zoneUuid')

    def _get_cluster(clusters_xml, clusters):
        for cluster in clusters:
            cluster_xml_obj = JsonToXml(cluster, 'cluster', clusters_xml)
            cluster_xml = cluster_xml_obj.generate_xml()

            #add_hosts
            cond = res_ops.gen_query_conditions('clusterUuid', '=', \
                    cluster.uuid)
            hosts = res_ops.safely_get_resource(res_ops.HOST, cond, \
                    session_uuid)
            if hosts:
                hosts_xml = etree.SubElement(cluster_xml, "hosts")
                add_xml_items(hosts, 'host', hosts_xml, \
                        'availableCpuCapacity availableMemoryCapacity \
                        clusterUuid hypervisorType totalCpuCapacity \
                        totalMemoryCapacity zoneUuid')
            
            #add ps ref
            cond = res_ops.gen_query_conditions('attachedClusterUuids', 'in', \
                    cluster.uuid)
            pss = res_ops.safely_get_resource(res_ops.PRIMARY_STORAGE, cond, \
                    session_uuid, fields=['name'])

            for ps in pss:
                _set_primary_strorage_ref(cluster_xml, ps.name)


            #add l2 ref
            cond = res_ops.gen_query_conditions('attachedClusterUuids', 'in', \
                    cluster.uuid)
            l2s = res_ops.safely_get_resource(res_ops.L2_NETWORK, cond, 
                    session_uuid, fields=['name'])

            for l2 in l2s:
                _set_l2_ref(cluster_xml, l2.name)

    def _add_l3(l2_xml, l2):
        #basic
        cond = res_ops.gen_query_conditions('l2NetworkUuid', '=', l2.uuid)
        cond = res_ops.gen_query_conditions('type', '=', 'L3BasicNetwork', cond)
        l3s = res_ops.safely_get_resource(res_ops.L3_NETWORK, cond, 
                session_uuid)
        if not l3s:
            return None

        l3s_xml = etree.SubElement(l2_xml, "l3Networks")
        for l3 in l3s:
            l3_xml_obj = JsonToXml(l3, 'l3BasicNetwork', l3s_xml, \
                    'type zoneUuid l2NetworkUuid')
            l3_xml = l3_xml_obj.generate_xml()

            #ip range
            cond = res_ops.gen_query_conditions('l3NetworkUuid', '=', l3.uuid)
            ip_ranges = res_ops.safely_get_resource(res_ops.IP_RANGE, cond, 
                    session_uuid)
            add_xml_items(ip_ranges, 'ipRange', l3_xml, 'l3NetworkUuid')

            #dns
            if l3.dns:
                for dns in l3.dns:
                    dns_xml = etree.SubElement(l3_xml, "dns")
                    dns_xml.text = dns

            #network service
            if l3.networkServices:
                nss_dict = {}
                for ns in l3.networkServices:
                    if not ns.networkServiceProviderUuid in nss_dict.keys():
                        nss_dict[ns.networkServiceProviderUuid] \
                                = [ns.networkServiceType]
                    else:
                        nss_dict[ns.networkServiceProviderUuid].append(ns.networkServiceType)

                for key in nss_dict.keys():
                    cond = res_ops.gen_query_conditions('uuid', '=', key)
                    ns = res_ops.safely_get_resource(\
                            res_ops.NETWORK_SERVICE_PROVIDER, cond, session_uuid)
                    ns_name = ns[0].name
    
                    ns_xml = etree.SubElement(l3_xml, "networkService")
                    ns_xml.set('provider', ns_name)
                    for value in nss_dict[key]:
                        ns_type_xml = etree.SubElement(ns_xml, 'serviceType')
                        ns_type_xml.text = value

    cond = []
    zones = res_ops.safely_get_resource(res_ops.ZONE, cond, session_uuid)

    if not zones:
        return None

    zones_xml = etree.SubElement(xml_root, "zones")

    for zone in zones:
        zone_xml_obj = JsonToXml(zone, 'zone', zones_xml)
        zone_xml = zone_xml_obj.generate_xml()

        #query bs ref
        cond = res_ops.gen_query_conditions('attachedZoneUuids', 'in', \
                zone.uuid)
        bss = res_ops.safely_get_resource(res_ops.BACKUP_STORAGE, cond, \
                session_uuid, fields=['name'])
        for bs in bss:
            _set_backup_strorage_ref(zone_xml, bs.name)

        #query ps
        cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
        pss = res_ops.safely_get_resource(res_ops.PRIMARY_STORAGE, cond, \
                session_uuid)

        if pss:
            pss_xml = etree.SubElement(zone_xml, "primaryStorages")
            _get_primary_storage(pss_xml, zone)

        #query cluster
        cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
        clusters = res_ops.safely_get_resource(res_ops.CLUSTER, cond, \
                session_uuid)
        if clusters:
            clusters_xml = etree.SubElement(zone_xml, "clusters")
            _get_cluster(clusters_xml, clusters)

        #add l2
        cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
        l2s = res_ops.safely_get_resource(res_ops.L2_NETWORK, cond, \
                session_uuid)
        if l2s:
            l2s_xml = etree.SubElement(zone_xml, "l2Networks")
            #query no vlan
            cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
            cond = res_ops.gen_query_conditions('type', '=', 'L2NoVlanNetwork')
            l2s_no_vlan = res_ops.safely_get_resource(res_ops.L2_NETWORK, 
                    cond, session_uuid)

            for l2 in l2s_no_vlan:
                l2_no_vlan_obj = JsonToXml(l2, 'l2NoVlanNetwork', l2s_xml, 
                        'type zoneUuid')
                l2_xml = l2_no_vlan_obj.generate_xml()
                _add_l3(l2_xml, l2)

            #query vlan
            cond = res_ops.gen_query_conditions('zoneUuid', '=', zone.uuid)
            l2s_vlan = res_ops.safely_get_resource(res_ops.L2_VLAN_NETWORK, 
                    cond, session_uuid)

            for l2 in l2s_vlan:
                l2_vlan_xml_obj = JsonToXml(l2, 'l2VlanNetwork', l2s_xml, 
                        'type zoneUuid')
                l2_xml = l2_vlan_xml_obj.generate_xml()
                _add_l3(l2_xml, l2)

def beautify_xml_element(xml_root_element):
    xml_str = minidom.parseString(ElementTree.tostring(xml_root_element))
    new_xml = xml_str.toprettyxml(indent=XML_INDENT)
    return new_xml

def make_xml_editable(xml_str):
    xml_list = xml_str.split('\n')
    new_list = []
    for line in xml_list:
        if not '" ' in line:
            if line.strip().startswith('<') and \
                    not line.strip().startswith('</'):
                new_list.append('')
            new_list.append(line)
        else:
            curr_len = len(line)
            if curr_len < 80:
                new_list.append(line)
                continue

            indents = curr_len - len(line.strip())
            blanks = ' ' * indents + XML_INDENT
            line = line.replace('" ', '"\n%s' % blanks)
            new_list.extend(line.split('\n'))

    return '\n'.join(new_list)

def dump_zstack(save_to_file = None, admin_passwd = None):
    xml_root = etree.Element("deployerConfig")
    try:
        session_uuid = account_operations.login_as_admin(admin_passwd)
        get_node(xml_root, session_uuid)
        get_instance_offering(xml_root, session_uuid)
        get_disk_offering(xml_root, session_uuid)
        get_backup_storage(xml_root, session_uuid)
        get_image(xml_root, session_uuid)
        get_zone(xml_root, session_uuid)
    except Exception as e:
        try:
            account_operations.logout(session_uuid)
        except:
            print ' '
        raise e

    account_operations.logout(session_uuid)

    new_xml = str(beautify_xml_element(xml_root))
#    new_xml = new_xml.replace('" ', '"\n')
    new_xml = make_xml_editable(new_xml)
    print new_xml
    if save_to_file:
        open(save_to_file, 'w').write(new_xml)

