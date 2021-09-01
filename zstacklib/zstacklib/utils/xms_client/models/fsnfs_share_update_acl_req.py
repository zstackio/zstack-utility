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


class FSNFSShareUpdateACLReq(object):
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
        'all_squash': 'bool',
        'id': 'int',
        'permission': 'str',
        'root_squash': 'bool',
        'sync': 'bool'
    }

    attribute_map = {
        'all_squash': 'all_squash',
        'id': 'id',
        'permission': 'permission',
        'root_squash': 'root_squash',
        'sync': 'sync'
    }

    def __init__(self, all_squash=None, id=None, permission=None, root_squash=None, sync=None):  # noqa: E501
        """FSNFSShareUpdateACLReq - a model defined in Swagger"""  # noqa: E501

        self._all_squash = None
        self._id = None
        self._permission = None
        self._root_squash = None
        self._sync = None
        self.discriminator = None

        if all_squash is not None:
            self.all_squash = all_squash
        if id is not None:
            self.id = id
        if permission is not None:
            self.permission = permission
        if root_squash is not None:
            self.root_squash = root_squash
        if sync is not None:
            self.sync = sync

    @property
    def all_squash(self):
        """Gets the all_squash of this FSNFSShareUpdateACLReq.  # noqa: E501

        all squash  # noqa: E501

        :return: The all_squash of this FSNFSShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._all_squash

    @all_squash.setter
    def all_squash(self, all_squash):
        """Sets the all_squash of this FSNFSShareUpdateACLReq.

        all squash  # noqa: E501

        :param all_squash: The all_squash of this FSNFSShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._all_squash = all_squash

    @property
    def id(self):
        """Gets the id of this FSNFSShareUpdateACLReq.  # noqa: E501

        id of user group  # noqa: E501

        :return: The id of this FSNFSShareUpdateACLReq.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this FSNFSShareUpdateACLReq.

        id of user group  # noqa: E501

        :param id: The id of this FSNFSShareUpdateACLReq.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def permission(self):
        """Gets the permission of this FSNFSShareUpdateACLReq.  # noqa: E501

        readonly or readwrite access  # noqa: E501

        :return: The permission of this FSNFSShareUpdateACLReq.  # noqa: E501
        :rtype: str
        """
        return self._permission

    @permission.setter
    def permission(self, permission):
        """Sets the permission of this FSNFSShareUpdateACLReq.

        readonly or readwrite access  # noqa: E501

        :param permission: The permission of this FSNFSShareUpdateACLReq.  # noqa: E501
        :type: str
        """

        self._permission = permission

    @property
    def root_squash(self):
        """Gets the root_squash of this FSNFSShareUpdateACLReq.  # noqa: E501

        root squash  # noqa: E501

        :return: The root_squash of this FSNFSShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._root_squash

    @root_squash.setter
    def root_squash(self, root_squash):
        """Sets the root_squash of this FSNFSShareUpdateACLReq.

        root squash  # noqa: E501

        :param root_squash: The root_squash of this FSNFSShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._root_squash = root_squash

    @property
    def sync(self):
        """Gets the sync of this FSNFSShareUpdateACLReq.  # noqa: E501

        write to disk by sync or async  # noqa: E501

        :return: The sync of this FSNFSShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._sync

    @sync.setter
    def sync(self, sync):
        """Sets the sync of this FSNFSShareUpdateACLReq.

        write to disk by sync or async  # noqa: E501

        :param sync: The sync of this FSNFSShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._sync = sync

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
        if not isinstance(other, FSNFSShareUpdateACLReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other