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

# from zstacklib.utils.xms_client.models.vm_flavor import VMFlavor  # noqa: F401,E501


class VMFlavorsResp(object):
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
        'vm_flavors': 'list[VMFlavor]'
    }

    attribute_map = {
        'vm_flavors': 'vm_flavors'
    }

    def __init__(self, vm_flavors=None):  # noqa: E501
        """VMFlavorsResp - a model defined in Swagger"""  # noqa: E501

        self._vm_flavors = None
        self.discriminator = None

        if vm_flavors is not None:
            self.vm_flavors = vm_flavors

    @property
    def vm_flavors(self):
        """Gets the vm_flavors of this VMFlavorsResp.  # noqa: E501


        :return: The vm_flavors of this VMFlavorsResp.  # noqa: E501
        :rtype: list[VMFlavor]
        """
        return self._vm_flavors

    @vm_flavors.setter
    def vm_flavors(self, vm_flavors):
        """Sets the vm_flavors of this VMFlavorsResp.


        :param vm_flavors: The vm_flavors of this VMFlavorsResp.  # noqa: E501
        :type: list[VMFlavor]
        """

        self._vm_flavors = vm_flavors

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
        if not isinstance(other, VMFlavorsResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other