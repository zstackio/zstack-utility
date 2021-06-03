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

# from zstacklib.utils.xms_client.models.remote_cluster_nestview import RemoteClusterNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.s3_load_balancer_group_nestview import S3LoadBalancerGroupNestview  # noqa: F401,E501


class ObjectStorageZone(object):
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
        'alias': 'str',
        'connected': 'bool',
        'create': 'datetime',
        'endpoints': 'list[str]',
        'epoch_uuid': 'str',
        'id': 'int',
        'local': 'bool',
        'master': 'bool',
        'name': 'str',
        'realm_name': 'str',
        'remote_cluster': 'RemoteClusterNestview',
        's3_load_balancer_group': 'S3LoadBalancerGroupNestview',
        'search_zone_uuid': 'str',
        'status': 'str',
        'switch_status': 'str',
        'system_access_key': 'str',
        'system_secret_key': 'str',
        'system_user': 'str',
        'tier_type': 'str',
        'update': 'datetime',
        'uuid': 'str',
        'zonegroup_name': 'str'
    }

    attribute_map = {
        'alias': 'alias',
        'connected': 'connected',
        'create': 'create',
        'endpoints': 'endpoints',
        'epoch_uuid': 'epoch_uuid',
        'id': 'id',
        'local': 'local',
        'master': 'master',
        'name': 'name',
        'realm_name': 'realm_name',
        'remote_cluster': 'remote_cluster',
        's3_load_balancer_group': 's3_load_balancer_group',
        'search_zone_uuid': 'search_zone_uuid',
        'status': 'status',
        'switch_status': 'switch_status',
        'system_access_key': 'system_access_key',
        'system_secret_key': 'system_secret_key',
        'system_user': 'system_user',
        'tier_type': 'tier_type',
        'update': 'update',
        'uuid': 'uuid',
        'zonegroup_name': 'zonegroup_name'
    }

    def __init__(self, alias=None, connected=None, create=None, endpoints=None, epoch_uuid=None, id=None, local=None, master=None, name=None, realm_name=None, remote_cluster=None, s3_load_balancer_group=None, search_zone_uuid=None, status=None, switch_status=None, system_access_key=None, system_secret_key=None, system_user=None, tier_type=None, update=None, uuid=None, zonegroup_name=None):  # noqa: E501
        """ObjectStorageZone - a model defined in Swagger"""  # noqa: E501

        self._alias = None
        self._connected = None
        self._create = None
        self._endpoints = None
        self._epoch_uuid = None
        self._id = None
        self._local = None
        self._master = None
        self._name = None
        self._realm_name = None
        self._remote_cluster = None
        self._s3_load_balancer_group = None
        self._search_zone_uuid = None
        self._status = None
        self._switch_status = None
        self._system_access_key = None
        self._system_secret_key = None
        self._system_user = None
        self._tier_type = None
        self._update = None
        self._uuid = None
        self._zonegroup_name = None
        self.discriminator = None

        if alias is not None:
            self.alias = alias
        if connected is not None:
            self.connected = connected
        if create is not None:
            self.create = create
        if endpoints is not None:
            self.endpoints = endpoints
        if epoch_uuid is not None:
            self.epoch_uuid = epoch_uuid
        if id is not None:
            self.id = id
        if local is not None:
            self.local = local
        if master is not None:
            self.master = master
        if name is not None:
            self.name = name
        if realm_name is not None:
            self.realm_name = realm_name
        if remote_cluster is not None:
            self.remote_cluster = remote_cluster
        if s3_load_balancer_group is not None:
            self.s3_load_balancer_group = s3_load_balancer_group
        if search_zone_uuid is not None:
            self.search_zone_uuid = search_zone_uuid
        if status is not None:
            self.status = status
        if switch_status is not None:
            self.switch_status = switch_status
        if system_access_key is not None:
            self.system_access_key = system_access_key
        if system_secret_key is not None:
            self.system_secret_key = system_secret_key
        if system_user is not None:
            self.system_user = system_user
        if tier_type is not None:
            self.tier_type = tier_type
        if update is not None:
            self.update = update
        if uuid is not None:
            self.uuid = uuid
        if zonegroup_name is not None:
            self.zonegroup_name = zonegroup_name

    @property
    def alias(self):
        """Gets the alias of this ObjectStorageZone.  # noqa: E501


        :return: The alias of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._alias

    @alias.setter
    def alias(self, alias):
        """Sets the alias of this ObjectStorageZone.


        :param alias: The alias of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._alias = alias

    @property
    def connected(self):
        """Gets the connected of this ObjectStorageZone.  # noqa: E501


        :return: The connected of this ObjectStorageZone.  # noqa: E501
        :rtype: bool
        """
        return self._connected

    @connected.setter
    def connected(self, connected):
        """Sets the connected of this ObjectStorageZone.


        :param connected: The connected of this ObjectStorageZone.  # noqa: E501
        :type: bool
        """

        self._connected = connected

    @property
    def create(self):
        """Gets the create of this ObjectStorageZone.  # noqa: E501


        :return: The create of this ObjectStorageZone.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this ObjectStorageZone.


        :param create: The create of this ObjectStorageZone.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def endpoints(self):
        """Gets the endpoints of this ObjectStorageZone.  # noqa: E501


        :return: The endpoints of this ObjectStorageZone.  # noqa: E501
        :rtype: list[str]
        """
        return self._endpoints

    @endpoints.setter
    def endpoints(self, endpoints):
        """Sets the endpoints of this ObjectStorageZone.


        :param endpoints: The endpoints of this ObjectStorageZone.  # noqa: E501
        :type: list[str]
        """

        self._endpoints = endpoints

    @property
    def epoch_uuid(self):
        """Gets the epoch_uuid of this ObjectStorageZone.  # noqa: E501


        :return: The epoch_uuid of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._epoch_uuid

    @epoch_uuid.setter
    def epoch_uuid(self, epoch_uuid):
        """Sets the epoch_uuid of this ObjectStorageZone.


        :param epoch_uuid: The epoch_uuid of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._epoch_uuid = epoch_uuid

    @property
    def id(self):
        """Gets the id of this ObjectStorageZone.  # noqa: E501


        :return: The id of this ObjectStorageZone.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this ObjectStorageZone.


        :param id: The id of this ObjectStorageZone.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def local(self):
        """Gets the local of this ObjectStorageZone.  # noqa: E501


        :return: The local of this ObjectStorageZone.  # noqa: E501
        :rtype: bool
        """
        return self._local

    @local.setter
    def local(self, local):
        """Sets the local of this ObjectStorageZone.


        :param local: The local of this ObjectStorageZone.  # noqa: E501
        :type: bool
        """

        self._local = local

    @property
    def master(self):
        """Gets the master of this ObjectStorageZone.  # noqa: E501


        :return: The master of this ObjectStorageZone.  # noqa: E501
        :rtype: bool
        """
        return self._master

    @master.setter
    def master(self, master):
        """Sets the master of this ObjectStorageZone.


        :param master: The master of this ObjectStorageZone.  # noqa: E501
        :type: bool
        """

        self._master = master

    @property
    def name(self):
        """Gets the name of this ObjectStorageZone.  # noqa: E501


        :return: The name of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this ObjectStorageZone.


        :param name: The name of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def realm_name(self):
        """Gets the realm_name of this ObjectStorageZone.  # noqa: E501


        :return: The realm_name of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._realm_name

    @realm_name.setter
    def realm_name(self, realm_name):
        """Sets the realm_name of this ObjectStorageZone.


        :param realm_name: The realm_name of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._realm_name = realm_name

    @property
    def remote_cluster(self):
        """Gets the remote_cluster of this ObjectStorageZone.  # noqa: E501


        :return: The remote_cluster of this ObjectStorageZone.  # noqa: E501
        :rtype: RemoteClusterNestview
        """
        return self._remote_cluster

    @remote_cluster.setter
    def remote_cluster(self, remote_cluster):
        """Sets the remote_cluster of this ObjectStorageZone.


        :param remote_cluster: The remote_cluster of this ObjectStorageZone.  # noqa: E501
        :type: RemoteClusterNestview
        """

        self._remote_cluster = remote_cluster

    @property
    def s3_load_balancer_group(self):
        """Gets the s3_load_balancer_group of this ObjectStorageZone.  # noqa: E501


        :return: The s3_load_balancer_group of this ObjectStorageZone.  # noqa: E501
        :rtype: S3LoadBalancerGroupNestview
        """
        return self._s3_load_balancer_group

    @s3_load_balancer_group.setter
    def s3_load_balancer_group(self, s3_load_balancer_group):
        """Sets the s3_load_balancer_group of this ObjectStorageZone.


        :param s3_load_balancer_group: The s3_load_balancer_group of this ObjectStorageZone.  # noqa: E501
        :type: S3LoadBalancerGroupNestview
        """

        self._s3_load_balancer_group = s3_load_balancer_group

    @property
    def search_zone_uuid(self):
        """Gets the search_zone_uuid of this ObjectStorageZone.  # noqa: E501


        :return: The search_zone_uuid of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._search_zone_uuid

    @search_zone_uuid.setter
    def search_zone_uuid(self, search_zone_uuid):
        """Sets the search_zone_uuid of this ObjectStorageZone.


        :param search_zone_uuid: The search_zone_uuid of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._search_zone_uuid = search_zone_uuid

    @property
    def status(self):
        """Gets the status of this ObjectStorageZone.  # noqa: E501


        :return: The status of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this ObjectStorageZone.


        :param status: The status of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def switch_status(self):
        """Gets the switch_status of this ObjectStorageZone.  # noqa: E501


        :return: The switch_status of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._switch_status

    @switch_status.setter
    def switch_status(self, switch_status):
        """Sets the switch_status of this ObjectStorageZone.


        :param switch_status: The switch_status of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._switch_status = switch_status

    @property
    def system_access_key(self):
        """Gets the system_access_key of this ObjectStorageZone.  # noqa: E501


        :return: The system_access_key of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._system_access_key

    @system_access_key.setter
    def system_access_key(self, system_access_key):
        """Sets the system_access_key of this ObjectStorageZone.


        :param system_access_key: The system_access_key of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._system_access_key = system_access_key

    @property
    def system_secret_key(self):
        """Gets the system_secret_key of this ObjectStorageZone.  # noqa: E501


        :return: The system_secret_key of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._system_secret_key

    @system_secret_key.setter
    def system_secret_key(self, system_secret_key):
        """Sets the system_secret_key of this ObjectStorageZone.


        :param system_secret_key: The system_secret_key of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._system_secret_key = system_secret_key

    @property
    def system_user(self):
        """Gets the system_user of this ObjectStorageZone.  # noqa: E501


        :return: The system_user of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._system_user

    @system_user.setter
    def system_user(self, system_user):
        """Sets the system_user of this ObjectStorageZone.


        :param system_user: The system_user of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._system_user = system_user

    @property
    def tier_type(self):
        """Gets the tier_type of this ObjectStorageZone.  # noqa: E501


        :return: The tier_type of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._tier_type

    @tier_type.setter
    def tier_type(self, tier_type):
        """Sets the tier_type of this ObjectStorageZone.


        :param tier_type: The tier_type of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._tier_type = tier_type

    @property
    def update(self):
        """Gets the update of this ObjectStorageZone.  # noqa: E501


        :return: The update of this ObjectStorageZone.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this ObjectStorageZone.


        :param update: The update of this ObjectStorageZone.  # noqa: E501
        :type: datetime
        """

        self._update = update

    @property
    def uuid(self):
        """Gets the uuid of this ObjectStorageZone.  # noqa: E501


        :return: The uuid of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._uuid

    @uuid.setter
    def uuid(self, uuid):
        """Sets the uuid of this ObjectStorageZone.


        :param uuid: The uuid of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._uuid = uuid

    @property
    def zonegroup_name(self):
        """Gets the zonegroup_name of this ObjectStorageZone.  # noqa: E501


        :return: The zonegroup_name of this ObjectStorageZone.  # noqa: E501
        :rtype: str
        """
        return self._zonegroup_name

    @zonegroup_name.setter
    def zonegroup_name(self, zonegroup_name):
        """Sets the zonegroup_name of this ObjectStorageZone.


        :param zonegroup_name: The zonegroup_name of this ObjectStorageZone.  # noqa: E501
        :type: str
        """

        self._zonegroup_name = zonegroup_name

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
        if not isinstance(other, ObjectStorageZone):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
