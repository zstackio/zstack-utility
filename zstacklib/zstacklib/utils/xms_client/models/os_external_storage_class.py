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

# from zstacklib.utils.xms_client.models.object_storage_policy import ObjectStoragePolicy  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.os_external_storage_platform import OSExternalStoragePlatform  # noqa: F401,E501


class OSExternalStorageClass(object):
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
        'create': 'datetime',
        'class_id': 'str',
        'class_status': 'str',
        'description': 'str',
        'external_storage_platforms': 'list[OSExternalStoragePlatform]',
        'id': 'int',
        'name': 'str',
        'os_policy': 'ObjectStoragePolicy',
        'os_policy_id': 'int',
        'platform': 'str',
        'platform_type': 'str',
        'prefix_enabled': 'bool',
        'status': 'str',
        'storage_pattern': 'list[str]'
    }

    attribute_map = {
        'create': 'Create',
        'class_id': 'class_id',
        'class_status': 'class_status',
        'description': 'description',
        'external_storage_platforms': 'external_storage_platforms',
        'id': 'id',
        'name': 'name',
        'os_policy': 'os_policy',
        'os_policy_id': 'os_policy_id',
        'platform': 'platform',
        'platform_type': 'platform_type',
        'prefix_enabled': 'prefix_enabled',
        'status': 'status',
        'storage_pattern': 'storage_pattern'
    }

    def __init__(self, create=None, class_id=None, class_status=None, description=None, external_storage_platforms=None, id=None, name=None, os_policy=None, os_policy_id=None, platform=None, platform_type=None, prefix_enabled=None, status=None, storage_pattern=None):  # noqa: E501
        """OSExternalStorageClass - a model defined in Swagger"""  # noqa: E501

        self._create = None
        self._class_id = None
        self._class_status = None
        self._description = None
        self._external_storage_platforms = None
        self._id = None
        self._name = None
        self._os_policy = None
        self._os_policy_id = None
        self._platform = None
        self._platform_type = None
        self._prefix_enabled = None
        self._status = None
        self._storage_pattern = None
        self.discriminator = None

        if create is not None:
            self.create = create
        if class_id is not None:
            self.class_id = class_id
        if class_status is not None:
            self.class_status = class_status
        if description is not None:
            self.description = description
        if external_storage_platforms is not None:
            self.external_storage_platforms = external_storage_platforms
        if id is not None:
            self.id = id
        if name is not None:
            self.name = name
        if os_policy is not None:
            self.os_policy = os_policy
        if os_policy_id is not None:
            self.os_policy_id = os_policy_id
        if platform is not None:
            self.platform = platform
        if platform_type is not None:
            self.platform_type = platform_type
        if prefix_enabled is not None:
            self.prefix_enabled = prefix_enabled
        if status is not None:
            self.status = status
        if storage_pattern is not None:
            self.storage_pattern = storage_pattern

    @property
    def create(self):
        """Gets the create of this OSExternalStorageClass.  # noqa: E501


        :return: The create of this OSExternalStorageClass.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this OSExternalStorageClass.


        :param create: The create of this OSExternalStorageClass.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def class_id(self):
        """Gets the class_id of this OSExternalStorageClass.  # noqa: E501


        :return: The class_id of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._class_id

    @class_id.setter
    def class_id(self, class_id):
        """Sets the class_id of this OSExternalStorageClass.


        :param class_id: The class_id of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._class_id = class_id

    @property
    def class_status(self):
        """Gets the class_status of this OSExternalStorageClass.  # noqa: E501


        :return: The class_status of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._class_status

    @class_status.setter
    def class_status(self, class_status):
        """Sets the class_status of this OSExternalStorageClass.


        :param class_status: The class_status of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._class_status = class_status

    @property
    def description(self):
        """Gets the description of this OSExternalStorageClass.  # noqa: E501


        :return: The description of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this OSExternalStorageClass.


        :param description: The description of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def external_storage_platforms(self):
        """Gets the external_storage_platforms of this OSExternalStorageClass.  # noqa: E501


        :return: The external_storage_platforms of this OSExternalStorageClass.  # noqa: E501
        :rtype: list[OSExternalStoragePlatform]
        """
        return self._external_storage_platforms

    @external_storage_platforms.setter
    def external_storage_platforms(self, external_storage_platforms):
        """Sets the external_storage_platforms of this OSExternalStorageClass.


        :param external_storage_platforms: The external_storage_platforms of this OSExternalStorageClass.  # noqa: E501
        :type: list[OSExternalStoragePlatform]
        """

        self._external_storage_platforms = external_storage_platforms

    @property
    def id(self):
        """Gets the id of this OSExternalStorageClass.  # noqa: E501


        :return: The id of this OSExternalStorageClass.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this OSExternalStorageClass.


        :param id: The id of this OSExternalStorageClass.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def name(self):
        """Gets the name of this OSExternalStorageClass.  # noqa: E501


        :return: The name of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this OSExternalStorageClass.


        :param name: The name of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def os_policy(self):
        """Gets the os_policy of this OSExternalStorageClass.  # noqa: E501

        used for alert  # noqa: E501

        :return: The os_policy of this OSExternalStorageClass.  # noqa: E501
        :rtype: ObjectStoragePolicy
        """
        return self._os_policy

    @os_policy.setter
    def os_policy(self, os_policy):
        """Sets the os_policy of this OSExternalStorageClass.

        used for alert  # noqa: E501

        :param os_policy: The os_policy of this OSExternalStorageClass.  # noqa: E501
        :type: ObjectStoragePolicy
        """

        self._os_policy = os_policy

    @property
    def os_policy_id(self):
        """Gets the os_policy_id of this OSExternalStorageClass.  # noqa: E501


        :return: The os_policy_id of this OSExternalStorageClass.  # noqa: E501
        :rtype: int
        """
        return self._os_policy_id

    @os_policy_id.setter
    def os_policy_id(self, os_policy_id):
        """Sets the os_policy_id of this OSExternalStorageClass.


        :param os_policy_id: The os_policy_id of this OSExternalStorageClass.  # noqa: E501
        :type: int
        """

        self._os_policy_id = os_policy_id

    @property
    def platform(self):
        """Gets the platform of this OSExternalStorageClass.  # noqa: E501


        :return: The platform of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._platform

    @platform.setter
    def platform(self, platform):
        """Sets the platform of this OSExternalStorageClass.


        :param platform: The platform of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._platform = platform

    @property
    def platform_type(self):
        """Gets the platform_type of this OSExternalStorageClass.  # noqa: E501


        :return: The platform_type of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._platform_type

    @platform_type.setter
    def platform_type(self, platform_type):
        """Sets the platform_type of this OSExternalStorageClass.


        :param platform_type: The platform_type of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._platform_type = platform_type

    @property
    def prefix_enabled(self):
        """Gets the prefix_enabled of this OSExternalStorageClass.  # noqa: E501


        :return: The prefix_enabled of this OSExternalStorageClass.  # noqa: E501
        :rtype: bool
        """
        return self._prefix_enabled

    @prefix_enabled.setter
    def prefix_enabled(self, prefix_enabled):
        """Sets the prefix_enabled of this OSExternalStorageClass.


        :param prefix_enabled: The prefix_enabled of this OSExternalStorageClass.  # noqa: E501
        :type: bool
        """

        self._prefix_enabled = prefix_enabled

    @property
    def status(self):
        """Gets the status of this OSExternalStorageClass.  # noqa: E501


        :return: The status of this OSExternalStorageClass.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this OSExternalStorageClass.


        :param status: The status of this OSExternalStorageClass.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def storage_pattern(self):
        """Gets the storage_pattern of this OSExternalStorageClass.  # noqa: E501


        :return: The storage_pattern of this OSExternalStorageClass.  # noqa: E501
        :rtype: list[str]
        """
        return self._storage_pattern

    @storage_pattern.setter
    def storage_pattern(self, storage_pattern):
        """Sets the storage_pattern of this OSExternalStorageClass.


        :param storage_pattern: The storage_pattern of this OSExternalStorageClass.  # noqa: E501
        :type: list[str]
        """

        self._storage_pattern = storage_pattern

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
        if not isinstance(other, OSExternalStorageClass):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
