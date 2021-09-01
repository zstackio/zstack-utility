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

# from zstacklib.utils.xms_client.models.osd_qos import OsdQos  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.pool_rule_req import PoolRuleReq  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.raw_message import RawMessage  # noqa: F401,E501


class PoolUpdateReqPool(object):
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
        'default_managed_volume_format': 'int',
        'failure_domain_type': 'str',
        'io_bypass_enabled': 'bool',
        'io_bypass_threshold': 'int',
        'name': 'str',
        'primary_placement_node_id': 'int',
        '_property': 'dict(str, RawMessage)',
        'qos': 'OsdQos',
        'ruleset': 'list[PoolRuleReq]',
        'size': 'int'
    }

    attribute_map = {
        'default_managed_volume_format': 'default_managed_volume_format',
        'failure_domain_type': 'failure_domain_type',
        'io_bypass_enabled': 'io_bypass_enabled',
        'io_bypass_threshold': 'io_bypass_threshold',
        'name': 'name',
        'primary_placement_node_id': 'primary_placement_node_id',
        '_property': 'property',
        'qos': 'qos',
        'ruleset': 'ruleset',
        'size': 'size'
    }

    def __init__(self, default_managed_volume_format=None, failure_domain_type=None, io_bypass_enabled=None, io_bypass_threshold=None, name=None, primary_placement_node_id=None, _property=None, qos=None, ruleset=None, size=None):  # noqa: E501
        """PoolUpdateReqPool - a model defined in Swagger"""  # noqa: E501

        self._default_managed_volume_format = None
        self._failure_domain_type = None
        self._io_bypass_enabled = None
        self._io_bypass_threshold = None
        self._name = None
        self._primary_placement_node_id = None
        self.__property = None
        self._qos = None
        self._ruleset = None
        self._size = None
        self.discriminator = None

        if default_managed_volume_format is not None:
            self.default_managed_volume_format = default_managed_volume_format
        if failure_domain_type is not None:
            self.failure_domain_type = failure_domain_type
        if io_bypass_enabled is not None:
            self.io_bypass_enabled = io_bypass_enabled
        if io_bypass_threshold is not None:
            self.io_bypass_threshold = io_bypass_threshold
        if name is not None:
            self.name = name
        if primary_placement_node_id is not None:
            self.primary_placement_node_id = primary_placement_node_id
        if _property is not None:
            self._property = _property
        if qos is not None:
            self.qos = qos
        if ruleset is not None:
            self.ruleset = ruleset
        if size is not None:
            self.size = size

    @property
    def default_managed_volume_format(self):
        """Gets the default_managed_volume_format of this PoolUpdateReqPool.  # noqa: E501

        default managed volume format: 128 or 129  # noqa: E501

        :return: The default_managed_volume_format of this PoolUpdateReqPool.  # noqa: E501
        :rtype: int
        """
        return self._default_managed_volume_format

    @default_managed_volume_format.setter
    def default_managed_volume_format(self, default_managed_volume_format):
        """Sets the default_managed_volume_format of this PoolUpdateReqPool.

        default managed volume format: 128 or 129  # noqa: E501

        :param default_managed_volume_format: The default_managed_volume_format of this PoolUpdateReqPool.  # noqa: E501
        :type: int
        """

        self._default_managed_volume_format = default_managed_volume_format

    @property
    def failure_domain_type(self):
        """Gets the failure_domain_type of this PoolUpdateReqPool.  # noqa: E501


        :return: The failure_domain_type of this PoolUpdateReqPool.  # noqa: E501
        :rtype: str
        """
        return self._failure_domain_type

    @failure_domain_type.setter
    def failure_domain_type(self, failure_domain_type):
        """Sets the failure_domain_type of this PoolUpdateReqPool.


        :param failure_domain_type: The failure_domain_type of this PoolUpdateReqPool.  # noqa: E501
        :type: str
        """

        self._failure_domain_type = failure_domain_type

    @property
    def io_bypass_enabled(self):
        """Gets the io_bypass_enabled of this PoolUpdateReqPool.  # noqa: E501


        :return: The io_bypass_enabled of this PoolUpdateReqPool.  # noqa: E501
        :rtype: bool
        """
        return self._io_bypass_enabled

    @io_bypass_enabled.setter
    def io_bypass_enabled(self, io_bypass_enabled):
        """Sets the io_bypass_enabled of this PoolUpdateReqPool.


        :param io_bypass_enabled: The io_bypass_enabled of this PoolUpdateReqPool.  # noqa: E501
        :type: bool
        """

        self._io_bypass_enabled = io_bypass_enabled

    @property
    def io_bypass_threshold(self):
        """Gets the io_bypass_threshold of this PoolUpdateReqPool.  # noqa: E501


        :return: The io_bypass_threshold of this PoolUpdateReqPool.  # noqa: E501
        :rtype: int
        """
        return self._io_bypass_threshold

    @io_bypass_threshold.setter
    def io_bypass_threshold(self, io_bypass_threshold):
        """Sets the io_bypass_threshold of this PoolUpdateReqPool.


        :param io_bypass_threshold: The io_bypass_threshold of this PoolUpdateReqPool.  # noqa: E501
        :type: int
        """

        self._io_bypass_threshold = io_bypass_threshold

    @property
    def name(self):
        """Gets the name of this PoolUpdateReqPool.  # noqa: E501


        :return: The name of this PoolUpdateReqPool.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this PoolUpdateReqPool.


        :param name: The name of this PoolUpdateReqPool.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def primary_placement_node_id(self):
        """Gets the primary_placement_node_id of this PoolUpdateReqPool.  # noqa: E501


        :return: The primary_placement_node_id of this PoolUpdateReqPool.  # noqa: E501
        :rtype: int
        """
        return self._primary_placement_node_id

    @primary_placement_node_id.setter
    def primary_placement_node_id(self, primary_placement_node_id):
        """Sets the primary_placement_node_id of this PoolUpdateReqPool.


        :param primary_placement_node_id: The primary_placement_node_id of this PoolUpdateReqPool.  # noqa: E501
        :type: int
        """

        self._primary_placement_node_id = primary_placement_node_id

    @property
    def _property(self):
        """Gets the _property of this PoolUpdateReqPool.  # noqa: E501


        :return: The _property of this PoolUpdateReqPool.  # noqa: E501
        :rtype: dict(str, RawMessage)
        """
        return self.__property

    @_property.setter
    def _property(self, _property):
        """Sets the _property of this PoolUpdateReqPool.


        :param _property: The _property of this PoolUpdateReqPool.  # noqa: E501
        :type: dict(str, RawMessage)
        """

        self.__property = _property

    @property
    def qos(self):
        """Gets the qos of this PoolUpdateReqPool.  # noqa: E501


        :return: The qos of this PoolUpdateReqPool.  # noqa: E501
        :rtype: OsdQos
        """
        return self._qos

    @qos.setter
    def qos(self, qos):
        """Sets the qos of this PoolUpdateReqPool.


        :param qos: The qos of this PoolUpdateReqPool.  # noqa: E501
        :type: OsdQos
        """

        self._qos = qos

    @property
    def ruleset(self):
        """Gets the ruleset of this PoolUpdateReqPool.  # noqa: E501


        :return: The ruleset of this PoolUpdateReqPool.  # noqa: E501
        :rtype: list[PoolRuleReq]
        """
        return self._ruleset

    @ruleset.setter
    def ruleset(self, ruleset):
        """Sets the ruleset of this PoolUpdateReqPool.


        :param ruleset: The ruleset of this PoolUpdateReqPool.  # noqa: E501
        :type: list[PoolRuleReq]
        """

        self._ruleset = ruleset

    @property
    def size(self):
        """Gets the size of this PoolUpdateReqPool.  # noqa: E501


        :return: The size of this PoolUpdateReqPool.  # noqa: E501
        :rtype: int
        """
        return self._size

    @size.setter
    def size(self, size):
        """Sets the size of this PoolUpdateReqPool.


        :param size: The size of this PoolUpdateReqPool.  # noqa: E501
        :type: int
        """

        self._size = size

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
        if not isinstance(other, PoolUpdateReqPool):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other