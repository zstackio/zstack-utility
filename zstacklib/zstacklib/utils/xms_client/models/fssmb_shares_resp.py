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

# from zstacklib.utils.xms_client.models.fssmb_share import FSSMBShare  # noqa: F401,E501


class FSSMBSharesResp(object):
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
        'fs_smb_shares': 'list[FSSMBShare]'
    }

    attribute_map = {
        'fs_smb_shares': 'fs_smb_shares'
    }

    def __init__(self, fs_smb_shares=None):  # noqa: E501
        """FSSMBSharesResp - a model defined in Swagger"""  # noqa: E501

        self._fs_smb_shares = None
        self.discriminator = None

        self.fs_smb_shares = fs_smb_shares

    @property
    def fs_smb_shares(self):
        """Gets the fs_smb_shares of this FSSMBSharesResp.  # noqa: E501

        fs smb shares  # noqa: E501

        :return: The fs_smb_shares of this FSSMBSharesResp.  # noqa: E501
        :rtype: list[FSSMBShare]
        """
        return self._fs_smb_shares

    @fs_smb_shares.setter
    def fs_smb_shares(self, fs_smb_shares):
        """Sets the fs_smb_shares of this FSSMBSharesResp.

        fs smb shares  # noqa: E501

        :param fs_smb_shares: The fs_smb_shares of this FSSMBSharesResp.  # noqa: E501
        :type: list[FSSMBShare]
        """
        if fs_smb_shares is None:
            raise ValueError("Invalid value for `fs_smb_shares`, must not be `None`")  # noqa: E501

        self._fs_smb_shares = fs_smb_shares

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
        if not isinstance(other, FSSMBSharesResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
