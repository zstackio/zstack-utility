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


class PlacementNodeCreateReqPlacementNode(object):
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
        'is_witness': 'bool',
        'name': 'str',
        'parent_id': 'int',
        'type': 'str'
    }

    attribute_map = {
        'is_witness': 'is_witness',
        'name': 'name',
        'parent_id': 'parent_id',
        'type': 'type'
    }

    def __init__(self, is_witness=None, name=None, parent_id=None, type=None):  # noqa: E501
        """PlacementNodeCreateReqPlacementNode - a model defined in Swagger"""  # noqa: E501

        self._is_witness = None
        self._name = None
        self._parent_id = None
        self._type = None
        self.discriminator = None

        if is_witness is not None:
            self.is_witness = is_witness
        self.name = name
        self.parent_id = parent_id
        self.type = type

    @property
    def is_witness(self):
        """Gets the is_witness of this PlacementNodeCreateReqPlacementNode.  # noqa: E501


        :return: The is_witness of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :rtype: bool
        """
        return self._is_witness

    @is_witness.setter
    def is_witness(self, is_witness):
        """Sets the is_witness of this PlacementNodeCreateReqPlacementNode.


        :param is_witness: The is_witness of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :type: bool
        """

        self._is_witness = is_witness

    @property
    def name(self):
        """Gets the name of this PlacementNodeCreateReqPlacementNode.  # noqa: E501


        :return: The name of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this PlacementNodeCreateReqPlacementNode.


        :param name: The name of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :type: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def parent_id(self):
        """Gets the parent_id of this PlacementNodeCreateReqPlacementNode.  # noqa: E501


        :return: The parent_id of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :rtype: int
        """
        return self._parent_id

    @parent_id.setter
    def parent_id(self, parent_id):
        """Sets the parent_id of this PlacementNodeCreateReqPlacementNode.


        :param parent_id: The parent_id of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :type: int
        """
        if parent_id is None:
            raise ValueError("Invalid value for `parent_id`, must not be `None`")  # noqa: E501

        self._parent_id = parent_id

    @property
    def type(self):
        """Gets the type of this PlacementNodeCreateReqPlacementNode.  # noqa: E501


        :return: The type of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
        :rtype: str
        """
        return self._type

    @type.setter
    def type(self, type):
        """Sets the type of this PlacementNodeCreateReqPlacementNode.


        :param type: The type of this PlacementNodeCreateReqPlacementNode.  # noqa: E501
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
        if not isinstance(other, PlacementNodeCreateReqPlacementNode):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other