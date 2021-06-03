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

# from zstacklib.utils.xms_client.models.auth_security_policy_update_req_auth_security_policy import AuthSecurityPolicyUpdateReqAuthSecurityPolicy  # noqa: F401,E501


class AuthSecurityPolicyUpdateReq(object):
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
        'auth_security_policy': 'AuthSecurityPolicyUpdateReqAuthSecurityPolicy'
    }

    attribute_map = {
        'auth_security_policy': 'auth_security_policy'
    }

    def __init__(self, auth_security_policy=None):  # noqa: E501
        """AuthSecurityPolicyUpdateReq - a model defined in Swagger"""  # noqa: E501

        self._auth_security_policy = None
        self.discriminator = None

        if auth_security_policy is not None:
            self.auth_security_policy = auth_security_policy

    @property
    def auth_security_policy(self):
        """Gets the auth_security_policy of this AuthSecurityPolicyUpdateReq.  # noqa: E501


        :return: The auth_security_policy of this AuthSecurityPolicyUpdateReq.  # noqa: E501
        :rtype: AuthSecurityPolicyUpdateReqAuthSecurityPolicy
        """
        return self._auth_security_policy

    @auth_security_policy.setter
    def auth_security_policy(self, auth_security_policy):
        """Sets the auth_security_policy of this AuthSecurityPolicyUpdateReq.


        :param auth_security_policy: The auth_security_policy of this AuthSecurityPolicyUpdateReq.  # noqa: E501
        :type: AuthSecurityPolicyUpdateReqAuthSecurityPolicy
        """

        self._auth_security_policy = auth_security_policy

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
        if not isinstance(other, AuthSecurityPolicyUpdateReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
