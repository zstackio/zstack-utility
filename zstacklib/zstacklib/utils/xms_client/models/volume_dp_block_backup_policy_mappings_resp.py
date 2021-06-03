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

# from zstacklib.utils.xms_client.models.volume_dp_block_backup_policy_mapping import VolumeDpBlockBackupPolicyMapping  # noqa: F401,E501


class VolumeDpBlockBackupPolicyMappingsResp(object):
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
        'volume_dp_block_backup_policy_mappings': 'list[VolumeDpBlockBackupPolicyMapping]'
    }

    attribute_map = {
        'volume_dp_block_backup_policy_mappings': 'volume_dp_block_backup_policy_mappings'
    }

    def __init__(self, volume_dp_block_backup_policy_mappings=None):  # noqa: E501
        """VolumeDpBlockBackupPolicyMappingsResp - a model defined in Swagger"""  # noqa: E501

        self._volume_dp_block_backup_policy_mappings = None
        self.discriminator = None

        if volume_dp_block_backup_policy_mappings is not None:
            self.volume_dp_block_backup_policy_mappings = volume_dp_block_backup_policy_mappings

    @property
    def volume_dp_block_backup_policy_mappings(self):
        """Gets the volume_dp_block_backup_policy_mappings of this VolumeDpBlockBackupPolicyMappingsResp.  # noqa: E501


        :return: The volume_dp_block_backup_policy_mappings of this VolumeDpBlockBackupPolicyMappingsResp.  # noqa: E501
        :rtype: list[VolumeDpBlockBackupPolicyMapping]
        """
        return self._volume_dp_block_backup_policy_mappings

    @volume_dp_block_backup_policy_mappings.setter
    def volume_dp_block_backup_policy_mappings(self, volume_dp_block_backup_policy_mappings):
        """Sets the volume_dp_block_backup_policy_mappings of this VolumeDpBlockBackupPolicyMappingsResp.


        :param volume_dp_block_backup_policy_mappings: The volume_dp_block_backup_policy_mappings of this VolumeDpBlockBackupPolicyMappingsResp.  # noqa: E501
        :type: list[VolumeDpBlockBackupPolicyMapping]
        """

        self._volume_dp_block_backup_policy_mappings = volume_dp_block_backup_policy_mappings

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
        if not isinstance(other, VolumeDpBlockBackupPolicyMappingsResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
