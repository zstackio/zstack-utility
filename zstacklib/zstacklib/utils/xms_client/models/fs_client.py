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

# from zstacklib.utils.xms_client.models.fs_client_group_nestview import FSClientGroupNestview  # noqa: F401,E501


class FSClient(object):
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
        'create': 'datetime',
        'fs_client_group_num': 'int',
        'fs_client_groups': 'list[FSClientGroupNestview]',
        'id': 'int',
        'ip': 'str',
        'name': 'str',
        'update': 'datetime'
    }

    attribute_map = {
        'create': 'create',
        'fs_client_group_num': 'fs_client_group_num',
        'fs_client_groups': 'fs_client_groups',
        'id': 'id',
        'ip': 'ip',
        'name': 'name',
        'update': 'update'
    }

    def __init__(self, create=None, fs_client_group_num=None, fs_client_groups=None, id=None, ip=None, name=None, update=None):  # noqa: E501
        """FSClient - a model defined in Swagger"""  # noqa: E501

        self._create = None
        self._fs_client_group_num = None
        self._fs_client_groups = None
        self._id = None
        self._ip = None
        self._name = None
        self._update = None
        self.discriminator = None

        if create is not None:
            self.create = create
        if fs_client_group_num is not None:
            self.fs_client_group_num = fs_client_group_num
        if fs_client_groups is not None:
            self.fs_client_groups = fs_client_groups
        if id is not None:
            self.id = id
        if ip is not None:
            self.ip = ip
        if name is not None:
            self.name = name
        if update is not None:
            self.update = update

    @property
    def create(self):
        """Gets the create of this FSClient.  # noqa: E501


        :return: The create of this FSClient.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this FSClient.


        :param create: The create of this FSClient.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def fs_client_group_num(self):
        """Gets the fs_client_group_num of this FSClient.  # noqa: E501


        :return: The fs_client_group_num of this FSClient.  # noqa: E501
        :rtype: int
        """
        return self._fs_client_group_num

    @fs_client_group_num.setter
    def fs_client_group_num(self, fs_client_group_num):
        """Sets the fs_client_group_num of this FSClient.


        :param fs_client_group_num: The fs_client_group_num of this FSClient.  # noqa: E501
        :type: int
        """

        self._fs_client_group_num = fs_client_group_num

    @property
    def fs_client_groups(self):
        """Gets the fs_client_groups of this FSClient.  # noqa: E501


        :return: The fs_client_groups of this FSClient.  # noqa: E501
        :rtype: list[FSClientGroupNestview]
        """
        return self._fs_client_groups

    @fs_client_groups.setter
    def fs_client_groups(self, fs_client_groups):
        """Sets the fs_client_groups of this FSClient.


        :param fs_client_groups: The fs_client_groups of this FSClient.  # noqa: E501
        :type: list[FSClientGroupNestview]
        """

        self._fs_client_groups = fs_client_groups

    @property
    def id(self):
        """Gets the id of this FSClient.  # noqa: E501


        :return: The id of this FSClient.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this FSClient.


        :param id: The id of this FSClient.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def ip(self):
        """Gets the ip of this FSClient.  # noqa: E501


        :return: The ip of this FSClient.  # noqa: E501
        :rtype: str
        """
        return self._ip

    @ip.setter
    def ip(self, ip):
        """Sets the ip of this FSClient.


        :param ip: The ip of this FSClient.  # noqa: E501
        :type: str
        """

        self._ip = ip

    @property
    def name(self):
        """Gets the name of this FSClient.  # noqa: E501


        :return: The name of this FSClient.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this FSClient.


        :param name: The name of this FSClient.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def update(self):
        """Gets the update of this FSClient.  # noqa: E501


        :return: The update of this FSClient.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this FSClient.


        :param update: The update of this FSClient.  # noqa: E501
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
        if not isinstance(other, FSClient):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
