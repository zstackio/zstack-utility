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

# from zstacklib.utils.xms_client.models.volume_qos_spec import VolumeQosSpec  # noqa: F401,E501


class FSFolderCreateReqFolder(object):
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
        'description': 'str',
        'flattened': 'bool',
        'fs_snapshot_id': 'int',
        'name': 'str',
        'pool_id': 'int',
        'qos': 'VolumeQosSpec',
        'qos_enabled': 'bool',
        'size': 'int'
    }

    attribute_map = {
        'description': 'description',
        'flattened': 'flattened',
        'fs_snapshot_id': 'fs_snapshot_id',
        'name': 'name',
        'pool_id': 'pool_id',
        'qos': 'qos',
        'qos_enabled': 'qos_enabled',
        'size': 'size'
    }

    def __init__(self, description=None, flattened=None, fs_snapshot_id=None, name=None, pool_id=None, qos=None, qos_enabled=None, size=None):  # noqa: E501
        """FSFolderCreateReqFolder - a model defined in Swagger"""  # noqa: E501

        self._description = None
        self._flattened = None
        self._fs_snapshot_id = None
        self._name = None
        self._pool_id = None
        self._qos = None
        self._qos_enabled = None
        self._size = None
        self.discriminator = None

        if description is not None:
            self.description = description
        if flattened is not None:
            self.flattened = flattened
        if fs_snapshot_id is not None:
            self.fs_snapshot_id = fs_snapshot_id
        self.name = name
        if pool_id is not None:
            self.pool_id = pool_id
        if qos is not None:
            self.qos = qos
        if qos_enabled is not None:
            self.qos_enabled = qos_enabled
        if size is not None:
            self.size = size

    @property
    def description(self):
        """Gets the description of this FSFolderCreateReqFolder.  # noqa: E501

        description of folder  # noqa: E501

        :return: The description of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this FSFolderCreateReqFolder.

        description of folder  # noqa: E501

        :param description: The description of this FSFolderCreateReqFolder.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def flattened(self):
        """Gets the flattened of this FSFolderCreateReqFolder.  # noqa: E501

        flatten or not flatten  # noqa: E501

        :return: The flattened of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: bool
        """
        return self._flattened

    @flattened.setter
    def flattened(self, flattened):
        """Sets the flattened of this FSFolderCreateReqFolder.

        flatten or not flatten  # noqa: E501

        :param flattened: The flattened of this FSFolderCreateReqFolder.  # noqa: E501
        :type: bool
        """

        self._flattened = flattened

    @property
    def fs_snapshot_id(self):
        """Gets the fs_snapshot_id of this FSFolderCreateReqFolder.  # noqa: E501

        file storage snapshot id  # noqa: E501

        :return: The fs_snapshot_id of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: int
        """
        return self._fs_snapshot_id

    @fs_snapshot_id.setter
    def fs_snapshot_id(self, fs_snapshot_id):
        """Sets the fs_snapshot_id of this FSFolderCreateReqFolder.

        file storage snapshot id  # noqa: E501

        :param fs_snapshot_id: The fs_snapshot_id of this FSFolderCreateReqFolder.  # noqa: E501
        :type: int
        """

        self._fs_snapshot_id = fs_snapshot_id

    @property
    def name(self):
        """Gets the name of this FSFolderCreateReqFolder.  # noqa: E501

        name of folder  # noqa: E501

        :return: The name of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this FSFolderCreateReqFolder.

        name of folder  # noqa: E501

        :param name: The name of this FSFolderCreateReqFolder.  # noqa: E501
        :type: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def pool_id(self):
        """Gets the pool_id of this FSFolderCreateReqFolder.  # noqa: E501

        id of pool  # noqa: E501

        :return: The pool_id of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: int
        """
        return self._pool_id

    @pool_id.setter
    def pool_id(self, pool_id):
        """Sets the pool_id of this FSFolderCreateReqFolder.

        id of pool  # noqa: E501

        :param pool_id: The pool_id of this FSFolderCreateReqFolder.  # noqa: E501
        :type: int
        """

        self._pool_id = pool_id

    @property
    def qos(self):
        """Gets the qos of this FSFolderCreateReqFolder.  # noqa: E501

        qos of volume  # noqa: E501

        :return: The qos of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: VolumeQosSpec
        """
        return self._qos

    @qos.setter
    def qos(self, qos):
        """Sets the qos of this FSFolderCreateReqFolder.

        qos of volume  # noqa: E501

        :param qos: The qos of this FSFolderCreateReqFolder.  # noqa: E501
        :type: VolumeQosSpec
        """

        self._qos = qos

    @property
    def qos_enabled(self):
        """Gets the qos_enabled of this FSFolderCreateReqFolder.  # noqa: E501

        enable or disable the qos  # noqa: E501

        :return: The qos_enabled of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: bool
        """
        return self._qos_enabled

    @qos_enabled.setter
    def qos_enabled(self, qos_enabled):
        """Sets the qos_enabled of this FSFolderCreateReqFolder.

        enable or disable the qos  # noqa: E501

        :param qos_enabled: The qos_enabled of this FSFolderCreateReqFolder.  # noqa: E501
        :type: bool
        """

        self._qos_enabled = qos_enabled

    @property
    def size(self):
        """Gets the size of this FSFolderCreateReqFolder.  # noqa: E501

        size of folder  # noqa: E501

        :return: The size of this FSFolderCreateReqFolder.  # noqa: E501
        :rtype: int
        """
        return self._size

    @size.setter
    def size(self, size):
        """Sets the size of this FSFolderCreateReqFolder.

        size of folder  # noqa: E501

        :param size: The size of this FSFolderCreateReqFolder.  # noqa: E501
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
        if not isinstance(other, FSFolderCreateReqFolder):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
