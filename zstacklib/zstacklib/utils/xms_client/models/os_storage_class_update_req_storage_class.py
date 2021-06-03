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


class OSStorageClassUpdateReqStorageClass(object):
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
        'active_pool_ids': 'list[int]',
        'description': 'str',
        'inactive_pool_ids': 'list[int]',
        'name': 'str'
    }

    attribute_map = {
        'active_pool_ids': 'active_pool_ids',
        'description': 'description',
        'inactive_pool_ids': 'inactive_pool_ids',
        'name': 'name'
    }

    def __init__(self, active_pool_ids=None, description=None, inactive_pool_ids=None, name=None):  # noqa: E501
        """OSStorageClassUpdateReqStorageClass - a model defined in Swagger"""  # noqa: E501

        self._active_pool_ids = None
        self._description = None
        self._inactive_pool_ids = None
        self._name = None
        self.discriminator = None

        if active_pool_ids is not None:
            self.active_pool_ids = active_pool_ids
        if description is not None:
            self.description = description
        if inactive_pool_ids is not None:
            self.inactive_pool_ids = inactive_pool_ids
        if name is not None:
            self.name = name

    @property
    def active_pool_ids(self):
        """Gets the active_pool_ids of this OSStorageClassUpdateReqStorageClass.  # noqa: E501


        :return: The active_pool_ids of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :rtype: list[int]
        """
        return self._active_pool_ids

    @active_pool_ids.setter
    def active_pool_ids(self, active_pool_ids):
        """Sets the active_pool_ids of this OSStorageClassUpdateReqStorageClass.


        :param active_pool_ids: The active_pool_ids of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :type: list[int]
        """

        self._active_pool_ids = active_pool_ids

    @property
    def description(self):
        """Gets the description of this OSStorageClassUpdateReqStorageClass.  # noqa: E501


        :return: The description of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this OSStorageClassUpdateReqStorageClass.


        :param description: The description of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def inactive_pool_ids(self):
        """Gets the inactive_pool_ids of this OSStorageClassUpdateReqStorageClass.  # noqa: E501


        :return: The inactive_pool_ids of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :rtype: list[int]
        """
        return self._inactive_pool_ids

    @inactive_pool_ids.setter
    def inactive_pool_ids(self, inactive_pool_ids):
        """Sets the inactive_pool_ids of this OSStorageClassUpdateReqStorageClass.


        :param inactive_pool_ids: The inactive_pool_ids of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :type: list[int]
        """

        self._inactive_pool_ids = inactive_pool_ids

    @property
    def name(self):
        """Gets the name of this OSStorageClassUpdateReqStorageClass.  # noqa: E501


        :return: The name of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this OSStorageClassUpdateReqStorageClass.


        :param name: The name of this OSStorageClassUpdateReqStorageClass.  # noqa: E501
        :type: str
        """

        self._name = name

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
        if not isinstance(other, OSStorageClassUpdateReqStorageClass):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
