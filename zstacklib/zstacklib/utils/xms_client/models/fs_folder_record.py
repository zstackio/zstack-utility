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

# from zstacklib.utils.xms_client.models.access_path_nestview import AccessPathNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.dp_fs_snapshot_policy_nestview import DpFSSnapshotPolicyNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.fs_folder import FSFolder  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.fs_folder_stat import FSFolderStat  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.fs_gateway_group import FSGatewayGroup  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.fs_snapshot_nestview import FSSnapshotNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.pool_nestview import PoolNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.volume_nestview import VolumeNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.volume_qos_spec import VolumeQosSpec  # noqa: F401,E501


class FSFolderRecord(object):
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
        'access_path': 'AccessPathNestview',
        'action_status': 'str',
        'actual_status': 'str',
        'block_volume': 'VolumeNestview',
        'block_volume_status': 'str',
        'create': 'datetime',
        'description': 'str',
        'dp_fs_snapshot_policy': 'DpFSSnapshotPolicyNestview',
        'flattened': 'bool',
        'formatted': 'bool',
        'fs_gateway_group': 'FSGatewayGroup',
        'fs_quota_tree_num': 'int',
        'fs_snapshot': 'FSSnapshotNestview',
        'fs_snapshot_num': 'int',
        'id': 'int',
        'latest_snapshot_time': 'datetime',
        'name': 'str',
        'pool': 'PoolNestview',
        'progress': 'float',
        'qos': 'VolumeQosSpec',
        'qos_enabled': 'bool',
        'quota_tree_share_types': 'list[str]',
        'quota_tree_shared': 'bool',
        'share_types': 'list[str]',
        'shared': 'bool',
        'size': 'int',
        'status': 'str',
        'update': 'datetime',
        'samples': 'list[FSFolderStat]'
    }

    attribute_map = {
        'access_path': 'access_path',
        'action_status': 'action_status',
        'actual_status': 'actual_status',
        'block_volume': 'block_volume',
        'block_volume_status': 'block_volume_status',
        'create': 'create',
        'description': 'description',
        'dp_fs_snapshot_policy': 'dp_fs_snapshot_policy',
        'flattened': 'flattened',
        'formatted': 'formatted',
        'fs_gateway_group': 'fs_gateway_group',
        'fs_quota_tree_num': 'fs_quota_tree_num',
        'fs_snapshot': 'fs_snapshot',
        'fs_snapshot_num': 'fs_snapshot_num',
        'id': 'id',
        'latest_snapshot_time': 'latest_snapshot_time',
        'name': 'name',
        'pool': 'pool',
        'progress': 'progress',
        'qos': 'qos',
        'qos_enabled': 'qos_enabled',
        'quota_tree_share_types': 'quota_tree_share_types',
        'quota_tree_shared': 'quota_tree_shared',
        'share_types': 'share_types',
        'shared': 'shared',
        'size': 'size',
        'status': 'status',
        'update': 'update',
        'samples': 'samples'
    }

    def __init__(self, access_path=None, action_status=None, actual_status=None, block_volume=None, block_volume_status=None, create=None, description=None, dp_fs_snapshot_policy=None, flattened=None, formatted=None, fs_gateway_group=None, fs_quota_tree_num=None, fs_snapshot=None, fs_snapshot_num=None, id=None, latest_snapshot_time=None, name=None, pool=None, progress=None, qos=None, qos_enabled=None, quota_tree_share_types=None, quota_tree_shared=None, share_types=None, shared=None, size=None, status=None, update=None, samples=None):  # noqa: E501
        """FSFolderRecord - a model defined in Swagger"""  # noqa: E501

        self._access_path = None
        self._action_status = None
        self._actual_status = None
        self._block_volume = None
        self._block_volume_status = None
        self._create = None
        self._description = None
        self._dp_fs_snapshot_policy = None
        self._flattened = None
        self._formatted = None
        self._fs_gateway_group = None
        self._fs_quota_tree_num = None
        self._fs_snapshot = None
        self._fs_snapshot_num = None
        self._id = None
        self._latest_snapshot_time = None
        self._name = None
        self._pool = None
        self._progress = None
        self._qos = None
        self._qos_enabled = None
        self._quota_tree_share_types = None
        self._quota_tree_shared = None
        self._share_types = None
        self._shared = None
        self._size = None
        self._status = None
        self._update = None
        self._samples = None
        self.discriminator = None

        if access_path is not None:
            self.access_path = access_path
        if action_status is not None:
            self.action_status = action_status
        if actual_status is not None:
            self.actual_status = actual_status
        if block_volume is not None:
            self.block_volume = block_volume
        if block_volume_status is not None:
            self.block_volume_status = block_volume_status
        if create is not None:
            self.create = create
        if description is not None:
            self.description = description
        if dp_fs_snapshot_policy is not None:
            self.dp_fs_snapshot_policy = dp_fs_snapshot_policy
        if flattened is not None:
            self.flattened = flattened
        if formatted is not None:
            self.formatted = formatted
        if fs_gateway_group is not None:
            self.fs_gateway_group = fs_gateway_group
        if fs_quota_tree_num is not None:
            self.fs_quota_tree_num = fs_quota_tree_num
        if fs_snapshot is not None:
            self.fs_snapshot = fs_snapshot
        if fs_snapshot_num is not None:
            self.fs_snapshot_num = fs_snapshot_num
        if id is not None:
            self.id = id
        if latest_snapshot_time is not None:
            self.latest_snapshot_time = latest_snapshot_time
        if name is not None:
            self.name = name
        if pool is not None:
            self.pool = pool
        if progress is not None:
            self.progress = progress
        if qos is not None:
            self.qos = qos
        if qos_enabled is not None:
            self.qos_enabled = qos_enabled
        if quota_tree_share_types is not None:
            self.quota_tree_share_types = quota_tree_share_types
        if quota_tree_shared is not None:
            self.quota_tree_shared = quota_tree_shared
        if share_types is not None:
            self.share_types = share_types
        if shared is not None:
            self.shared = shared
        if size is not None:
            self.size = size
        if status is not None:
            self.status = status
        if update is not None:
            self.update = update
        if samples is not None:
            self.samples = samples

    @property
    def access_path(self):
        """Gets the access_path of this FSFolderRecord.  # noqa: E501


        :return: The access_path of this FSFolderRecord.  # noqa: E501
        :rtype: AccessPathNestview
        """
        return self._access_path

    @access_path.setter
    def access_path(self, access_path):
        """Sets the access_path of this FSFolderRecord.


        :param access_path: The access_path of this FSFolderRecord.  # noqa: E501
        :type: AccessPathNestview
        """

        self._access_path = access_path

    @property
    def action_status(self):
        """Gets the action_status of this FSFolderRecord.  # noqa: E501


        :return: The action_status of this FSFolderRecord.  # noqa: E501
        :rtype: str
        """
        return self._action_status

    @action_status.setter
    def action_status(self, action_status):
        """Sets the action_status of this FSFolderRecord.


        :param action_status: The action_status of this FSFolderRecord.  # noqa: E501
        :type: str
        """

        self._action_status = action_status

    @property
    def actual_status(self):
        """Gets the actual_status of this FSFolderRecord.  # noqa: E501


        :return: The actual_status of this FSFolderRecord.  # noqa: E501
        :rtype: str
        """
        return self._actual_status

    @actual_status.setter
    def actual_status(self, actual_status):
        """Sets the actual_status of this FSFolderRecord.


        :param actual_status: The actual_status of this FSFolderRecord.  # noqa: E501
        :type: str
        """

        self._actual_status = actual_status

    @property
    def block_volume(self):
        """Gets the block_volume of this FSFolderRecord.  # noqa: E501


        :return: The block_volume of this FSFolderRecord.  # noqa: E501
        :rtype: VolumeNestview
        """
        return self._block_volume

    @block_volume.setter
    def block_volume(self, block_volume):
        """Sets the block_volume of this FSFolderRecord.


        :param block_volume: The block_volume of this FSFolderRecord.  # noqa: E501
        :type: VolumeNestview
        """

        self._block_volume = block_volume

    @property
    def block_volume_status(self):
        """Gets the block_volume_status of this FSFolderRecord.  # noqa: E501


        :return: The block_volume_status of this FSFolderRecord.  # noqa: E501
        :rtype: str
        """
        return self._block_volume_status

    @block_volume_status.setter
    def block_volume_status(self, block_volume_status):
        """Sets the block_volume_status of this FSFolderRecord.


        :param block_volume_status: The block_volume_status of this FSFolderRecord.  # noqa: E501
        :type: str
        """

        self._block_volume_status = block_volume_status

    @property
    def create(self):
        """Gets the create of this FSFolderRecord.  # noqa: E501


        :return: The create of this FSFolderRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this FSFolderRecord.


        :param create: The create of this FSFolderRecord.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def description(self):
        """Gets the description of this FSFolderRecord.  # noqa: E501


        :return: The description of this FSFolderRecord.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this FSFolderRecord.


        :param description: The description of this FSFolderRecord.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def dp_fs_snapshot_policy(self):
        """Gets the dp_fs_snapshot_policy of this FSFolderRecord.  # noqa: E501


        :return: The dp_fs_snapshot_policy of this FSFolderRecord.  # noqa: E501
        :rtype: DpFSSnapshotPolicyNestview
        """
        return self._dp_fs_snapshot_policy

    @dp_fs_snapshot_policy.setter
    def dp_fs_snapshot_policy(self, dp_fs_snapshot_policy):
        """Sets the dp_fs_snapshot_policy of this FSFolderRecord.


        :param dp_fs_snapshot_policy: The dp_fs_snapshot_policy of this FSFolderRecord.  # noqa: E501
        :type: DpFSSnapshotPolicyNestview
        """

        self._dp_fs_snapshot_policy = dp_fs_snapshot_policy

    @property
    def flattened(self):
        """Gets the flattened of this FSFolderRecord.  # noqa: E501


        :return: The flattened of this FSFolderRecord.  # noqa: E501
        :rtype: bool
        """
        return self._flattened

    @flattened.setter
    def flattened(self, flattened):
        """Sets the flattened of this FSFolderRecord.


        :param flattened: The flattened of this FSFolderRecord.  # noqa: E501
        :type: bool
        """

        self._flattened = flattened

    @property
    def formatted(self):
        """Gets the formatted of this FSFolderRecord.  # noqa: E501


        :return: The formatted of this FSFolderRecord.  # noqa: E501
        :rtype: bool
        """
        return self._formatted

    @formatted.setter
    def formatted(self, formatted):
        """Sets the formatted of this FSFolderRecord.


        :param formatted: The formatted of this FSFolderRecord.  # noqa: E501
        :type: bool
        """

        self._formatted = formatted

    @property
    def fs_gateway_group(self):
        """Gets the fs_gateway_group of this FSFolderRecord.  # noqa: E501


        :return: The fs_gateway_group of this FSFolderRecord.  # noqa: E501
        :rtype: FSGatewayGroup
        """
        return self._fs_gateway_group

    @fs_gateway_group.setter
    def fs_gateway_group(self, fs_gateway_group):
        """Sets the fs_gateway_group of this FSFolderRecord.


        :param fs_gateway_group: The fs_gateway_group of this FSFolderRecord.  # noqa: E501
        :type: FSGatewayGroup
        """

        self._fs_gateway_group = fs_gateway_group

    @property
    def fs_quota_tree_num(self):
        """Gets the fs_quota_tree_num of this FSFolderRecord.  # noqa: E501


        :return: The fs_quota_tree_num of this FSFolderRecord.  # noqa: E501
        :rtype: int
        """
        return self._fs_quota_tree_num

    @fs_quota_tree_num.setter
    def fs_quota_tree_num(self, fs_quota_tree_num):
        """Sets the fs_quota_tree_num of this FSFolderRecord.


        :param fs_quota_tree_num: The fs_quota_tree_num of this FSFolderRecord.  # noqa: E501
        :type: int
        """

        self._fs_quota_tree_num = fs_quota_tree_num

    @property
    def fs_snapshot(self):
        """Gets the fs_snapshot of this FSFolderRecord.  # noqa: E501


        :return: The fs_snapshot of this FSFolderRecord.  # noqa: E501
        :rtype: FSSnapshotNestview
        """
        return self._fs_snapshot

    @fs_snapshot.setter
    def fs_snapshot(self, fs_snapshot):
        """Sets the fs_snapshot of this FSFolderRecord.


        :param fs_snapshot: The fs_snapshot of this FSFolderRecord.  # noqa: E501
        :type: FSSnapshotNestview
        """

        self._fs_snapshot = fs_snapshot

    @property
    def fs_snapshot_num(self):
        """Gets the fs_snapshot_num of this FSFolderRecord.  # noqa: E501


        :return: The fs_snapshot_num of this FSFolderRecord.  # noqa: E501
        :rtype: int
        """
        return self._fs_snapshot_num

    @fs_snapshot_num.setter
    def fs_snapshot_num(self, fs_snapshot_num):
        """Sets the fs_snapshot_num of this FSFolderRecord.


        :param fs_snapshot_num: The fs_snapshot_num of this FSFolderRecord.  # noqa: E501
        :type: int
        """

        self._fs_snapshot_num = fs_snapshot_num

    @property
    def id(self):
        """Gets the id of this FSFolderRecord.  # noqa: E501


        :return: The id of this FSFolderRecord.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this FSFolderRecord.


        :param id: The id of this FSFolderRecord.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def latest_snapshot_time(self):
        """Gets the latest_snapshot_time of this FSFolderRecord.  # noqa: E501


        :return: The latest_snapshot_time of this FSFolderRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._latest_snapshot_time

    @latest_snapshot_time.setter
    def latest_snapshot_time(self, latest_snapshot_time):
        """Sets the latest_snapshot_time of this FSFolderRecord.


        :param latest_snapshot_time: The latest_snapshot_time of this FSFolderRecord.  # noqa: E501
        :type: datetime
        """

        self._latest_snapshot_time = latest_snapshot_time

    @property
    def name(self):
        """Gets the name of this FSFolderRecord.  # noqa: E501


        :return: The name of this FSFolderRecord.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this FSFolderRecord.


        :param name: The name of this FSFolderRecord.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def pool(self):
        """Gets the pool of this FSFolderRecord.  # noqa: E501


        :return: The pool of this FSFolderRecord.  # noqa: E501
        :rtype: PoolNestview
        """
        return self._pool

    @pool.setter
    def pool(self, pool):
        """Sets the pool of this FSFolderRecord.


        :param pool: The pool of this FSFolderRecord.  # noqa: E501
        :type: PoolNestview
        """

        self._pool = pool

    @property
    def progress(self):
        """Gets the progress of this FSFolderRecord.  # noqa: E501


        :return: The progress of this FSFolderRecord.  # noqa: E501
        :rtype: float
        """
        return self._progress

    @progress.setter
    def progress(self, progress):
        """Sets the progress of this FSFolderRecord.


        :param progress: The progress of this FSFolderRecord.  # noqa: E501
        :type: float
        """

        self._progress = progress

    @property
    def qos(self):
        """Gets the qos of this FSFolderRecord.  # noqa: E501


        :return: The qos of this FSFolderRecord.  # noqa: E501
        :rtype: VolumeQosSpec
        """
        return self._qos

    @qos.setter
    def qos(self, qos):
        """Sets the qos of this FSFolderRecord.


        :param qos: The qos of this FSFolderRecord.  # noqa: E501
        :type: VolumeQosSpec
        """

        self._qos = qos

    @property
    def qos_enabled(self):
        """Gets the qos_enabled of this FSFolderRecord.  # noqa: E501


        :return: The qos_enabled of this FSFolderRecord.  # noqa: E501
        :rtype: bool
        """
        return self._qos_enabled

    @qos_enabled.setter
    def qos_enabled(self, qos_enabled):
        """Sets the qos_enabled of this FSFolderRecord.


        :param qos_enabled: The qos_enabled of this FSFolderRecord.  # noqa: E501
        :type: bool
        """

        self._qos_enabled = qos_enabled

    @property
    def quota_tree_share_types(self):
        """Gets the quota_tree_share_types of this FSFolderRecord.  # noqa: E501


        :return: The quota_tree_share_types of this FSFolderRecord.  # noqa: E501
        :rtype: list[str]
        """
        return self._quota_tree_share_types

    @quota_tree_share_types.setter
    def quota_tree_share_types(self, quota_tree_share_types):
        """Sets the quota_tree_share_types of this FSFolderRecord.


        :param quota_tree_share_types: The quota_tree_share_types of this FSFolderRecord.  # noqa: E501
        :type: list[str]
        """

        self._quota_tree_share_types = quota_tree_share_types

    @property
    def quota_tree_shared(self):
        """Gets the quota_tree_shared of this FSFolderRecord.  # noqa: E501


        :return: The quota_tree_shared of this FSFolderRecord.  # noqa: E501
        :rtype: bool
        """
        return self._quota_tree_shared

    @quota_tree_shared.setter
    def quota_tree_shared(self, quota_tree_shared):
        """Sets the quota_tree_shared of this FSFolderRecord.


        :param quota_tree_shared: The quota_tree_shared of this FSFolderRecord.  # noqa: E501
        :type: bool
        """

        self._quota_tree_shared = quota_tree_shared

    @property
    def share_types(self):
        """Gets the share_types of this FSFolderRecord.  # noqa: E501


        :return: The share_types of this FSFolderRecord.  # noqa: E501
        :rtype: list[str]
        """
        return self._share_types

    @share_types.setter
    def share_types(self, share_types):
        """Sets the share_types of this FSFolderRecord.


        :param share_types: The share_types of this FSFolderRecord.  # noqa: E501
        :type: list[str]
        """

        self._share_types = share_types

    @property
    def shared(self):
        """Gets the shared of this FSFolderRecord.  # noqa: E501

        before version 3.2.14, these fields was calculated by wizard, but there is quota trees in new verion, calculations is too complicated, so add the fields to folder struct  # noqa: E501

        :return: The shared of this FSFolderRecord.  # noqa: E501
        :rtype: bool
        """
        return self._shared

    @shared.setter
    def shared(self, shared):
        """Sets the shared of this FSFolderRecord.

        before version 3.2.14, these fields was calculated by wizard, but there is quota trees in new verion, calculations is too complicated, so add the fields to folder struct  # noqa: E501

        :param shared: The shared of this FSFolderRecord.  # noqa: E501
        :type: bool
        """

        self._shared = shared

    @property
    def size(self):
        """Gets the size of this FSFolderRecord.  # noqa: E501


        :return: The size of this FSFolderRecord.  # noqa: E501
        :rtype: int
        """
        return self._size

    @size.setter
    def size(self, size):
        """Sets the size of this FSFolderRecord.


        :param size: The size of this FSFolderRecord.  # noqa: E501
        :type: int
        """

        self._size = size

    @property
    def status(self):
        """Gets the status of this FSFolderRecord.  # noqa: E501


        :return: The status of this FSFolderRecord.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this FSFolderRecord.


        :param status: The status of this FSFolderRecord.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def update(self):
        """Gets the update of this FSFolderRecord.  # noqa: E501


        :return: The update of this FSFolderRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this FSFolderRecord.


        :param update: The update of this FSFolderRecord.  # noqa: E501
        :type: datetime
        """

        self._update = update

    @property
    def samples(self):
        """Gets the samples of this FSFolderRecord.  # noqa: E501


        :return: The samples of this FSFolderRecord.  # noqa: E501
        :rtype: list[FSFolderStat]
        """
        return self._samples

    @samples.setter
    def samples(self, samples):
        """Sets the samples of this FSFolderRecord.


        :param samples: The samples of this FSFolderRecord.  # noqa: E501
        :type: list[FSFolderStat]
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
        if not isinstance(other, FSFolderRecord):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
