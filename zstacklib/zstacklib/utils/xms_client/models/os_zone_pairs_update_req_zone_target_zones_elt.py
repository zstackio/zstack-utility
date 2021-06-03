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


class OSZonePairsUpdateReqZoneTargetZonesElt(object):
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
        'clock_diff': 'int',
        'zone_uuid': 'str'
    }

    attribute_map = {
        'clock_diff': 'clock_diff',
        'zone_uuid': 'zone_uuid'
    }

    def __init__(self, clock_diff=None, zone_uuid=None):  # noqa: E501
        """OSZonePairsUpdateReqZoneTargetZonesElt - a model defined in Swagger"""  # noqa: E501

        self._clock_diff = None
        self._zone_uuid = None
        self.discriminator = None

        self.clock_diff = clock_diff
        self.zone_uuid = zone_uuid

    @property
    def clock_diff(self):
        """Gets the clock_diff of this OSZonePairsUpdateReqZoneTargetZonesElt.  # noqa: E501


        :return: The clock_diff of this OSZonePairsUpdateReqZoneTargetZonesElt.  # noqa: E501
        :rtype: int
        """
        return self._clock_diff

    @clock_diff.setter
    def clock_diff(self, clock_diff):
        """Sets the clock_diff of this OSZonePairsUpdateReqZoneTargetZonesElt.


        :param clock_diff: The clock_diff of this OSZonePairsUpdateReqZoneTargetZonesElt.  # noqa: E501
        :type: int
        """
        if clock_diff is None:
            raise ValueError("Invalid value for `clock_diff`, must not be `None`")  # noqa: E501

        self._clock_diff = clock_diff

    @property
    def zone_uuid(self):
        """Gets the zone_uuid of this OSZonePairsUpdateReqZoneTargetZonesElt.  # noqa: E501


        :return: The zone_uuid of this OSZonePairsUpdateReqZoneTargetZonesElt.  # noqa: E501
        :rtype: str
        """
        return self._zone_uuid

    @zone_uuid.setter
    def zone_uuid(self, zone_uuid):
        """Sets the zone_uuid of this OSZonePairsUpdateReqZoneTargetZonesElt.


        :param zone_uuid: The zone_uuid of this OSZonePairsUpdateReqZoneTargetZonesElt.  # noqa: E501
        :type: str
        """
        if zone_uuid is None:
            raise ValueError("Invalid value for `zone_uuid`, must not be `None`")  # noqa: E501

        self._zone_uuid = zone_uuid

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
        if not isinstance(other, OSZonePairsUpdateReqZoneTargetZonesElt):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
