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

# from zstacklib.utils.xms_client.models.dp_block_backup_policy_update_req_policy import DpBlockBackupPolicyUpdateReqPolicy  # noqa: F401,E501


class DpBlockBackupPolicyUpdateReq(object):
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
        'dp_block_backup_policy': 'DpBlockBackupPolicyUpdateReqPolicy'
    }

    attribute_map = {
        'dp_block_backup_policy': 'dp_block_backup_policy'
    }

    def __init__(self, dp_block_backup_policy=None):  # noqa: E501
        """DpBlockBackupPolicyUpdateReq - a model defined in Swagger"""  # noqa: E501

        self._dp_block_backup_policy = None
        self.discriminator = None

        self.dp_block_backup_policy = dp_block_backup_policy

    @property
    def dp_block_backup_policy(self):
        """Gets the dp_block_backup_policy of this DpBlockBackupPolicyUpdateReq.  # noqa: E501


        :return: The dp_block_backup_policy of this DpBlockBackupPolicyUpdateReq.  # noqa: E501
        :rtype: DpBlockBackupPolicyUpdateReqPolicy
        """
        return self._dp_block_backup_policy

    @dp_block_backup_policy.setter
    def dp_block_backup_policy(self, dp_block_backup_policy):
        """Sets the dp_block_backup_policy of this DpBlockBackupPolicyUpdateReq.


        :param dp_block_backup_policy: The dp_block_backup_policy of this DpBlockBackupPolicyUpdateReq.  # noqa: E501
        :type: DpBlockBackupPolicyUpdateReqPolicy
        """
        if dp_block_backup_policy is None:
            raise ValueError("Invalid value for `dp_block_backup_policy`, must not be `None`")  # noqa: E501

        self._dp_block_backup_policy = dp_block_backup_policy

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
        if not isinstance(other, DpBlockBackupPolicyUpdateReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
