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

# from zstacklib.utils.xms_client.models.os_external_storage_bucket_info import OSExternalStorageBucketInfo  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.os_external_storage_class import OSExternalStorageClass  # noqa: F401,E501


class OSExternalStoragePlatform(object):
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
        'access_key': 'str',
        'authentication': 'str',
        'buckets': 'list[OSExternalStorageBucketInfo]',
        'connected': 'bool',
        'create': 'datetime',
        'endpoint': 'str',
        'host_style': 'str',
        'id': 'int',
        'name': 'str',
        'os_external_storage_class': 'OSExternalStorageClass',
        'region': 'str',
        'secret_key': 'str',
        'status': 'str',
        'uuid': 'str',
        'weight': 'int'
    }

    attribute_map = {
        'access_key': 'access_key',
        'authentication': 'authentication',
        'buckets': 'buckets',
        'connected': 'connected',
        'create': 'create',
        'endpoint': 'endpoint',
        'host_style': 'host_style',
        'id': 'id',
        'name': 'name',
        'os_external_storage_class': 'os_external_storage_class',
        'region': 'region',
        'secret_key': 'secret_key',
        'status': 'status',
        'uuid': 'uuid',
        'weight': 'weight'
    }

    def __init__(self, access_key=None, authentication=None, buckets=None, connected=None, create=None, endpoint=None, host_style=None, id=None, name=None, os_external_storage_class=None, region=None, secret_key=None, status=None, uuid=None, weight=None):  # noqa: E501
        """OSExternalStoragePlatform - a model defined in Swagger"""  # noqa: E501

        self._access_key = None
        self._authentication = None
        self._buckets = None
        self._connected = None
        self._create = None
        self._endpoint = None
        self._host_style = None
        self._id = None
        self._name = None
        self._os_external_storage_class = None
        self._region = None
        self._secret_key = None
        self._status = None
        self._uuid = None
        self._weight = None
        self.discriminator = None

        if access_key is not None:
            self.access_key = access_key
        if authentication is not None:
            self.authentication = authentication
        if buckets is not None:
            self.buckets = buckets
        if connected is not None:
            self.connected = connected
        if create is not None:
            self.create = create
        if endpoint is not None:
            self.endpoint = endpoint
        if host_style is not None:
            self.host_style = host_style
        if id is not None:
            self.id = id
        if name is not None:
            self.name = name
        if os_external_storage_class is not None:
            self.os_external_storage_class = os_external_storage_class
        if region is not None:
            self.region = region
        if secret_key is not None:
            self.secret_key = secret_key
        if status is not None:
            self.status = status
        if uuid is not None:
            self.uuid = uuid
        if weight is not None:
            self.weight = weight

    @property
    def access_key(self):
        """Gets the access_key of this OSExternalStoragePlatform.  # noqa: E501


        :return: The access_key of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._access_key

    @access_key.setter
    def access_key(self, access_key):
        """Sets the access_key of this OSExternalStoragePlatform.


        :param access_key: The access_key of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._access_key = access_key

    @property
    def authentication(self):
        """Gets the authentication of this OSExternalStoragePlatform.  # noqa: E501


        :return: The authentication of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._authentication

    @authentication.setter
    def authentication(self, authentication):
        """Sets the authentication of this OSExternalStoragePlatform.


        :param authentication: The authentication of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._authentication = authentication

    @property
    def buckets(self):
        """Gets the buckets of this OSExternalStoragePlatform.  # noqa: E501


        :return: The buckets of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: list[OSExternalStorageBucketInfo]
        """
        return self._buckets

    @buckets.setter
    def buckets(self, buckets):
        """Sets the buckets of this OSExternalStoragePlatform.


        :param buckets: The buckets of this OSExternalStoragePlatform.  # noqa: E501
        :type: list[OSExternalStorageBucketInfo]
        """

        self._buckets = buckets

    @property
    def connected(self):
        """Gets the connected of this OSExternalStoragePlatform.  # noqa: E501


        :return: The connected of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: bool
        """
        return self._connected

    @connected.setter
    def connected(self, connected):
        """Sets the connected of this OSExternalStoragePlatform.


        :param connected: The connected of this OSExternalStoragePlatform.  # noqa: E501
        :type: bool
        """

        self._connected = connected

    @property
    def create(self):
        """Gets the create of this OSExternalStoragePlatform.  # noqa: E501


        :return: The create of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this OSExternalStoragePlatform.


        :param create: The create of this OSExternalStoragePlatform.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def endpoint(self):
        """Gets the endpoint of this OSExternalStoragePlatform.  # noqa: E501


        :return: The endpoint of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._endpoint

    @endpoint.setter
    def endpoint(self, endpoint):
        """Sets the endpoint of this OSExternalStoragePlatform.


        :param endpoint: The endpoint of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._endpoint = endpoint

    @property
    def host_style(self):
        """Gets the host_style of this OSExternalStoragePlatform.  # noqa: E501


        :return: The host_style of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._host_style

    @host_style.setter
    def host_style(self, host_style):
        """Sets the host_style of this OSExternalStoragePlatform.


        :param host_style: The host_style of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._host_style = host_style

    @property
    def id(self):
        """Gets the id of this OSExternalStoragePlatform.  # noqa: E501


        :return: The id of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this OSExternalStoragePlatform.


        :param id: The id of this OSExternalStoragePlatform.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def name(self):
        """Gets the name of this OSExternalStoragePlatform.  # noqa: E501


        :return: The name of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this OSExternalStoragePlatform.


        :param name: The name of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def os_external_storage_class(self):
        """Gets the os_external_storage_class of this OSExternalStoragePlatform.  # noqa: E501

        used for alert  # noqa: E501

        :return: The os_external_storage_class of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: OSExternalStorageClass
        """
        return self._os_external_storage_class

    @os_external_storage_class.setter
    def os_external_storage_class(self, os_external_storage_class):
        """Sets the os_external_storage_class of this OSExternalStoragePlatform.

        used for alert  # noqa: E501

        :param os_external_storage_class: The os_external_storage_class of this OSExternalStoragePlatform.  # noqa: E501
        :type: OSExternalStorageClass
        """

        self._os_external_storage_class = os_external_storage_class

    @property
    def region(self):
        """Gets the region of this OSExternalStoragePlatform.  # noqa: E501


        :return: The region of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._region

    @region.setter
    def region(self, region):
        """Sets the region of this OSExternalStoragePlatform.


        :param region: The region of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._region = region

    @property
    def secret_key(self):
        """Gets the secret_key of this OSExternalStoragePlatform.  # noqa: E501


        :return: The secret_key of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._secret_key

    @secret_key.setter
    def secret_key(self, secret_key):
        """Sets the secret_key of this OSExternalStoragePlatform.


        :param secret_key: The secret_key of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._secret_key = secret_key

    @property
    def status(self):
        """Gets the status of this OSExternalStoragePlatform.  # noqa: E501


        :return: The status of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this OSExternalStoragePlatform.


        :param status: The status of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def uuid(self):
        """Gets the uuid of this OSExternalStoragePlatform.  # noqa: E501


        :return: The uuid of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: str
        """
        return self._uuid

    @uuid.setter
    def uuid(self, uuid):
        """Sets the uuid of this OSExternalStoragePlatform.


        :param uuid: The uuid of this OSExternalStoragePlatform.  # noqa: E501
        :type: str
        """

        self._uuid = uuid

    @property
    def weight(self):
        """Gets the weight of this OSExternalStoragePlatform.  # noqa: E501


        :return: The weight of this OSExternalStoragePlatform.  # noqa: E501
        :rtype: int
        """
        return self._weight

    @weight.setter
    def weight(self, weight):
        """Sets the weight of this OSExternalStoragePlatform.


        :param weight: The weight of this OSExternalStoragePlatform.  # noqa: E501
        :type: int
        """

        self._weight = weight

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
        if not isinstance(other, OSExternalStoragePlatform):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other