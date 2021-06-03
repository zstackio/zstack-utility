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


class FSFTPShareUpdateACLReq(object):
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
        'create_enabled': 'bool',
        'delete_enabled': 'bool',
        'download_bandwidth': 'int',
        'download_enabled': 'bool',
        'id': 'int',
        'list_enabled': 'bool',
        'rename_enabled': 'bool',
        'upload_bandwidth': 'int',
        'upload_enabled': 'bool'
    }

    attribute_map = {
        'create_enabled': 'create_enabled',
        'delete_enabled': 'delete_enabled',
        'download_bandwidth': 'download_bandwidth',
        'download_enabled': 'download_enabled',
        'id': 'id',
        'list_enabled': 'list_enabled',
        'rename_enabled': 'rename_enabled',
        'upload_bandwidth': 'upload_bandwidth',
        'upload_enabled': 'upload_enabled'
    }

    def __init__(self, create_enabled=None, delete_enabled=None, download_bandwidth=None, download_enabled=None, id=None, list_enabled=None, rename_enabled=None, upload_bandwidth=None, upload_enabled=None):  # noqa: E501
        """FSFTPShareUpdateACLReq - a model defined in Swagger"""  # noqa: E501

        self._create_enabled = None
        self._delete_enabled = None
        self._download_bandwidth = None
        self._download_enabled = None
        self._id = None
        self._list_enabled = None
        self._rename_enabled = None
        self._upload_bandwidth = None
        self._upload_enabled = None
        self.discriminator = None

        if create_enabled is not None:
            self.create_enabled = create_enabled
        if delete_enabled is not None:
            self.delete_enabled = delete_enabled
        if download_bandwidth is not None:
            self.download_bandwidth = download_bandwidth
        if download_enabled is not None:
            self.download_enabled = download_enabled
        if id is not None:
            self.id = id
        if list_enabled is not None:
            self.list_enabled = list_enabled
        if rename_enabled is not None:
            self.rename_enabled = rename_enabled
        if upload_bandwidth is not None:
            self.upload_bandwidth = upload_bandwidth
        if upload_enabled is not None:
            self.upload_enabled = upload_enabled

    @property
    def create_enabled(self):
        """Gets the create_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501

        enable creating files  # noqa: E501

        :return: The create_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._create_enabled

    @create_enabled.setter
    def create_enabled(self, create_enabled):
        """Sets the create_enabled of this FSFTPShareUpdateACLReq.

        enable creating files  # noqa: E501

        :param create_enabled: The create_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._create_enabled = create_enabled

    @property
    def delete_enabled(self):
        """Gets the delete_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501

        enable deleting files  # noqa: E501

        :return: The delete_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._delete_enabled

    @delete_enabled.setter
    def delete_enabled(self, delete_enabled):
        """Sets the delete_enabled of this FSFTPShareUpdateACLReq.

        enable deleting files  # noqa: E501

        :param delete_enabled: The delete_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._delete_enabled = delete_enabled

    @property
    def download_bandwidth(self):
        """Gets the download_bandwidth of this FSFTPShareUpdateACLReq.  # noqa: E501

        max bandwidth of downloading  # noqa: E501

        :return: The download_bandwidth of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: int
        """
        return self._download_bandwidth

    @download_bandwidth.setter
    def download_bandwidth(self, download_bandwidth):
        """Sets the download_bandwidth of this FSFTPShareUpdateACLReq.

        max bandwidth of downloading  # noqa: E501

        :param download_bandwidth: The download_bandwidth of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: int
        """

        self._download_bandwidth = download_bandwidth

    @property
    def download_enabled(self):
        """Gets the download_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501

        enable downloading files  # noqa: E501

        :return: The download_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._download_enabled

    @download_enabled.setter
    def download_enabled(self, download_enabled):
        """Sets the download_enabled of this FSFTPShareUpdateACLReq.

        enable downloading files  # noqa: E501

        :param download_enabled: The download_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._download_enabled = download_enabled

    @property
    def id(self):
        """Gets the id of this FSFTPShareUpdateACLReq.  # noqa: E501

        id of user group  # noqa: E501

        :return: The id of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this FSFTPShareUpdateACLReq.

        id of user group  # noqa: E501

        :param id: The id of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def list_enabled(self):
        """Gets the list_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501

        enable listing files  # noqa: E501

        :return: The list_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._list_enabled

    @list_enabled.setter
    def list_enabled(self, list_enabled):
        """Sets the list_enabled of this FSFTPShareUpdateACLReq.

        enable listing files  # noqa: E501

        :param list_enabled: The list_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._list_enabled = list_enabled

    @property
    def rename_enabled(self):
        """Gets the rename_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501

        enable renaming files  # noqa: E501

        :return: The rename_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._rename_enabled

    @rename_enabled.setter
    def rename_enabled(self, rename_enabled):
        """Sets the rename_enabled of this FSFTPShareUpdateACLReq.

        enable renaming files  # noqa: E501

        :param rename_enabled: The rename_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._rename_enabled = rename_enabled

    @property
    def upload_bandwidth(self):
        """Gets the upload_bandwidth of this FSFTPShareUpdateACLReq.  # noqa: E501

        max bandwidth of uploading  # noqa: E501

        :return: The upload_bandwidth of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: int
        """
        return self._upload_bandwidth

    @upload_bandwidth.setter
    def upload_bandwidth(self, upload_bandwidth):
        """Sets the upload_bandwidth of this FSFTPShareUpdateACLReq.

        max bandwidth of uploading  # noqa: E501

        :param upload_bandwidth: The upload_bandwidth of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: int
        """

        self._upload_bandwidth = upload_bandwidth

    @property
    def upload_enabled(self):
        """Gets the upload_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501

        enable uploading files  # noqa: E501

        :return: The upload_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :rtype: bool
        """
        return self._upload_enabled

    @upload_enabled.setter
    def upload_enabled(self, upload_enabled):
        """Sets the upload_enabled of this FSFTPShareUpdateACLReq.

        enable uploading files  # noqa: E501

        :param upload_enabled: The upload_enabled of this FSFTPShareUpdateACLReq.  # noqa: E501
        :type: bool
        """

        self._upload_enabled = upload_enabled

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
        if not isinstance(other, FSFTPShareUpdateACLReq):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
