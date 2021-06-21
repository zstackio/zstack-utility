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

# from zstacklib.utils.xms_client.models.paging import Paging  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.s3_load_balancer_stat import S3LoadBalancerStat  # noqa: F401,E501


class S3LoadBalancerSamplesElem(object):
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
        'id': 'int',
        'paging': 'Paging',
        'samples': 'list[S3LoadBalancerStat]'
    }

    attribute_map = {
        'id': 'id',
        'paging': 'paging',
        'samples': 'samples'
    }

    def __init__(self, id=None, paging=None, samples=None):  # noqa: E501
        """S3LoadBalancerSamplesElem - a model defined in Swagger"""  # noqa: E501

        self._id = None
        self._paging = None
        self._samples = None
        self.discriminator = None

        if id is not None:
            self.id = id
        if paging is not None:
            self.paging = paging
        if samples is not None:
            self.samples = samples

    @property
    def id(self):
        """Gets the id of this S3LoadBalancerSamplesElem.  # noqa: E501


        :return: The id of this S3LoadBalancerSamplesElem.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this S3LoadBalancerSamplesElem.


        :param id: The id of this S3LoadBalancerSamplesElem.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def paging(self):
        """Gets the paging of this S3LoadBalancerSamplesElem.  # noqa: E501


        :return: The paging of this S3LoadBalancerSamplesElem.  # noqa: E501
        :rtype: Paging
        """
        return self._paging

    @paging.setter
    def paging(self, paging):
        """Sets the paging of this S3LoadBalancerSamplesElem.


        :param paging: The paging of this S3LoadBalancerSamplesElem.  # noqa: E501
        :type: Paging
        """

        self._paging = paging

    @property
    def samples(self):
        """Gets the samples of this S3LoadBalancerSamplesElem.  # noqa: E501


        :return: The samples of this S3LoadBalancerSamplesElem.  # noqa: E501
        :rtype: list[S3LoadBalancerStat]
        """
        return self._samples

    @samples.setter
    def samples(self, samples):
        """Sets the samples of this S3LoadBalancerSamplesElem.


        :param samples: The samples of this S3LoadBalancerSamplesElem.  # noqa: E501
        :type: list[S3LoadBalancerStat]
        """

        self._samples = samples

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
        if not isinstance(other, S3LoadBalancerSamplesElem):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
