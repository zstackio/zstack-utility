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

# from zstacklib.utils.xms_client.models.action_log import ActionLog  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.error_record import ErrorRecord  # noqa: F401,E501
# from zstacklib.utils.xms_client.models.user_nestview import UserNestview  # noqa: F401,E501


class ActionLogRecord(object):
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
        'action': 'str',
        'client_ip': 'str',
        'create': 'datetime',
        'finish': 'datetime',
        'id': 'int',
        'message': 'str',
        'new_data': 'object',
        'old_data': 'object',
        'parameter': 'str',
        'related_resources': 'list[object]',
        'resource_id': 'int',
        'resource_type': 'str',
        'start': 'datetime',
        'status': 'str',
        'user': 'UserNestview',
        'error_records': 'list[ErrorRecord]'
    }

    attribute_map = {
        'action': 'action',
        'client_ip': 'client_ip',
        'create': 'create',
        'finish': 'finish',
        'id': 'id',
        'message': 'message',
        'new_data': 'new_data',
        'old_data': 'old_data',
        'parameter': 'parameter',
        'related_resources': 'related_resources',
        'resource_id': 'resource_id',
        'resource_type': 'resource_type',
        'start': 'start',
        'status': 'status',
        'user': 'user',
        'error_records': 'error_records'
    }

    def __init__(self, action=None, client_ip=None, create=None, finish=None, id=None, message=None, new_data=None, old_data=None, parameter=None, related_resources=None, resource_id=None, resource_type=None, start=None, status=None, user=None, error_records=None):  # noqa: E501
        """ActionLogRecord - a model defined in Swagger"""  # noqa: E501

        self._action = None
        self._client_ip = None
        self._create = None
        self._finish = None
        self._id = None
        self._message = None
        self._new_data = None
        self._old_data = None
        self._parameter = None
        self._related_resources = None
        self._resource_id = None
        self._resource_type = None
        self._start = None
        self._status = None
        self._user = None
        self._error_records = None
        self.discriminator = None

        if action is not None:
            self.action = action
        if client_ip is not None:
            self.client_ip = client_ip
        if create is not None:
            self.create = create
        if finish is not None:
            self.finish = finish
        if id is not None:
            self.id = id
        if message is not None:
            self.message = message
        if new_data is not None:
            self.new_data = new_data
        if old_data is not None:
            self.old_data = old_data
        if parameter is not None:
            self.parameter = parameter
        if related_resources is not None:
            self.related_resources = related_resources
        if resource_id is not None:
            self.resource_id = resource_id
        if resource_type is not None:
            self.resource_type = resource_type
        if start is not None:
            self.start = start
        if status is not None:
            self.status = status
        if user is not None:
            self.user = user
        if error_records is not None:
            self.error_records = error_records

    @property
    def action(self):
        """Gets the action of this ActionLogRecord.  # noqa: E501


        :return: The action of this ActionLogRecord.  # noqa: E501
        :rtype: str
        """
        return self._action

    @action.setter
    def action(self, action):
        """Sets the action of this ActionLogRecord.


        :param action: The action of this ActionLogRecord.  # noqa: E501
        :type: str
        """

        self._action = action

    @property
    def client_ip(self):
        """Gets the client_ip of this ActionLogRecord.  # noqa: E501


        :return: The client_ip of this ActionLogRecord.  # noqa: E501
        :rtype: str
        """
        return self._client_ip

    @client_ip.setter
    def client_ip(self, client_ip):
        """Sets the client_ip of this ActionLogRecord.


        :param client_ip: The client_ip of this ActionLogRecord.  # noqa: E501
        :type: str
        """

        self._client_ip = client_ip

    @property
    def create(self):
        """Gets the create of this ActionLogRecord.  # noqa: E501


        :return: The create of this ActionLogRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._create

    @create.setter
    def create(self, create):
        """Sets the create of this ActionLogRecord.


        :param create: The create of this ActionLogRecord.  # noqa: E501
        :type: datetime
        """

        self._create = create

    @property
    def finish(self):
        """Gets the finish of this ActionLogRecord.  # noqa: E501


        :return: The finish of this ActionLogRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._finish

    @finish.setter
    def finish(self, finish):
        """Sets the finish of this ActionLogRecord.


        :param finish: The finish of this ActionLogRecord.  # noqa: E501
        :type: datetime
        """

        self._finish = finish

    @property
    def id(self):
        """Gets the id of this ActionLogRecord.  # noqa: E501


        :return: The id of this ActionLogRecord.  # noqa: E501
        :rtype: int
        """
        return self._id

    @id.setter
    def id(self, id):
        """Sets the id of this ActionLogRecord.


        :param id: The id of this ActionLogRecord.  # noqa: E501
        :type: int
        """

        self._id = id

    @property
    def message(self):
        """Gets the message of this ActionLogRecord.  # noqa: E501


        :return: The message of this ActionLogRecord.  # noqa: E501
        :rtype: str
        """
        return self._message

    @message.setter
    def message(self, message):
        """Sets the message of this ActionLogRecord.


        :param message: The message of this ActionLogRecord.  # noqa: E501
        :type: str
        """

        self._message = message

    @property
    def new_data(self):
        """Gets the new_data of this ActionLogRecord.  # noqa: E501


        :return: The new_data of this ActionLogRecord.  # noqa: E501
        :rtype: object
        """
        return self._new_data

    @new_data.setter
    def new_data(self, new_data):
        """Sets the new_data of this ActionLogRecord.


        :param new_data: The new_data of this ActionLogRecord.  # noqa: E501
        :type: object
        """

        self._new_data = new_data

    @property
    def old_data(self):
        """Gets the old_data of this ActionLogRecord.  # noqa: E501


        :return: The old_data of this ActionLogRecord.  # noqa: E501
        :rtype: object
        """
        return self._old_data

    @old_data.setter
    def old_data(self, old_data):
        """Sets the old_data of this ActionLogRecord.


        :param old_data: The old_data of this ActionLogRecord.  # noqa: E501
        :type: object
        """

        self._old_data = old_data

    @property
    def parameter(self):
        """Gets the parameter of this ActionLogRecord.  # noqa: E501


        :return: The parameter of this ActionLogRecord.  # noqa: E501
        :rtype: str
        """
        return self._parameter

    @parameter.setter
    def parameter(self, parameter):
        """Sets the parameter of this ActionLogRecord.


        :param parameter: The parameter of this ActionLogRecord.  # noqa: E501
        :type: str
        """

        self._parameter = parameter

    @property
    def related_resources(self):
        """Gets the related_resources of this ActionLogRecord.  # noqa: E501


        :return: The related_resources of this ActionLogRecord.  # noqa: E501
        :rtype: list[object]
        """
        return self._related_resources

    @related_resources.setter
    def related_resources(self, related_resources):
        """Sets the related_resources of this ActionLogRecord.


        :param related_resources: The related_resources of this ActionLogRecord.  # noqa: E501
        :type: list[object]
        """

        self._related_resources = related_resources

    @property
    def resource_id(self):
        """Gets the resource_id of this ActionLogRecord.  # noqa: E501


        :return: The resource_id of this ActionLogRecord.  # noqa: E501
        :rtype: int
        """
        return self._resource_id

    @resource_id.setter
    def resource_id(self, resource_id):
        """Sets the resource_id of this ActionLogRecord.


        :param resource_id: The resource_id of this ActionLogRecord.  # noqa: E501
        :type: int
        """

        self._resource_id = resource_id

    @property
    def resource_type(self):
        """Gets the resource_type of this ActionLogRecord.  # noqa: E501


        :return: The resource_type of this ActionLogRecord.  # noqa: E501
        :rtype: str
        """
        return self._resource_type

    @resource_type.setter
    def resource_type(self, resource_type):
        """Sets the resource_type of this ActionLogRecord.


        :param resource_type: The resource_type of this ActionLogRecord.  # noqa: E501
        :type: str
        """

        self._resource_type = resource_type

    @property
    def start(self):
        """Gets the start of this ActionLogRecord.  # noqa: E501


        :return: The start of this ActionLogRecord.  # noqa: E501
        :rtype: datetime
        """
        return self._start

    @start.setter
    def start(self, start):
        """Sets the start of this ActionLogRecord.


        :param start: The start of this ActionLogRecord.  # noqa: E501
        :type: datetime
        """

        self._start = start

    @property
    def status(self):
        """Gets the status of this ActionLogRecord.  # noqa: E501


        :return: The status of this ActionLogRecord.  # noqa: E501
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this ActionLogRecord.


        :param status: The status of this ActionLogRecord.  # noqa: E501
        :type: str
        """

        self._status = status

    @property
    def user(self):
        """Gets the user of this ActionLogRecord.  # noqa: E501


        :return: The user of this ActionLogRecord.  # noqa: E501
        :rtype: UserNestview
        """
        return self._user

    @user.setter
    def user(self, user):
        """Sets the user of this ActionLogRecord.


        :param user: The user of this ActionLogRecord.  # noqa: E501
        :type: UserNestview
        """

        self._user = user

    @property
    def error_records(self):
        """Gets the error_records of this ActionLogRecord.  # noqa: E501


        :return: The error_records of this ActionLogRecord.  # noqa: E501
        :rtype: list[ErrorRecord]
        """
        return self._error_records

    @error_records.setter
    def error_records(self, error_records):
        """Sets the error_records of this ActionLogRecord.


        :param error_records: The error_records of this ActionLogRecord.  # noqa: E501
        :type: list[ErrorRecord]
        """

        self._error_records = error_records

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
        if not isinstance(other, ActionLogRecord):
            return False

        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        return not self == other
