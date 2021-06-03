# coding: utf-8

"""
    XMS API

    XMS is the controller of distributed storage system  # noqa: E501

    OpenAPI spec version: SDS_4.2.300.2
    
    Generated by: https://github.com/swagger-api/swagger-codegen.git
"""


from __future__ import absolute_import

import re  # noqa: F401

# python 2 and python 3 compatibility library
import six

from zstacklib.utils.xms_client.api_client import ApiClient


class HostValidatorsApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def create_host_validator(self, body, **kwargs):  # noqa: E501
        """create_host_validator  # noqa: E501

        Create host validator  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_host_validator(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param HostValidatorCreateReq body: host validator info (required)
        :return: HostValidatorResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_host_validator_with_http_info(body, **kwargs)  # noqa: E501
        else:
            (data) = self.create_host_validator_with_http_info(body, **kwargs)  # noqa: E501
            return data

    def create_host_validator_with_http_info(self, body, **kwargs):  # noqa: E501
        """create_host_validator  # noqa: E501

        Create host validator  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_host_validator_with_http_info(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param HostValidatorCreateReq body: host validator info (required)
        :return: HostValidatorResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method create_host_validator" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `create_host_validator`")  # noqa: E501

        collection_formats = {}

        path_params = {}

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'body' in params:
            body_params = params['body']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/host-validators/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='HostValidatorResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_host_validator(self, host_validator_id, **kwargs):  # noqa: E501
        """get_host_validator  # noqa: E501

        Get host validator  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_host_validator(host_validator_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int host_validator_id: host validator id (required)
        :return: HostValidatorResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_host_validator_with_http_info(host_validator_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_host_validator_with_http_info(host_validator_id, **kwargs)  # noqa: E501
            return data

    def get_host_validator_with_http_info(self, host_validator_id, **kwargs):  # noqa: E501
        """get_host_validator  # noqa: E501

        Get host validator  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_host_validator_with_http_info(host_validator_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int host_validator_id: host validator id (required)
        :return: HostValidatorResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['host_validator_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_host_validator" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'host_validator_id' is set
        if ('host_validator_id' not in params or
                params['host_validator_id'] is None):
            raise ValueError("Missing the required parameter `host_validator_id` when calling `get_host_validator`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'host_validator_id' in params:
            path_params['host_validator_id'] = params['host_validator_id']  # noqa: E501

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/host-validators/{host_validator_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='HostValidatorResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
