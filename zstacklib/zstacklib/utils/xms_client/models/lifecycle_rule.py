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

# from zstacklib.utils.xms_client.models.lifecycle_expiration import LifecycleExpiration  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.lifecycle_transition import LifecycleTransition  # noqa: F401,E501


class LifecycleRule(object):
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
        'enabled': 'bool',
        'expiration': 'LifecycleExpiration',
        'name': 'str',
        'prefix': 'str',
        'transitions': 'list[LifecycleTransition]'
    }

    attribute_map = {
        'enabled': 'enabled',
        'expiration': 'expiration',
        'name': 'name',
        'prefix': 'prefix',
        'transitions': 'transitions'
    }

    def __init__(self, enabled=None, expiration=None, name=None, prefix=None, transitions=None):  # noqa: E501
        """LifecycleRule - a model defined in Swagger"""  # noqa: E501

        self._enabled = None
        self._expiration = None
        self._name = None
        self._prefix = None
        self._transitions = None
        self.discriminator = None

        if enabled is not None:
            self.enabled = enabled
        if expiration is not None:
            self.expiration = expiration
        if name is not None:
            self.name = name
        if prefix is not None:
            self.prefix = prefix
        if transitions is not None:
            self.transitions = transitions

    @property
    def enabled(self):
        """Gets the enabled of this LifecycleRule.  # noqa: E501


        :return: The enabled of this LifecycleRule.  # noqa: E501
        :rtype: bool
        """
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        """Sets the enabled of this LifecycleRule.


        :param enabled: The enabled of this LifecycleRule.  # noqa: E501
        :type: bool
        """

        self._enabled = enabled

    @property
    def expiration(self):
        """Gets the expiration of this LifecycleRule.  # noqa: E501


        :return: The expiration of this LifecycleRule.  # noqa: E501
        :rtype: LifecycleExpiration
        """
        return self._expiration

    @expiration.setter
    def expiration(self, expiration):
        """Sets the expiration of this LifecycleRule.


        :param expiration: The expiration of this LifecycleRule.  # noqa: E501
        :type: LifecycleExpiration
        """

        self._expiration = expiration

    @property
    def name(self):
        """Gets the name of this LifecycleRule.  # noqa: E501


        :return: The name of this LifecycleRule.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this LifecycleRule.


        :param name: The name of this LifecycleRule.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def prefix(self):
        """Gets the prefix of this LifecycleRule.  # noqa: E501


        :return: The prefix of this LifecycleRule.  # noqa: E501
        :rtype: str
        """
        return self._prefix

    @prefix.setter
    def prefix(self, prefix):
        """Sets the prefix of this LifecycleRule.


        :param prefix: The prefix of this LifecycleRule.  # noqa: E501
        :type: str
        """

        self._prefix = prefix

    @property
    def transitions(self):
        """Gets the transitions of this LifecycleRule.  # noqa: E501


        :return: The transitions of this LifecycleRule.  # noqa: E501
        :rtype: list[LifecycleTransition]
        """
        return self._transitions

    @transitions.setter
    def transitions(self, transitions):
        """Sets the transitions of this LifecycleRule.


        :param transitions: The transitions of this LifecycleRule.  # noqa: E501
        :type: list[LifecycleTransition]
        """

        self._transitions = transitions

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
        if not isinstance(other, LifecycleRule):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
