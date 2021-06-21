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


class TrashResourcesApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def delete_trash_resource(self, trash_resource_id, **kwargs):  # noqa: E501
        """delete_trash_resource  # noqa: E501

        Delete trash resource  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_trash_resource(trash_resource_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int trash_resource_id: trash resource id (required)
        :return: TrashResourceResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_trash_resource_with_http_info(trash_resource_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_trash_resource_with_http_info(trash_resource_id, **kwargs)  # noqa: E501
            return data

    def delete_trash_resource_with_http_info(self, trash_resource_id, **kwargs):  # noqa: E501
        """delete_trash_resource  # noqa: E501

        Delete trash resource  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_trash_resource_with_http_info(trash_resource_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int trash_resource_id: trash resource id (required)
        :return: TrashResourceResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['trash_resource_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_trash_resource" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'trash_resource_id' is set
        if ('trash_resource_id' not in params or
                params['trash_resource_id'] is None):
            raise ValueError("Missing the required parameter `trash_resource_id` when calling `delete_trash_resource`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'trash_resource_id' in params:
            path_params['trash_resource_id'] = params['trash_resource_id']  # noqa: E501

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
            '/trash-resources/{trash_resource_id}', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TrashResourceResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_trash_resource(self, trash_resource_id, **kwargs):  # noqa: E501
        """get_trash_resource  # noqa: E501

        get a trash resource  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_trash_resource(trash_resource_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int trash_resource_id: trash resource id (required)
        :return: TrashResourceResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_trash_resource_with_http_info(trash_resource_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_trash_resource_with_http_info(trash_resource_id, **kwargs)  # noqa: E501
            return data

    def get_trash_resource_with_http_info(self, trash_resource_id, **kwargs):  # noqa: E501
        """get_trash_resource  # noqa: E501

        get a trash resource  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_trash_resource_with_http_info(trash_resource_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int trash_resource_id: trash resource id (required)
        :return: TrashResourceResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['trash_resource_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_trash_resource" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'trash_resource_id' is set
        if ('trash_resource_id' not in params or
                params['trash_resource_id'] is None):
            raise ValueError("Missing the required parameter `trash_resource_id` when calling `get_trash_resource`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'trash_resource_id' in params:
            path_params['trash_resource_id'] = params['trash_resource_id']  # noqa: E501

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
            '/trash-resources/{trash_resource_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TrashResourceResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_trash_resources(self, **kwargs):  # noqa: E501
        """list_trash_resources  # noqa: E501

        List trash resources  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_trash_resources(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param str type: the type of trash resources
        :param str q: query param of search
        :param str sort: sort param of search
        :return: TrashResourcesResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_trash_resources_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_trash_resources_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_trash_resources_with_http_info(self, **kwargs):  # noqa: E501
        """list_trash_resources  # noqa: E501

        List trash resources  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_trash_resources_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param str type: the type of trash resources
        :param str q: query param of search
        :param str sort: sort param of search
        :return: TrashResourcesResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'type', 'q', 'sort']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_trash_resources" % key
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
        if 'type' in params:
            query_params.append(('type', params['type']))  # noqa: E501
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
            '/trash-resources/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TrashResourcesResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def restore_trash_resource(self, trash_resource_id, **kwargs):  # noqa: E501
        """restore_trash_resource  # noqa: E501

        Restore trash resource  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.restore_trash_resource(trash_resource_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int trash_resource_id: trash resource id (required)
        :return: TrashResourceResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.restore_trash_resource_with_http_info(trash_resource_id, **kwargs)  # noqa: E501
        else:
            (data) = self.restore_trash_resource_with_http_info(trash_resource_id, **kwargs)  # noqa: E501
            return data

    def restore_trash_resource_with_http_info(self, trash_resource_id, **kwargs):  # noqa: E501
        """restore_trash_resource  # noqa: E501

        Restore trash resource  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.restore_trash_resource_with_http_info(trash_resource_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int trash_resource_id: trash resource id (required)
        :return: TrashResourceResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['trash_resource_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method restore_trash_resource" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'trash_resource_id' is set
        if ('trash_resource_id' not in params or
                params['trash_resource_id'] is None):
            raise ValueError("Missing the required parameter `trash_resource_id` when calling `restore_trash_resource`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'trash_resource_id' in params:
            path_params['trash_resource_id'] = params['trash_resource_id']  # noqa: E501

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
            '/trash-resources/{trash_resource_id}:restore', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='TrashResourceResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
