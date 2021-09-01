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


class S3LoadBalancerGroupCreateReqGroupLoadBalancersElt(object):
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
        'host_id': 'int',
        'interface_name': 'str',
        'ip': 'str',
        'vip': 'str'
    }

    attribute_map = {
        'host_id': 'host_id',
        'interface_name': 'interface_name',
        'ip': 'ip',
        'vip': 'vip'
    }

    def __init__(self, host_id=None, interface_name=None, ip=None, vip=None):  # noqa: E501
        """S3LoadBalancerGroupCreateReqGroupLoadBalancersElt - a model defined in Swagger"""  # noqa: E501

        self._host_id = None
        self._interface_name = None
        self._ip = None
        self._vip = None
        self.discriminator = None

        self.host_id = host_id
        if interface_name is not None:
            self.interface_name = interface_name
        if ip is not None:
            self.ip = ip
        self.vip = vip

    @property
    def host_id(self):
        """Gets the host_id of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501

        host id of load balancer  # noqa: E501

        :return: The host_id of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :rtype: int
        """
        return self._host_id

    @host_id.setter
    def host_id(self, host_id):
        """Sets the host_id of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.

        host id of load balancer  # noqa: E501

        :param host_id: The host_id of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :type: int
        """
        if host_id is None:
            raise ValueError("Invalid value for `host_id`, must not be `None`")  # noqa: E501

        self._host_id = host_id

    @property
    def interface_name(self):
        """Gets the interface_name of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501

        vip will be bounded to interface, exclusive to ip  # noqa: E501

        :return: The interface_name of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :rtype: str
        """
        return self._interface_name

    @interface_name.setter
    def interface_name(self, interface_name):
        """Sets the interface_name of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.

        vip will be bounded to interface, exclusive to ip  # noqa: E501

        :param interface_name: The interface_name of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :type: str
        """

        self._interface_name = interface_name

    @property
    def ip(self):
        """Gets the ip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501

        vip will be bounded to interface of the gateway ip, exclusive to interface name  # noqa: E501

        :return: The ip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :rtype: str
        """
        return self._ip

    @ip.setter
    def ip(self, ip):
        """Sets the ip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.

        vip will be bounded to interface of the gateway ip, exclusive to interface name  # noqa: E501

        :param ip: The ip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :type: str
        """

        self._ip = ip

    @property
    def vip(self):
        """Gets the vip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501

        vip of load balancer  # noqa: E501

        :return: The vip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :rtype: str
        """
        return self._vip

    @vip.setter
    def vip(self, vip):
        """Sets the vip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.

        vip of load balancer  # noqa: E501

        :param vip: The vip of this S3LoadBalancerGroupCreateReqGroupLoadBalancersElt.  # noqa: E501
        :type: str
        """
        if vip is None:
            raise ValueError("Invalid value for `vip`, must not be `None`")  # noqa: E501

        self._vip = vip

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
        if not isinstance(other, S3LoadBalancerGroupCreateReqGroupLoadBalancersElt):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other