# Copyright (c) ZStack.io, Inc.

"""
Network link (interface) operations.

Provides functions for querying, creating, deleting, and modifying
network link devices (interfaces).
"""

from typing import Any, Dict, List, Optional, Set, Union

from .decorators import log_iproute_call, no_error_do
from .exceptions import NoSuchLinkDevice
from .models import IpLink
from .utils import (
    check_index_and_ifname,
    get_device_index,
    get_iproute,
    query_index_by_ifname,
)


def query_link(ifname_or_index, namespace=None):
    # type: (Union[str, int], Optional[str]) -> IpLink
    """
    Query a single network link device.
    
    Equivalent to: ip link show {ifname}
    
    Args:
        ifname_or_index: Interface name or index
        namespace: Network namespace (None for default)
    
    Returns:
        IpLink object for the device
    
    Raises:
        Exception: If the device does not exist
    
    Example:
        >>> link = query_link('eth0')
        >>> print(link.mac, link.state)
    """
    results = query_links_use_namespace(namespace, ifname_or_index)
    if not results:
        raise Exception("device %s not found" % ifname_or_index)
    return results[0]


def query_links(*argv):
    # type: (*Union[str, int]) -> List[IpLink]
    """
    Query multiple network link devices.
    
    Equivalent to: ip link
    
    Args:
        *argv: Interface names or indexes. If empty, returns all devices.
    
    Returns:
        List of IpLink objects
    
    Raises:
        Exception: If any specified device does not exist
    
    Example:
        >>> links = query_links()  # All devices
        >>> links = query_links('eth0', 'lo')  # Specific devices
        >>> links = query_links(1, 2, 3)  # By index
    """
    return query_links_use_namespace(None, *argv)


def query_links_use_namespace(namespace, *argv):
    # type: (Optional[str], *Union[str, int]) -> List[IpLink]
    """
    Query network link devices in a specific namespace.
    
    Args:
        namespace: Network namespace (None for default)
        *argv: Interface names or indexes
    
    Returns:
        List of IpLink objects
    
    Raises:
        Exception: If any specified device does not exist or arguments are invalid
    """
    indexes = set()  # type: Set[int]
    ifnames = set()  # type: Set[str]
    
    for item in argv:
        if isinstance(item, int) and item != 0:
            indexes.add(item)
        elif isinstance(item, str):
            ifnames.add(item)
        else:
            raise Exception('Argument %s in method query_links is invalid.' % item)
    
    with get_iproute(namespace) as ipr:
        if not indexes and not ifnames:
            return [IpLink(chunk) for chunk in ipr.get_links()]
        
        if ifnames:
            for ifname in ifnames:
                indexes.add(check_index_and_ifname(ifname, None, ipr, True))
        
        try:
            return [IpLink(chunk) for chunk in ipr.get_links(*indexes)]
        except Exception:
            import pyroute2.netlink.exceptions
            raise Exception('Query link device failed. arguments: %s, indexes: %s' % (argv, indexes))


@log_iproute_call("link add")
def add_link(ifname, device_type, namespace=None, **kwargs):
    # type: (str, str, Optional[str], **Any) -> None
    """
    Create a new network link device.
    
    Equivalent to: ip link add {ifname} type {device_type} [options]
    
    Args:
        ifname: Name for the new device
        device_type: Device type (vlan, veth, vcan, dummy, ifb, macvlan, macvtap,
                     bridge, bond, team, ipoib, ip6tnl, ipip, sit, vxlan,
                     gre, gretap, ip6gre, ip6gretap, vti, nlmon, team_slave,
                     bond_slave, ipvlan, geneve, bridge_slave, vrf, macsec)
        namespace: Network namespace (None for default)
        **kwargs: Device-specific options
    
    Example:
        >>> add_link('my_veth', 'veth', peer='veth_peer')
        >>> add_link('my_gre', 'gretap', remote='192.168.0.56', local='10.4.0.15', ttl=255, key=15)
        >>> add_link('my_vlan', 'vlan', link=3, id=100)
    """
    with get_iproute(namespace) as ipr:
        ipr.link("add", ifname=ifname, kind=device_type,
                 **_wrap_link_param(device_type, ipr, kwargs))


def _wrap_link_param(device_type, ipr, kwargs):
    # type: (str, Any, Dict[str, Any]) -> Dict[str, Any]
    """Wrap link parameters with device-type-specific prefixes."""
    prefix_map = {
        'vlan': 'vlan_',
        'veth': '',
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
    }
    
    prefix = prefix_map.get(device_type, device_type + '_')
    
    if prefix == 'gre_':
        return _wrap_gre_link_param(kwargs)
    
    params = {}  # type: Dict[str, Any]
    for item in kwargs:
        params["%s%s" % (prefix, item)] = kwargs[item]
    return params


def _wrap_gre_link_param(kwargs):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """Wrap GRE tunnel parameters."""
    params = {}  # type: Dict[str, Any]
    params["gre_local"] = kwargs.get('local')
    params["gre_remote"] = kwargs.get('remote')
    params["gre_ttl"] = kwargs.get('ttl')
    params["gre_ikey"] = kwargs.get('ikey', kwargs.get('key', 0))
    params["gre_okey"] = kwargs.get('okey', kwargs.get('key', 0))
    # flags default: 0x2000 - NOCACHE
    params["gre_iflags"] = kwargs.get('iflags', kwargs.get('flags', 0x2000))
    params["gre_oflags"] = kwargs.get('oflags', kwargs.get('flags', 0x2000))
    if 'pmtudisc' in kwargs and kwargs['pmtudisc'] is not None:
        params["gre_pmtudisc"] = 1 if kwargs['pmtudisc'] else 0
    if 'ignore_df' in kwargs and kwargs['ignore_df'] is not None:
        params["gre_ignore_df"] = 1 if kwargs['ignore_df'] else 0
    if kwargs.get('mtu') is not None:
        params["mtu"] = int(kwargs['mtu'])
    return params


@no_error_do
def add_link_no_error(*args, **kwargs):
    # type: (*Any, **Any) -> bool
    """
    Create a link device, returning False on error instead of raising.
    
    See add_link for arguments.
    
    Returns:
        True on success, False on error
    """
    add_link(*args, **kwargs)
    return True


@log_iproute_call("link delete")
def delete_link(ifname_or_index, namespace=None):
    # type: (Union[str, int], Optional[str]) -> None
    """
    Delete a network link device.
    
    Equivalent to: ip link delete {ifname}
    
    Args:
        ifname_or_index: Interface name or index
        namespace: Network namespace (None for default)
    
    Raises:
        NoSuchLinkDevice: If the device does not exist
    """
    with get_iproute(namespace) as ipr:
        index = get_device_index(ifname_or_index, ipr)
        ipr.link("del", index=index)


@no_error_do
def delete_link_no_error(*args, **kwargs):
    # type: (*Any, **Any) -> bool
    """
    Delete a link device, returning False on error instead of raising.
    
    See delete_link for arguments.
    
    Returns:
        True on success, False on error
    """
    delete_link(*args, **kwargs)
    return True


def set_link_up(ifname_or_index, namespace=None):
    # type: (Union[str, int], Optional[str]) -> None
    """
    Bring a network link device up.
    
    Equivalent to: ip link set {ifname} up
    
    Args:
        ifname_or_index: Interface name or index
        namespace: Network namespace (None for default)
    """
    set_link_attribute(ifname_or_index, namespace, state='up')


def set_link_down(ifname_or_index, namespace=None):
    # type: (Union[str, int], Optional[str]) -> None
    """
    Bring a network link device down.
    
    Equivalent to: ip link set {ifname} down
    
    Args:
        ifname_or_index: Interface name or index
        namespace: Network namespace (None for default)
    """
    set_link_attribute(ifname_or_index, namespace, state='down')


@no_error_do
def set_link_up_no_error(*args, **kwargs):
    # type: (*Any, **Any) -> bool
    """Set link up, returning False on error."""
    set_link_up(*args, **kwargs)
    return True


@no_error_do
def set_link_down_no_error(*args, **kwargs):
    # type: (*Any, **Any) -> bool
    """Set link down, returning False on error."""
    set_link_down(*args, **kwargs)
    return True


@log_iproute_call("link set")
def set_link_attribute(ifname_or_index, namespace=None, **attributes):
    # type: (Union[str, int], Optional[str], **Any) -> None
    """
    Set attributes on a network link device.
    
    Equivalent to: ip link set {ifname} [attribute value ...]
    
    Args:
        ifname_or_index: Interface name or index
        namespace: Network namespace (None for default)
        **attributes: Attributes to set:
            - state: 'up' or 'down'
            - mtu: Maximum transmission unit
            - master: Master device (name or index)
            - netns: Move to network namespace
            - alias: Interface alias
            - address: MAC address
    
    Example:
        >>> set_link_attribute('eth0', state='up', mtu=9000)
        >>> set_link_attribute('veth0', netns='my_namespace')
    """
    with get_iproute(namespace) as ipr:
        index = get_device_index(ifname_or_index, ipr)
        if attributes:
            if 'master' in attributes:
                attributes['master'] = get_device_index(attributes['master'], ipr)
            if 'netns' in attributes:
                attributes['net_ns_fd'] = attributes['netns']
                del attributes['netns']
            if 'alias' in attributes:
                attributes['IFLA_IFALIAS'] = attributes['alias']
                del attributes['alias']
        ipr.link('set', index=index, **attributes)


@no_error_do
def set_link_attribute_no_error(*args, **kwargs):
    # type: (*Any, **Any) -> bool
    """
    Set link attributes, returning False on error instead of raising.
    
    See set_link_attribute for arguments.
    
    Returns:
        True on success, False on error
    """
    set_link_attribute(*args, **kwargs)
    return True
