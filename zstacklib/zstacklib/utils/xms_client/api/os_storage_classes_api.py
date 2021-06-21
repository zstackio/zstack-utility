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


class OsStorageClassesApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def create_os_storage_class(self, body, **kwargs):  # noqa: E501
        """create_os_storage_class  # noqa: E501

        Create os storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_os_storage_class(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param OSStorageClassCreateReq body: storage class info (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_os_storage_class_with_http_info(body, **kwargs)  # noqa: E501
        else:
            (data) = self.create_os_storage_class_with_http_info(body, **kwargs)  # noqa: E501
            return data

    def create_os_storage_class_with_http_info(self, body, **kwargs):  # noqa: E501
        """create_os_storage_class  # noqa: E501

        Create os storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_os_storage_class_with_http_info(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param OSStorageClassCreateReq body: storage class info (required)
        :return: OSStorageClassResp
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
                    " to method create_os_storage_class" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `create_os_storage_class`")  # noqa: E501

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
            '/os-storage-classes/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='OSStorageClassResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def delete_os_storage_class(self, storage_class_id, **kwargs):  # noqa: E501
        """delete_os_storage_class  # noqa: E501

        Delete an os storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_os_storage_class(storage_class_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int storage_class_id: storage class id (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_os_storage_class_with_http_info(storage_class_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_os_storage_class_with_http_info(storage_class_id, **kwargs)  # noqa: E501
            return data

    def delete_os_storage_class_with_http_info(self, storage_class_id, **kwargs):  # noqa: E501
        """delete_os_storage_class  # noqa: E501

        Delete an os storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_os_storage_class_with_http_info(storage_class_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int storage_class_id: storage class id (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['storage_class_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_os_storage_class" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'storage_class_id' is set
        if ('storage_class_id' not in params or
                params['storage_class_id'] is None):
            raise ValueError("Missing the required parameter `storage_class_id` when calling `delete_os_storage_class`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'storage_class_id' in params:
            path_params['storage_class_id'] = params['storage_class_id']  # noqa: E501

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
            '/os-storage-classes/{storage_class_id}', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='OSStorageClassResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_os_storage_class(self, storage_class_id, **kwargs):  # noqa: E501
        """get_os_storage_class  # noqa: E501

        Get an os storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_os_storage_class(storage_class_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param str storage_class_id: storage class id (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_os_storage_class_with_http_info(storage_class_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_os_storage_class_with_http_info(storage_class_id, **kwargs)  # noqa: E501
            return data

    def get_os_storage_class_with_http_info(self, storage_class_id, **kwargs):  # noqa: E501
        """get_os_storage_class  # noqa: E501

        Get an os storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_os_storage_class_with_http_info(storage_class_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param str storage_class_id: storage class id (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['storage_class_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_os_storage_class" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'storage_class_id' is set
        if ('storage_class_id' not in params or
                params['storage_class_id'] is None):
            raise ValueError("Missing the required parameter `storage_class_id` when calling `get_os_storage_class`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'storage_class_id' in params:
            path_params['storage_class_id'] = params['storage_class_id']  # noqa: E501

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
            '/os-storage-classes/{storage_class_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='OSStorageClassResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_os_storage_classes(self, **kwargs):  # noqa: E501
        """list_os_storage_classes  # noqa: E501

        List os storage classes  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_os_storage_classes(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int os_policy_id: os policy id
        :return: OSStorageClassesResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_os_storage_classes_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_os_storage_classes_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_os_storage_classes_with_http_info(self, **kwargs):  # noqa: E501
        """list_os_storage_classes  # noqa: E501

        List os storage classes  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_os_storage_classes_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int os_policy_id: os policy id
        :return: OSStorageClassesResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'os_policy_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_os_storage_classes" % key
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
        if 'os_policy_id' in params:
            query_params.append(('os_policy_id', params['os_policy_id']))  # noqa: E501

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
            '/os-storage-classes/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='OSStorageClassesResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_os_storage_class(self, storage_class_id, body, **kwargs):  # noqa: E501
        """update_os_storage_class  # noqa: E501

        update storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_os_storage_class(storage_class_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int storage_class_id: storage class id (required)
        :param OSStorageClassUpdateReq body: storage class info (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_os_storage_class_with_http_info(storage_class_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.update_os_storage_class_with_http_info(storage_class_id, body, **kwargs)  # noqa: E501
            return data

    def update_os_storage_class_with_http_info(self, storage_class_id, body, **kwargs):  # noqa: E501
        """update_os_storage_class  # noqa: E501

        update storage class  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_os_storage_class_with_http_info(storage_class_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int storage_class_id: storage class id (required)
        :param OSStorageClassUpdateReq body: storage class info (required)
        :return: OSStorageClassResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['storage_class_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_os_storage_class" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'storage_class_id' is set
        if ('storage_class_id' not in params or
                params['storage_class_id'] is None):
            raise ValueError("Missing the required parameter `storage_class_id` when calling `update_os_storage_class`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `update_os_storage_class`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'storage_class_id' in params:
            path_params['storage_class_id'] = params['storage_class_id']  # noqa: E501

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
            '/os-storage-classes/{storage_class_id}', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='OSStorageClassResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
