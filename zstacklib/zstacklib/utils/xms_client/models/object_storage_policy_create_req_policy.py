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

# from zstacklib.utils.xms_client.models.object_storage_policy_create_req_policy_storage_classes_elt import ObjectStoragePolicyCreateReqPolicyStorageClassesElt  # noqa: F401,E501


class ObjectStoragePolicyCreateReqPolicy(object):
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
        'cache_pool_id': 'int',
        'compress': 'bool',
        'crypto': 'bool',
        'deduplication': 'bool',
        'description': 'str',
        'index_pool_id': 'int',
        'name': 'str',
        'shared': 'bool',
        'storage_classes': 'list[ObjectStoragePolicyCreateReqPolicyStorageClassesElt]'
    }

    attribute_map = {
        'cache_pool_id': 'cache_pool_id',
        'compress': 'compress',
        'crypto': 'crypto',
        'deduplication': 'deduplication',
        'description': 'description',
        'index_pool_id': 'index_pool_id',
        'name': 'name',
        'shared': 'shared',
        'storage_classes': 'storage_classes'
    }

    def __init__(self, cache_pool_id=None, compress=None, crypto=None, deduplication=None, description=None, index_pool_id=None, name=None, shared=None, storage_classes=None):  # noqa: E501
        """ObjectStoragePolicyCreateReqPolicy - a model defined in Swagger"""  # noqa: E501

        self._cache_pool_id = None
        self._compress = None
        self._crypto = None
        self._deduplication = None
        self._description = None
        self._index_pool_id = None
        self._name = None
        self._shared = None
        self._storage_classes = None
        self.discriminator = None

        if cache_pool_id is not None:
            self.cache_pool_id = cache_pool_id
        if compress is not None:
            self.compress = compress
        if crypto is not None:
            self.crypto = crypto
        if deduplication is not None:
            self.deduplication = deduplication
        if description is not None:
            self.description = description
        self.index_pool_id = index_pool_id
        self.name = name
        if shared is not None:
            self.shared = shared
        self.storage_classes = storage_classes

    @property
    def cache_pool_id(self):
        """Gets the cache_pool_id of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The cache_pool_id of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: int
        """
        return self._cache_pool_id

    @cache_pool_id.setter
    def cache_pool_id(self, cache_pool_id):
        """Sets the cache_pool_id of this ObjectStoragePolicyCreateReqPolicy.


        :param cache_pool_id: The cache_pool_id of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: int
        """

        self._cache_pool_id = cache_pool_id

    @property
    def compress(self):
        """Gets the compress of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The compress of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: bool
        """
        return self._compress

    @compress.setter
    def compress(self, compress):
        """Sets the compress of this ObjectStoragePolicyCreateReqPolicy.


        :param compress: The compress of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: bool
        """

        self._compress = compress

    @property
    def crypto(self):
        """Gets the crypto of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The crypto of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: bool
        """
        return self._crypto

    @crypto.setter
    def crypto(self, crypto):
        """Sets the crypto of this ObjectStoragePolicyCreateReqPolicy.


        :param crypto: The crypto of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: bool
        """

        self._crypto = crypto

    @property
    def deduplication(self):
        """Gets the deduplication of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The deduplication of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: bool
        """
        return self._deduplication

    @deduplication.setter
    def deduplication(self, deduplication):
        """Sets the deduplication of this ObjectStoragePolicyCreateReqPolicy.


        :param deduplication: The deduplication of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: bool
        """

        self._deduplication = deduplication

    @property
    def description(self):
        """Gets the description of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The description of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this ObjectStoragePolicyCreateReqPolicy.


        :param description: The description of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def index_pool_id(self):
        """Gets the index_pool_id of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The index_pool_id of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: int
        """
        return self._index_pool_id

    @index_pool_id.setter
    def index_pool_id(self, index_pool_id):
        """Sets the index_pool_id of this ObjectStoragePolicyCreateReqPolicy.


        :param index_pool_id: The index_pool_id of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: int
        """
        if index_pool_id is None:
            raise ValueError("Invalid value for `index_pool_id`, must not be `None`")  # noqa: E501

        self._index_pool_id = index_pool_id

    @property
    def name(self):
        """Gets the name of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The name of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this ObjectStoragePolicyCreateReqPolicy.


        :param name: The name of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: str
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def shared(self):
        """Gets the shared of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The shared of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: bool
        """
        return self._shared

    @shared.setter
    def shared(self, shared):
        """Sets the shared of this ObjectStoragePolicyCreateReqPolicy.


        :param shared: The shared of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: bool
        """

        self._shared = shared

    @property
    def storage_classes(self):
        """Gets the storage_classes of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501


        :return: The storage_classes of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :rtype: list[ObjectStoragePolicyCreateReqPolicyStorageClassesElt]
        """
        return self._storage_classes

    @storage_classes.setter
    def storage_classes(self, storage_classes):
        """Sets the storage_classes of this ObjectStoragePolicyCreateReqPolicy.


        :param storage_classes: The storage_classes of this ObjectStoragePolicyCreateReqPolicy.  # noqa: E501
        :type: list[ObjectStoragePolicyCreateReqPolicyStorageClassesElt]
        """
        if storage_classes is None:
            raise ValueError("Invalid value for `storage_classes`, must not be `None`")  # noqa: E501

        self._storage_classes = storage_classes

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
        if not isinstance(other, ObjectStoragePolicyCreateReqPolicy):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
