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


class VolumeCrcSetReqVolume(object):
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
        'crc_check': 'bool'
    }

    attribute_map = {
        'crc_check': 'crc_check'
    }

    def __init__(self, crc_check=None):  # noqa: E501
        """VolumeCrcSetReqVolume - a model defined in Swagger"""  # noqa: E501

        self._crc_check = None
        self.discriminator = None

        self.crc_check = crc_check

    @property
    def crc_check(self):
        """Gets the crc_check of this VolumeCrcSetReqVolume.  # noqa: E501


        :return: The crc_check of this VolumeCrcSetReqVolume.  # noqa: E501
        :rtype: bool
        """
        return self._crc_check

    @crc_check.setter
    def crc_check(self, crc_check):
        """Sets the crc_check of this VolumeCrcSetReqVolume.


        :param crc_check: The crc_check of this VolumeCrcSetReqVolume.  # noqa: E501
        :type: bool
        """
        if crc_check is None:
            raise ValueError("Invalid value for `crc_check`, must not be `None`")  # noqa: E501

        self._crc_check = crc_check

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
        if not isinstance(other, VolumeCrcSetReqVolume):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other