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

# from zstacklib.utils.xms_client.models.cloud_platform import CloudPlatform  # noqa: F401,E501


class CloudPlatformResp(object):
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
        'cloud_platform': 'CloudPlatform'
    }

    attribute_map = {
        'cloud_platform': 'cloud_platform'
    }

    def __init__(self, cloud_platform=None):  # noqa: E501
        """CloudPlatformResp - a model defined in Swagger"""  # noqa: E501

        self._cloud_platform = None
        self.discriminator = None

        if cloud_platform is not None:
            self.cloud_platform = cloud_platform

    @property
    def cloud_platform(self):
        """Gets the cloud_platform of this CloudPlatformResp.  # noqa: E501

        cloud platform  # noqa: E501

        :return: The cloud_platform of this CloudPlatformResp.  # noqa: E501
        :rtype: CloudPlatform
        """
        return self._cloud_platform

    @cloud_platform.setter
    def cloud_platform(self, cloud_platform):
        """Sets the cloud_platform of this CloudPlatformResp.

        cloud platform  # noqa: E501

        :param cloud_platform: The cloud_platform of this CloudPlatformResp.  # noqa: E501
        :type: CloudPlatform
        """

        self._cloud_platform = cloud_platform

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
        if not isinstance(other, CloudPlatformResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
