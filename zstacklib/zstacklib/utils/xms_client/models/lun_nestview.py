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


class LunNestview(object):
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
        'id': 'int',
        'lun_id': 'int'
    }

    attribute_map = {
        'id': 'id',
        'lun_id': 'lun_id'
    }

    def __init__(self, id=None, lun_id=None):  # noqa: E501
        """LunNestview - a model defined in Swagger"""  # noqa: E501

        self._id = None
        self._lun_id = None
        self.discriminator = None

        if id is not None:
            self.id = id
        if lun_id is not None:
            self.lun_id = lun_id

    @property
    def id(self):
        """Gets the id of this LunNestview.  # noqa: E501


        :return: The id of this LunNestview.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this LunNestview.


        :param id: The id of this LunNestview.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def lun_id(self):
        """Gets the lun_id of this LunNestview.  # noqa: E501


        :return: The lun_id of this LunNestview.  # noqa: E501
        :rtype: int
        """
        return self._lun_id

    @lun_id.setter
    def lun_id(self, lun_id):
        """Sets the lun_id of this LunNestview.


        :param lun_id: The lun_id of this LunNestview.  # noqa: E501
        :type: int
        """

        self._lun_id = lun_id

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
        if not isinstance(other, LunNestview):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other