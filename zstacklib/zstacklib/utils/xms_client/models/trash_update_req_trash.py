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


class TrashUpdateReqTrash(object):
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
        'enabled': 'bool',
        'retention': 'str'
    }

    attribute_map = {
        'enabled': 'enabled',
        'retention': 'retention'
    }

    def __init__(self, enabled=None, retention=None):  # noqa: E501
        """TrashUpdateReqTrash - a model defined in Swagger"""  # noqa: E501

        self._enabled = None
        self._retention = None
        self.discriminator = None

        if enabled is not None:
            self.enabled = enabled
        if retention is not None:
            self.retention = retention

    @property
    def enabled(self):
        """Gets the enabled of this TrashUpdateReqTrash.  # noqa: E501


        :return: The enabled of this TrashUpdateReqTrash.  # noqa: E501
        :rtype: bool
        """
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        """Sets the enabled of this TrashUpdateReqTrash.


        :param enabled: The enabled of this TrashUpdateReqTrash.  # noqa: E501
        :type: bool
        """

        self._enabled = enabled

    @property
    def retention(self):
        """Gets the retention of this TrashUpdateReqTrash.  # noqa: E501


        :return: The retention of this TrashUpdateReqTrash.  # noqa: E501
        :rtype: str
        """
        return self._retention

    @retention.setter
    def retention(self, retention):
        """Sets the retention of this TrashUpdateReqTrash.


        :param retention: The retention of this TrashUpdateReqTrash.  # noqa: E501
        :type: str
        """

        self._retention = retention

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
        if not isinstance(other, TrashUpdateReqTrash):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
