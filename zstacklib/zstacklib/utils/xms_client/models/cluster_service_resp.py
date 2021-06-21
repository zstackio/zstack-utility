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

# from zstacklib.utils.xms_client.models.cluster_service import ClusterService  # noqa: F401,E501


class ClusterServiceResp(object):
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
        'cluster_service': 'ClusterService'
    }

    attribute_map = {
        'cluster_service': 'cluster_service'
    }

    def __init__(self, cluster_service=None):  # noqa: E501
        """ClusterServiceResp - a model defined in Swagger"""  # noqa: E501

        self._cluster_service = None
        self.discriminator = None

        if cluster_service is not None:
            self.cluster_service = cluster_service

    @property
    def cluster_service(self):
        """Gets the cluster_service of this ClusterServiceResp.  # noqa: E501


        :return: The cluster_service of this ClusterServiceResp.  # noqa: E501
        :rtype: ClusterService
        """
        return self._cluster_service

    @cluster_service.setter
    def cluster_service(self, cluster_service):
        """Sets the cluster_service of this ClusterServiceResp.


        :param cluster_service: The cluster_service of this ClusterServiceResp.  # noqa: E501
        :type: ClusterService
        """

        self._cluster_service = cluster_service

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
        if not isinstance(other, ClusterServiceResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
