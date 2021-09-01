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


class HostInitialization(object):
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
        'admin_ips': 'list[str]',
        'create': 'datetime',
        'disable_firewalld': 'bool',
        'hostname_prefix': 'str',
        'id': 'int',
        'message': 'str',
        'set_hostname': 'bool',
        'ssh_user': 'str',
        'status': 'str'
    }

    attribute_map = {
        'admin_ips': 'admin_ips',
        'create': 'create',
        'disable_firewalld': 'disable_firewalld',
        'hostname_prefix': 'hostname_prefix',
        'id': 'id',
        'message': 'message',
        'set_hostname': 'set_hostname',
        'ssh_user': 'ssh_user',
        'status': 'status'
    }

    def __init__(self, admin_ips=None, create=None, disable_firewalld=None, hostname_prefix=None, id=None, message=None, set_hostname=None, ssh_user=None, status=None):  # noqa: E501
        """HostInitialization - a model defined in Swagger"""  # noqa: E501

        self._admin_ips = None
        self._create = None
        self._disable_firewalld = None
        self._hostname_prefix = None
        self._id = None
        self._message = None
        self._set_hostname = None
        self._ssh_user = None
        self._status = None
        self.discriminator = None

        if admin_ips is not None:
            self.admin_ips = admin_ips
        if create is not None:
            self.create = create
        if disable_firewalld is not None:
            self.disable_firewalld = disable_firewalld
        if hostname_prefix is not None:
            self.hostname_prefix = hostname_prefix
        if id is not None:
            self.id = id
        if message is not None:
            self.message = message
        if set_hostname is not None:
            self.set_hostname = set_hostname
        if ssh_user is not None:
            self.ssh_user = ssh_user
        if status is not None:
            self.status = status

    @property
    def admin_ips(self):
        """Gets the admin_ips of this HostInitialization.  # noqa: E501


        :return: The admin_ips of this HostInitialization.  # noqa: E501
        :rtype: list[str]
        """
        return self._admin_ips

    @admin_ips.setter
    def admin_ips(self, admin_ips):
        """Sets the admin_ips of this HostInitialization.


        :param admin_ips: The admin_ips of this HostInitialization.  # noqa: E501
        :type: list[str]
        """

        self._admin_ips = admin_ips

    @property
    def create(self):
        """Gets the create of this HostInitialization.  # noqa: E501


        :return: The create of this HostInitialization.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this HostInitialization.


        :param create: The create of this HostInitialization.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def disable_firewalld(self):
        """Gets the disable_firewalld of this HostInitialization.  # noqa: E501


        :return: The disable_firewalld of this HostInitialization.  # noqa: E501
        :rtype: bool
        """
        return self._disable_firewalld

    @disable_firewalld.setter
    def disable_firewalld(self, disable_firewalld):
        """Sets the disable_firewalld of this HostInitialization.


        :param disable_firewalld: The disable_firewalld of this HostInitialization.  # noqa: E501
        :type: bool
        """

        self._disable_firewalld = disable_firewalld

    @property
    def hostname_prefix(self):
        """Gets the hostname_prefix of this HostInitialization.  # noqa: E501


        :return: The hostname_prefix of this HostInitialization.  # noqa: E501
        :rtype: str
        """
        return self._hostname_prefix

    @hostname_prefix.setter
    def hostname_prefix(self, hostname_prefix):
        """Sets the hostname_prefix of this HostInitialization.


        :param hostname_prefix: The hostname_prefix of this HostInitialization.  # noqa: E501
        :type: str
        """

        self._hostname_prefix = hostname_prefix

    @property
    def id(self):
        """Gets the id of this HostInitialization.  # noqa: E501


        :return: The id of this HostInitialization.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this HostInitialization.


        :param id: The id of this HostInitialization.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def message(self):
        """Gets the message of this HostInitialization.  # noqa: E501


        :return: The message of this HostInitialization.  # noqa: E501
        :rtype: str
        """
        return self._message

    @message.setter
    def message(self, message):
        """Sets the message of this HostInitialization.


        :param message: The message of this HostInitialization.  # noqa: E501
        :type: str
        """

        self._message = message

    @property
    def set_hostname(self):
        """Gets the set_hostname of this HostInitialization.  # noqa: E501


        :return: The set_hostname of this HostInitialization.  # noqa: E501
        :rtype: bool
        """
        return self._set_hostname

    @set_hostname.setter
    def set_hostname(self, set_hostname):
        """Sets the set_hostname of this HostInitialization.


        :param set_hostname: The set_hostname of this HostInitialization.  # noqa: E501
        :type: bool
        """

        self._set_hostname = set_hostname

    @property
    def ssh_user(self):
        """Gets the ssh_user of this HostInitialization.  # noqa: E501


        :return: The ssh_user of this HostInitialization.  # noqa: E501
        :rtype: str
        """
        return self._ssh_user

    @ssh_user.setter
    def ssh_user(self, ssh_user):
        """Sets the ssh_user of this HostInitialization.


        :param ssh_user: The ssh_user of this HostInitialization.  # noqa: E501
        :type: str
        """

        self._ssh_user = ssh_user

    @property
    def status(self):
        """Gets the status of this HostInitialization.  # noqa: E501


        :return: The status of this HostInitialization.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this HostInitialization.


        :param status: The status of this HostInitialization.  # noqa: E501
        :type: str
        """

        self._status = status

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
        if not isinstance(other, HostInitialization):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other