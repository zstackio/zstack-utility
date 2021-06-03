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


class UserUpdateReqUser(object):
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
        'email': 'str',
        'enabled': 'bool',
        'name': 'str',
        'roles': 'list[str]'
    }

    attribute_map = {
        'email': 'email',
        'enabled': 'enabled',
        'name': 'name',
        'roles': 'roles'
    }

    def __init__(self, email=None, enabled=None, name=None, roles=None):  # noqa: E501
        """UserUpdateReqUser - a model defined in Swagger"""  # noqa: E501

        self._email = None
        self._enabled = None
        self._name = None
        self._roles = None
        self.discriminator = None

        self.email = email
        self.enabled = enabled
        self.name = name
        if roles is not None:
            self.roles = roles

    @property
    def email(self):
        """Gets the email of this UserUpdateReqUser.  # noqa: E501

        email of user  # noqa: E501

        :return: The email of this UserUpdateReqUser.  # noqa: E501
        :rtype: str
        """
        return self._email

    @email.setter
    def email(self, email):
        """Sets the email of this UserUpdateReqUser.

        email of user  # noqa: E501

        :param email: The email of this UserUpdateReqUser.  # noqa: E501
        :type: str
        """
        if email is None:
            raise ValueError("Invalid value for `email`, must not be `None`")  # noqa: E501

        self._email = email

    @property
    def enabled(self):
        """Gets the enabled of this UserUpdateReqUser.  # noqa: E501

        enable or disable the user  # noqa: E501

        :return: The enabled of this UserUpdateReqUser.  # noqa: E501
        :rtype: bool
        """
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        """Sets the enabled of this UserUpdateReqUser.

        enable or disable the user  # noqa: E501

        :param enabled: The enabled of this UserUpdateReqUser.  # noqa: E501
        :type: bool
        """
        if enabled is None:
            raise ValueError("Invalid value for `enabled`, must not be `None`")  # noqa: E501

        self._enabled = enabled

    @property
    def name(self):
        """Gets the name of this UserUpdateReqUser.  # noqa: E501

        name of user  # noqa: E501

        :return: The name of this UserUpdateReqUser.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this UserUpdateReqUser.

        name of user  # noqa: E501

        :param name: The name of this UserUpdateReqUser.  # noqa: E501
        :type: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def roles(self):
        """Gets the roles of this UserUpdateReqUser.  # noqa: E501

        roles of user  # noqa: E501

        :return: The roles of this UserUpdateReqUser.  # noqa: E501
        :rtype: list[str]
        """
        return self._roles

    @roles.setter
    def roles(self, roles):
        """Sets the roles of this UserUpdateReqUser.

        roles of user  # noqa: E501

        :param roles: The roles of this UserUpdateReqUser.  # noqa: E501
        :type: list[str]
        """

        self._roles = roles

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
        if not isinstance(other, UserUpdateReqUser):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
