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


class OSBucketCustomLabelsAddReqBucketLabelsElt(object):
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
        'category': 'str',
        'name': 'str',
        'type': 'str'
    }

    attribute_map = {
        'category': 'category',
        'name': 'name',
        'type': 'type'
    }

    def __init__(self, category=None, name=None, type=None):  # noqa: E501
        """OSBucketCustomLabelsAddReqBucketLabelsElt - a model defined in Swagger"""  # noqa: E501

        self._category = None
        self._name = None
        self._type = None
        self.discriminator = None

        self.category = category
        self.name = name
        self.type = type

    @property
    def category(self):
        """Gets the category of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501


        :return: The category of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501
        :rtype: str
        """
        return self._category

    @category.setter
    def category(self, category):
        """Sets the category of this OSBucketCustomLabelsAddReqBucketLabelsElt.


        :param category: The category of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501
        :type: str
        """
        if category is None:
            raise ValueError("Invalid value for `category`, must not be `None`")  # noqa: E501

        self._category = category

    @property
    def name(self):
        """Gets the name of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501


        :return: The name of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this OSBucketCustomLabelsAddReqBucketLabelsElt.


        :param name: The name of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501
        :type: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def type(self):
        """Gets the type of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501


        :return: The type of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501
        :rtype: str
        """
        return self._type

    @type.setter
    def type(self, type):
        """Sets the type of this OSBucketCustomLabelsAddReqBucketLabelsElt.


        :param type: The type of this OSBucketCustomLabelsAddReqBucketLabelsElt.  # noqa: E501
        :type: str
        """
        if type is None:
            raise ValueError("Invalid value for `type`, must not be `None`")  # noqa: E501

        self._type = type

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
        if not isinstance(other, OSBucketCustomLabelsAddReqBucketLabelsElt):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
