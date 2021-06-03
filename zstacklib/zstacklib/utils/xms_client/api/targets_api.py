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


class TargetsApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def create_target(self, target, **kwargs):  # noqa: E501
        """create_target  # noqa: E501

        Create target  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_target(target, async=True)
        >>> result = thread.get()

        :param async bool
        :param TargetCreateReq target: target info (required)
        :return: TargetResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_target_with_http_info(target, **kwargs)  # noqa: E501
        else:
            (data) = self.create_target_with_http_info(target, **kwargs)  # noqa: E501
            return data

    def create_target_with_http_info(self, target, **kwargs):  # noqa: E501
        """create_target  # noqa: E501

        Create target  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_target_with_http_info(target, async=True)
        >>> result = thread.get()

        :param async bool
        :param TargetCreateReq target: target info (required)
        :return: TargetResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['target']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method create_target" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'target' is set
        if ('target' not in params or
                params['target'] is None):
            raise ValueError("Missing the required parameter `target` when calling `create_target`")  # noqa: E501

        collection_formats = {}

        path_params = {}

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'target' in params:
            body_params = params['target']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/targets/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TargetResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def delete_target(self, target_id, **kwargs):  # noqa: E501
        """delete_target  # noqa: E501

        delete target  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_target(target_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int target_id: target id (required)
        :param bool force: force delete or not
        :return: TargetResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_target_with_http_info(target_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_target_with_http_info(target_id, **kwargs)  # noqa: E501
            return data

    def delete_target_with_http_info(self, target_id, **kwargs):  # noqa: E501
        """delete_target  # noqa: E501

        delete target  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_target_with_http_info(target_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int target_id: target id (required)
        :param bool force: force delete or not
        :return: TargetResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['target_id', 'force']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_target" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'target_id' is set
        if ('target_id' not in params or
                params['target_id'] is None):
            raise ValueError("Missing the required parameter `target_id` when calling `delete_target`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'target_id' in params:
            path_params['target_id'] = params['target_id']  # noqa: E501

        query_params = []
        if 'force' in params:
            query_params.append(('force', params['force']))  # noqa: E501

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
            '/targets/{target_id}', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TargetResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_targets(self, **kwargs):  # noqa: E501
        """list_targets  # noqa: E501

        List all targets in the cluster  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_targets(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int host_id: host id
        :param int access_path_id: access path id
        :param str q: query param of search
        :param str sort: sort param of search
        :return: TargetsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_targets_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_targets_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_targets_with_http_info(self, **kwargs):  # noqa: E501
        """list_targets  # noqa: E501

        List all targets in the cluster  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_targets_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int host_id: host id
        :param int access_path_id: access path id
        :param str q: query param of search
        :param str sort: sort param of search
        :return: TargetsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'host_id', 'access_path_id', 'q', 'sort']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_targets" % key
                )
            params[key] = val
        del params['kwargs']

        collection_formats = {}

        path_params = {}

        query_params = []
        if 'limit' in params:
            query_params.append(('limit', params['limit']))  # noqa: E501
        if 'offset' in params:
            query_params.append(('offset', params['offset']))  # noqa: E501
        if 'host_id' in params:
            query_params.append(('host_id', params['host_id']))  # noqa: E501
        if 'access_path_id' in params:
            query_params.append(('access_path_id', params['access_path_id']))  # noqa: E501
        if 'q' in params:
            query_params.append(('q', params['q']))  # noqa: E501
        if 'sort' in params:
            query_params.append(('sort', params['sort']))  # noqa: E501

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
            '/targets/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TargetsResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
