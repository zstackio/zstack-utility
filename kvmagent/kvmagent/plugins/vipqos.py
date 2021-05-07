from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import iproute
from zstacklib.utils.bash import *

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class VipQos(kvmagent.KvmAgent):

    APPLY_VIPQOS_PATH = "/flatnetworkprovider/vipqos/apply"
    DELETE_VIPQOS_PATH = "/flatnetworkprovider/vipqos/delete"
    DELETE_VIPALLQOS_PATH = "/flatnetworkprovider/vipqos/deleteall"
    VIPQOS_DEFAULT_RULE_BANDWIDTH = 10737418240          #bandwidth is 10G

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.APPLY_VIPQOS_PATH, self.apply_vipqos)
        http_server.register_async_uri(self.DELETE_VIPQOS_PATH, self.delete_vipqos)
        http_server.register_async_uri(self.DELETE_VIPALLQOS_PATH, self.delete_vipallqos)

    def stop(self):
        pass

    @kvmagent.replyerror
    def apply_vipqos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._apply_vipqos_rules(cmd.vipQosSettings)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def delete_vipqos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._delete_vipqos_rules(cmd.vipQosSettings)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def delete_vipallqos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._delete_vipallqos_rules(cmd.vipQosSettings)
        return jsonobject.dumps(AgentRsp())

    @lock.lock('vipqos')
    def _apply_vipqos_rules(self, rules):
        for rule in rules:
            self._apply_vipqos_rule(rule)

    @lock.lock('vipqos')
    def _delete_vipqos_rules(self, rules):
        for rule in rules:
            self._delete_vipqos_rule(rule)

    @lock.lock('vipqos')
    def _delete_vipallqos_rules(self, rules):
        for rule in rules:
            self._delete_vipallqos_rule(rule)

    @in_bash
    def _apply_vipqos_rule(self, rule):
        '''
        qos rules format:
        {
            "vipUuid":              "1a81681c6e42457788c851cb4db62d1c",  ############# This is the eip uuid which bound to vip
            "vip":                  "11.168.100.95",
            "port":                 0,
            "inboundBandwidth":     1048576,
            "outboundBandwidth":    0
        }
        '''

        EIP_UUID = rule['vipUuid'][-9:]

        PUB_IDEV = "%s_ei" % (EIP_UUID)
        PRI_IDEV = "%s_i" % (EIP_UUID)
        NS_NAME = self._find_ns_name(rule['vip'])
        NS_CMD = "ip netns exec %s " % NS_NAME.strip('\n')
        if NS_NAME == "":
            raise Exception('namespace for Vip %s is not created' % rule['vip'])

        if rule['inboundBandwidth'] != 0:
            self._delete_vipqos_rule_from_nic(PRI_IDEV, NS_CMD, rule['port'])
            self._apply_vipqos_rule_to_nic(PRI_IDEV, NS_CMD, rule['port'], rule['inboundBandwidth'])

        if rule['outboundBandwidth'] != 0:
            self._delete_vipqos_rule_from_nic(PUB_IDEV, NS_CMD, rule['port'])
            self._apply_vipqos_rule_to_nic(PUB_IDEV, NS_CMD, rule['port'], rule['outboundBandwidth'])

    @in_bash
    def _find_ns_name(self, vip):
        vip = vip.replace('.', '_')
        nslist = filter(lambda x: x.find(vip) >= 0, iproute.query_all_namespaces())
        return nslist[0] if nslist else ""

    @in_bash
    def _apply_vipqos_rule_to_nic(self, nic, ns_cmd, port, bandiwith):
        self._init_vipqos_rules(nic, ns_cmd)

        if port == 0:
            self._change_vipqos_default_rule_bandwidth(nic, ns_cmd, bandiwith)
            return

        classId = self._find_empty_classid(nic, ns_cmd)
        if classId == 0:
            raise Exception('Too much qos rules added to %s' % nic)

        bash_r("{{ns_cmd}} tc class add dev {{nic}} parent 1:0 classid 1:{{classId}} htb rate {{bandiwith}} ceil {{bandiwith}} burst 15736 cburst 15736; "+
               "{{ns_cmd}} tc qdisc add dev {{nic}} parent 1:{{classId}} sfq")

        #if nic suffix is "_ei", use for outbound, so match sport
        handleId = format(classId, '03x')
        if nic.find("_ei") == -1:
            bash_r("{{ns_cmd}} tc filter add dev {{nic}} parent 1:0 prio 1 handle 800::{{handleId}} protocol ip u32 match ip dport {{port}} 0xffff flowid 1:{{classId}}")
        else:
            bash_r("{{ns_cmd}} tc filter add dev {{nic}} parent 1:0 prio 1 handle 800::{{handleId}} protocol ip u32 match ip sport {{port}} 0xffff flowid 1:{{classId}}")

    @in_bash
    def _find_empty_classid(self, nic, ns_cmd):
        classIds = bash_o("{{ns_cmd}} tc class show dev {{nic}} | awk '{print $3}' | awk -F ':' '{print $2}'")
        classIds = classIds.split('\n')

        classMap = {}
        for id in classIds:
            classMap[id] = ''

        classId = 0
        for index in range(2, 0xFFF + 1):
            if classMap.has_key(str(index)) == False:
                classId = index
                break

        return classId

    @in_bash
    def _change_vipqos_default_rule_bandwidth(self, nic, ns_cmd, bandiwith):
        '''
            qos rule without port will is the default rule, its classid is 1:1
            so only need to do is change the bandwith in class 1:1
        '''
        bash_r("{{ns_cmd}} tc class change dev {{nic}} parent 1:0 classid 1:1 htb rate {{bandiwith}} ceil {{bandiwith}} burst 15k cburst 15k")

    @in_bash
    def _init_vipqos_rules(self, nic, ns_cmd):
        qdisc_type = bash_o("{{ns_cmd}} tc qdisc show dev {{nic}} | grep -m1 \"\" | awk '{print $2}'")
        qdisc_type = qdisc_type.strip('\n').strip(' ')

        if qdisc_type == "htb":
            return

        bandwith = self.VIPQOS_DEFAULT_RULE_BANDWIDTH
        bash_r("{{ns_cmd}} tc qdisc replace dev {{nic}} root handle 1: htb default 1;"+
               "{{ns_cmd}} tc class add dev {{nic}} parent 1:0 classid 1:1 htb rate {{bandwith}} ceil {{bandwith}};"+
               "{{ns_cmd}} tc qdisc add dev {{nic}} parent 1:1 sfq;" +
               "{{ns_cmd}} tc filter add dev {{nic}} parent 1:0 prio 1 protocol ip u32")

    @in_bash
    def _delete_vipqos_rule(self, rule):
        EIP_UUID = rule['vipUuid'][-9:]

        PUB_IDEV = "%s_ei" % (EIP_UUID)
        PRI_IDEV = "%s_i" % (EIP_UUID)
        NS_NAME = self._find_ns_name(rule['vip'])
        if NS_NAME == "":
            raise Exception('namespace for Vip %s is not created' % rule['vip'])
        NS_CMD = "ip netns exec %s " % NS_NAME.strip('\n')

        if rule['inboundBandwidth'] != 0:
            self._delete_vipqos_rule_from_nic(PRI_IDEV, NS_CMD, rule['port'])

        if rule['outboundBandwidth'] != 0:
            self._delete_vipqos_rule_from_nic(PUB_IDEV, NS_CMD, rule['port'])

    @in_bash
    def _find_classid_with_port(self, nic, ns_cmd, port):
        portstr = format(port, '04x')
        if nic.find("_ei") == -1:
            filter = "0000%s/0000ffff" % portstr
        else:
            filter = "%s0000/ffff0000" % portstr

        classId = bash_o("{{ns_cmd}} tc filter show dev {{nic}} | grep -B 1 {{filter}} | grep -m1 \"\" | awk '{print $19}' | awk -F ':' '{print $2}'")
        return classId

    @in_bash
    def _delete_vipqos_rule_from_nic(self, nic, ns_cmd, port):
        if port == 0:
            self._change_vipqos_default_rule_bandwidth(nic, ns_cmd, self.VIPQOS_DEFAULT_RULE_BANDWIDTH)
        else:
            classid = self._find_classid_with_port(nic, ns_cmd, port)
            if classid == "":
                logger.warn("can not find classid for nic %s port %s" % (nic, port))
                return

            classidx = int(classid)
            classidHex = format(classidx, '03x')
            bash_r("{{ns_cmd}} tc filter del dev {{nic}} parent 1:0 prio 1 handle 800::{{classidHex}} protocol ip u32;"+
                   "{{ns_cmd}} tc qdisc del dev {{nic}} parent 1:{{classidx}} sfq;"+
                   "{{ns_cmd}} tc class del dev {{nic}} parent 1:0 classid 1:{{classidx}};")

    @in_bash
    def _delete_vipallqos_rule(self, rule):
        EIP_UUID = rule['vipUuid'][-9:]
        PUB_IDEV = "%s_ei" % (EIP_UUID)
        PRI_IDEV = "%s_i" % (EIP_UUID)
        NS_NAME = self._find_ns_name(rule['vip'])
        if NS_NAME == "":
            raise Exception('namespace for Vip %s is not created' % rule['vip'])
        NS_CMD = "ip netns exec %s " % NS_NAME.strip('\n')

        bash_r("{{NS_CMD}} tc qdisc del dev {{PUB_IDEV}} root")
        bash_r("{{NS_CMD}} tc qdisc del dev {{PRI_IDEV}} root")

'''
if __name__ == '__main__':
    rule1 = {
        "vipUuid":              "2a342b3ddd0f408c945c3576940a5a3a",
        "vip":                  "10.86.1.51",
        "port":                 0,
        "inboundBandwidth":     1048576,
        "outboundBandwidth":    1048576
    }
    rule2 = {
        "vipUuid":              "2a342b3ddd0f408c945c3576940a5a3a",
        "vip":                  "10.86.1.51",
        "port":                 100,
        "inboundBandwidth":     1048576,
        "outboundBandwidth":    1048576
    }
    rule3 = {
        "vipUuid":              "2a342b3ddd0f408c945c3576940a5a3a",
        "vip":                  "10.86.1.51",
        "port":                 200,
        "inboundBandwidth":     2048576,
        "outboundBandwidth":    2048576
    }
    rule4 = {
        "vipUuid":              "2a342b3ddd0f408c945c3576940a5a3a",
        "vip":                  "10.86.1.51",
        "port":                 300,
        "inboundBandwidth":     3048576,
        "outboundBandwidth":    3048576
    }
    rule5 = {
        "vipUuid":              "2a342b3ddd0f408c945c3576940a5a3a",
        "vip":                  "10.86.1.51",
        "port":                 400,
        "inboundBandwidth":     4048576,
        "outboundBandwidth":    4048576
    }
    vipqos = VipQos()
    rules1 = [rule1, rule2, rule3, rule4, rule5]
    vipqos._apply_vipqos_rules(rules1)
    vipqos._delete_vipqos_rules(rules1)

    rules2 = [rule5, rule1]
    vipqos._apply_vipqos_rules(rules2)
    vipqos._delete_vipallqos_rule(rule1)
'''
