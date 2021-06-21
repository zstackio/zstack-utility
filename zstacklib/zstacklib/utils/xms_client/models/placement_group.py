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


class PlacementGroup(object):
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
        'chunk_id': 'str',
        'id': 'int',
        'osd_ids': 'list[int]',
        'status': 'str',
        'update': 'datetime'
    }

    attribute_map = {
        'chunk_id': 'chunk_id',
        'id': 'id',
        'osd_ids': 'osd_ids',
        'status': 'status',
        'update': 'update'
    }

    def __init__(self, chunk_id=None, id=None, osd_ids=None, status=None, update=None):  # noqa: E501
        """PlacementGroup - a model defined in Swagger"""  # noqa: E501

        self._chunk_id = None
        self._id = None
        self._osd_ids = None
        self._status = None
        self._update = None
        self.discriminator = None

        if chunk_id is not None:
            self.chunk_id = chunk_id
        if id is not None:
            self.id = id
        if osd_ids is not None:
            self.osd_ids = osd_ids
        if status is not None:
            self.status = status
        if update is not None:
            self.update = update

    @property
    def chunk_id(self):
        """Gets the chunk_id of this PlacementGroup.  # noqa: E501


        :return: The chunk_id of this PlacementGroup.  # noqa: E501
        :rtype: str
        """
        return self._chunk_id

    @chunk_id.setter
    def chunk_id(self, chunk_id):
        """Sets the chunk_id of this PlacementGroup.


        :param chunk_id: The chunk_id of this PlacementGroup.  # noqa: E501
        :type: str
        """

        self._chunk_id = chunk_id

    @property
    def id(self):
        """Gets the id of this PlacementGroup.  # noqa: E501


        :return: The id of this PlacementGroup.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this PlacementGroup.


        :param id: The id of this PlacementGroup.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def osd_ids(self):
        """Gets the osd_ids of this PlacementGroup.  # noqa: E501


        :return: The osd_ids of this PlacementGroup.  # noqa: E501
        :rtype: list[int]
        """
        return self._osd_ids

    @osd_ids.setter
    def osd_ids(self, osd_ids):
        """Sets the osd_ids of this PlacementGroup.


        :param osd_ids: The osd_ids of this PlacementGroup.  # noqa: E501
        :type: list[int]
        """

        self._osd_ids = osd_ids

    @property
    def status(self):
        """Gets the status of this PlacementGroup.  # noqa: E501


        :return: The status of this PlacementGroup.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this PlacementGroup.


        :param status: The status of this PlacementGroup.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def update(self):
        """Gets the update of this PlacementGroup.  # noqa: E501


        :return: The update of this PlacementGroup.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this PlacementGroup.


        :param update: The update of this PlacementGroup.  # noqa: E501
        :type: datetime
        """

        self._update = update

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
        if not isinstance(other, PlacementGroup):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
