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

# from zstacklib.utils.xms_client.models.dp_volume_group_snapshot_replication_pair_nestview import DpVolumeGroupSnapshotReplicationPairNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.volume_group_snapshot_nestview import VolumeGroupSnapshotNestview  # noqa: F401,E501


class DpVolumeGroupSnapshotReplicationJob(object):
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
        'diff_type': 'str',
        'dp_volume_group_snapshot_replication_pair': 'DpVolumeGroupSnapshotReplicationPairNestview',
        'finished_at': 'datetime',
        'id': 'int',
        'max_retry_times': 'int',
        'progress': 'float',
        'size': 'int',
        'snapshot': 'VolumeGroupSnapshotNestview',
        'started_at': 'datetime',
        'status': 'str',
        'updated_at': 'datetime',
        'volume_group_name': 'str'
    }

    attribute_map = {
        'diff_type': 'diff_type',
        'dp_volume_group_snapshot_replication_pair': 'dp_volume_group_snapshot_replication_pair',
        'finished_at': 'finished_at',
        'id': 'id',
        'max_retry_times': 'max_retry_times',
        'progress': 'progress',
        'size': 'size',
        'snapshot': 'snapshot',
        'started_at': 'started_at',
        'status': 'status',
        'updated_at': 'updated_at',
        'volume_group_name': 'volume_group_name'
    }

    def __init__(self, diff_type=None, dp_volume_group_snapshot_replication_pair=None, finished_at=None, id=None, max_retry_times=None, progress=None, size=None, snapshot=None, started_at=None, status=None, updated_at=None, volume_group_name=None):  # noqa: E501
        """DpVolumeGroupSnapshotReplicationJob - a model defined in Swagger"""  # noqa: E501

        self._diff_type = None
        self._dp_volume_group_snapshot_replication_pair = None
        self._finished_at = None
        self._id = None
        self._max_retry_times = None
        self._progress = None
        self._size = None
        self._snapshot = None
        self._started_at = None
        self._status = None
        self._updated_at = None
        self._volume_group_name = None
        self.discriminator = None

        if diff_type is not None:
            self.diff_type = diff_type
        if dp_volume_group_snapshot_replication_pair is not None:
            self.dp_volume_group_snapshot_replication_pair = dp_volume_group_snapshot_replication_pair
        if finished_at is not None:
            self.finished_at = finished_at
        if id is not None:
            self.id = id
        if max_retry_times is not None:
            self.max_retry_times = max_retry_times
        if progress is not None:
            self.progress = progress
        if size is not None:
            self.size = size
        if snapshot is not None:
            self.snapshot = snapshot
        if started_at is not None:
            self.started_at = started_at
        if status is not None:
            self.status = status
        if updated_at is not None:
            self.updated_at = updated_at
        if volume_group_name is not None:
            self.volume_group_name = volume_group_name

    @property
    def diff_type(self):
        """Gets the diff_type of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The diff_type of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: str
        """
        return self._diff_type

    @diff_type.setter
    def diff_type(self, diff_type):
        """Sets the diff_type of this DpVolumeGroupSnapshotReplicationJob.


        :param diff_type: The diff_type of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: str
        """

        self._diff_type = diff_type

    @property
    def dp_volume_group_snapshot_replication_pair(self):
        """Gets the dp_volume_group_snapshot_replication_pair of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The dp_volume_group_snapshot_replication_pair of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: DpVolumeGroupSnapshotReplicationPairNestview
        """
        return self._dp_volume_group_snapshot_replication_pair

    @dp_volume_group_snapshot_replication_pair.setter
    def dp_volume_group_snapshot_replication_pair(self, dp_volume_group_snapshot_replication_pair):
        """Sets the dp_volume_group_snapshot_replication_pair of this DpVolumeGroupSnapshotReplicationJob.


        :param dp_volume_group_snapshot_replication_pair: The dp_volume_group_snapshot_replication_pair of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: DpVolumeGroupSnapshotReplicationPairNestview
        """

        self._dp_volume_group_snapshot_replication_pair = dp_volume_group_snapshot_replication_pair

    @property
    def finished_at(self):
        """Gets the finished_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The finished_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: datetime
        """
        return self._finished_at

    @finished_at.setter
    def finished_at(self, finished_at):
        """Sets the finished_at of this DpVolumeGroupSnapshotReplicationJob.


        :param finished_at: The finished_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: datetime
        """

        self._finished_at = finished_at

    @property
    def id(self):
        """Gets the id of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The id of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this DpVolumeGroupSnapshotReplicationJob.


        :param id: The id of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def max_retry_times(self):
        """Gets the max_retry_times of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The max_retry_times of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: int
        """
        return self._max_retry_times

    @max_retry_times.setter
    def max_retry_times(self, max_retry_times):
        """Sets the max_retry_times of this DpVolumeGroupSnapshotReplicationJob.


        :param max_retry_times: The max_retry_times of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: int
        """

        self._max_retry_times = max_retry_times

    @property
    def progress(self):
        """Gets the progress of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The progress of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: float
        """
        return self._progress

    @progress.setter
    def progress(self, progress):
        """Sets the progress of this DpVolumeGroupSnapshotReplicationJob.


        :param progress: The progress of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: float
        """

        self._progress = progress

    @property
    def size(self):
        """Gets the size of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The size of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: int
        """
        return self._size

    @size.setter
    def size(self, size):
        """Sets the size of this DpVolumeGroupSnapshotReplicationJob.


        :param size: The size of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: int
        """

        self._size = size

    @property
    def snapshot(self):
        """Gets the snapshot of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The snapshot of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: VolumeGroupSnapshotNestview
        """
        return self._snapshot

    @snapshot.setter
    def snapshot(self, snapshot):
        """Sets the snapshot of this DpVolumeGroupSnapshotReplicationJob.


        :param snapshot: The snapshot of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: VolumeGroupSnapshotNestview
        """

        self._snapshot = snapshot

    @property
    def started_at(self):
        """Gets the started_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The started_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: datetime
        """
        return self._started_at

    @started_at.setter
    def started_at(self, started_at):
        """Sets the started_at of this DpVolumeGroupSnapshotReplicationJob.


        :param started_at: The started_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: datetime
        """

        self._started_at = started_at

    @property
    def status(self):
        """Gets the status of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The status of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this DpVolumeGroupSnapshotReplicationJob.


        :param status: The status of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def updated_at(self):
        """Gets the updated_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The updated_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: datetime
        """
        return self._updated_at

    @updated_at.setter
    def updated_at(self, updated_at):
        """Sets the updated_at of this DpVolumeGroupSnapshotReplicationJob.


        :param updated_at: The updated_at of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: datetime
        """

        self._updated_at = updated_at

    @property
    def volume_group_name(self):
        """Gets the volume_group_name of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501


        :return: The volume_group_name of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :rtype: str
        """
        return self._volume_group_name

    @volume_group_name.setter
    def volume_group_name(self, volume_group_name):
        """Sets the volume_group_name of this DpVolumeGroupSnapshotReplicationJob.


        :param volume_group_name: The volume_group_name of this DpVolumeGroupSnapshotReplicationJob.  # noqa: E501
        :type: str
        """

        self._volume_group_name = volume_group_name

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
        if not isinstance(other, DpVolumeGroupSnapshotReplicationJob):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
