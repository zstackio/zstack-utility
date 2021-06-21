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


class ClientGroupsApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def create_client_group(self, client, **kwargs):  # noqa: E501
        """create_client_group  # noqa: E501

        Create a client group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_client_group(client, async=True)
        >>> result = thread.get()

        :param async bool
        :param ClientGroupCreateReq client: client group info (required)
        :return: ClientGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_client_group_with_http_info(client, **kwargs)  # noqa: E501
        else:
            (data) = self.create_client_group_with_http_info(client, **kwargs)  # noqa: E501
            return data

    def create_client_group_with_http_info(self, client, **kwargs):  # noqa: E501
        """create_client_group  # noqa: E501

        Create a client group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_client_group_with_http_info(client, async=True)
        >>> result = thread.get()

        :param async bool
        :param ClientGroupCreateReq client: client group info (required)
        :return: ClientGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['client']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method create_client_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'client' is set
        if ('client' not in params or
                params['client'] is None):
            raise ValueError("Missing the required parameter `client` when calling `create_client_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'client' in params:
            body_params = params['client']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/client-groups/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='ClientGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def delete_client_group(self, client_group_id, **kwargs):  # noqa: E501
        """delete_client_group  # noqa: E501

        Delete a client  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_client_group(client_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int client_group_id: client group id (required)
        :return: None
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_client_group_with_http_info(client_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_client_group_with_http_info(client_group_id, **kwargs)  # noqa: E501
            return data

    def delete_client_group_with_http_info(self, client_group_id, **kwargs):  # noqa: E501
        """delete_client_group  # noqa: E501

        Delete a client  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_client_group_with_http_info(client_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int client_group_id: client group id (required)
        :return: None
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['client_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_client_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'client_group_id' is set
        if ('client_group_id' not in params or
                params['client_group_id'] is None):
            raise ValueError("Missing the required parameter `client_group_id` when calling `delete_client_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'client_group_id' in params:
            path_params['client_group_id'] = params['client_group_id']  # noqa: E501

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
            '/client-groups/{client_group_id}', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type=None,  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_client_group(self, client_group_id, **kwargs):  # noqa: E501
        """get_client_group  # noqa: E501

        get a client group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_client_group(client_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int client_group_id: client group id (required)
        :return: ClientGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_client_group_with_http_info(client_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_client_group_with_http_info(client_group_id, **kwargs)  # noqa: E501
            return data

    def get_client_group_with_http_info(self, client_group_id, **kwargs):  # noqa: E501
        """get_client_group  # noqa: E501

        get a client group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_client_group_with_http_info(client_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int client_group_id: client group id (required)
        :return: ClientGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['client_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_client_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'client_group_id' is set
        if ('client_group_id' not in params or
                params['client_group_id'] is None):
            raise ValueError("Missing the required parameter `client_group_id` when calling `get_client_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'client_group_id' in params:
            path_params['client_group_id'] = params['client_group_id']  # noqa: E501

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
            '/client-groups/{client_group_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='ClientGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_client_groups(self, **kwargs):  # noqa: E501
        """list_client_groups  # noqa: E501

        List client groups  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_client_groups(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int block_volume_id: related block volume id
        :param str q: query param of search
        :param str sort: sort param of search
        :return: ClientGroupsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_client_groups_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_client_groups_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_client_groups_with_http_info(self, **kwargs):  # noqa: E501
        """list_client_groups  # noqa: E501

        List client groups  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_client_groups_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int block_volume_id: related block volume id
        :param str q: query param of search
        :param str sort: sort param of search
        :return: ClientGroupsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'block_volume_id', 'q', 'sort']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_client_groups" % key
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
        if 'block_volume_id' in params:
            query_params.append(('block_volume_id', params['block_volume_id']))  # noqa: E501
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
            '/client-groups/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='ClientGroupsResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_client_group(self, client_group_id, client, **kwargs):  # noqa: E501
        """update_client_group  # noqa: E501

        update client group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_client_group(client_group_id, client, async=True)
        >>> result = thread.get()

        :param async bool
        :param int client_group_id: client group id (required)
        :param ClientGroupUpdateReq client: client group info (required)
        :return: ClientGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_client_group_with_http_info(client_group_id, client, **kwargs)  # noqa: E501
        else:
            (data) = self.update_client_group_with_http_info(client_group_id, client, **kwargs)  # noqa: E501
            return data

    def update_client_group_with_http_info(self, client_group_id, client, **kwargs):  # noqa: E501
        """update_client_group  # noqa: E501

        update client group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_client_group_with_http_info(client_group_id, client, async=True)
        >>> result = thread.get()

        :param async bool
        :param int client_group_id: client group id (required)
        :param ClientGroupUpdateReq client: client group info (required)
        :return: ClientGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['client_group_id', 'client']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_client_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'client_group_id' is set
        if ('client_group_id' not in params or
                params['client_group_id'] is None):
            raise ValueError("Missing the required parameter `client_group_id` when calling `update_client_group`")  # noqa: E501
        # verify the required parameter 'client' is set
        if ('client' not in params or
                params['client'] is None):
            raise ValueError("Missing the required parameter `client` when calling `update_client_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'client_group_id' in params:
            path_params['client_group_id'] = params['client_group_id']  # noqa: E501

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'client' in params:
            body_params = params['client']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/client-groups/{client_group_id}', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='ClientGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
