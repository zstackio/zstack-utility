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

# from zstacklib.utils.xms_client.models.os_search_gateway_req import OSSearchGatewayReq  # noqa: F401,E501


class OSSearchEngineAddGatewaysReqSearchEngine(object):
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
        'os_search_gateways': 'list[OSSearchGatewayReq]'
    }

    attribute_map = {
        'os_search_gateways': 'os_search_gateways'
    }

    def __init__(self, os_search_gateways=None):  # noqa: E501
        """OSSearchEngineAddGatewaysReqSearchEngine - a model defined in Swagger"""  # noqa: E501

        self._os_search_gateways = None
        self.discriminator = None

        self.os_search_gateways = os_search_gateways

    @property
    def os_search_gateways(self):
        """Gets the os_search_gateways of this OSSearchEngineAddGatewaysReqSearchEngine.  # noqa: E501


        :return: The os_search_gateways of this OSSearchEngineAddGatewaysReqSearchEngine.  # noqa: E501
        :rtype: list[OSSearchGatewayReq]
        """
        return self._os_search_gateways

    @os_search_gateways.setter
    def os_search_gateways(self, os_search_gateways):
        """Sets the os_search_gateways of this OSSearchEngineAddGatewaysReqSearchEngine.


        :param os_search_gateways: The os_search_gateways of this OSSearchEngineAddGatewaysReqSearchEngine.  # noqa: E501
        :type: list[OSSearchGatewayReq]
        """
        if os_search_gateways is None:
            raise ValueError("Invalid value for `os_search_gateways`, must not be `None`")  # noqa: E501

        self._os_search_gateways = os_search_gateways

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
        if not isinstance(other, OSSearchEngineAddGatewaysReqSearchEngine):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
