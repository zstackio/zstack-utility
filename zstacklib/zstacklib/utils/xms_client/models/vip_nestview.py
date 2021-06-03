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


class VIPNestview(object):
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
        'id': 'int',
        'ip': 'str',
        'mask': 'int'
    }

    attribute_map = {
        'id': 'id',
        'ip': 'ip',
        'mask': 'mask'
    }

    def __init__(self, id=None, ip=None, mask=None):  # noqa: E501
        """VIPNestview - a model defined in Swagger"""  # noqa: E501

        self._id = None
        self._ip = None
        self._mask = None
        self.discriminator = None

        if id is not None:
            self.id = id
        if ip is not None:
            self.ip = ip
        if mask is not None:
            self.mask = mask

    @property
    def id(self):
        """Gets the id of this VIPNestview.  # noqa: E501


        :return: The id of this VIPNestview.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this VIPNestview.


        :param id: The id of this VIPNestview.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def ip(self):
        """Gets the ip of this VIPNestview.  # noqa: E501


        :return: The ip of this VIPNestview.  # noqa: E501
        :rtype: str
        """
        return self._ip

    @ip.setter
    def ip(self, ip):
        """Sets the ip of this VIPNestview.


        :param ip: The ip of this VIPNestview.  # noqa: E501
        :type: str
        """

        self._ip = ip

    @property
    def mask(self):
        """Gets the mask of this VIPNestview.  # noqa: E501


        :return: The mask of this VIPNestview.  # noqa: E501
        :rtype: int
        """
        return self._mask

    @mask.setter
    def mask(self, mask):
        """Sets the mask of this VIPNestview.


        :param mask: The mask of this VIPNestview.  # noqa: E501
        :type: int
        """

        self._mask = mask

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
        if not isinstance(other, VIPNestview):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
