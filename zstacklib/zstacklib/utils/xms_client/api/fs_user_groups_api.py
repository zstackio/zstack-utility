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


class FsUserGroupsApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def add_fs_users(self, fs_user_group_id, body, **kwargs):  # noqa: E501
        """add_fs_users  # noqa: E501

        add users to file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.add_fs_users(fs_user_group_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :param FSUserGroupAddUsersReq body: users info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.add_fs_users_with_http_info(fs_user_group_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.add_fs_users_with_http_info(fs_user_group_id, body, **kwargs)  # noqa: E501
            return data

    def add_fs_users_with_http_info(self, fs_user_group_id, body, **kwargs):  # noqa: E501
        """add_fs_users  # noqa: E501

        add users to file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.add_fs_users_with_http_info(fs_user_group_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :param FSUserGroupAddUsersReq body: users info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_user_group_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method add_fs_users" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_user_group_id' is set
        if ('fs_user_group_id' not in params or
                params['fs_user_group_id'] is None):
            raise ValueError("Missing the required parameter `fs_user_group_id` when calling `add_fs_users`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `add_fs_users`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_user_group_id' in params:
            path_params['fs_user_group_id'] = params['fs_user_group_id']  # noqa: E501

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
            '/fs-user-groups/{fs_user_group_id}/fs-users', 'PUT',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSUserGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def create_fs_user_group(self, body, **kwargs):  # noqa: E501
        """create_fs_user_group  # noqa: E501

        Create file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_fs_user_group(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param FSUserGroupCreateReq body: user group info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_fs_user_group_with_http_info(body, **kwargs)  # noqa: E501
        else:
            (data) = self.create_fs_user_group_with_http_info(body, **kwargs)  # noqa: E501
            return data

    def create_fs_user_group_with_http_info(self, body, **kwargs):  # noqa: E501
        """create_fs_user_group  # noqa: E501

        Create file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_fs_user_group_with_http_info(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param FSUserGroupCreateReq body: user group info (required)
        :return: FSUserGroupResp
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
                    " to method create_fs_user_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `create_fs_user_group`")  # noqa: E501

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
            '/fs-user-groups/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSUserGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def delete_fs_user_group(self, fs_user_group_id, **kwargs):  # noqa: E501
        """delete_fs_user_group  # noqa: E501

        delete file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_fs_user_group(fs_user_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :return: None
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_fs_user_group_with_http_info(fs_user_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_fs_user_group_with_http_info(fs_user_group_id, **kwargs)  # noqa: E501
            return data

    def delete_fs_user_group_with_http_info(self, fs_user_group_id, **kwargs):  # noqa: E501
        """delete_fs_user_group  # noqa: E501

        delete file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_fs_user_group_with_http_info(fs_user_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :return: None
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_user_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_fs_user_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_user_group_id' is set
        if ('fs_user_group_id' not in params or
                params['fs_user_group_id'] is None):
            raise ValueError("Missing the required parameter `fs_user_group_id` when calling `delete_fs_user_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_user_group_id' in params:
            path_params['fs_user_group_id'] = params['fs_user_group_id']  # noqa: E501

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
            '/fs-user-groups/{fs_user_group_id}', 'DELETE',
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

    def get_fs_user_group(self, fs_user_group_id, **kwargs):  # noqa: E501
        """get_fs_user_group  # noqa: E501

        Get file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_fs_user_group(fs_user_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_fs_user_group_with_http_info(fs_user_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_fs_user_group_with_http_info(fs_user_group_id, **kwargs)  # noqa: E501
            return data

    def get_fs_user_group_with_http_info(self, fs_user_group_id, **kwargs):  # noqa: E501
        """get_fs_user_group  # noqa: E501

        Get file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_fs_user_group_with_http_info(fs_user_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_user_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_fs_user_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_user_group_id' is set
        if ('fs_user_group_id' not in params or
                params['fs_user_group_id'] is None):
            raise ValueError("Missing the required parameter `fs_user_group_id` when calling `get_fs_user_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_user_group_id' in params:
            path_params['fs_user_group_id'] = params['fs_user_group_id']  # noqa: E501

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
            '/fs-user-groups/{fs_user_group_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSUserGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_fs_user_groups(self, **kwargs):  # noqa: E501
        """list_fs_user_groups  # noqa: E501

        List file storage user groups  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_fs_user_groups(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param str q: query param of search
        :param str sort: sort param of search
        :param str type: security type of file storage user group
        :param int fs_user_id: file storage user id
        :return: FSUserGroupsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_fs_user_groups_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_fs_user_groups_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_fs_user_groups_with_http_info(self, **kwargs):  # noqa: E501
        """list_fs_user_groups  # noqa: E501

        List file storage user groups  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_fs_user_groups_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param str q: query param of search
        :param str sort: sort param of search
        :param str type: security type of file storage user group
        :param int fs_user_id: file storage user id
        :return: FSUserGroupsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'q', 'sort', 'type', 'fs_user_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_fs_user_groups" % key
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
        if 'type' in params:
            query_params.append(('type', params['type']))  # noqa: E501
        if 'fs_user_id' in params:
            query_params.append(('fs_user_id', params['fs_user_id']))  # noqa: E501

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
            '/fs-user-groups/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSUserGroupsResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def remove_fs_users(self, fs_user_group_id, body, **kwargs):  # noqa: E501
        """remove_fs_users  # noqa: E501

        remove users from file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.remove_fs_users(fs_user_group_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :param FSUserGroupRemoveUsersReq body: users info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.remove_fs_users_with_http_info(fs_user_group_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.remove_fs_users_with_http_info(fs_user_group_id, body, **kwargs)  # noqa: E501
            return data

    def remove_fs_users_with_http_info(self, fs_user_group_id, body, **kwargs):  # noqa: E501
        """remove_fs_users  # noqa: E501

        remove users from file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.remove_fs_users_with_http_info(fs_user_group_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :param FSUserGroupRemoveUsersReq body: users info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_user_group_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method remove_fs_users" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_user_group_id' is set
        if ('fs_user_group_id' not in params or
                params['fs_user_group_id'] is None):
            raise ValueError("Missing the required parameter `fs_user_group_id` when calling `remove_fs_users`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `remove_fs_users`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_user_group_id' in params:
            path_params['fs_user_group_id'] = params['fs_user_group_id']  # noqa: E501

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
            '/fs-user-groups/{fs_user_group_id}/fs-users', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSUserGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_fs_user_group(self, fs_user_group_id, body, **kwargs):  # noqa: E501
        """update_fs_user_group  # noqa: E501

        Update file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_fs_user_group(fs_user_group_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :param FSUserGroupUpdateReq body: user group info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_fs_user_group_with_http_info(fs_user_group_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.update_fs_user_group_with_http_info(fs_user_group_id, body, **kwargs)  # noqa: E501
            return data

    def update_fs_user_group_with_http_info(self, fs_user_group_id, body, **kwargs):  # noqa: E501
        """update_fs_user_group  # noqa: E501

        Update file storage user group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_fs_user_group_with_http_info(fs_user_group_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_user_group_id: user group id (required)
        :param FSUserGroupUpdateReq body: user group info (required)
        :return: FSUserGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_user_group_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_fs_user_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_user_group_id' is set
        if ('fs_user_group_id' not in params or
                params['fs_user_group_id'] is None):
            raise ValueError("Missing the required parameter `fs_user_group_id` when calling `update_fs_user_group`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `update_fs_user_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_user_group_id' in params:
            path_params['fs_user_group_id'] = params['fs_user_group_id']  # noqa: E501

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
            '/fs-user-groups/{fs_user_group_id}', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSUserGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)