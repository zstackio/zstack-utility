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

# from zstacklib.utils.xms_client.models.disk_nestview import DiskNestview  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.host import Host  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.host_fc_port import HostFcPort  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.host_stat import HostStat  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.protection_domain_nestview import ProtectionDomainNestview  # noqa: F401,E501


class HostRecord(object):
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
        'admin_ip': 'str',
        'clock_diff': 'int',
        'cores': 'int',
        'cpu_model': 'str',
        'create': 'datetime',
        'description': 'str',
        'disk_num': 'int',
        'enclosures': 'list[object]',
        'fcports': 'list[HostFcPort]',
        'gateway_ips': 'str',
        'id': 'int',
        'is_master_db': 'bool',
        'memory_kbyte': 'int',
        'model': 'str',
        'name': 'str',
        'os': 'str',
        'private_ip': 'str',
        'protection_domain': 'ProtectionDomainNestview',
        'public_ips': 'str',
        'rack': 'str',
        'roles': 'str',
        'root_disk': 'DiskNestview',
        'serial': 'str',
        'status': 'str',
        'type': 'str',
        'up': 'bool',
        'update': 'datetime',
        'vendor': 'str',
        'samples': 'list[HostStat]'
    }

    attribute_map = {
        'action_status': 'action_status',
        'admin_ip': 'admin_ip',
        'clock_diff': 'clock_diff',
        'cores': 'cores',
        'cpu_model': 'cpu_model',
        'create': 'create',
        'description': 'description',
        'disk_num': 'disk_num',
        'enclosures': 'enclosures',
        'fcports': 'fcports',
        'gateway_ips': 'gateway_ips',
        'id': 'id',
        'is_master_db': 'is_master_db',
        'memory_kbyte': 'memory_kbyte',
        'model': 'model',
        'name': 'name',
        'os': 'os',
        'private_ip': 'private_ip',
        'protection_domain': 'protection_domain',
        'public_ips': 'public_ips',
        'rack': 'rack',
        'roles': 'roles',
        'root_disk': 'root_disk',
        'serial': 'serial',
        'status': 'status',
        'type': 'type',
        'up': 'up',
        'update': 'update',
        'vendor': 'vendor',
        'samples': 'samples'
    }

    def __init__(self, action_status=None, admin_ip=None, clock_diff=None, cores=None, cpu_model=None, create=None, description=None, disk_num=None, enclosures=None, fcports=None, gateway_ips=None, id=None, is_master_db=None, memory_kbyte=None, model=None, name=None, os=None, private_ip=None, protection_domain=None, public_ips=None, rack=None, roles=None, root_disk=None, serial=None, status=None, type=None, up=None, update=None, vendor=None, samples=None):  # noqa: E501
        """HostRecord - a model defined in Swagger"""  # noqa: E501

        self._action_status = None
        self._admin_ip = None
        self._clock_diff = None
        self._cores = None
        self._cpu_model = None
        self._create = None
        self._description = None
        self._disk_num = None
        self._enclosures = None
        self._fcports = None
        self._gateway_ips = None
        self._id = None
        self._is_master_db = None
        self._memory_kbyte = None
        self._model = None
        self._name = None
        self._os = None
        self._private_ip = None
        self._protection_domain = None
        self._public_ips = None
        self._rack = None
        self._roles = None
        self._root_disk = None
        self._serial = None
        self._status = None
        self._type = None
        self._up = None
        self._update = None
        self._vendor = None
        self._samples = None
        self.discriminator = None

        if action_status is not None:
            self.action_status = action_status
        self.admin_ip = admin_ip
        if clock_diff is not None:
            self.clock_diff = clock_diff
        if cores is not None:
            self.cores = cores
        if cpu_model is not None:
            self.cpu_model = cpu_model
        if create is not None:
            self.create = create
        if description is not None:
            self.description = description
        if disk_num is not None:
            self.disk_num = disk_num
        if enclosures is not None:
            self.enclosures = enclosures
        if fcports is not None:
            self.fcports = fcports
        if gateway_ips is not None:
            self.gateway_ips = gateway_ips
        if id is not None:
            self.id = id
        if is_master_db is not None:
            self.is_master_db = is_master_db
        if memory_kbyte is not None:
            self.memory_kbyte = memory_kbyte
        if model is not None:
            self.model = model
        if name is not None:
            self.name = name
        if os is not None:
            self.os = os
        if private_ip is not None:
            self.private_ip = private_ip
        if protection_domain is not None:
            self.protection_domain = protection_domain
        if public_ips is not None:
            self.public_ips = public_ips
        if rack is not None:
            self.rack = rack
        if roles is not None:
            self.roles = roles
        if root_disk is not None:
            self.root_disk = root_disk
        if serial is not None:
            self.serial = serial
        if status is not None:
            self.status = status
        if type is not None:
            self.type = type
        if up is not None:
            self.up = up
        if update is not None:
            self.update = update
        if vendor is not None:
            self.vendor = vendor
        if samples is not None:
            self.samples = samples

    @property
    def action_status(self):
        """Gets the action_status of this HostRecord.  # noqa: E501


        :return: The action_status of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._action_status

    @action_status.setter
    def action_status(self, action_status):
        """Sets the action_status of this HostRecord.


        :param action_status: The action_status of this HostRecord.  # noqa: E501
        :type: str
        """

        self._action_status = action_status

    @property
    def admin_ip(self):
        """Gets the admin_ip of this HostRecord.  # noqa: E501


        :return: The admin_ip of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._admin_ip

    @admin_ip.setter
    def admin_ip(self, admin_ip):
        """Sets the admin_ip of this HostRecord.


        :param admin_ip: The admin_ip of this HostRecord.  # noqa: E501
        :type: str
        """
        if admin_ip is None:
            raise ValueError("Invalid value for `admin_ip`, must not be `None`")  # noqa: E501

        self._admin_ip = admin_ip

    @property
    def clock_diff(self):
        """Gets the clock_diff of this HostRecord.  # noqa: E501

        clock diff in milliseconds with primary host  # noqa: E501

        :return: The clock_diff of this HostRecord.  # noqa: E501
        :rtype: int
        """
        return self._clock_diff

    @clock_diff.setter
    def clock_diff(self, clock_diff):
        """Sets the clock_diff of this HostRecord.

        clock diff in milliseconds with primary host  # noqa: E501

        :param clock_diff: The clock_diff of this HostRecord.  # noqa: E501
        :type: int
        """

        self._clock_diff = clock_diff

    @property
    def cores(self):
        """Gets the cores of this HostRecord.  # noqa: E501


        :return: The cores of this HostRecord.  # noqa: E501
        :rtype: int
        """
        return self._cores

    @cores.setter
    def cores(self, cores):
        """Sets the cores of this HostRecord.


        :param cores: The cores of this HostRecord.  # noqa: E501
        :type: int
        """

        self._cores = cores

    @property
    def cpu_model(self):
        """Gets the cpu_model of this HostRecord.  # noqa: E501


        :return: The cpu_model of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._cpu_model

    @cpu_model.setter
    def cpu_model(self, cpu_model):
        """Sets the cpu_model of this HostRecord.


        :param cpu_model: The cpu_model of this HostRecord.  # noqa: E501
        :type: str
        """

        self._cpu_model = cpu_model

    @property
    def create(self):
        """Gets the create of this HostRecord.  # noqa: E501


        :return: The create of this HostRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this HostRecord.


        :param create: The create of this HostRecord.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def description(self):
        """Gets the description of this HostRecord.  # noqa: E501


        :return: The description of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._description

    @description.setter
    def description(self, description):
        """Sets the description of this HostRecord.


        :param description: The description of this HostRecord.  # noqa: E501
        :type: str
        """

        self._description = description

    @property
    def disk_num(self):
        """Gets the disk_num of this HostRecord.  # noqa: E501


        :return: The disk_num of this HostRecord.  # noqa: E501
        :rtype: int
        """
        return self._disk_num

    @disk_num.setter
    def disk_num(self, disk_num):
        """Sets the disk_num of this HostRecord.


        :param disk_num: The disk_num of this HostRecord.  # noqa: E501
        :type: int
        """

        self._disk_num = disk_num

    @property
    def enclosures(self):
        """Gets the enclosures of this HostRecord.  # noqa: E501


        :return: The enclosures of this HostRecord.  # noqa: E501
        :rtype: list[object]
        """
        return self._enclosures

    @enclosures.setter
    def enclosures(self, enclosures):
        """Sets the enclosures of this HostRecord.


        :param enclosures: The enclosures of this HostRecord.  # noqa: E501
        :type: list[object]
        """

        self._enclosures = enclosures

    @property
    def fcports(self):
        """Gets the fcports of this HostRecord.  # noqa: E501

        fc ports of host  # noqa: E501

        :return: The fcports of this HostRecord.  # noqa: E501
        :rtype: list[HostFcPort]
        """
        return self._fcports

    @fcports.setter
    def fcports(self, fcports):
        """Sets the fcports of this HostRecord.

        fc ports of host  # noqa: E501

        :param fcports: The fcports of this HostRecord.  # noqa: E501
        :type: list[HostFcPort]
        """

        self._fcports = fcports

    @property
    def gateway_ips(self):
        """Gets the gateway_ips of this HostRecord.  # noqa: E501


        :return: The gateway_ips of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._gateway_ips

    @gateway_ips.setter
    def gateway_ips(self, gateway_ips):
        """Sets the gateway_ips of this HostRecord.


        :param gateway_ips: The gateway_ips of this HostRecord.  # noqa: E501
        :type: str
        """

        self._gateway_ips = gateway_ips

    @property
    def id(self):
        """Gets the id of this HostRecord.  # noqa: E501


        :return: The id of this HostRecord.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this HostRecord.


        :param id: The id of this HostRecord.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def is_master_db(self):
        """Gets the is_master_db of this HostRecord.  # noqa: E501


        :return: The is_master_db of this HostRecord.  # noqa: E501
        :rtype: bool
        """
        return self._is_master_db

    @is_master_db.setter
    def is_master_db(self, is_master_db):
        """Sets the is_master_db of this HostRecord.


        :param is_master_db: The is_master_db of this HostRecord.  # noqa: E501
        :type: bool
        """

        self._is_master_db = is_master_db

    @property
    def memory_kbyte(self):
        """Gets the memory_kbyte of this HostRecord.  # noqa: E501


        :return: The memory_kbyte of this HostRecord.  # noqa: E501
        :rtype: int
        """
        return self._memory_kbyte

    @memory_kbyte.setter
    def memory_kbyte(self, memory_kbyte):
        """Sets the memory_kbyte of this HostRecord.


        :param memory_kbyte: The memory_kbyte of this HostRecord.  # noqa: E501
        :type: int
        """

        self._memory_kbyte = memory_kbyte

    @property
    def model(self):
        """Gets the model of this HostRecord.  # noqa: E501


        :return: The model of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._model

    @model.setter
    def model(self, model):
        """Sets the model of this HostRecord.


        :param model: The model of this HostRecord.  # noqa: E501
        :type: str
        """

        self._model = model

    @property
    def name(self):
        """Gets the name of this HostRecord.  # noqa: E501


        :return: The name of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this HostRecord.


        :param name: The name of this HostRecord.  # noqa: E501
        :type: str
        """

        self._name = name

    @property
    def os(self):
        """Gets the os of this HostRecord.  # noqa: E501


        :return: The os of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._os

    @os.setter
    def os(self, os):
        """Sets the os of this HostRecord.


        :param os: The os of this HostRecord.  # noqa: E501
        :type: str
        """

        self._os = os

    @property
    def private_ip(self):
        """Gets the private_ip of this HostRecord.  # noqa: E501


        :return: The private_ip of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._private_ip

    @private_ip.setter
    def private_ip(self, private_ip):
        """Sets the private_ip of this HostRecord.


        :param private_ip: The private_ip of this HostRecord.  # noqa: E501
        :type: str
        """

        self._private_ip = private_ip

    @property
    def protection_domain(self):
        """Gets the protection_domain of this HostRecord.  # noqa: E501

        protection domain of host  # noqa: E501

        :return: The protection_domain of this HostRecord.  # noqa: E501
        :rtype: ProtectionDomainNestview
        """
        return self._protection_domain

    @protection_domain.setter
    def protection_domain(self, protection_domain):
        """Sets the protection_domain of this HostRecord.

        protection domain of host  # noqa: E501

        :param protection_domain: The protection_domain of this HostRecord.  # noqa: E501
        :type: ProtectionDomainNestview
        """

        self._protection_domain = protection_domain

    @property
    def public_ips(self):
        """Gets the public_ips of this HostRecord.  # noqa: E501


        :return: The public_ips of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._public_ips

    @public_ips.setter
    def public_ips(self, public_ips):
        """Sets the public_ips of this HostRecord.


        :param public_ips: The public_ips of this HostRecord.  # noqa: E501
        :type: str
        """

        self._public_ips = public_ips

    @property
    def rack(self):
        """Gets the rack of this HostRecord.  # noqa: E501


        :return: The rack of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._rack

    @rack.setter
    def rack(self, rack):
        """Sets the rack of this HostRecord.


        :param rack: The rack of this HostRecord.  # noqa: E501
        :type: str
        """

        self._rack = rack

    @property
    def roles(self):
        """Gets the roles of this HostRecord.  # noqa: E501


        :return: The roles of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._roles

    @roles.setter
    def roles(self, roles):
        """Sets the roles of this HostRecord.


        :param roles: The roles of this HostRecord.  # noqa: E501
        :type: str
        """

        self._roles = roles

    @property
    def root_disk(self):
        """Gets the root_disk of this HostRecord.  # noqa: E501


        :return: The root_disk of this HostRecord.  # noqa: E501
        :rtype: DiskNestview
        """
        return self._root_disk

    @root_disk.setter
    def root_disk(self, root_disk):
        """Sets the root_disk of this HostRecord.


        :param root_disk: The root_disk of this HostRecord.  # noqa: E501
        :type: DiskNestview
        """

        self._root_disk = root_disk

    @property
    def serial(self):
        """Gets the serial of this HostRecord.  # noqa: E501


        :return: The serial of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._serial

    @serial.setter
    def serial(self, serial):
        """Sets the serial of this HostRecord.


        :param serial: The serial of this HostRecord.  # noqa: E501
        :type: str
        """

        self._serial = serial

    @property
    def status(self):
        """Gets the status of this HostRecord.  # noqa: E501


        :return: The status of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this HostRecord.


        :param status: The status of this HostRecord.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def type(self):
        """Gets the type of this HostRecord.  # noqa: E501


        :return: The type of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._type

    @type.setter
    def type(self, type):
        """Sets the type of this HostRecord.


        :param type: The type of this HostRecord.  # noqa: E501
        :type: str
        """

        self._type = type

    @property
    def up(self):
        """Gets the up of this HostRecord.  # noqa: E501


        :return: The up of this HostRecord.  # noqa: E501
        :rtype: bool
        """
        return self._up

    @up.setter
    def up(self, up):
        """Sets the up of this HostRecord.


        :param up: The up of this HostRecord.  # noqa: E501
        :type: bool
        """

        self._up = up

    @property
    def update(self):
        """Gets the update of this HostRecord.  # noqa: E501


        :return: The update of this HostRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._update

    @update.setter
    def update(self, update):
        """Sets the update of this HostRecord.


        :param update: The update of this HostRecord.  # noqa: E501
        :type: datetime
        """

        self._update = update

    @property
    def vendor(self):
        """Gets the vendor of this HostRecord.  # noqa: E501


        :return: The vendor of this HostRecord.  # noqa: E501
        :rtype: str
        """
        return self._vendor

    @vendor.setter
    def vendor(self, vendor):
        """Sets the vendor of this HostRecord.


        :param vendor: The vendor of this HostRecord.  # noqa: E501
        :type: str
        """

        self._vendor = vendor

    @property
    def samples(self):
        """Gets the samples of this HostRecord.  # noqa: E501


        :return: The samples of this HostRecord.  # noqa: E501
        :rtype: list[HostStat]
        """
        return self._samples

    @samples.setter
    def samples(self, samples):
        """Sets the samples of this HostRecord.


        :param samples: The samples of this HostRecord.  # noqa: E501
        :type: list[HostStat]
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
        if not isinstance(other, HostRecord):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
