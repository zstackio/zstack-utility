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

# from zstacklib.utils.xms_client.models.client import Client  # noqa: F401,E501


class ClientsResp(object):
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
        'clients': 'list[Client]'
    }

    attribute_map = {
        'clients': 'clients'
    }

    def __init__(self, clients=None):  # noqa: E501
        """ClientsResp - a model defined in Swagger"""  # noqa: E501

        self._clients = None
        self.discriminator = None

        self.clients = clients

    @property
    def clients(self):
        """Gets the clients of this ClientsResp.  # noqa: E501


        :return: The clients of this ClientsResp.  # noqa: E501
        :rtype: list[Client]
        """
        return self._clients

    @clients.setter
    def clients(self, clients):
        """Sets the clients of this ClientsResp.


        :param clients: The clients of this ClientsResp.  # noqa: E501
        :type: list[Client]
        """
        if clients is None:
            raise ValueError("Invalid value for `clients`, must not be `None`")  # noqa: E501

        self._clients = clients

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
        if not isinstance(other, ClientsResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
