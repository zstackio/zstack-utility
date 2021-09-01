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


class FSActiveDirectoryUpdateReqInfo(object):
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
        'ip': 'str',
        'name': 'str',
        'password': 'str',
        'realm': 'str',
        'username': 'str',
        'workgroup': 'str'
    }

    attribute_map = {
        'ip': 'ip',
        'name': 'name',
        'password': 'password',
        'realm': 'realm',
        'username': 'username',
        'workgroup': 'workgroup'
    }

    def __init__(self, ip=None, name=None, password=None, realm=None, username=None, workgroup=None):  # noqa: E501
        """FSActiveDirectoryUpdateReqInfo - a model defined in Swagger"""  # noqa: E501

        self._ip = None
        self._name = None
        self._password = None
        self._realm = None
        self._username = None
        self._workgroup = None
        self.discriminator = None

        if ip is not None:
            self.ip = ip
        if name is not None:
            self.name = name
        if password is not None:
            self.password = password
        if realm is not None:
            self.realm = realm
        if username is not None:
            self.username = username
        if workgroup is not None:
            self.workgroup = workgroup

    @property
    def ip(self):
        """Gets the ip of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501

        ip of dns server  # noqa: E501

        :return: The ip of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :rtype: str
        """
        return self._ip

    @ip.setter
    def ip(self, ip):
        """Sets the ip of this FSActiveDirectoryUpdateReqInfo.

        ip of dns server  # noqa: E501

        :param ip: The ip of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :type: str
        """

        self._ip = ip

    @property
    def name(self):
        """Gets the name of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501

        name of active directory  # noqa: E501

        :return: The name of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this FSActiveDirectoryUpdateReqInfo.

        name of active directory  # noqa: E501

        :param name: The name of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def password(self):
        """Gets the password of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501

        password of active directory  # noqa: E501

        :return: The password of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :rtype: str
        """
        return self._password

    @password.setter
    def password(self, password):
        """Sets the password of this FSActiveDirectoryUpdateReqInfo.

        password of active directory  # noqa: E501

        :param password: The password of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :type: str
        """

        self._password = password

    @property
    def realm(self):
        """Gets the realm of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501

        realm of active directory  # noqa: E501

        :return: The realm of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :rtype: str
        """
        return self._realm

    @realm.setter
    def realm(self, realm):
        """Sets the realm of this FSActiveDirectoryUpdateReqInfo.

        realm of active directory  # noqa: E501

        :param realm: The realm of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :type: str
        """

        self._realm = realm

    @property
    def username(self):
        """Gets the username of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501

        username of active directory  # noqa: E501

        :return: The username of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :rtype: str
        """
        return self._username

    @username.setter
    def username(self, username):
        """Sets the username of this FSActiveDirectoryUpdateReqInfo.

        username of active directory  # noqa: E501

        :param username: The username of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :type: str
        """

        self._username = username

    @property
    def workgroup(self):
        """Gets the workgroup of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501

        workgroup of active directory  # noqa: E501

        :return: The workgroup of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :rtype: str
        """
        return self._workgroup

    @workgroup.setter
    def workgroup(self, workgroup):
        """Sets the workgroup of this FSActiveDirectoryUpdateReqInfo.

        workgroup of active directory  # noqa: E501

        :param workgroup: The workgroup of this FSActiveDirectoryUpdateReqInfo.  # noqa: E501
        :type: str
        """

        self._workgroup = workgroup

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
        if not isinstance(other, FSActiveDirectoryUpdateReqInfo):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other