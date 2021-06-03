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

# from zstacklib.utils.xms_client.models.host_nestview import HostNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.os_search_engine_nestview import OSSearchEngineNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.os_search_gateway import OSSearchGateway  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.os_search_gateway_stat import OSSearchGatewayStat  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.pool_nestview import PoolNestview  # noqa: F401,E501


class OSSearchGatewayRecord(object):
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
        'action_status': 'str',
        'create': 'datetime',
        'host': 'HostNestview',
        'id': 'int',
        'pool': 'PoolNestview',
        'search_engine': 'OSSearchEngineNestview',
        'status': 'str',
        'update': 'datetime',
        'samples': 'list[OSSearchGatewayStat]'
    }

    attribute_map = {
        'action_status': 'action_status',
        'create': 'create',
        'host': 'host',
        'id': 'id',
        'pool': 'pool',
        'search_engine': 'search_engine',
        'status': 'status',
        'update': 'update',
        'samples': 'samples'
    }

    def __init__(self, action_status=None, create=None, host=None, id=None, pool=None, search_engine=None, status=None, update=None, samples=None):  # noqa: E501
        """OSSearchGatewayRecord - a model defined in Swagger"""  # noqa: E501

        self._action_status = None
        self._create = None
        self._host = None
        self._id = None
        self._pool = None
        self._search_engine = None
        self._status = None
        self._update = None
        self._samples = None
        self.discriminator = None

        if action_status is not None:
            self.action_status = action_status
        if create is not None:
            self.create = create
        if host is not None:
            self.host = host
        if id is not None:
            self.id = id
        if pool is not None:
            self.pool = pool
        if search_engine is not None:
            self.search_engine = search_engine
        if status is not None:
            self.status = status
        if update is not None:
            self.update = update
        if samples is not None:
            self.samples = samples

    @property
    def action_status(self):
        """Gets the action_status of this OSSearchGatewayRecord.  # noqa: E501


        :return: The action_status of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: str
        """
        return self._action_status

    @action_status.setter
    def action_status(self, action_status):
        """Sets the action_status of this OSSearchGatewayRecord.


        :param action_status: The action_status of this OSSearchGatewayRecord.  # noqa: E501
        :type: str
        """

        self._action_status = action_status

    @property
    def create(self):
        """Gets the create of this OSSearchGatewayRecord.  # noqa: E501


        :return: The create of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this OSSearchGatewayRecord.


        :param create: The create of this OSSearchGatewayRecord.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def host(self):
        """Gets the host of this OSSearchGatewayRecord.  # noqa: E501


        :return: The host of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: HostNestview
        """
        return self._host

    @host.setter
    def host(self, host):
        """Sets the host of this OSSearchGatewayRecord.


        :param host: The host of this OSSearchGatewayRecord.  # noqa: E501
        :type: HostNestview
        """

        self._host = host

    @property
    def id(self):
        """Gets the id of this OSSearchGatewayRecord.  # noqa: E501


        :return: The id of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this OSSearchGatewayRecord.


        :param id: The id of this OSSearchGatewayRecord.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def pool(self):
        """Gets the pool of this OSSearchGatewayRecord.  # noqa: E501


        :return: The pool of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: PoolNestview
        """
        return self._pool

    @pool.setter
    def pool(self, pool):
        """Sets the pool of this OSSearchGatewayRecord.


        :param pool: The pool of this OSSearchGatewayRecord.  # noqa: E501
        :type: PoolNestview
        """

        self._pool = pool

    @property
    def search_engine(self):
        """Gets the search_engine of this OSSearchGatewayRecord.  # noqa: E501


        :return: The search_engine of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: OSSearchEngineNestview
        """
        return self._search_engine

    @search_engine.setter
    def search_engine(self, search_engine):
        """Sets the search_engine of this OSSearchGatewayRecord.


        :param search_engine: The search_engine of this OSSearchGatewayRecord.  # noqa: E501
        :type: OSSearchEngineNestview
        """

        self._search_engine = search_engine

    @property
    def status(self):
        """Gets the status of this OSSearchGatewayRecord.  # noqa: E501


        :return: The status of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this OSSearchGatewayRecord.


        :param status: The status of this OSSearchGatewayRecord.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def update(self):
        """Gets the update of this OSSearchGatewayRecord.  # noqa: E501


        :return: The update of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this OSSearchGatewayRecord.


        :param update: The update of this OSSearchGatewayRecord.  # noqa: E501
        :type: datetime
        """

        self._update = update

    @property
    def samples(self):
        """Gets the samples of this OSSearchGatewayRecord.  # noqa: E501


        :return: The samples of this OSSearchGatewayRecord.  # noqa: E501
        :rtype: list[OSSearchGatewayStat]
        """
        return self._samples

    @samples.setter
    def samples(self, samples):
        """Sets the samples of this OSSearchGatewayRecord.


        :param samples: The samples of this OSSearchGatewayRecord.  # noqa: E501
        :type: list[OSSearchGatewayStat]
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
        if not isinstance(other, OSSearchGatewayRecord):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
