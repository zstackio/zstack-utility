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

# from zstacklib.utils.xms_client.models.s3_load_balancer_samples_elem import S3LoadBalancerSamplesElem  # noqa: F401,E501


class MultiS3LoadBalancersSamplesResp(object):
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
        's3_load_balancers_samples': 'list[S3LoadBalancerSamplesElem]'
    }

    attribute_map = {
        's3_load_balancers_samples': 's3_load_balancers_samples'
    }

    def __init__(self, s3_load_balancers_samples=None):  # noqa: E501
        """MultiS3LoadBalancersSamplesResp - a model defined in Swagger"""  # noqa: E501

        self._s3_load_balancers_samples = None
        self.discriminator = None

        if s3_load_balancers_samples is not None:
            self.s3_load_balancers_samples = s3_load_balancers_samples

    @property
    def s3_load_balancers_samples(self):
        """Gets the s3_load_balancers_samples of this MultiS3LoadBalancersSamplesResp.  # noqa: E501


        :return: The s3_load_balancers_samples of this MultiS3LoadBalancersSamplesResp.  # noqa: E501
        :rtype: list[S3LoadBalancerSamplesElem]
        """
        return self._s3_load_balancers_samples

    @s3_load_balancers_samples.setter
    def s3_load_balancers_samples(self, s3_load_balancers_samples):
        """Sets the s3_load_balancers_samples of this MultiS3LoadBalancersSamplesResp.


        :param s3_load_balancers_samples: The s3_load_balancers_samples of this MultiS3LoadBalancersSamplesResp.  # noqa: E501
        :type: list[S3LoadBalancerSamplesElem]
        """

        self._s3_load_balancers_samples = s3_load_balancers_samples

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
        if not isinstance(other, MultiS3LoadBalancersSamplesResp):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
