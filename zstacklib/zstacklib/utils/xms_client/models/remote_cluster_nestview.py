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


class RemoteClusterNestview(object):
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
        'fs_id': 'str',
        'id': 'int',
        'name': 'str',
        'url': 'str'
    }

    attribute_map = {
        'fs_id': 'fs_id',
        'id': 'id',
        'name': 'name',
        'url': 'url'
    }

    def __init__(self, fs_id=None, id=None, name=None, url=None):  # noqa: E501
        """RemoteClusterNestview - a model defined in Swagger"""  # noqa: E501

        self._fs_id = None
        self._id = None
        self._name = None
        self._url = None
        self.discriminator = None

        if fs_id is not None:
            self.fs_id = fs_id
        if id is not None:
            self.id = id
        if name is not None:
            self.name = name
        if url is not None:
            self.url = url

    @property
    def fs_id(self):
        """Gets the fs_id of this RemoteClusterNestview.  # noqa: E501


        :return: The fs_id of this RemoteClusterNestview.  # noqa: E501
        :rtype: str
        """
        return self._fs_id

    @fs_id.setter
    def fs_id(self, fs_id):
        """Sets the fs_id of this RemoteClusterNestview.


        :param fs_id: The fs_id of this RemoteClusterNestview.  # noqa: E501
        :type: str
        """

        self._fs_id = fs_id

    @property
    def id(self):
        """Gets the id of this RemoteClusterNestview.  # noqa: E501


        :return: The id of this RemoteClusterNestview.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this RemoteClusterNestview.


        :param id: The id of this RemoteClusterNestview.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def name(self):
        """Gets the name of this RemoteClusterNestview.  # noqa: E501


        :return: The name of this RemoteClusterNestview.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this RemoteClusterNestview.


        :param name: The name of this RemoteClusterNestview.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def url(self):
        """Gets the url of this RemoteClusterNestview.  # noqa: E501


        :return: The url of this RemoteClusterNestview.  # noqa: E501
        :rtype: str
        """
        return self._url

    @url.setter
    def url(self, url):
        """Sets the url of this RemoteClusterNestview.


        :param url: The url of this RemoteClusterNestview.  # noqa: E501
        :type: str
        """

        self._url = url

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
        if not isinstance(other, RemoteClusterNestview):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
