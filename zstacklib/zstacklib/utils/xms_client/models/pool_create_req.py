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

# from zstacklib.utils.xms_client.models.pool_create_req_pool import PoolCreateReqPool  # noqa: F401,E501


class PoolCreateReq(object):
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
        'pool': 'PoolCreateReqPool'
    }

    attribute_map = {
        'pool': 'pool'
    }

    def __init__(self, pool=None):  # noqa: E501
        """PoolCreateReq - a model defined in Swagger"""  # noqa: E501

        self._pool = None
        self.discriminator = None

        if pool is not None:
            self.pool = pool

    @property
    def pool(self):
        """Gets the pool of this PoolCreateReq.  # noqa: E501


        :return: The pool of this PoolCreateReq.  # noqa: E501
        :rtype: PoolCreateReqPool
        """
        return self._pool

    @pool.setter
    def pool(self, pool):
        """Sets the pool of this PoolCreateReq.


        :param pool: The pool of this PoolCreateReq.  # noqa: E501
        :type: PoolCreateReqPool
        """

        self._pool = pool

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
        if not isinstance(other, PoolCreateReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other