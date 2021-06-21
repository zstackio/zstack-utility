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

# from zstacklib.utils.xms_client.models.object_storage_bucket_nfs_client import ObjectStorageBucketNFSClient  # noqa: F401,E501


class ObjectStorageBucketNFSClientResp(object):
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
        'os_bucket_nfs_client': 'ObjectStorageBucketNFSClient'
    }

    attribute_map = {
        'os_bucket_nfs_client': 'os_bucket_nfs_client'
    }

    def __init__(self, os_bucket_nfs_client=None):  # noqa: E501
        """ObjectStorageBucketNFSClientResp - a model defined in Swagger"""  # noqa: E501

        self._os_bucket_nfs_client = None
        self.discriminator = None

        self.os_bucket_nfs_client = os_bucket_nfs_client

    @property
    def os_bucket_nfs_client(self):
        """Gets the os_bucket_nfs_client of this ObjectStorageBucketNFSClientResp.  # noqa: E501

        nfs client of object storage bucket  # noqa: E501

        :return: The os_bucket_nfs_client of this ObjectStorageBucketNFSClientResp.  # noqa: E501
        :rtype: ObjectStorageBucketNFSClient
        """
        return self._os_bucket_nfs_client

    @os_bucket_nfs_client.setter
    def os_bucket_nfs_client(self, os_bucket_nfs_client):
        """Sets the os_bucket_nfs_client of this ObjectStorageBucketNFSClientResp.

        nfs client of object storage bucket  # noqa: E501

        :param os_bucket_nfs_client: The os_bucket_nfs_client of this ObjectStorageBucketNFSClientResp.  # noqa: E501
        :type: ObjectStorageBucketNFSClient
        """
        if os_bucket_nfs_client is None:
            raise ValueError("Invalid value for `os_bucket_nfs_client`, must not be `None`")  # noqa: E501

        self._os_bucket_nfs_client = os_bucket_nfs_client

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
        if not isinstance(other, ObjectStorageBucketNFSClientResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
