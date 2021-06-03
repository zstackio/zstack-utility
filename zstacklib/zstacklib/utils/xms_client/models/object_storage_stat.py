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


class ObjectStorageStat(object):
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
        'allocated_objects': 'int',
        'allocated_size': 'int',
        'create': 'datetime',
        'external_allocated_objects': 'int',
        'external_allocated_size': 'int',
        'local_allocated_objects': 'int',
        'local_allocated_size': 'int'
    }

    attribute_map = {
        'allocated_objects': 'allocated_objects',
        'allocated_size': 'allocated_size',
        'create': 'create',
        'external_allocated_objects': 'external_allocated_objects',
        'external_allocated_size': 'external_allocated_size',
        'local_allocated_objects': 'local_allocated_objects',
        'local_allocated_size': 'local_allocated_size'
    }

    def __init__(self, allocated_objects=None, allocated_size=None, create=None, external_allocated_objects=None, external_allocated_size=None, local_allocated_objects=None, local_allocated_size=None):  # noqa: E501
        """ObjectStorageStat - a model defined in Swagger"""  # noqa: E501

        self._allocated_objects = None
        self._allocated_size = None
        self._create = None
        self._external_allocated_objects = None
        self._external_allocated_size = None
        self._local_allocated_objects = None
        self._local_allocated_size = None
        self.discriminator = None

        if allocated_objects is not None:
            self.allocated_objects = allocated_objects
        if allocated_size is not None:
            self.allocated_size = allocated_size
        if create is not None:
            self.create = create
        if external_allocated_objects is not None:
            self.external_allocated_objects = external_allocated_objects
        if external_allocated_size is not None:
            self.external_allocated_size = external_allocated_size
        if local_allocated_objects is not None:
            self.local_allocated_objects = local_allocated_objects
        if local_allocated_size is not None:
            self.local_allocated_size = local_allocated_size

    @property
    def allocated_objects(self):
        """Gets the allocated_objects of this ObjectStorageStat.  # noqa: E501


        :return: The allocated_objects of this ObjectStorageStat.  # noqa: E501
        :rtype: int
        """
        return self._allocated_objects

    @allocated_objects.setter
    def allocated_objects(self, allocated_objects):
        """Sets the allocated_objects of this ObjectStorageStat.


        :param allocated_objects: The allocated_objects of this ObjectStorageStat.  # noqa: E501
        :type: int
        """

        self._allocated_objects = allocated_objects

    @property
    def allocated_size(self):
        """Gets the allocated_size of this ObjectStorageStat.  # noqa: E501


        :return: The allocated_size of this ObjectStorageStat.  # noqa: E501
        :rtype: int
        """
        return self._allocated_size

    @allocated_size.setter
    def allocated_size(self, allocated_size):
        """Sets the allocated_size of this ObjectStorageStat.


        :param allocated_size: The allocated_size of this ObjectStorageStat.  # noqa: E501
        :type: int
        """

        self._allocated_size = allocated_size

    @property
    def create(self):
        """Gets the create of this ObjectStorageStat.  # noqa: E501


        :return: The create of this ObjectStorageStat.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this ObjectStorageStat.


        :param create: The create of this ObjectStorageStat.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def external_allocated_objects(self):
        """Gets the external_allocated_objects of this ObjectStorageStat.  # noqa: E501


        :return: The external_allocated_objects of this ObjectStorageStat.  # noqa: E501
        :rtype: int
        """
        return self._external_allocated_objects

    @external_allocated_objects.setter
    def external_allocated_objects(self, external_allocated_objects):
        """Sets the external_allocated_objects of this ObjectStorageStat.


        :param external_allocated_objects: The external_allocated_objects of this ObjectStorageStat.  # noqa: E501
        :type: int
        """

        self._external_allocated_objects = external_allocated_objects

    @property
    def external_allocated_size(self):
        """Gets the external_allocated_size of this ObjectStorageStat.  # noqa: E501


        :return: The external_allocated_size of this ObjectStorageStat.  # noqa: E501
        :rtype: int
        """
        return self._external_allocated_size

    @external_allocated_size.setter
    def external_allocated_size(self, external_allocated_size):
        """Sets the external_allocated_size of this ObjectStorageStat.


        :param external_allocated_size: The external_allocated_size of this ObjectStorageStat.  # noqa: E501
        :type: int
        """

        self._external_allocated_size = external_allocated_size

    @property
    def local_allocated_objects(self):
        """Gets the local_allocated_objects of this ObjectStorageStat.  # noqa: E501


        :return: The local_allocated_objects of this ObjectStorageStat.  # noqa: E501
        :rtype: int
        """
        return self._local_allocated_objects

    @local_allocated_objects.setter
    def local_allocated_objects(self, local_allocated_objects):
        """Sets the local_allocated_objects of this ObjectStorageStat.


        :param local_allocated_objects: The local_allocated_objects of this ObjectStorageStat.  # noqa: E501
        :type: int
        """

        self._local_allocated_objects = local_allocated_objects

    @property
    def local_allocated_size(self):
        """Gets the local_allocated_size of this ObjectStorageStat.  # noqa: E501


        :return: The local_allocated_size of this ObjectStorageStat.  # noqa: E501
        :rtype: int
        """
        return self._local_allocated_size

    @local_allocated_size.setter
    def local_allocated_size(self, local_allocated_size):
        """Sets the local_allocated_size of this ObjectStorageStat.


        :param local_allocated_size: The local_allocated_size of this ObjectStorageStat.  # noqa: E501
        :type: int
        """

        self._local_allocated_size = local_allocated_size

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
        if not isinstance(other, ObjectStorageStat):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
