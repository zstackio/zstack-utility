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


class DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair(object):
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
        'chain_name': 'str',
        'master_cluster_fs_id': 'str',
        'master_gateway': 'str',
        'master_pair_id': 'int',
        'master_volume_group_id': 'int',
        'master_volume_group_name': 'str',
        'policy_cron': 'str',
        'slave_gateway': 'str'
    }

    attribute_map = {
        'chain_name': 'chain_name',
        'master_cluster_fs_id': 'master_cluster_fs_id',
        'master_gateway': 'master_gateway',
        'master_pair_id': 'master_pair_id',
        'master_volume_group_id': 'master_volume_group_id',
        'master_volume_group_name': 'master_volume_group_name',
        'policy_cron': 'policy_cron',
        'slave_gateway': 'slave_gateway'
    }

    def __init__(self, chain_name=None, master_cluster_fs_id=None, master_gateway=None, master_pair_id=None, master_volume_group_id=None, master_volume_group_name=None, policy_cron=None, slave_gateway=None):  # noqa: E501
        """DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair - a model defined in Swagger"""  # noqa: E501

        self._chain_name = None
        self._master_cluster_fs_id = None
        self._master_gateway = None
        self._master_pair_id = None
        self._master_volume_group_id = None
        self._master_volume_group_name = None
        self._policy_cron = None
        self._slave_gateway = None
        self.discriminator = None

        self.chain_name = chain_name
        self.master_cluster_fs_id = master_cluster_fs_id
        self.master_gateway = master_gateway
        self.master_pair_id = master_pair_id
        self.master_volume_group_id = master_volume_group_id
        self.master_volume_group_name = master_volume_group_name
        self.policy_cron = policy_cron
        self.slave_gateway = slave_gateway

    @property
    def chain_name(self):
        """Gets the chain_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        chain name  # noqa: E501

        :return: The chain_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: str
        """
        return self._chain_name

    @chain_name.setter
    def chain_name(self, chain_name):
        """Sets the chain_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        chain name  # noqa: E501

        :param chain_name: The chain_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: str
        """
        if chain_name is None:
            raise ValueError("Invalid value for `chain_name`, must not be `None`")  # noqa: E501

        self._chain_name = chain_name

    @property
    def master_cluster_fs_id(self):
        """Gets the master_cluster_fs_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        master cluster fs id  # noqa: E501

        :return: The master_cluster_fs_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: str
        """
        return self._master_cluster_fs_id

    @master_cluster_fs_id.setter
    def master_cluster_fs_id(self, master_cluster_fs_id):
        """Sets the master_cluster_fs_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        master cluster fs id  # noqa: E501

        :param master_cluster_fs_id: The master_cluster_fs_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: str
        """
        if master_cluster_fs_id is None:
            raise ValueError("Invalid value for `master_cluster_fs_id`, must not be `None`")  # noqa: E501

        self._master_cluster_fs_id = master_cluster_fs_id

    @property
    def master_gateway(self):
        """Gets the master_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        gateway ip  # noqa: E501

        :return: The master_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: str
        """
        return self._master_gateway

    @master_gateway.setter
    def master_gateway(self, master_gateway):
        """Sets the master_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        gateway ip  # noqa: E501

        :param master_gateway: The master_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: str
        """
        if master_gateway is None:
            raise ValueError("Invalid value for `master_gateway`, must not be `None`")  # noqa: E501

        self._master_gateway = master_gateway

    @property
    def master_pair_id(self):
        """Gets the master_pair_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        master pair id  # noqa: E501

        :return: The master_pair_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: int
        """
        return self._master_pair_id

    @master_pair_id.setter
    def master_pair_id(self, master_pair_id):
        """Sets the master_pair_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        master pair id  # noqa: E501

        :param master_pair_id: The master_pair_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: int
        """
        if master_pair_id is None:
            raise ValueError("Invalid value for `master_pair_id`, must not be `None`")  # noqa: E501

        self._master_pair_id = master_pair_id

    @property
    def master_volume_group_id(self):
        """Gets the master_volume_group_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        master volume group id  # noqa: E501

        :return: The master_volume_group_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: int
        """
        return self._master_volume_group_id

    @master_volume_group_id.setter
    def master_volume_group_id(self, master_volume_group_id):
        """Sets the master_volume_group_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        master volume group id  # noqa: E501

        :param master_volume_group_id: The master_volume_group_id of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: int
        """
        if master_volume_group_id is None:
            raise ValueError("Invalid value for `master_volume_group_id`, must not be `None`")  # noqa: E501

        self._master_volume_group_id = master_volume_group_id

    @property
    def master_volume_group_name(self):
        """Gets the master_volume_group_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        master volume group name  # noqa: E501

        :return: The master_volume_group_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: str
        """
        return self._master_volume_group_name

    @master_volume_group_name.setter
    def master_volume_group_name(self, master_volume_group_name):
        """Sets the master_volume_group_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        master volume group name  # noqa: E501

        :param master_volume_group_name: The master_volume_group_name of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: str
        """
        if master_volume_group_name is None:
            raise ValueError("Invalid value for `master_volume_group_name`, must not be `None`")  # noqa: E501

        self._master_volume_group_name = master_volume_group_name

    @property
    def policy_cron(self):
        """Gets the policy_cron of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        policy cron  # noqa: E501

        :return: The policy_cron of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: str
        """
        return self._policy_cron

    @policy_cron.setter
    def policy_cron(self, policy_cron):
        """Sets the policy_cron of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        policy cron  # noqa: E501

        :param policy_cron: The policy_cron of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: str
        """
        if policy_cron is None:
            raise ValueError("Invalid value for `policy_cron`, must not be `None`")  # noqa: E501

        self._policy_cron = policy_cron

    @property
    def slave_gateway(self):
        """Gets the slave_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501

        gateway ip  # noqa: E501

        :return: The slave_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :rtype: str
        """
        return self._slave_gateway

    @slave_gateway.setter
    def slave_gateway(self, slave_gateway):
        """Sets the slave_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.

        gateway ip  # noqa: E501

        :param slave_gateway: The slave_gateway of this DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair.  # noqa: E501
        :type: str
        """
        if slave_gateway is None:
            raise ValueError("Invalid value for `slave_gateway`, must not be `None`")  # noqa: E501

        self._slave_gateway = slave_gateway

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
        if not isinstance(other, DpVolumeGroupSnapshotReplicationPairCreateReqGroupPair):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other