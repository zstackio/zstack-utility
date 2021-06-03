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

# from zstacklib.utils.xms_client.models.object_storage_policy_nestview import ObjectStoragePolicyNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.object_storage_user import ObjectStorageUser  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.object_storage_user_nestview import ObjectStorageUserNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.object_storage_user_stat import ObjectStorageUserStat  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.os_user_properties import OSUserProperties  # noqa: F401,E501


class ObjectStorageUserRecord(object):
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
        'bucket_num': 'int',
        'bucket_quota_max_objects': 'int',
        'bucket_quota_max_size': 'int',
        'create': 'datetime',
        'display_name': 'str',
        'email': 'str',
        'external_bucket_quota_max_objects': 'int',
        'external_bucket_quota_max_size': 'int',
        'external_user_quota_max_objects': 'int',
        'external_user_quota_max_size': 'int',
        'id': 'int',
        'local_bucket_quota_max_objects': 'int',
        'local_bucket_quota_max_size': 'int',
        'local_user_quota_max_objects': 'int',
        'local_user_quota_max_size': 'int',
        'location_constraint_enabled': 'bool',
        'max_buckets': 'int',
        'name': 'str',
        'op_mask': 'str',
        'parent': 'ObjectStorageUserNestview',
        'policy': 'ObjectStoragePolicyNestview',
        'policy_polling_enabled': 'bool',
        'properties': 'OSUserProperties',
        'status': 'str',
        'suspended': 'bool',
        'update': 'datetime',
        'user_quota_max_objects': 'int',
        'user_quota_max_size': 'int',
        'samples': 'list[ObjectStorageUserStat]'
    }

    attribute_map = {
        'bucket_num': 'bucket_num',
        'bucket_quota_max_objects': 'bucket_quota_max_objects',
        'bucket_quota_max_size': 'bucket_quota_max_size',
        'create': 'create',
        'display_name': 'display_name',
        'email': 'email',
        'external_bucket_quota_max_objects': 'external_bucket_quota_max_objects',
        'external_bucket_quota_max_size': 'external_bucket_quota_max_size',
        'external_user_quota_max_objects': 'external_user_quota_max_objects',
        'external_user_quota_max_size': 'external_user_quota_max_size',
        'id': 'id',
        'local_bucket_quota_max_objects': 'local_bucket_quota_max_objects',
        'local_bucket_quota_max_size': 'local_bucket_quota_max_size',
        'local_user_quota_max_objects': 'local_user_quota_max_objects',
        'local_user_quota_max_size': 'local_user_quota_max_size',
        'location_constraint_enabled': 'location_constraint_enabled',
        'max_buckets': 'max_buckets',
        'name': 'name',
        'op_mask': 'op_mask',
        'parent': 'parent',
        'policy': 'policy',
        'policy_polling_enabled': 'policy_polling_enabled',
        'properties': 'properties',
        'status': 'status',
        'suspended': 'suspended',
        'update': 'update',
        'user_quota_max_objects': 'user_quota_max_objects',
        'user_quota_max_size': 'user_quota_max_size',
        'samples': 'samples'
    }

    def __init__(self, bucket_num=None, bucket_quota_max_objects=None, bucket_quota_max_size=None, create=None, display_name=None, email=None, external_bucket_quota_max_objects=None, external_bucket_quota_max_size=None, external_user_quota_max_objects=None, external_user_quota_max_size=None, id=None, local_bucket_quota_max_objects=None, local_bucket_quota_max_size=None, local_user_quota_max_objects=None, local_user_quota_max_size=None, location_constraint_enabled=None, max_buckets=None, name=None, op_mask=None, parent=None, policy=None, policy_polling_enabled=None, properties=None, status=None, suspended=None, update=None, user_quota_max_objects=None, user_quota_max_size=None, samples=None):  # noqa: E501
        """ObjectStorageUserRecord - a model defined in Swagger"""  # noqa: E501

        self._bucket_num = None
        self._bucket_quota_max_objects = None
        self._bucket_quota_max_size = None
        self._create = None
        self._display_name = None
        self._email = None
        self._external_bucket_quota_max_objects = None
        self._external_bucket_quota_max_size = None
        self._external_user_quota_max_objects = None
        self._external_user_quota_max_size = None
        self._id = None
        self._local_bucket_quota_max_objects = None
        self._local_bucket_quota_max_size = None
        self._local_user_quota_max_objects = None
        self._local_user_quota_max_size = None
        self._location_constraint_enabled = None
        self._max_buckets = None
        self._name = None
        self._op_mask = None
        self._parent = None
        self._policy = None
        self._policy_polling_enabled = None
        self._properties = None
        self._status = None
        self._suspended = None
        self._update = None
        self._user_quota_max_objects = None
        self._user_quota_max_size = None
        self._samples = None
        self.discriminator = None

        if bucket_num is not None:
            self.bucket_num = bucket_num
        if bucket_quota_max_objects is not None:
            self.bucket_quota_max_objects = bucket_quota_max_objects
        if bucket_quota_max_size is not None:
            self.bucket_quota_max_size = bucket_quota_max_size
        if create is not None:
            self.create = create
        if display_name is not None:
            self.display_name = display_name
        if email is not None:
            self.email = email
        if external_bucket_quota_max_objects is not None:
            self.external_bucket_quota_max_objects = external_bucket_quota_max_objects
        if external_bucket_quota_max_size is not None:
            self.external_bucket_quota_max_size = external_bucket_quota_max_size
        if external_user_quota_max_objects is not None:
            self.external_user_quota_max_objects = external_user_quota_max_objects
        if external_user_quota_max_size is not None:
            self.external_user_quota_max_size = external_user_quota_max_size
        if id is not None:
            self.id = id
        if local_bucket_quota_max_objects is not None:
            self.local_bucket_quota_max_objects = local_bucket_quota_max_objects
        if local_bucket_quota_max_size is not None:
            self.local_bucket_quota_max_size = local_bucket_quota_max_size
        if local_user_quota_max_objects is not None:
            self.local_user_quota_max_objects = local_user_quota_max_objects
        if local_user_quota_max_size is not None:
            self.local_user_quota_max_size = local_user_quota_max_size
        if location_constraint_enabled is not None:
            self.location_constraint_enabled = location_constraint_enabled
        if max_buckets is not None:
            self.max_buckets = max_buckets
        if name is not None:
            self.name = name
        if op_mask is not None:
            self.op_mask = op_mask
        if parent is not None:
            self.parent = parent
        if policy is not None:
            self.policy = policy
        if policy_polling_enabled is not None:
            self.policy_polling_enabled = policy_polling_enabled
        if properties is not None:
            self.properties = properties
        if status is not None:
            self.status = status
        if suspended is not None:
            self.suspended = suspended
        if update is not None:
            self.update = update
        if user_quota_max_objects is not None:
            self.user_quota_max_objects = user_quota_max_objects
        if user_quota_max_size is not None:
            self.user_quota_max_size = user_quota_max_size
        if samples is not None:
            self.samples = samples

    @property
    def bucket_num(self):
        """Gets the bucket_num of this ObjectStorageUserRecord.  # noqa: E501


        :return: The bucket_num of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._bucket_num

    @bucket_num.setter
    def bucket_num(self, bucket_num):
        """Sets the bucket_num of this ObjectStorageUserRecord.


        :param bucket_num: The bucket_num of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._bucket_num = bucket_num

    @property
    def bucket_quota_max_objects(self):
        """Gets the bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501


        :return: The bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._bucket_quota_max_objects

    @bucket_quota_max_objects.setter
    def bucket_quota_max_objects(self, bucket_quota_max_objects):
        """Sets the bucket_quota_max_objects of this ObjectStorageUserRecord.


        :param bucket_quota_max_objects: The bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._bucket_quota_max_objects = bucket_quota_max_objects

    @property
    def bucket_quota_max_size(self):
        """Gets the bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501


        :return: The bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._bucket_quota_max_size

    @bucket_quota_max_size.setter
    def bucket_quota_max_size(self, bucket_quota_max_size):
        """Sets the bucket_quota_max_size of this ObjectStorageUserRecord.


        :param bucket_quota_max_size: The bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._bucket_quota_max_size = bucket_quota_max_size

    @property
    def create(self):
        """Gets the create of this ObjectStorageUserRecord.  # noqa: E501


        :return: The create of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this ObjectStorageUserRecord.


        :param create: The create of this ObjectStorageUserRecord.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def display_name(self):
        """Gets the display_name of this ObjectStorageUserRecord.  # noqa: E501


        :return: The display_name of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: str
        """
        return self._display_name

    @display_name.setter
    def display_name(self, display_name):
        """Sets the display_name of this ObjectStorageUserRecord.


        :param display_name: The display_name of this ObjectStorageUserRecord.  # noqa: E501
        :type: str
        """

        self._display_name = display_name

    @property
    def email(self):
        """Gets the email of this ObjectStorageUserRecord.  # noqa: E501


        :return: The email of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: str
        """
        return self._email

    @email.setter
    def email(self, email):
        """Sets the email of this ObjectStorageUserRecord.


        :param email: The email of this ObjectStorageUserRecord.  # noqa: E501
        :type: str
        """

        self._email = email

    @property
    def external_bucket_quota_max_objects(self):
        """Gets the external_bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501


        :return: The external_bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._external_bucket_quota_max_objects

    @external_bucket_quota_max_objects.setter
    def external_bucket_quota_max_objects(self, external_bucket_quota_max_objects):
        """Sets the external_bucket_quota_max_objects of this ObjectStorageUserRecord.


        :param external_bucket_quota_max_objects: The external_bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._external_bucket_quota_max_objects = external_bucket_quota_max_objects

    @property
    def external_bucket_quota_max_size(self):
        """Gets the external_bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501


        :return: The external_bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._external_bucket_quota_max_size

    @external_bucket_quota_max_size.setter
    def external_bucket_quota_max_size(self, external_bucket_quota_max_size):
        """Sets the external_bucket_quota_max_size of this ObjectStorageUserRecord.


        :param external_bucket_quota_max_size: The external_bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._external_bucket_quota_max_size = external_bucket_quota_max_size

    @property
    def external_user_quota_max_objects(self):
        """Gets the external_user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501


        :return: The external_user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._external_user_quota_max_objects

    @external_user_quota_max_objects.setter
    def external_user_quota_max_objects(self, external_user_quota_max_objects):
        """Sets the external_user_quota_max_objects of this ObjectStorageUserRecord.


        :param external_user_quota_max_objects: The external_user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._external_user_quota_max_objects = external_user_quota_max_objects

    @property
    def external_user_quota_max_size(self):
        """Gets the external_user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501


        :return: The external_user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._external_user_quota_max_size

    @external_user_quota_max_size.setter
    def external_user_quota_max_size(self, external_user_quota_max_size):
        """Sets the external_user_quota_max_size of this ObjectStorageUserRecord.


        :param external_user_quota_max_size: The external_user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._external_user_quota_max_size = external_user_quota_max_size

    @property
    def id(self):
        """Gets the id of this ObjectStorageUserRecord.  # noqa: E501


        :return: The id of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this ObjectStorageUserRecord.


        :param id: The id of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def local_bucket_quota_max_objects(self):
        """Gets the local_bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501


        :return: The local_bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._local_bucket_quota_max_objects

    @local_bucket_quota_max_objects.setter
    def local_bucket_quota_max_objects(self, local_bucket_quota_max_objects):
        """Sets the local_bucket_quota_max_objects of this ObjectStorageUserRecord.


        :param local_bucket_quota_max_objects: The local_bucket_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._local_bucket_quota_max_objects = local_bucket_quota_max_objects

    @property
    def local_bucket_quota_max_size(self):
        """Gets the local_bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501


        :return: The local_bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._local_bucket_quota_max_size

    @local_bucket_quota_max_size.setter
    def local_bucket_quota_max_size(self, local_bucket_quota_max_size):
        """Sets the local_bucket_quota_max_size of this ObjectStorageUserRecord.


        :param local_bucket_quota_max_size: The local_bucket_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._local_bucket_quota_max_size = local_bucket_quota_max_size

    @property
    def local_user_quota_max_objects(self):
        """Gets the local_user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501


        :return: The local_user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._local_user_quota_max_objects

    @local_user_quota_max_objects.setter
    def local_user_quota_max_objects(self, local_user_quota_max_objects):
        """Sets the local_user_quota_max_objects of this ObjectStorageUserRecord.


        :param local_user_quota_max_objects: The local_user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._local_user_quota_max_objects = local_user_quota_max_objects

    @property
    def local_user_quota_max_size(self):
        """Gets the local_user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501


        :return: The local_user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._local_user_quota_max_size

    @local_user_quota_max_size.setter
    def local_user_quota_max_size(self, local_user_quota_max_size):
        """Sets the local_user_quota_max_size of this ObjectStorageUserRecord.


        :param local_user_quota_max_size: The local_user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._local_user_quota_max_size = local_user_quota_max_size

    @property
    def location_constraint_enabled(self):
        """Gets the location_constraint_enabled of this ObjectStorageUserRecord.  # noqa: E501


        :return: The location_constraint_enabled of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: bool
        """
        return self._location_constraint_enabled

    @location_constraint_enabled.setter
    def location_constraint_enabled(self, location_constraint_enabled):
        """Sets the location_constraint_enabled of this ObjectStorageUserRecord.


        :param location_constraint_enabled: The location_constraint_enabled of this ObjectStorageUserRecord.  # noqa: E501
        :type: bool
        """

        self._location_constraint_enabled = location_constraint_enabled

    @property
    def max_buckets(self):
        """Gets the max_buckets of this ObjectStorageUserRecord.  # noqa: E501


        :return: The max_buckets of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._max_buckets

    @max_buckets.setter
    def max_buckets(self, max_buckets):
        """Sets the max_buckets of this ObjectStorageUserRecord.


        :param max_buckets: The max_buckets of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._max_buckets = max_buckets

    @property
    def name(self):
        """Gets the name of this ObjectStorageUserRecord.  # noqa: E501


        :return: The name of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this ObjectStorageUserRecord.


        :param name: The name of this ObjectStorageUserRecord.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def op_mask(self):
        """Gets the op_mask of this ObjectStorageUserRecord.  # noqa: E501


        :return: The op_mask of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: str
        """
        return self._op_mask

    @op_mask.setter
    def op_mask(self, op_mask):
        """Sets the op_mask of this ObjectStorageUserRecord.


        :param op_mask: The op_mask of this ObjectStorageUserRecord.  # noqa: E501
        :type: str
        """

        self._op_mask = op_mask

    @property
    def parent(self):
        """Gets the parent of this ObjectStorageUserRecord.  # noqa: E501


        :return: The parent of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: ObjectStorageUserNestview
        """
        return self._parent

    @parent.setter
    def parent(self, parent):
        """Sets the parent of this ObjectStorageUserRecord.


        :param parent: The parent of this ObjectStorageUserRecord.  # noqa: E501
        :type: ObjectStorageUserNestview
        """

        self._parent = parent

    @property
    def policy(self):
        """Gets the policy of this ObjectStorageUserRecord.  # noqa: E501


        :return: The policy of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: ObjectStoragePolicyNestview
        """
        return self._policy

    @policy.setter
    def policy(self, policy):
        """Sets the policy of this ObjectStorageUserRecord.


        :param policy: The policy of this ObjectStorageUserRecord.  # noqa: E501
        :type: ObjectStoragePolicyNestview
        """

        self._policy = policy

    @property
    def policy_polling_enabled(self):
        """Gets the policy_polling_enabled of this ObjectStorageUserRecord.  # noqa: E501


        :return: The policy_polling_enabled of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: bool
        """
        return self._policy_polling_enabled

    @policy_polling_enabled.setter
    def policy_polling_enabled(self, policy_polling_enabled):
        """Sets the policy_polling_enabled of this ObjectStorageUserRecord.


        :param policy_polling_enabled: The policy_polling_enabled of this ObjectStorageUserRecord.  # noqa: E501
        :type: bool
        """

        self._policy_polling_enabled = policy_polling_enabled

    @property
    def properties(self):
        """Gets the properties of this ObjectStorageUserRecord.  # noqa: E501


        :return: The properties of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: OSUserProperties
        """
        return self._properties

    @properties.setter
    def properties(self, properties):
        """Sets the properties of this ObjectStorageUserRecord.


        :param properties: The properties of this ObjectStorageUserRecord.  # noqa: E501
        :type: OSUserProperties
        """

        self._properties = properties

    @property
    def status(self):
        """Gets the status of this ObjectStorageUserRecord.  # noqa: E501


        :return: The status of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this ObjectStorageUserRecord.


        :param status: The status of this ObjectStorageUserRecord.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def suspended(self):
        """Gets the suspended of this ObjectStorageUserRecord.  # noqa: E501


        :return: The suspended of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: bool
        """
        return self._suspended

    @suspended.setter
    def suspended(self, suspended):
        """Sets the suspended of this ObjectStorageUserRecord.


        :param suspended: The suspended of this ObjectStorageUserRecord.  # noqa: E501
        :type: bool
        """

        self._suspended = suspended

    @property
    def update(self):
        """Gets the update of this ObjectStorageUserRecord.  # noqa: E501


        :return: The update of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this ObjectStorageUserRecord.


        :param update: The update of this ObjectStorageUserRecord.  # noqa: E501
        :type: datetime
        """

        self._update = update

    @property
    def user_quota_max_objects(self):
        """Gets the user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501


        :return: The user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._user_quota_max_objects

    @user_quota_max_objects.setter
    def user_quota_max_objects(self, user_quota_max_objects):
        """Sets the user_quota_max_objects of this ObjectStorageUserRecord.


        :param user_quota_max_objects: The user_quota_max_objects of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._user_quota_max_objects = user_quota_max_objects

    @property
    def user_quota_max_size(self):
        """Gets the user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501


        :return: The user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: int
        """
        return self._user_quota_max_size

    @user_quota_max_size.setter
    def user_quota_max_size(self, user_quota_max_size):
        """Sets the user_quota_max_size of this ObjectStorageUserRecord.


        :param user_quota_max_size: The user_quota_max_size of this ObjectStorageUserRecord.  # noqa: E501
        :type: int
        """

        self._user_quota_max_size = user_quota_max_size

    @property
    def samples(self):
        """Gets the samples of this ObjectStorageUserRecord.  # noqa: E501


        :return: The samples of this ObjectStorageUserRecord.  # noqa: E501
        :rtype: list[ObjectStorageUserStat]
        """
        return self._samples

    @samples.setter
    def samples(self, samples):
        """Sets the samples of this ObjectStorageUserRecord.


        :param samples: The samples of this ObjectStorageUserRecord.  # noqa: E501
        :type: list[ObjectStorageUserStat]
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
        if not isinstance(other, ObjectStorageUserRecord):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
