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

# from zstacklib.utils.xms_client.models.osd_group_nestview import OsdGroupNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.osd_qos import OsdQos  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.placement_node_nestview import PlacementNodeNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.protection_domain_nestview import ProtectionDomainNestview  # noqa: F401,E501


class Pool(object):
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
        'action_status': 'str',
        'block_volume_num': 'int',
        'coding_chunk_num': 'int',
        'create': 'datetime',
        'data_chunk_num': 'int',
        'default_managed_volume_format': 'int',
        'device_type': 'str',
        'device_type_check_disabled': 'bool',
        'failure_domain_type': 'str',
        'hidden': 'bool',
        'id': 'int',
        'io_bypass_enabled': 'bool',
        'io_bypass_threshold': 'int',
        'name': 'str',
        'osd_group': 'OsdGroupNestview',
        'osd_num': 'int',
        'pool_id': 'int',
        'pool_mode': 'str',
        'pool_name': 'str',
        'pool_role': 'str',
        'pool_type': 'str',
        'primary_placement_node': 'PlacementNodeNestview',
        '_property': 'object',
        'protection_domain': 'ProtectionDomainNestview',
        'qos': 'OsdQos',
        'replicate_size': 'int',
        'status': 'str',
        'stretched': 'bool',
        'update': 'datetime'
    }

    attribute_map = {
        'action_status': 'action_status',
        'block_volume_num': 'block_volume_num',
        'coding_chunk_num': 'coding_chunk_num',
        'create': 'create',
        'data_chunk_num': 'data_chunk_num',
        'default_managed_volume_format': 'default_managed_volume_format',
        'device_type': 'device_type',
        'device_type_check_disabled': 'device_type_check_disabled',
        'failure_domain_type': 'failure_domain_type',
        'hidden': 'hidden',
        'id': 'id',
        'io_bypass_enabled': 'io_bypass_enabled',
        'io_bypass_threshold': 'io_bypass_threshold',
        'name': 'name',
        'osd_group': 'osd_group',
        'osd_num': 'osd_num',
        'pool_id': 'pool_id',
        'pool_mode': 'pool_mode',
        'pool_name': 'pool_name',
        'pool_role': 'pool_role',
        'pool_type': 'pool_type',
        'primary_placement_node': 'primary_placement_node',
        '_property': 'property',
        'protection_domain': 'protection_domain',
        'qos': 'qos',
        'replicate_size': 'replicate_size',
        'status': 'status',
        'stretched': 'stretched',
        'update': 'update'
    }

    def __init__(self, action_status=None, block_volume_num=None, coding_chunk_num=None, create=None, data_chunk_num=None, default_managed_volume_format=None, device_type=None, device_type_check_disabled=None, failure_domain_type=None, hidden=None, id=None, io_bypass_enabled=None, io_bypass_threshold=None, name=None, osd_group=None, osd_num=None, pool_id=None, pool_mode=None, pool_name=None, pool_role=None, pool_type=None, primary_placement_node=None, _property=None, protection_domain=None, qos=None, replicate_size=None, status=None, stretched=None, update=None):  # noqa: E501
        """Pool - a model defined in Swagger"""  # noqa: E501

        self._action_status = None
        self._block_volume_num = None
        self._coding_chunk_num = None
        self._create = None
        self._data_chunk_num = None
        self._default_managed_volume_format = None
        self._device_type = None
        self._device_type_check_disabled = None
        self._failure_domain_type = None
        self._hidden = None
        self._id = None
        self._io_bypass_enabled = None
        self._io_bypass_threshold = None
        self._name = None
        self._osd_group = None
        self._osd_num = None
        self._pool_id = None
        self._pool_mode = None
        self._pool_name = None
        self._pool_role = None
        self._pool_type = None
        self._primary_placement_node = None
        self.__property = None
        self._protection_domain = None
        self._qos = None
        self._replicate_size = None
        self._status = None
        self._stretched = None
        self._update = None
        self.discriminator = None

        if action_status is not None:
            self.action_status = action_status
        if block_volume_num is not None:
            self.block_volume_num = block_volume_num
        if coding_chunk_num is not None:
            self.coding_chunk_num = coding_chunk_num
        if create is not None:
            self.create = create
        if data_chunk_num is not None:
            self.data_chunk_num = data_chunk_num
        if default_managed_volume_format is not None:
            self.default_managed_volume_format = default_managed_volume_format
        if device_type is not None:
            self.device_type = device_type
        if device_type_check_disabled is not None:
            self.device_type_check_disabled = device_type_check_disabled
        if failure_domain_type is not None:
            self.failure_domain_type = failure_domain_type
        if hidden is not None:
            self.hidden = hidden
        if id is not None:
            self.id = id
        if io_bypass_enabled is not None:
            self.io_bypass_enabled = io_bypass_enabled
        if io_bypass_threshold is not None:
            self.io_bypass_threshold = io_bypass_threshold
        if name is not None:
            self.name = name
        if osd_group is not None:
            self.osd_group = osd_group
        if osd_num is not None:
            self.osd_num = osd_num
        if pool_id is not None:
            self.pool_id = pool_id
        if pool_mode is not None:
            self.pool_mode = pool_mode
        if pool_name is not None:
            self.pool_name = pool_name
        if pool_role is not None:
            self.pool_role = pool_role
        if pool_type is not None:
            self.pool_type = pool_type
        if primary_placement_node is not None:
            self.primary_placement_node = primary_placement_node
        if _property is not None:
            self._property = _property
        if protection_domain is not None:
            self.protection_domain = protection_domain
        if qos is not None:
            self.qos = qos
        if replicate_size is not None:
            self.replicate_size = replicate_size
        if status is not None:
            self.status = status
        if stretched is not None:
            self.stretched = stretched
        if update is not None:
            self.update = update

    @property
    def action_status(self):
        """Gets the action_status of this Pool.  # noqa: E501


        :return: The action_status of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._action_status

    @action_status.setter
    def action_status(self, action_status):
        """Sets the action_status of this Pool.


        :param action_status: The action_status of this Pool.  # noqa: E501
        :type: str
        """

        self._action_status = action_status

    @property
    def block_volume_num(self):
        """Gets the block_volume_num of this Pool.  # noqa: E501


        :return: The block_volume_num of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._block_volume_num

    @block_volume_num.setter
    def block_volume_num(self, block_volume_num):
        """Sets the block_volume_num of this Pool.


        :param block_volume_num: The block_volume_num of this Pool.  # noqa: E501
        :type: int
        """

        self._block_volume_num = block_volume_num

    @property
    def coding_chunk_num(self):
        """Gets the coding_chunk_num of this Pool.  # noqa: E501


        :return: The coding_chunk_num of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._coding_chunk_num

    @coding_chunk_num.setter
    def coding_chunk_num(self, coding_chunk_num):
        """Sets the coding_chunk_num of this Pool.


        :param coding_chunk_num: The coding_chunk_num of this Pool.  # noqa: E501
        :type: int
        """

        self._coding_chunk_num = coding_chunk_num

    @property
    def create(self):
        """Gets the create of this Pool.  # noqa: E501


        :return: The create of this Pool.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this Pool.


        :param create: The create of this Pool.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def data_chunk_num(self):
        """Gets the data_chunk_num of this Pool.  # noqa: E501


        :return: The data_chunk_num of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._data_chunk_num

    @data_chunk_num.setter
    def data_chunk_num(self, data_chunk_num):
        """Sets the data_chunk_num of this Pool.


        :param data_chunk_num: The data_chunk_num of this Pool.  # noqa: E501
        :type: int
        """

        self._data_chunk_num = data_chunk_num

    @property
    def default_managed_volume_format(self):
        """Gets the default_managed_volume_format of this Pool.  # noqa: E501


        :return: The default_managed_volume_format of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._default_managed_volume_format

    @default_managed_volume_format.setter
    def default_managed_volume_format(self, default_managed_volume_format):
        """Sets the default_managed_volume_format of this Pool.


        :param default_managed_volume_format: The default_managed_volume_format of this Pool.  # noqa: E501
        :type: int
        """

        self._default_managed_volume_format = default_managed_volume_format

    @property
    def device_type(self):
        """Gets the device_type of this Pool.  # noqa: E501


        :return: The device_type of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._device_type

    @device_type.setter
    def device_type(self, device_type):
        """Sets the device_type of this Pool.


        :param device_type: The device_type of this Pool.  # noqa: E501
        :type: str
        """

        self._device_type = device_type

    @property
    def device_type_check_disabled(self):
        """Gets the device_type_check_disabled of this Pool.  # noqa: E501


        :return: The device_type_check_disabled of this Pool.  # noqa: E501
        :rtype: bool
        """
        return self._device_type_check_disabled

    @device_type_check_disabled.setter
    def device_type_check_disabled(self, device_type_check_disabled):
        """Sets the device_type_check_disabled of this Pool.


        :param device_type_check_disabled: The device_type_check_disabled of this Pool.  # noqa: E501
        :type: bool
        """

        self._device_type_check_disabled = device_type_check_disabled

    @property
    def failure_domain_type(self):
        """Gets the failure_domain_type of this Pool.  # noqa: E501


        :return: The failure_domain_type of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._failure_domain_type

    @failure_domain_type.setter
    def failure_domain_type(self, failure_domain_type):
        """Sets the failure_domain_type of this Pool.


        :param failure_domain_type: The failure_domain_type of this Pool.  # noqa: E501
        :type: str
        """

        self._failure_domain_type = failure_domain_type

    @property
    def hidden(self):
        """Gets the hidden of this Pool.  # noqa: E501


        :return: The hidden of this Pool.  # noqa: E501
        :rtype: bool
        """
        return self._hidden

    @hidden.setter
    def hidden(self, hidden):
        """Sets the hidden of this Pool.


        :param hidden: The hidden of this Pool.  # noqa: E501
        :type: bool
        """

        self._hidden = hidden

    @property
    def id(self):
        """Gets the id of this Pool.  # noqa: E501


        :return: The id of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this Pool.


        :param id: The id of this Pool.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def io_bypass_enabled(self):
        """Gets the io_bypass_enabled of this Pool.  # noqa: E501


        :return: The io_bypass_enabled of this Pool.  # noqa: E501
        :rtype: bool
        """
        return self._io_bypass_enabled

    @io_bypass_enabled.setter
    def io_bypass_enabled(self, io_bypass_enabled):
        """Sets the io_bypass_enabled of this Pool.


        :param io_bypass_enabled: The io_bypass_enabled of this Pool.  # noqa: E501
        :type: bool
        """

        self._io_bypass_enabled = io_bypass_enabled

    @property
    def io_bypass_threshold(self):
        """Gets the io_bypass_threshold of this Pool.  # noqa: E501


        :return: The io_bypass_threshold of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._io_bypass_threshold

    @io_bypass_threshold.setter
    def io_bypass_threshold(self, io_bypass_threshold):
        """Sets the io_bypass_threshold of this Pool.


        :param io_bypass_threshold: The io_bypass_threshold of this Pool.  # noqa: E501
        :type: int
        """

        self._io_bypass_threshold = io_bypass_threshold

    @property
    def name(self):
        """Gets the name of this Pool.  # noqa: E501


        :return: The name of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this Pool.


        :param name: The name of this Pool.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def osd_group(self):
        """Gets the osd_group of this Pool.  # noqa: E501


        :return: The osd_group of this Pool.  # noqa: E501
        :rtype: OsdGroupNestview
        """
        return self._osd_group

    @osd_group.setter
    def osd_group(self, osd_group):
        """Sets the osd_group of this Pool.


        :param osd_group: The osd_group of this Pool.  # noqa: E501
        :type: OsdGroupNestview
        """

        self._osd_group = osd_group

    @property
    def osd_num(self):
        """Gets the osd_num of this Pool.  # noqa: E501


        :return: The osd_num of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._osd_num

    @osd_num.setter
    def osd_num(self, osd_num):
        """Sets the osd_num of this Pool.


        :param osd_num: The osd_num of this Pool.  # noqa: E501
        :type: int
        """

        self._osd_num = osd_num

    @property
    def pool_id(self):
        """Gets the pool_id of this Pool.  # noqa: E501


        :return: The pool_id of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._pool_id

    @pool_id.setter
    def pool_id(self, pool_id):
        """Sets the pool_id of this Pool.


        :param pool_id: The pool_id of this Pool.  # noqa: E501
        :type: int
        """

        self._pool_id = pool_id

    @property
    def pool_mode(self):
        """Gets the pool_mode of this Pool.  # noqa: E501


        :return: The pool_mode of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._pool_mode

    @pool_mode.setter
    def pool_mode(self, pool_mode):
        """Sets the pool_mode of this Pool.


        :param pool_mode: The pool_mode of this Pool.  # noqa: E501
        :type: str
        """

        self._pool_mode = pool_mode

    @property
    def pool_name(self):
        """Gets the pool_name of this Pool.  # noqa: E501


        :return: The pool_name of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._pool_name

    @pool_name.setter
    def pool_name(self, pool_name):
        """Sets the pool_name of this Pool.


        :param pool_name: The pool_name of this Pool.  # noqa: E501
        :type: str
        """

        self._pool_name = pool_name

    @property
    def pool_role(self):
        """Gets the pool_role of this Pool.  # noqa: E501


        :return: The pool_role of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._pool_role

    @pool_role.setter
    def pool_role(self, pool_role):
        """Sets the pool_role of this Pool.


        :param pool_role: The pool_role of this Pool.  # noqa: E501
        :type: str
        """

        self._pool_role = pool_role

    @property
    def pool_type(self):
        """Gets the pool_type of this Pool.  # noqa: E501


        :return: The pool_type of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._pool_type

    @pool_type.setter
    def pool_type(self, pool_type):
        """Sets the pool_type of this Pool.


        :param pool_type: The pool_type of this Pool.  # noqa: E501
        :type: str
        """

        self._pool_type = pool_type

    @property
    def primary_placement_node(self):
        """Gets the primary_placement_node of this Pool.  # noqa: E501

        placement node with the primary replica  # noqa: E501

        :return: The primary_placement_node of this Pool.  # noqa: E501
        :rtype: PlacementNodeNestview
        """
        return self._primary_placement_node

    @primary_placement_node.setter
    def primary_placement_node(self, primary_placement_node):
        """Sets the primary_placement_node of this Pool.

        placement node with the primary replica  # noqa: E501

        :param primary_placement_node: The primary_placement_node of this Pool.  # noqa: E501
        :type: PlacementNodeNestview
        """

        self._primary_placement_node = primary_placement_node

    @property
    def _property(self):
        """Gets the _property of this Pool.  # noqa: E501


        :return: The _property of this Pool.  # noqa: E501
        :rtype: object
        """
        return self.__property

    @_property.setter
    def _property(self, _property):
        """Sets the _property of this Pool.


        :param _property: The _property of this Pool.  # noqa: E501
        :type: object
        """

        self.__property = _property

    @property
    def protection_domain(self):
        """Gets the protection_domain of this Pool.  # noqa: E501


        :return: The protection_domain of this Pool.  # noqa: E501
        :rtype: ProtectionDomainNestview
        """
        return self._protection_domain

    @protection_domain.setter
    def protection_domain(self, protection_domain):
        """Sets the protection_domain of this Pool.


        :param protection_domain: The protection_domain of this Pool.  # noqa: E501
        :type: ProtectionDomainNestview
        """

        self._protection_domain = protection_domain

    @property
    def qos(self):
        """Gets the qos of this Pool.  # noqa: E501


        :return: The qos of this Pool.  # noqa: E501
        :rtype: OsdQos
        """
        return self._qos

    @qos.setter
    def qos(self, qos):
        """Sets the qos of this Pool.


        :param qos: The qos of this Pool.  # noqa: E501
        :type: OsdQos
        """

        self._qos = qos

    @property
    def replicate_size(self):
        """Gets the replicate_size of this Pool.  # noqa: E501


        :return: The replicate_size of this Pool.  # noqa: E501
        :rtype: int
        """
        return self._replicate_size

    @replicate_size.setter
    def replicate_size(self, replicate_size):
        """Sets the replicate_size of this Pool.


        :param replicate_size: The replicate_size of this Pool.  # noqa: E501
        :type: int
        """

        self._replicate_size = replicate_size

    @property
    def status(self):
        """Gets the status of this Pool.  # noqa: E501


        :return: The status of this Pool.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this Pool.


        :param status: The status of this Pool.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def stretched(self):
        """Gets the stretched of this Pool.  # noqa: E501


        :return: The stretched of this Pool.  # noqa: E501
        :rtype: bool
        """
        return self._stretched

    @stretched.setter
    def stretched(self, stretched):
        """Sets the stretched of this Pool.


        :param stretched: The stretched of this Pool.  # noqa: E501
        :type: bool
        """

        self._stretched = stretched

    @property
    def update(self):
        """Gets the update of this Pool.  # noqa: E501


        :return: The update of this Pool.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this Pool.


        :param update: The update of this Pool.  # noqa: E501
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
        if not isinstance(other, Pool):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
