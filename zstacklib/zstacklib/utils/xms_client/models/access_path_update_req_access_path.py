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


class AccessPathUpdateReqAccessPath(object):
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
        'chap': 'bool',
        'description': 'str',
        'name': 'str',
        'tname': 'str',
        'tsecret': 'str'
    }

    attribute_map = {
        'chap': 'chap',
        'description': 'description',
        'name': 'name',
        'tname': 'tname',
        'tsecret': 'tsecret'
    }

    def __init__(self, chap=None, description=None, name=None, tname=None, tsecret=None):  # noqa: E501
        """AccessPathUpdateReqAccessPath - a model defined in Swagger"""  # noqa: E501

        self._chap = None
        self._description = None
        self._name = None
        self._tname = None
        self._tsecret = None
        self.discriminator = None

        if chap is not None:
            self.chap = chap
        if description is not None:
            self.description = description
        if name is not None:
            self.name = name
        if tname is not None:
            self.tname = tname
        if tsecret is not None:
            self.tsecret = tsecret

    @property
    def chap(self):
        """Gets the chap of this AccessPathUpdateReqAccessPath.  # noqa: E501


        :return: The chap of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :rtype: bool
        """
        return self._chap

    @chap.setter
    def chap(self, chap):
        """Sets the chap of this AccessPathUpdateReqAccessPath.


        :param chap: The chap of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :type: bool
        """

        self._chap = chap

    @property
    def description(self):
        """Gets the description of this AccessPathUpdateReqAccessPath.  # noqa: E501


        :return: The description of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this AccessPathUpdateReqAccessPath.


        :param description: The description of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def name(self):
        """Gets the name of this AccessPathUpdateReqAccessPath.  # noqa: E501


        :return: The name of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this AccessPathUpdateReqAccessPath.


        :param name: The name of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def tname(self):
        """Gets the tname of this AccessPathUpdateReqAccessPath.  # noqa: E501


        :return: The tname of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :rtype: str
        """
        return self._tname

    @tname.setter
    def tname(self, tname):
        """Sets the tname of this AccessPathUpdateReqAccessPath.


        :param tname: The tname of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :type: str
        """

        self._tname = tname

    @property
    def tsecret(self):
        """Gets the tsecret of this AccessPathUpdateReqAccessPath.  # noqa: E501


        :return: The tsecret of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :rtype: str
        """
        return self._tsecret

    @tsecret.setter
    def tsecret(self, tsecret):
        """Sets the tsecret of this AccessPathUpdateReqAccessPath.


        :param tsecret: The tsecret of this AccessPathUpdateReqAccessPath.  # noqa: E501
        :type: str
        """

        self._tsecret = tsecret

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
        if not isinstance(other, AccessPathUpdateReqAccessPath):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
