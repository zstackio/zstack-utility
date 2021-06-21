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

# from zstacklib.utils.xms_client.models.fs_ldap import FSLdap  # noqa: F401,E501


class FSLdapsResp(object):
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
        'fs_ldaps': 'list[FSLdap]'
    }

    attribute_map = {
        'fs_ldaps': 'fs_ldaps'
    }

    def __init__(self, fs_ldaps=None):  # noqa: E501
        """FSLdapsResp - a model defined in Swagger"""  # noqa: E501

        self._fs_ldaps = None
        self.discriminator = None

        self.fs_ldaps = fs_ldaps

    @property
    def fs_ldaps(self):
        """Gets the fs_ldaps of this FSLdapsResp.  # noqa: E501

        file storage ldaps  # noqa: E501

        :return: The fs_ldaps of this FSLdapsResp.  # noqa: E501
        :rtype: list[FSLdap]
        """
        return self._fs_ldaps

    @fs_ldaps.setter
    def fs_ldaps(self, fs_ldaps):
        """Sets the fs_ldaps of this FSLdapsResp.

        file storage ldaps  # noqa: E501

        :param fs_ldaps: The fs_ldaps of this FSLdapsResp.  # noqa: E501
        :type: list[FSLdap]
        """
        if fs_ldaps is None:
            raise ValueError("Invalid value for `fs_ldaps`, must not be `None`")  # noqa: E501

        self._fs_ldaps = fs_ldaps

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
        if not isinstance(other, FSLdapsResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
