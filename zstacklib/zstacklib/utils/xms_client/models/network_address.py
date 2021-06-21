# coding: utf-8

"""
    XMS API

    XMS is the controller of distributed storage system  # noqa: E501

    OpenAPI spec version: SDS_4.2.300.2
    
    Generated by: https://github.com/swagger-api/swagger-codegen.git
"""


import pprint
import re  # noqa: F401
import six

# from zstacklib.utils.xms_client.models.host_nestview import HostNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.network_interface_nestview import NetworkInterfaceNestview  # noqa: F401,E501


class NetworkAddress(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    """

    """
    Attributes:
      swagger_types (dict): The key is attribute name
                            and the value is attribute type.
      attribute_map (dict): The key is attribute name
                            and the value is json key in definition.
    """
    swagger_types = {
        'available': 'bool',
        'create': 'datetime',
        'host': 'HostNestview',
        'id': 'int',
        'ip': 'str',
        'mask': 'int',
        'network_interface': 'NetworkInterfaceNestview',
        'roles': 'list[str]',
        'slave_switch_time': 'datetime',
        'slave_switched': 'bool',
        'update': 'datetime'
    }

    attribute_map = {
        'available': 'available',
        'create': 'create',
        'host': 'host',
        'id': 'id',
        'ip': 'ip',
        'mask': 'mask',
        'network_interface': 'network_interface',
        'roles': 'roles',
        'slave_switch_time': 'slave_switch_time',
        'slave_switched': 'slave_switched',
        'update': 'update'
    }

    def __init__(self, available=None, create=None, host=None, id=None, ip=None, mask=None, network_interface=None, roles=None, slave_switch_time=None, slave_switched=None, update=None):  # noqa: E501
        """NetworkAddress - a model defined in Swagger"""  # noqa: E501

        self._available = None
        self._create = None
        self._host = None
        self._id = None
        self._ip = None
        self._mask = None
        self._network_interface = None
        self._roles = None
        self._slave_switch_time = None
        self._slave_switched = None
        self._update = None
        self.discriminator = None

        if available is not None:
            self.available = available
        if create is not None:
            self.create = create
        if host is not None:
            self.host = host
        if id is not None:
            self.id = id
        if ip is not None:
            self.ip = ip
        if mask is not None:
            self.mask = mask
        if network_interface is not None:
            self.network_interface = network_interface
        if roles is not None:
            self.roles = roles
        if slave_switch_time is not None:
            self.slave_switch_time = slave_switch_time
        if slave_switched is not None:
            self.slave_switched = slave_switched
        if update is not None:
            self.update = update

    @property
    def available(self):
        """Gets the available of this NetworkAddress.  # noqa: E501


        :return: The available of this NetworkAddress.  # noqa: E501
        :rtype: bool
        """
        return self._available

    @available.setter
    def available(self, available):
        """Sets the available of this NetworkAddress.


        :param available: The available of this NetworkAddress.  # noqa: E501
        :type: bool
        """

        self._available = available

    @property
    def create(self):
        """Gets the create of this NetworkAddress.  # noqa: E501


        :return: The create of this NetworkAddress.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this NetworkAddress.


        :param create: The create of this NetworkAddress.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def host(self):
        """Gets the host of this NetworkAddress.  # noqa: E501


        :return: The host of this NetworkAddress.  # noqa: E501
        :rtype: HostNestview
        """
        return self._host

    @host.setter
    def host(self, host):
        """Sets the host of this NetworkAddress.


        :param host: The host of this NetworkAddress.  # noqa: E501
        :type: HostNestview
        """

        self._host = host

    @property
    def id(self):
        """Gets the id of this NetworkAddress.  # noqa: E501


        :return: The id of this NetworkAddress.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this NetworkAddress.


        :param id: The id of this NetworkAddress.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def ip(self):
        """Gets the ip of this NetworkAddress.  # noqa: E501


        :return: The ip of this NetworkAddress.  # noqa: E501
        :rtype: str
        """
        return self._ip

    @ip.setter
    def ip(self, ip):
        """Sets the ip of this NetworkAddress.


        :param ip: The ip of this NetworkAddress.  # noqa: E501
        :type: str
        """

        self._ip = ip

    @property
    def mask(self):
        """Gets the mask of this NetworkAddress.  # noqa: E501


        :return: The mask of this NetworkAddress.  # noqa: E501
        :rtype: int
        """
        return self._mask

    @mask.setter
    def mask(self, mask):
        """Sets the mask of this NetworkAddress.


        :param mask: The mask of this NetworkAddress.  # noqa: E501
        :type: int
        """

        self._mask = mask

    @property
    def network_interface(self):
        """Gets the network_interface of this NetworkAddress.  # noqa: E501


        :return: The network_interface of this NetworkAddress.  # noqa: E501
        :rtype: NetworkInterfaceNestview
        """
        return self._network_interface

    @network_interface.setter
    def network_interface(self, network_interface):
        """Sets the network_interface of this NetworkAddress.


        :param network_interface: The network_interface of this NetworkAddress.  # noqa: E501
        :type: NetworkInterfaceNestview
        """

        self._network_interface = network_interface

    @property
    def roles(self):
        """Gets the roles of this NetworkAddress.  # noqa: E501


        :return: The roles of this NetworkAddress.  # noqa: E501
        :rtype: list[str]
        """
        return self._roles

    @roles.setter
    def roles(self, roles):
        """Sets the roles of this NetworkAddress.


        :param roles: The roles of this NetworkAddress.  # noqa: E501
        :type: list[str]
        """

        self._roles = roles

    @property
    def slave_switch_time(self):
        """Gets the slave_switch_time of this NetworkAddress.  # noqa: E501


        :return: The slave_switch_time of this NetworkAddress.  # noqa: E501
        :rtype: datetime
        """
        return self._slave_switch_time

    @slave_switch_time.setter
    def slave_switch_time(self, slave_switch_time):
        """Sets the slave_switch_time of this NetworkAddress.


        :param slave_switch_time: The slave_switch_time of this NetworkAddress.  # noqa: E501
        :type: datetime
        """

        self._slave_switch_time = slave_switch_time

    @property
    def slave_switched(self):
        """Gets the slave_switched of this NetworkAddress.  # noqa: E501


        :return: The slave_switched of this NetworkAddress.  # noqa: E501
        :rtype: bool
        """
        return self._slave_switched

    @slave_switched.setter
    def slave_switched(self, slave_switched):
        """Sets the slave_switched of this NetworkAddress.


        :param slave_switched: The slave_switched of this NetworkAddress.  # noqa: E501
        :type: bool
        """

        self._slave_switched = slave_switched

    @property
    def update(self):
        """Gets the update of this NetworkAddress.  # noqa: E501


        :return: The update of this NetworkAddress.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this NetworkAddress.


        :param update: The update of this NetworkAddress.  # noqa: E501
        :type: datetime
        """

        self._update = update

    def to_dict(self):
        """Returns the model properties as a dict"""
        result = {}

        for attr, _ in six.iteritems(self.swagger_types):
            value = getattr(self, attr)
            if isinstance(value, list):
                result[attr] = list(map(
                    lambda x: x.to_dict() if hasattr(x, "to_dict") else x,
                    value
                ))
            elif hasattr(value, "to_dict"):
                result[attr] = value.to_dict()
            elif isinstance(value, dict):
                result[attr] = dict(map(
                    lambda item: (item[0], item[1].to_dict())
                    if hasattr(item[1], "to_dict") else item,
                    value.items()
                ))
            else:
                result[attr] = value

        return result

    def to_str(self):
        """Returns the string representation of the model"""
        return pprint.pformat(self.to_dict())

    def __repr__(self):
        """For `print` and `pprint`"""
        return self.to_str()

    def __eq__(self, other):
        """Returns true if both objects are equal"""
        if not isinstance(other, NetworkAddress):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
