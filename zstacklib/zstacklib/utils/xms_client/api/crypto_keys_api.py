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


class CryptoKeysApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def create_crypto_key(self, name, **kwargs):  # noqa: E501
        """create_crypto_key  # noqa: E501

        Create a crypto key  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_crypto_key(name, async=True)
        >>> result = thread.get()

        :param async bool
        :param str name: crypto key name (required)
        :param str key: crypto key
        :return: CryptoKeyResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_crypto_key_with_http_info(name, **kwargs)  # noqa: E501
        else:
            (data) = self.create_crypto_key_with_http_info(name, **kwargs)  # noqa: E501
            return data

    def create_crypto_key_with_http_info(self, name, **kwargs):  # noqa: E501
        """create_crypto_key  # noqa: E501

        Create a crypto key  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_crypto_key_with_http_info(name, async=True)
        >>> result = thread.get()

        :param async bool
        :param str name: crypto key name (required)
        :param str key: crypto key
        :return: CryptoKeyResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['name', 'key']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method create_crypto_key" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'name' is set
        if ('name' not in params or
                params['name'] is None):
            raise ValueError("Missing the required parameter `name` when calling `create_crypto_key`")  # noqa: E501

        collection_formats = {}

        path_params = {}

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}
        if 'name' in params:
            form_params.append(('name', params['name']))  # noqa: E501
        if 'key' in params:
            form_params.append(('key', params['key']))  # noqa: E501

        body_params = None
        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['multipart/form-data'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/crypto-keys/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='CryptoKeyResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def download_crypto_key(self, key_id, **kwargs):  # noqa: E501
        """download_crypto_key  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.download_crypto_key(key_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int key_id: crypto key id (required)
        :param str password: password
        :return: str
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.download_crypto_key_with_http_info(key_id, **kwargs)  # noqa: E501
        else:
            (data) = self.download_crypto_key_with_http_info(key_id, **kwargs)  # noqa: E501
            return data

    def download_crypto_key_with_http_info(self, key_id, **kwargs):  # noqa: E501
        """download_crypto_key  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.download_crypto_key_with_http_info(key_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int key_id: crypto key id (required)
        :param str password: password
        :return: str
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['key_id', 'password']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method download_crypto_key" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'key_id' is set
        if ('key_id' not in params or
                params['key_id'] is None):
            raise ValueError("Missing the required parameter `key_id` when calling `download_crypto_key`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'key_id' in params:
            path_params['key_id'] = params['key_id']  # noqa: E501

        query_params = []
        if 'password' in params:
            query_params.append(('password', params['password']))  # noqa: E501

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/octet-stream'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/octet-stream'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/crypto-keys/{key_id}/key', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='str',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_crypto_key(self, key_id, **kwargs):  # noqa: E501
        """get_crypto_key  # noqa: E501

        Get a crypto key  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_crypto_key(key_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int key_id: crypto key id (required)
        :return: CryptoKeyResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_crypto_key_with_http_info(key_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_crypto_key_with_http_info(key_id, **kwargs)  # noqa: E501
            return data

    def get_crypto_key_with_http_info(self, key_id, **kwargs):  # noqa: E501
        """get_crypto_key  # noqa: E501

        Get a crypto key  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_crypto_key_with_http_info(key_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int key_id: crypto key id (required)
        :return: CryptoKeyResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['key_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_crypto_key" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'key_id' is set
        if ('key_id' not in params or
                params['key_id'] is None):
            raise ValueError("Missing the required parameter `key_id` when calling `get_crypto_key`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'key_id' in params:
            path_params['key_id'] = params['key_id']  # noqa: E501

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
            '/crypto-keys/{key_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='CryptoKeyResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_crypto_keys(self, **kwargs):  # noqa: E501
        """list_crypto_keys  # noqa: E501

        List crypto keys  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_crypto_keys(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param str q: query param of search
        :param str sort: sort param of search
        :return: CryptoKeysResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_crypto_keys_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_crypto_keys_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_crypto_keys_with_http_info(self, **kwargs):  # noqa: E501
        """list_crypto_keys  # noqa: E501

        List crypto keys  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_crypto_keys_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param str q: query param of search
        :param str sort: sort param of search
        :return: CryptoKeysResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'q', 'sort']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_crypto_keys" % key
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
            '/crypto-keys/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='CryptoKeysResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_crypto_key(self, key_id, body, **kwargs):  # noqa: E501
        """update_crypto_key  # noqa: E501

        Update a crypto key  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_crypto_key(key_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int key_id: crypto key id (required)
        :param CryptoKeyUpdateReq body: crypto key info (required)
        :return: CryptoKeyResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_crypto_key_with_http_info(key_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.update_crypto_key_with_http_info(key_id, body, **kwargs)  # noqa: E501
            return data

    def update_crypto_key_with_http_info(self, key_id, body, **kwargs):  # noqa: E501
        """update_crypto_key  # noqa: E501

        Update a crypto key  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_crypto_key_with_http_info(key_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int key_id: crypto key id (required)
        :param CryptoKeyUpdateReq body: crypto key info (required)
        :return: CryptoKeyResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['key_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_crypto_key" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'key_id' is set
        if ('key_id' not in params or
                params['key_id'] is None):
            raise ValueError("Missing the required parameter `key_id` when calling `update_crypto_key`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `update_crypto_key`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'key_id' in params:
            path_params['key_id'] = params['key_id']  # noqa: E501

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
            '/crypto-keys/{key_id}', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='CryptoKeyResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
