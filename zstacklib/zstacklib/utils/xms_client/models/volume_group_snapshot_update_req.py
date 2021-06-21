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

# from zstacklib.utils.xms_client.models.volume_group_snapshot_update_req_volume_group_snapshot import VolumeGroupSnapshotUpdateReqVolumeGroupSnapshot  # noqa: F401,E501


class VolumeGroupSnapshotUpdateReq(object):
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
        'block_volume_group_snapshot': 'VolumeGroupSnapshotUpdateReqVolumeGroupSnapshot'
    }

    attribute_map = {
        'block_volume_group_snapshot': 'block_volume_group_snapshot'
    }

    def __init__(self, block_volume_group_snapshot=None):  # noqa: E501
        """VolumeGroupSnapshotUpdateReq - a model defined in Swagger"""  # noqa: E501

        self._block_volume_group_snapshot = None
        self.discriminator = None

        self.block_volume_group_snapshot = block_volume_group_snapshot

    @property
    def block_volume_group_snapshot(self):
        """Gets the block_volume_group_snapshot of this VolumeGroupSnapshotUpdateReq.  # noqa: E501


        :return: The block_volume_group_snapshot of this VolumeGroupSnapshotUpdateReq.  # noqa: E501
        :rtype: VolumeGroupSnapshotUpdateReqVolumeGroupSnapshot
        """
        return self._block_volume_group_snapshot

    @block_volume_group_snapshot.setter
    def block_volume_group_snapshot(self, block_volume_group_snapshot):
        """Sets the block_volume_group_snapshot of this VolumeGroupSnapshotUpdateReq.


        :param block_volume_group_snapshot: The block_volume_group_snapshot of this VolumeGroupSnapshotUpdateReq.  # noqa: E501
        :type: VolumeGroupSnapshotUpdateReqVolumeGroupSnapshot
        """
        if block_volume_group_snapshot is None:
            raise ValueError("Invalid value for `block_volume_group_snapshot`, must not be `None`")  # noqa: E501

        self._block_volume_group_snapshot = block_volume_group_snapshot

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
        if not isinstance(other, VolumeGroupSnapshotUpdateReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
