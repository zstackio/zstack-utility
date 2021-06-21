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

# from zstacklib.utils.xms_client.models.client import Client  # noqa: F401,E501


class ClientGroup(object):
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
        'access_path_num': 'int',
        'block_volume_num': 'int',
        'chap': 'bool',
        'client_num': 'int',
        'clients': 'list[Client]',
        'create': 'datetime',
        'description': 'str',
        'id': 'int',
        'iname': 'str',
        'isecret': 'str',
        'name': 'str',
        'status': 'str',
        'type': 'str',
        'update': 'datetime'
    }

    attribute_map = {
        'access_path_num': 'access_path_num',
        'block_volume_num': 'block_volume_num',
        'chap': 'chap',
        'client_num': 'client_num',
        'clients': 'clients',
        'create': 'create',
        'description': 'description',
        'id': 'id',
        'iname': 'iname',
        'isecret': 'isecret',
        'name': 'name',
        'status': 'status',
        'type': 'type',
        'update': 'update'
    }

    def __init__(self, access_path_num=None, block_volume_num=None, chap=None, client_num=None, clients=None, create=None, description=None, id=None, iname=None, isecret=None, name=None, status=None, type=None, update=None):  # noqa: E501
        """ClientGroup - a model defined in Swagger"""  # noqa: E501

        self._access_path_num = None
        self._block_volume_num = None
        self._chap = None
        self._client_num = None
        self._clients = None
        self._create = None
        self._description = None
        self._id = None
        self._iname = None
        self._isecret = None
        self._name = None
        self._status = None
        self._type = None
        self._update = None
        self.discriminator = None

        if access_path_num is not None:
            self.access_path_num = access_path_num
        if block_volume_num is not None:
            self.block_volume_num = block_volume_num
        if chap is not None:
            self.chap = chap
        if client_num is not None:
            self.client_num = client_num
        if clients is not None:
            self.clients = clients
        if create is not None:
            self.create = create
        if description is not None:
            self.description = description
        if id is not None:
            self.id = id
        if iname is not None:
            self.iname = iname
        if isecret is not None:
            self.isecret = isecret
        if name is not None:
            self.name = name
        if status is not None:
            self.status = status
        if type is not None:
            self.type = type
        if update is not None:
            self.update = update

    @property
    def access_path_num(self):
        """Gets the access_path_num of this ClientGroup.  # noqa: E501


        :return: The access_path_num of this ClientGroup.  # noqa: E501
        :rtype: int
        """
        return self._access_path_num

    @access_path_num.setter
    def access_path_num(self, access_path_num):
        """Sets the access_path_num of this ClientGroup.


        :param access_path_num: The access_path_num of this ClientGroup.  # noqa: E501
        :type: int
        """

        self._access_path_num = access_path_num

    @property
    def block_volume_num(self):
        """Gets the block_volume_num of this ClientGroup.  # noqa: E501


        :return: The block_volume_num of this ClientGroup.  # noqa: E501
        :rtype: int
        """
        return self._block_volume_num

    @block_volume_num.setter
    def block_volume_num(self, block_volume_num):
        """Sets the block_volume_num of this ClientGroup.


        :param block_volume_num: The block_volume_num of this ClientGroup.  # noqa: E501
        :type: int
        """

        self._block_volume_num = block_volume_num

    @property
    def chap(self):
        """Gets the chap of this ClientGroup.  # noqa: E501


        :return: The chap of this ClientGroup.  # noqa: E501
        :rtype: bool
        """
        return self._chap

    @chap.setter
    def chap(self, chap):
        """Sets the chap of this ClientGroup.


        :param chap: The chap of this ClientGroup.  # noqa: E501
        :type: bool
        """

        self._chap = chap

    @property
    def client_num(self):
        """Gets the client_num of this ClientGroup.  # noqa: E501


        :return: The client_num of this ClientGroup.  # noqa: E501
        :rtype: int
        """
        return self._client_num

    @client_num.setter
    def client_num(self, client_num):
        """Sets the client_num of this ClientGroup.


        :param client_num: The client_num of this ClientGroup.  # noqa: E501
        :type: int
        """

        self._client_num = client_num

    @property
    def clients(self):
        """Gets the clients of this ClientGroup.  # noqa: E501


        :return: The clients of this ClientGroup.  # noqa: E501
        :rtype: list[Client]
        """
        return self._clients

    @clients.setter
    def clients(self, clients):
        """Sets the clients of this ClientGroup.


        :param clients: The clients of this ClientGroup.  # noqa: E501
        :type: list[Client]
        """

        self._clients = clients

    @property
    def create(self):
        """Gets the create of this ClientGroup.  # noqa: E501


        :return: The create of this ClientGroup.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this ClientGroup.


        :param create: The create of this ClientGroup.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def description(self):
        """Gets the description of this ClientGroup.  # noqa: E501


        :return: The description of this ClientGroup.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this ClientGroup.


        :param description: The description of this ClientGroup.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def id(self):
        """Gets the id of this ClientGroup.  # noqa: E501


        :return: The id of this ClientGroup.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this ClientGroup.


        :param id: The id of this ClientGroup.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def iname(self):
        """Gets the iname of this ClientGroup.  # noqa: E501


        :return: The iname of this ClientGroup.  # noqa: E501
        :rtype: str
        """
        return self._iname

    @iname.setter
    def iname(self, iname):
        """Sets the iname of this ClientGroup.


        :param iname: The iname of this ClientGroup.  # noqa: E501
        :type: str
        """

        self._iname = iname

    @property
    def isecret(self):
        """Gets the isecret of this ClientGroup.  # noqa: E501


        :return: The isecret of this ClientGroup.  # noqa: E501
        :rtype: str
        """
        return self._isecret

    @isecret.setter
    def isecret(self, isecret):
        """Sets the isecret of this ClientGroup.


        :param isecret: The isecret of this ClientGroup.  # noqa: E501
        :type: str
        """

        self._isecret = isecret

    @property
    def name(self):
        """Gets the name of this ClientGroup.  # noqa: E501


        :return: The name of this ClientGroup.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this ClientGroup.


        :param name: The name of this ClientGroup.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def status(self):
        """Gets the status of this ClientGroup.  # noqa: E501


        :return: The status of this ClientGroup.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this ClientGroup.


        :param status: The status of this ClientGroup.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def type(self):
        """Gets the type of this ClientGroup.  # noqa: E501


        :return: The type of this ClientGroup.  # noqa: E501
        :rtype: str
        """
        return self._type

    @type.setter
    def type(self, type):
        """Sets the type of this ClientGroup.


        :param type: The type of this ClientGroup.  # noqa: E501
        :type: str
        """

        self._type = type

    @property
    def update(self):
        """Gets the update of this ClientGroup.  # noqa: E501


        :return: The update of this ClientGroup.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this ClientGroup.


        :param update: The update of this ClientGroup.  # noqa: E501
        :type: datetime
        """

        self._update = update

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
        if not isinstance(other, ClientGroup):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
