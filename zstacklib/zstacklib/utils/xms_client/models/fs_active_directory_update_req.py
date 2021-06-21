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

# from zstacklib.utils.xms_client.models.fs_active_directory_update_req_info import FSActiveDirectoryUpdateReqInfo  # noqa: F401,E501


class FSActiveDirectoryUpdateReq(object):
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
        'fs_active_directory': 'FSActiveDirectoryUpdateReqInfo'
    }

    attribute_map = {
        'fs_active_directory': 'fs_active_directory'
    }

    def __init__(self, fs_active_directory=None):  # noqa: E501
        """FSActiveDirectoryUpdateReq - a model defined in Swagger"""  # noqa: E501

        self._fs_active_directory = None
        self.discriminator = None

        self.fs_active_directory = fs_active_directory

    @property
    def fs_active_directory(self):
        """Gets the fs_active_directory of this FSActiveDirectoryUpdateReq.  # noqa: E501


        :return: The fs_active_directory of this FSActiveDirectoryUpdateReq.  # noqa: E501
        :rtype: FSActiveDirectoryUpdateReqInfo
        """
        return self._fs_active_directory

    @fs_active_directory.setter
    def fs_active_directory(self, fs_active_directory):
        """Sets the fs_active_directory of this FSActiveDirectoryUpdateReq.


        :param fs_active_directory: The fs_active_directory of this FSActiveDirectoryUpdateReq.  # noqa: E501
        :type: FSActiveDirectoryUpdateReqInfo
        """
        if fs_active_directory is None:
            raise ValueError("Invalid value for `fs_active_directory`, must not be `None`")  # noqa: E501

        self._fs_active_directory = fs_active_directory

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
        if not isinstance(other, FSActiveDirectoryUpdateReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
