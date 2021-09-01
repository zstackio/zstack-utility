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


class FsSmbSharesApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def add_fssmb_share_ac_ls(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """add_fssmb_share_ac_ls  # noqa: E501

        Add fs smb share acls  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.add_fssmb_share_ac_ls(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: fs smb share id (required)
        :param FSSMBShareAddACLsReq body: share acls info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.add_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.add_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
            return data

    def add_fssmb_share_ac_ls_with_http_info(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """add_fssmb_share_ac_ls  # noqa: E501

        Add fs smb share acls  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.add_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: fs smb share id (required)
        :param FSSMBShareAddACLsReq body: share acls info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_smb_share_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method add_fssmb_share_ac_ls" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_smb_share_id' is set
        if ('fs_smb_share_id' not in params or
                params['fs_smb_share_id'] is None):
            raise ValueError("Missing the required parameter `fs_smb_share_id` when calling `add_fssmb_share_ac_ls`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `add_fssmb_share_ac_ls`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_smb_share_id' in params:
            path_params['fs_smb_share_id'] = params['fs_smb_share_id']  # noqa: E501

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
            '/fs-smb-shares/{fs_smb_share_id}:add-acls', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def create_fssmb_share(self, body, **kwargs):  # noqa: E501
        """create_fssmb_share  # noqa: E501

        Create fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_fssmb_share(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param FSSMBShareCreateReq body: share info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_fssmb_share_with_http_info(body, **kwargs)  # noqa: E501
        else:
            (data) = self.create_fssmb_share_with_http_info(body, **kwargs)  # noqa: E501
            return data

    def create_fssmb_share_with_http_info(self, body, **kwargs):  # noqa: E501
        """create_fssmb_share  # noqa: E501

        Create fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_fssmb_share_with_http_info(body, async=True)
        >>> result = thread.get()

        :param async bool
        :param FSSMBShareCreateReq body: share info (required)
        :return: FSSMBShareResp
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
                    " to method create_fssmb_share" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `create_fssmb_share`")  # noqa: E501

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
            '/fs-smb-shares/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def delete_fssmb_share(self, fs_smb_share_id, **kwargs):  # noqa: E501
        """delete_fssmb_share  # noqa: E501

        delete fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_fssmb_share(fs_smb_share_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :param bool force: force delete or not
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_fssmb_share_with_http_info(fs_smb_share_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_fssmb_share_with_http_info(fs_smb_share_id, **kwargs)  # noqa: E501
            return data

    def delete_fssmb_share_with_http_info(self, fs_smb_share_id, **kwargs):  # noqa: E501
        """delete_fssmb_share  # noqa: E501

        delete fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_fssmb_share_with_http_info(fs_smb_share_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :param bool force: force delete or not
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_smb_share_id', 'force']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_fssmb_share" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_smb_share_id' is set
        if ('fs_smb_share_id' not in params or
                params['fs_smb_share_id'] is None):
            raise ValueError("Missing the required parameter `fs_smb_share_id` when calling `delete_fssmb_share`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_smb_share_id' in params:
            path_params['fs_smb_share_id'] = params['fs_smb_share_id']  # noqa: E501

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
            '/fs-smb-shares/{fs_smb_share_id}', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_fssmb_share(self, fs_smb_share_id, **kwargs):  # noqa: E501
        """get_fssmb_share  # noqa: E501

        Get fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_fssmb_share(fs_smb_share_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_fssmb_share_with_http_info(fs_smb_share_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_fssmb_share_with_http_info(fs_smb_share_id, **kwargs)  # noqa: E501
            return data

    def get_fssmb_share_with_http_info(self, fs_smb_share_id, **kwargs):  # noqa: E501
        """get_fssmb_share  # noqa: E501

        Get fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_fssmb_share_with_http_info(fs_smb_share_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_smb_share_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_fssmb_share" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_smb_share_id' is set
        if ('fs_smb_share_id' not in params or
                params['fs_smb_share_id'] is None):
            raise ValueError("Missing the required parameter `fs_smb_share_id` when calling `get_fssmb_share`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_smb_share_id' in params:
            path_params['fs_smb_share_id'] = params['fs_smb_share_id']  # noqa: E501

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
            '/fs-smb-shares/{fs_smb_share_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_fssmb_shares(self, **kwargs):  # noqa: E501
        """list_fssmb_shares  # noqa: E501

        List fs smb shares  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_fssmb_shares(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int fs_folder_id: fs folder id
        :param int fs_gateway_group_id: fs gateway group id
        :param str q: query param of search
        :param str sort: sort param of search
        :return: FSSMBSharesResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_fssmb_shares_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_fssmb_shares_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_fssmb_shares_with_http_info(self, **kwargs):  # noqa: E501
        """list_fssmb_shares  # noqa: E501

        List fs smb shares  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_fssmb_shares_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int fs_folder_id: fs folder id
        :param int fs_gateway_group_id: fs gateway group id
        :param str q: query param of search
        :param str sort: sort param of search
        :return: FSSMBSharesResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'fs_folder_id', 'fs_gateway_group_id', 'q', 'sort']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_fssmb_shares" % key
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
        if 'fs_folder_id' in params:
            query_params.append(('fs_folder_id', params['fs_folder_id']))  # noqa: E501
        if 'fs_gateway_group_id' in params:
            query_params.append(('fs_gateway_group_id', params['fs_gateway_group_id']))  # noqa: E501
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
            '/fs-smb-shares/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBSharesResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def remove_fssmb_share_ac_ls(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """remove_fssmb_share_ac_ls  # noqa: E501

        remove fs smb share acls  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.remove_fssmb_share_ac_ls(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: fs smb share id (required)
        :param FSSMBShareRemoveACLsReq body: share acls info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.remove_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.remove_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
            return data

    def remove_fssmb_share_ac_ls_with_http_info(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """remove_fssmb_share_ac_ls  # noqa: E501

        remove fs smb share acls  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.remove_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: fs smb share id (required)
        :param FSSMBShareRemoveACLsReq body: share acls info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_smb_share_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method remove_fssmb_share_ac_ls" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_smb_share_id' is set
        if ('fs_smb_share_id' not in params or
                params['fs_smb_share_id'] is None):
            raise ValueError("Missing the required parameter `fs_smb_share_id` when calling `remove_fssmb_share_ac_ls`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `remove_fssmb_share_ac_ls`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_smb_share_id' in params:
            path_params['fs_smb_share_id'] = params['fs_smb_share_id']  # noqa: E501

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
            '/fs-smb-shares/{fs_smb_share_id}:remove-acls', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_fssmb_share(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """update_fssmb_share  # noqa: E501

        Update fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_fssmb_share(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :param FSSMBShareUpdateReq body: share info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_fssmb_share_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.update_fssmb_share_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
            return data

    def update_fssmb_share_with_http_info(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """update_fssmb_share  # noqa: E501

        Update fs smb share  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_fssmb_share_with_http_info(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :param FSSMBShareUpdateReq body: share info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_smb_share_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_fssmb_share" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_smb_share_id' is set
        if ('fs_smb_share_id' not in params or
                params['fs_smb_share_id'] is None):
            raise ValueError("Missing the required parameter `fs_smb_share_id` when calling `update_fssmb_share`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `update_fssmb_share`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_smb_share_id' in params:
            path_params['fs_smb_share_id'] = params['fs_smb_share_id']  # noqa: E501

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
            '/fs-smb-shares/{fs_smb_share_id}', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_fssmb_share_ac_ls(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """update_fssmb_share_ac_ls  # noqa: E501

        Update fs smb share ACL  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_fssmb_share_ac_ls(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :param FSSMBShareUpdateACLsReq body: share acls info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
        else:
            (data) = self.update_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, **kwargs)  # noqa: E501
            return data

    def update_fssmb_share_ac_ls_with_http_info(self, fs_smb_share_id, body, **kwargs):  # noqa: E501
        """update_fssmb_share_ac_ls  # noqa: E501

        Update fs smb share ACL  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_fssmb_share_ac_ls_with_http_info(fs_smb_share_id, body, async=True)
        >>> result = thread.get()

        :param async bool
        :param int fs_smb_share_id: share id (required)
        :param FSSMBShareUpdateACLsReq body: share acls info (required)
        :return: FSSMBShareResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['fs_smb_share_id', 'body']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_fssmb_share_ac_ls" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'fs_smb_share_id' is set
        if ('fs_smb_share_id' not in params or
                params['fs_smb_share_id'] is None):
            raise ValueError("Missing the required parameter `fs_smb_share_id` when calling `update_fssmb_share_ac_ls`")  # noqa: E501
        # verify the required parameter 'body' is set
        if ('body' not in params or
                params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `update_fssmb_share_ac_ls`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'fs_smb_share_id' in params:
            path_params['fs_smb_share_id'] = params['fs_smb_share_id']  # noqa: E501

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
            '/fs-smb-shares/{fs_smb_share_id}:update-acls', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='FSSMBShareResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)