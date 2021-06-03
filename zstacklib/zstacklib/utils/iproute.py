
import os
import socket
import pyroute2
from zstacklib.utils import log

logger = log.get_logger(__name__)

# annotation
def _log_iproute_call(text):
    def wrap(func):
        def inner(*args, **kwargs):
            cmd = '%s: args=%s,%s' % (text, args, kwargs)
            try:
                ret = func(*args, **kwargs)
                logger.debug(cmd if ret == None else '%s, return %s' % (cmd, ret))
                return ret
            except Exception as e:
                logger.warn('%s, raise: %s' % (cmd, e))
                raise
        return inner
    return wrap

# annotation
def _no_error_do(func):
    def aim_to_do(*args, **kwargs):
        try:
            func(*args, **kwargs)
            return True
        except Exception:
            return False
    return aim_to_do

def get_iproute(namespace=None):
    '''
        :raise NoSuchNamespace   if namespace is not None and not exists
    '''
    # From iproute.py:
    # `IPRoute` -- RTNL API to the current network namespace
    # `NetNS` -- RTNL API to another network namespace
    if namespace is not None:
        # do not try and create the namespace
        if is_namespace_exists(namespace):
            return pyroute2.NetNS(namespace)
        raise NoSuchNamespace(namespace)
    else:
        return pyroute2.IPRoute()

_IP_VERSION_FAMILY_MAP = {4: socket.AF_INET, 6: socket.AF_INET6}

def _get_scope_name(scope, exception_if_wrong = False):
    '''
        Metheds from openstack/neutron
        Return the name of the scope (given as a number), or the scope number
        if the name is unknown. 'universe' is equals to 'global'.

        :param scope  str or int:  'universe'('global'), 'site', 'link', 'host', 'nowhere'
        :return       int or str
        :raise        InvalidScope: if param scope is invalid
    '''
    scope = 'universe' if scope == 'global' else scope
    ret = pyroute2.netlink.rtnl.rt_scope.get(scope)
    if ret is None and exception_if_wrong:
        raise InvalidScope(scope)
    return ret

class NoSuchNamespace(RuntimeError):
    def __init__(self, namespace):
        super(NoSuchNamespace, self).__init__("Network namespace : %(namespace)s could not be found." % {'namespace': namespace})
        self.namespace = namespace

class NamespaceAlreadyExists(RuntimeError):
    def __init__(self, namespace):
        super(NamespaceAlreadyExists, self).__init__("Network namespace : %(namespace)s has already exists." % {'namespace': namespace})
        self.namespace = namespace

class InvalidScope(RuntimeError):
    def __init__(self, scope):
        super(NoSuchScope, self).__init__("Scope : %(scope)s is invalid." % {'scope': scope})
        self.scope = scope

class InvalidIpVersion(RuntimeError):
    def __init__(self, ip_version):
        super(NoSuchScope, self).__init__("IpVersion : %(ip_version)s is invalid." % {'ip_version': ip_version})
        self.ip_version = ip_version

class NoSuchLinkDevice(RuntimeError):
    def __init__(self, ifname, index = None, cause = None):
        super(NoSuchLinkDevice, self).__init__("Link device(s) :%(ifname)s%(index)s could not be found.%(cause)s" %
            {
                'ifname': ' ifname=%s' % ifname if ifname is not None else '',
                'index': ' index=%s' % index if index is not None else '',
                'cause': ' Because : %s' % cause if cause else ''
            })
        self.ifname = ifname
        self.index = index
        self.cause = cause

class IpAddr:
    def __init__(self, chunk, iproute):
        self.index = chunk['index']
        self.family = chunk['family']
        self.ip_version = 4 if chunk['family'] == socket.AF_INET else 6
        self.prefixlen = chunk['prefixlen']
        self.address = None
        self.label = ''
        self.ifname = '' # alias for label
        self.chunk = chunk
        for attr in chunk['attrs']:
            if attr[0] == 'IFA_ADDRESS':
                self.address = attr[1]
            elif attr[0] == 'IFA_LABEL':
                self.label = attr[1]
                self.ifname = attr[1]
        self.scope = _get_scope_name(chunk['scope'])
        if not self.ifname:
            try:
                link = iproute.get_links(self.index)[0]
                self.ifname = link.get_attr('IFA_LABEL') or link.get_attr('IFLA_IFNAME')
            except:
                pass

class IpLink:
    def __init__(self, chunk):
        self.index = chunk['index']
        self.ip_version = 4 if chunk['family'] == socket.AF_INET else 6
        # self.state = chunk['state'] # 'up'
        self.mac = chunk.get_attr('IFLA_ADDRESS') # link/ether, mac address, type str
        self.ifname = chunk.get_attr('IFA_LABEL') or chunk.get_attr('IFLA_IFNAME') # type: str | None
        self.mtu = chunk.get_attr('IFLA_MTU') # type: int
        self.qlen = chunk.get_attr('IFLA_TXQLEN') # type: int
        self.state = chunk.get_attr('IFLA_OPERSTATE') # type: str
        self.qdisc = chunk.get_attr('IFLA_QDISC') # type: tuple
        self.alias = chunk.get_attr('IFLA_IFALIAS') # type: tuple. if no alias, self.alias = (None,)
        self.allmulticast = bool(chunk['flags'] & pyroute2.netlink.rtnl.ifinfmsg.IFF_ALLMULTI) # type: tuple
        self.device_type = chunk.get_nested('IFLA_LINKINFO', 'IFLA_INFO_KIND')
        self.broadcast = chunk.get_attr('IFLA_BROADCAST') # type: str
        self.group = chunk.get_attr('IFLA_GROUP') # type: int
        self.chunk = chunk  

class IpRoute:
    def __init__(self, chunk):
        self.family = chunk['family']
        self.ip_version = 4 if chunk['family'] == socket.AF_INET else 6
        self.via_ip = chunk.get_attr('RTA_GATEWAY')
        self.src_ip = chunk.get_attr('RTA_PREFSRC')
        self.src_len = chunk['src_len']
        self.dst_ip = chunk.get_attr('RTA_DST')
        self.dst_len = chunk['dst_len']
        self.device_index = chunk.get_attr('RTA_OIF')
        self.table = chunk['table']
        self.scope = _get_scope_name(chunk['scope'])
        self.chunk = chunk
    def get_related_addresses(self, namespace=None):
        '''
            :return IpAddr[]
        '''
        return query_addresses(index=self.devIndex, namespace=namespace)
    def get_related_link_device(self, namespace=None):
        '''
            :return IpLink
        '''
        return query_link(self.device_index, namespace)

def _get_device_index(ifname_or_index, iproute, exception_if_wrong = True):
    '''
        :param iproute: not None
    '''
    if isinstance(ifname_or_index, int):
        return ifname_or_index
    elif isinstance(ifname_or_index, (str, unicode)):
        ret = _query_index_by_ifname(ifname_or_index, iproute)
        if ret or not exception_if_wrong:
            return ret
    if exception_if_wrong:
        raise NoSuchLinkDevice(ifname_or_index)
    return None

def query_index_by_ifname(ifname, namespace = None):
    '''
        :return int or None
    '''
    with get_iproute(namespace) as ipr:
        return _query_index_by_ifname(ifname, ipr)

def is_device_ifname_exists(ifname, namespace = None):
    '''
        :return bool
    '''
    return query_index_by_ifname(ifname, namespace) is not None

def is_device_index_exists(index, namespace = None):
    '''
        :return bool
    '''
    with get_iproute(namespace) as ipr:
        return _is_device_index_exists(index, ipr)

def _query_index_by_ifname(ifname, iproute):
    '''
        :param iproute: not None
        :return int or None
    '''
    rets = iproute.link_lookup(ifname=ifname)
    return rets[0] if rets else None

def _is_device_index_exists(index, iproute):
    '''
        :param iproute: not None
        :return bool
    '''
    rets = iproute.link_lookup(index=index)
    return len(rets) == 1

def _check_index_and_ifname(ifname, index, iproute, exception_if_wrong = False):
    '''
        @param iproute: not None
        @return index: int, 0 is invalid
    '''
    if ifname:
        ret = _query_index_by_ifname(ifname, iproute)
        if ret is None and exception_if_wrong:
            raise NoSuchLinkDevice(ifname)
        if index is None:
            return ret if ret else 0
        elif ret != index:
            if exception_if_wrong:
                raise NoSuchLinkDevice(ifname, index, 'param ifname and index is not match')
            else:
                return 0
        else:
            return ret
    else:
        if index is None or not _is_device_index_exists(index, iproute):
            if exception_if_wrong:
                raise NoSuchLinkDevice(None, None, 'param ifname and index can not be None at the same time') if index is None else NoSuchLinkDevice(None, index)
            return 0
        return index

def _check_ip_version(ip_version, none_is_supported = True, exception_if_wrong = True):
    '''
        :param ip_version   4 or 6
        :return   socket.family, type int
        :raise   InvalidIpVersion
    '''
    if ip_version is None:
        if none_is_supported or not exception_if_wrong:
            return None
        else:
            raise InvalidIpVersion(ip_version)
    ret = _IP_VERSION_FAMILY_MAP.get(ip_version)
    if ret is None and exception_if_wrong:
        raise InvalidIpVersion(ip_version)
    return ret

# ========= address =========
def query_addresses(namespace=None, **kwargs):
    '''
        :kwargs condition. If empty, return all IpAddrs.
                    ifname: device name.
                    scope: 'host', 'global', and so on
                    ip: ip address
                    ip_version: 4 or 6, or None for all
                    index: device index. It is recommended to choose between ifname and index, not both
        :return IpAddr[]
    '''
    with get_iproute(namespace) as ipr:
        if kwargs is not None:
            # ifname is not supported in pyroute2.IPRoute, unless use index
            if kwargs.has_key('ifname'):
                device_index = _check_index_and_ifname(kwargs['ifname'], kwargs.get('index'), ipr, False)
                if device_index == 0:
                    return []
                kwargs['index'] = device_index
                del kwargs['ifname']
            # scope should convert to int type
            if kwargs.has_key('scope') and isinstance(kwargs['scope'], (str, unicode)):
                kwargs['scope'] = _get_scope_name(kwargs['scope'], True)
            if kwargs.has_key('ip') and isinstance(kwargs['ip'], (str, unicode)):
                kwargs['address'] = kwargs['ip']
                del kwargs['ip']
            if kwargs.has_key('ip_version'):
                kwargs['family'] = _check_ip_version(kwargs['ip_version'])
                del kwargs['ip_version']
        return [IpAddr(chunk, ipr) for chunk in ipr.get_addr(**kwargs)]
    
def is_addresses_exists(namespace=None, **kwargs):
    '''
        :kwargs condition   see function query_addresses()
        :return bool   any addressed matched
    '''
    return len(query_addresses(namespace, **kwargs)) > 0

def query_addresses_by_ifname(ifname, namespace=None):
    '''
        :return IpAddr[]
    '''
    return query_addresses(namespace, ifname=ifname)

def query_addresses_by_scope(scope, namespace=None):
    '''
        :param scope str or int, ex: 'host', 'global'
        :see _get_scope_name()
        :return IpAddr[]
    '''
    return query_addresses(namespace, scope=scope)

def query_addresses_by_ip(ip, ip_version=None, namespace=None):
    '''
        :return IpAddr[]
    '''
    return query_addresses(namespace, address=ip, ip_version=ip_version)

@_log_iproute_call("address add")
def add_address(ip, prefixlen, ip_version, ifname_or_index, broadcast=None, scope=None, namespace=None):
    '''
        bash: ip address add ${ip}/${prefixlen} dev ${ifname} ...
        :return None
    '''
    if ip is None or prefixlen is None:
        raise Exception('Ip and prefixlen can not be None')
    family = _check_ip_version(ip_version, False)
    with get_iproute(namespace) as ipr:
        index = _get_device_index(ifname_or_index, ipr)
        if scope:
            scope = _get_scope_name(scope, True)
        ipr.addr('add', index=index, address=ip, prefixlen=prefixlen,
                        broadcast=broadcast,
                        scope=scope,
                        family=family)

@_no_error_do
def add_address_no_error(*args, **kwargs):
    add_address(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

@_log_iproute_call("address delete")
def delete_address(ip, prefixlen, ip_version, ifname_or_index, namespace=None):
    '''
        bash: ip address delete ${ip}/${prefixlen} dev ${ifname} ...
        :return None
    '''
    if ip is None or prefixlen is None:
        raise Exception('Ip and prefixlen can not be None')
    family = _check_ip_version(ip_version)
    with get_iproute(namespace) as ipr:
        index = _get_device_index(ifname_or_index, ipr)
        ipr.addr('delete', index=index, address=ip, prefixlen=prefixlen, family=family)

@_no_error_do
def delete_address_no_error(*args, **kwargs):
    delete_address(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

@_log_iproute_call("address flush")
def flush_address(ifname_or_index, namespace=None):
    '''
        bash: ip address flush dev ${ifname}
        bash: ip netns exec ${namespace} ip address flush dev ${ifname}
        :return None
    '''
    with get_iproute(namespace) as ipr:
        index = _get_device_index(ifname_or_index, ipr)
        ipr.flush_addr(index=index)

@_no_error_do
def flush_address_no_error(*args, **kwargs):
    flush_address(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

# ========= link =========

def query_link(ifname_or_index, namespace=None):
    '''
        bash: ip link\n
        usage: 
            query_link(1) # query device whose index is 1
            query_link('eth0') # query device whose name is 'eth0'
        :return IpLink
        :raise Exception: If any device is not exist
    '''
    return query_links_use_namespace(namespace, ifname_or_index)[0]

def query_links(*argv):
    '''
        bash: ip link\n
        usage: 
            query_links(1) # query device whose index is 1
            query_links(1, 2, 3) # query device whose index is 1 or 2 or 3
            query_links('eth0') # query device whose name is 'eth0'
            query_links('eth0', 'lo')
            query_links('eth0', 6)
            query_links() # query all
        :return IpLink[]
        :raise Exception: If any device is not exist
    '''
    return query_links_use_namespace(None, *argv)

def query_links_use_namespace(namespace, *argv):
    indexes=set([])
    ifnames=set([])
    for item in argv:
        if isinstance(item, int) and item != 0:
            indexes.add(item)
        elif isinstance(item, (str, unicode)):
            ifnames.add(item)
        else:
            raise Exception('Argument %s in method query_links is invalid.' % item)
    with get_iproute(namespace) as ipr:
        if not indexes and not ifnames:
            return [IpLink(chunk) for chunk in ipr.get_links()]
        if ifnames:
            for ifname in ifnames:
                indexes.add(_check_index_and_ifname(ifname, None, ipr, True))
        try:
            return [IpLink(chunk) for chunk in ipr.get_links(*indexes)]
        except pyroute2.netlink.exceptions.NetlinkError:
            raise Exception('Query link device fall. arguments : %s, indexes : %s' % (argv, indexes))

@_log_iproute_call("link add")
def add_link(ifname, device_type, namespace=None, **kwargs):
    '''
        bash: ip link add ${ifname} type ${device_type} ...
        ex: add_link('my_device', 'gretap', remote='192.168.0.56', local='10.4.0.15', ttl=255, key=15)
        ex: add_link('my_device', 'veth', peer='v1p1')
        ex: add_link('my_device', 'veth', peer={'ifname': 'v1p1', 'net_ns_fd': 'test_netns'})
        ---
        bash: ip netns ${namespace} exec ip link add ${ifname} type ${device_type} ...
        ---
        :param device_type: str { vlan | veth | vcan | dummy | ifb | macvlan | macvtap |
                    bridge | bond | team | ipoib | ip6tnl | ipip | sit | vxlan |
                    gre | gretap | ip6gre | ip6gretap | vti | nlmon | team_slave |
                    bond_slave | ipvlan | geneve | bridge_slave | vrf | macsec }

    '''
    with get_iproute(namespace) as ipr:
        ipr.link("add", ifname=ifname, kind=device_type, **_warp_link_param(device_type, ipr, kwargs))

def _warp_link_param(device_type, ipr, kwargs):
    prefix = {
        'vlan': 'vlan_',
        'veth': 'veth_',
        'macvlan': 'macvlan_',
        'macvtap': 'macvtap_',
        'dummy': '',
        'bridge': '',
        'bond': '',
        'ipoib': '',
        'ip6tnl': 'ip6tnl_',
        'ipip': 'ipip_',
        'sit': 'sit_',
        'vxlan': 'vxlan_',
        'gre': 'gre_',
        'gretap': 'gre_',
        'ip6gre': 'ip6gre_',
        'ip6gretap': 'ip6gre_',
        'geneve': 'geneve_',
        'vrf': 'vrf_'
    }.get(device_type, device_type + '_')
    if prefix == 'gre_':
        return _warp_gre_link_param(kwargs)
    params = {}
    for item in kwargs:
        params["%s%s" % (prefix, item)] = kwargs[item]
    return params

def _warp_gre_link_param(kwargs):
    params = {}
    params["gre_local"] = kwargs.get('local')
    params["gre_remote"] = kwargs.get('remote')
    params["gre_ttl"] = kwargs.get('ttl')
    params["gre_ikey"] = kwargs.get('ikey', kwargs.get('key', 0))
    params["gre_okey"] = kwargs.get('okey', kwargs.get('key', 0))
    # flags default : 0x2000 - NOCACHE
    params["gre_iflags"] = kwargs.get('iflags', kwargs.get('flags', 0x2000))
    params["gre_oflags"] = kwargs.get('oflags', kwargs.get('flags', 0x2000))
    return params

@_no_error_do
def add_link_no_error(*args, **kwargs):
    add_link(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

@_log_iproute_call("link delete")
def delete_link(ifname_or_index, namespace=None):
    '''
        bash: ip link delete ${ifname} ...
        ex: delete_link('my_device')
            delete_link(2)
        :param ifname_or_index: both ifname and index are supported
    '''
    with get_iproute(namespace) as ipr:
        index = _get_device_index(ifname_or_index, ipr)
        ipr.link("del", index=index)

@_no_error_do
def delete_link_no_error(*args, **kwargs):
    delete_link(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

def set_link_up(ifname_or_index, namespace=None):
    set_link_attribute(ifname_or_index, namespace, state='up')

def set_link_down(ifname_or_index, namespace=None):
    set_link_attribute(ifname_or_index, namespace, state='down')

@_no_error_do
def set_link_up_no_error(*args, **kwargs):
    set_link_up(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

@_no_error_do
def set_link_down_no_error(*args, **kwargs):
    set_link_down(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

@_log_iproute_call("link set")
def set_link_attribute(ifname_or_index, namespace=None, **attributes):
    with get_iproute(namespace) as ipr:
        index = _get_device_index(ifname_or_index, ipr)
        if attributes:
            if attributes.has_key('master'):
                attributes['master'] = _get_device_index(attributes['master'], ipr)
            if attributes.has_key('netns'): # ip link set ${dev} netns ${namespace}
                attributes['net_ns_fd'] = attributes['netns']
                del attributes['netns']
            if attributes.has_key('alias'):
                attributes['IFLA_IFALIAS'] = attributes['alias']
                del attributes['alias']
        ipr.link('set', index=index, **attributes)

@_no_error_do
def set_link_attribute_no_error(*args, **kwargs):
    set_link_attribute(*args, **kwargs)
    return True # if raise Exception, @_no_error_do will return False

# ========= route =========

def _make_pyroute2_route_args(namespace, ip_version, ip, ifname, via, table,
                              metric, scope, protocol):
    '''
        Metheds from openstack/neutron
        Returns a dictionary of arguments to be used in pyroute route commands

        :param namespace: (string) name of the namespace
        :param ip_version: (int) [4, 6, or None]
        :param ip: (string) source IP or CIDR address (IPv4, IPv6)
        :param ifname: (string) input interface name
        :param via: (string) gateway IP address
        :param table: (string, int) table number or name
        :param metric: (int) route metric
        :param scope: (int) route scope
        :param protocol: (string) protocol name (pyroute2.netlink.rtnl.rt_proto)
        :return: a dictionary with the kwargs needed in pyroute rule commands
    '''
    args = {'family': _check_ip_version(ip_version)}
    if not scope:
        scope = 'global' if via else 'link'
    scope = _get_scope_name(scope)
    if scope:
        args['scope'] = scope
    if ip:
        args['dst'] = ip
    if ifname:
        args['oif'] = query_index_by_ifname(ifname, namespace)
    if via:
        args['gateway'] = via
    if table:
        args['table'] = int(table)
    if metric:
        args['priority'] = int(metric)
    if protocol:
        args['proto'] = protocol
    return args

def get_routes_by_ip(dst_ip, ip_version=None, namespace=None):
    '''
        :return IpRoute[]
    '''
    return get_routes(ip_version=ip_version, namespace=namespace, dst=dst_ip)

def get_routes(ifname=None, ip_version=None, table=None, namespace=None, **kwargs):
    '''
        List IP routes
        :return IpRoute[]
    '''
    kwargs.update(_make_pyroute2_route_args(
        namespace, ip_version, None, ifname, None, table, None, None, None))
    with get_iproute(namespace) as ipr:
        return map(lambda chunk: IpRoute(chunk), ipr.route('get', **kwargs))

def show_routes(ifname=None, ip_version=4, table=None, namespace=None, **kwargs):
    '''
        List IP routes
        :return IpRoute[]
    '''
    kwargs.update(_make_pyroute2_route_args(
        namespace, ip_version, None, ifname, None, table, None, None, None))
    with get_iproute(namespace) as ipr:
        return map(lambda chunk: IpRoute(chunk), ipr.route('show', **kwargs))

def add_route(ip, ip_version, ifname=None, via=None,
                 table=None, metric=None, scope=None, namespace=None, **kwargs):
    '''
        Add an IP route
    '''
    kwargs.update(_make_pyroute2_route_args(
        namespace, ip_version, ip, ifname, via, table, metric, scope,
        'static'))
    with get_iproute(namespace) as ipr:
        ipr.route('replace', **kwargs)

def delete_route(ip, ip_version, ifname=None, via=None,
                    table=None, scope=None, namespace=None, **kwargs):
    '''
        Delete an IP route
    '''
    kwargs.update(_make_pyroute2_route_args(
        namespace, ip_version, ip, ifname, via, table, None, scope, None))
    with get_iproute(namespace) as ipr:
        ipr.route('delete', **kwargs)

# ========= netns =========

NETNS_RUN_DIR = '/var/run/netns'

def list_namespace_pids(namespace):
    '''
        Metheds from openstack/neutron
        List namespace process PIDs

        :return int[]
    '''
    ns_pids = []
    try:
        ns_path = os.path.join(NETNS_RUN_DIR, namespace)
        ns_inode = os.stat(ns_path).st_ino
    except OSError:
        return ns_pids
    
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            pid_path = os.path.join('/proc', pid, 'ns', 'net')
            if os.stat(pid_path).st_ino == ns_inode:
                ns_pids.append(int(pid))
        except OSError:
            continue
    
    return ns_pids

@_log_iproute_call("netns add")
def add_namespace(namespace):
    '''
        Metheds from openstack/neutron
        Create a network namespace.
        bash: ip netns add ${namespace}

        :param namespace: The name of the namespace to create
    '''
    try:
        pyroute2.netns.create(namespace)
    except OSError as e:
        if e.errno == os.errno.EEXIST: # namespace already exists
            raise NamespaceAlreadyExists(namespace)
        raise

@_no_error_do
def add_namespace_no_error(namespace):
    add_namespace(namespace)
    return True # if raise Exception, @_no_error_do will return False

@_log_iproute_call("netns delete")
def delete_namespace(namespace):
    '''
        Metheds from openstack/neutron
        Remove a network namespace. if namespace no exist will throw OSError.
        bash: ip netns del ${namespace}

        :param namespace: The name of the namespace to remove
    '''
    try:
        pyroute2.netns.remove(namespace)
    except OSError as e:
        if e.errno == os.errno.ENOENT: # no namespace found
            raise NoSuchNamespace(namespace)
        raise

def delete_namespace_if_exists(namespace):
    '''
        Metheds from openstack/neutron
        Remove a network namespace if specific namespace is exists.

        :param namespace: The name of the namespace to remove
    '''
    if is_namespace_exists(namespace):
        try:
            delete_namespace(namespace)
            return True
        except NoSuchNamespace as e: # no namespace found, maybe someone has deleted it already.
            return False
    return False

@_no_error_do
def delete_namespace_no_error(namespace):
    delete_namespace(namespace)
    return True # if raise Exception, @_no_error_do will return False

def query_all_namespaces():
    '''
        List all network namespaces.

        Caller requires raised priveleges to list namespaces
        :return list(str)
    '''
    return pyroute2.netns.listnetns()

def is_namespace_exists(namespace):
    for name in query_all_namespaces():
        if name == namespace:
            return True
    return False
