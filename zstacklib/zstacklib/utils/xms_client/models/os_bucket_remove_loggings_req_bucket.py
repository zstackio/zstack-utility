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


class OSBucketRemoveLoggingsReqBucket(object):
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
        'os_bucket_logging_ids': 'list[int]'
    }

    attribute_map = {
        'os_bucket_logging_ids': 'os_bucket_logging_ids'
    }

    def __init__(self, os_bucket_logging_ids=None):  # noqa: E501
        """OSBucketRemoveLoggingsReqBucket - a model defined in Swagger"""  # noqa: E501

        self._os_bucket_logging_ids = None
        self.discriminator = None

        self.os_bucket_logging_ids = os_bucket_logging_ids

    @property
    def os_bucket_logging_ids(self):
        """Gets the os_bucket_logging_ids of this OSBucketRemoveLoggingsReqBucket.  # noqa: E501


        :return: The os_bucket_logging_ids of this OSBucketRemoveLoggingsReqBucket.  # noqa: E501
        :rtype: list[int]
        """
        return self._os_bucket_logging_ids

    @os_bucket_logging_ids.setter
    def os_bucket_logging_ids(self, os_bucket_logging_ids):
        """Sets the os_bucket_logging_ids of this OSBucketRemoveLoggingsReqBucket.


        :param os_bucket_logging_ids: The os_bucket_logging_ids of this OSBucketRemoveLoggingsReqBucket.  # noqa: E501
        :type: list[int]
        """
        if os_bucket_logging_ids is None:
            raise ValueError("Invalid value for `os_bucket_logging_ids`, must not be `None`")  # noqa: E501

        self._os_bucket_logging_ids = os_bucket_logging_ids

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
        if not isinstance(other, OSBucketRemoveLoggingsReqBucket):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
