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


class ProductService(object):
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
        'expired_time': 'datetime',
        'name': 'str',
        'start_time': 'datetime'
    }

    attribute_map = {
        'expired_time': 'expired_time',
        'name': 'name',
        'start_time': 'start_time'
    }

    def __init__(self, expired_time=None, name=None, start_time=None):  # noqa: E501
        """ProductService - a model defined in Swagger"""  # noqa: E501

        self._expired_time = None
        self._name = None
        self._start_time = None
        self.discriminator = None

        if expired_time is not None:
            self.expired_time = expired_time
        if name is not None:
            self.name = name
        if start_time is not None:
            self.start_time = start_time

    @property
    def expired_time(self):
        """Gets the expired_time of this ProductService.  # noqa: E501


        :return: The expired_time of this ProductService.  # noqa: E501
        :rtype: datetime
        """
        return self._expired_time

    @expired_time.setter
    def expired_time(self, expired_time):
        """Sets the expired_time of this ProductService.


        :param expired_time: The expired_time of this ProductService.  # noqa: E501
        :type: datetime
        """

        self._expired_time = expired_time

    @property
    def name(self):
        """Gets the name of this ProductService.  # noqa: E501


        :return: The name of this ProductService.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this ProductService.


        :param name: The name of this ProductService.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def start_time(self):
        """Gets the start_time of this ProductService.  # noqa: E501


        :return: The start_time of this ProductService.  # noqa: E501
        :rtype: datetime
        """
        return self._start_time

    @start_time.setter
    def start_time(self, start_time):
        """Sets the start_time of this ProductService.


        :param start_time: The start_time of this ProductService.  # noqa: E501
        :type: datetime
        """

        self._start_time = start_time

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
        if not isinstance(other, ProductService):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
