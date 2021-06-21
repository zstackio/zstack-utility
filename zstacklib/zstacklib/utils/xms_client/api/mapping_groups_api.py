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


class MappingGroupsApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def add_volumes(self, mapping_group_id, block_volume_ids, **kwargs):  # noqa: E501
        """add_volumes  # noqa: E501

        add volumes to mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.add_volumes(mapping_group_id, block_volume_ids, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupAddVolumesReq block_volume_ids: block volume ids (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.add_volumes_with_http_info(mapping_group_id, block_volume_ids, **kwargs)  # noqa: E501
        else:
            (data) = self.add_volumes_with_http_info(mapping_group_id, block_volume_ids, **kwargs)  # noqa: E501
            return data

    def add_volumes_with_http_info(self, mapping_group_id, block_volume_ids, **kwargs):  # noqa: E501
        """add_volumes  # noqa: E501

        add volumes to mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.add_volumes_with_http_info(mapping_group_id, block_volume_ids, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupAddVolumesReq block_volume_ids: block volume ids (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group_id', 'block_volume_ids']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method add_volumes" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group_id' is set
        if ('mapping_group_id' not in params or
                params['mapping_group_id'] is None):
            raise ValueError("Missing the required parameter `mapping_group_id` when calling `add_volumes`")  # noqa: E501
        # verify the required parameter 'block_volume_ids' is set
        if ('block_volume_ids' not in params or
                params['block_volume_ids'] is None):
            raise ValueError("Missing the required parameter `block_volume_ids` when calling `add_volumes`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'mapping_group_id' in params:
            path_params['mapping_group_id'] = params['mapping_group_id']  # noqa: E501

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'block_volume_ids' in params:
            body_params = params['block_volume_ids']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/mapping-groups/{mapping_group_id}/block-volumes', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def create_mapping_group(self, mapping_group, **kwargs):  # noqa: E501
        """create_mapping_group  # noqa: E501

        create a mapping group in access path  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_mapping_group(mapping_group, async=True)
        >>> result = thread.get()

        :param async bool
        :param MappingGroupCreateReq mapping_group: mapping info (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.create_mapping_group_with_http_info(mapping_group, **kwargs)  # noqa: E501
        else:
            (data) = self.create_mapping_group_with_http_info(mapping_group, **kwargs)  # noqa: E501
            return data

    def create_mapping_group_with_http_info(self, mapping_group, **kwargs):  # noqa: E501
        """create_mapping_group  # noqa: E501

        create a mapping group in access path  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.create_mapping_group_with_http_info(mapping_group, async=True)
        >>> result = thread.get()

        :param async bool
        :param MappingGroupCreateReq mapping_group: mapping info (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method create_mapping_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group' is set
        if ('mapping_group' not in params or
                params['mapping_group'] is None):
            raise ValueError("Missing the required parameter `mapping_group` when calling `create_mapping_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'mapping_group' in params:
            body_params = params['mapping_group']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/mapping-groups/', 'POST',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def delete_mapping_group(self, mapping_group_id, **kwargs):  # noqa: E501
        """delete_mapping_group  # noqa: E501

        Delete mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_mapping_group(mapping_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param bool force: force delete or not
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.delete_mapping_group_with_http_info(mapping_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.delete_mapping_group_with_http_info(mapping_group_id, **kwargs)  # noqa: E501
            return data

    def delete_mapping_group_with_http_info(self, mapping_group_id, **kwargs):  # noqa: E501
        """delete_mapping_group  # noqa: E501

        Delete mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.delete_mapping_group_with_http_info(mapping_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param bool force: force delete or not
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group_id', 'force']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method delete_mapping_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group_id' is set
        if ('mapping_group_id' not in params or
                params['mapping_group_id'] is None):
            raise ValueError("Missing the required parameter `mapping_group_id` when calling `delete_mapping_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'mapping_group_id' in params:
            path_params['mapping_group_id'] = params['mapping_group_id']  # noqa: E501

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
            '/mapping-groups/{mapping_group_id}', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def get_mapping_group(self, mapping_group_id, **kwargs):  # noqa: E501
        """get_mapping_group  # noqa: E501

        Get mapping group by id  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_mapping_group(mapping_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.get_mapping_group_with_http_info(mapping_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.get_mapping_group_with_http_info(mapping_group_id, **kwargs)  # noqa: E501
            return data

    def get_mapping_group_with_http_info(self, mapping_group_id, **kwargs):  # noqa: E501
        """get_mapping_group  # noqa: E501

        Get mapping group by id  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.get_mapping_group_with_http_info(mapping_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method get_mapping_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group_id' is set
        if ('mapping_group_id' not in params or
                params['mapping_group_id'] is None):
            raise ValueError("Missing the required parameter `mapping_group_id` when calling `get_mapping_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'mapping_group_id' in params:
            path_params['mapping_group_id'] = params['mapping_group_id']  # noqa: E501

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
            '/mapping-groups/{mapping_group_id}', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def list_mapping_groups(self, **kwargs):  # noqa: E501
        """list_mapping_groups  # noqa: E501

        List mapping groups  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_mapping_groups(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int access_path_id: access path id
        :param int client_group_id: client group id
        :return: MappingGroupsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_mapping_groups_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_mapping_groups_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_mapping_groups_with_http_info(self, **kwargs):  # noqa: E501
        """list_mapping_groups  # noqa: E501

        List mapping groups  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_mapping_groups_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param int limit: paging param
        :param int offset: paging param
        :param int access_path_id: access path id
        :param int client_group_id: client group id
        :return: MappingGroupsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['limit', 'offset', 'access_path_id', 'client_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_mapping_groups" % key
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
        if 'access_path_id' in params:
            query_params.append(('access_path_id', params['access_path_id']))  # noqa: E501
        if 'client_group_id' in params:
            query_params.append(('client_group_id', params['client_group_id']))  # noqa: E501

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
            '/mapping-groups/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupsResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def remove_volumes(self, mapping_group_id, block_volume_ids, **kwargs):  # noqa: E501
        """remove_volumes  # noqa: E501

        remove volumes from mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.remove_volumes(mapping_group_id, block_volume_ids, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupRemoveVolumesReq block_volume_ids: block volume ids (required)
        :param bool force: force delete or not
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.remove_volumes_with_http_info(mapping_group_id, block_volume_ids, **kwargs)  # noqa: E501
        else:
            (data) = self.remove_volumes_with_http_info(mapping_group_id, block_volume_ids, **kwargs)  # noqa: E501
            return data

    def remove_volumes_with_http_info(self, mapping_group_id, block_volume_ids, **kwargs):  # noqa: E501
        """remove_volumes  # noqa: E501

        remove volumes from mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.remove_volumes_with_http_info(mapping_group_id, block_volume_ids, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupRemoveVolumesReq block_volume_ids: block volume ids (required)
        :param bool force: force delete or not
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group_id', 'block_volume_ids', 'force']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method remove_volumes" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group_id' is set
        if ('mapping_group_id' not in params or
                params['mapping_group_id'] is None):
            raise ValueError("Missing the required parameter `mapping_group_id` when calling `remove_volumes`")  # noqa: E501
        # verify the required parameter 'block_volume_ids' is set
        if ('block_volume_ids' not in params or
                params['block_volume_ids'] is None):
            raise ValueError("Missing the required parameter `block_volume_ids` when calling `remove_volumes`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'mapping_group_id' in params:
            path_params['mapping_group_id'] = params['mapping_group_id']  # noqa: E501

        query_params = []
        if 'force' in params:
            query_params.append(('force', params['force']))  # noqa: E501

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'block_volume_ids' in params:
            body_params = params['block_volume_ids']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/mapping-groups/{mapping_group_id}/block-volumes', 'DELETE',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_mapping_group(self, mapping_group_id, mapping_group, **kwargs):  # noqa: E501
        """update_mapping_group  # noqa: E501

        update mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_mapping_group(mapping_group_id, mapping_group, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupUpdateReq mapping_group: mapping info (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_mapping_group_with_http_info(mapping_group_id, mapping_group, **kwargs)  # noqa: E501
        else:
            (data) = self.update_mapping_group_with_http_info(mapping_group_id, mapping_group, **kwargs)  # noqa: E501
            return data

    def update_mapping_group_with_http_info(self, mapping_group_id, mapping_group, **kwargs):  # noqa: E501
        """update_mapping_group  # noqa: E501

        update mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_mapping_group_with_http_info(mapping_group_id, mapping_group, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupUpdateReq mapping_group: mapping info (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group_id', 'mapping_group']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_mapping_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group_id' is set
        if ('mapping_group_id' not in params or
                params['mapping_group_id'] is None):
            raise ValueError("Missing the required parameter `mapping_group_id` when calling `update_mapping_group`")  # noqa: E501
        # verify the required parameter 'mapping_group' is set
        if ('mapping_group' not in params or
                params['mapping_group'] is None):
            raise ValueError("Missing the required parameter `mapping_group` when calling `update_mapping_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'mapping_group_id' in params:
            path_params['mapping_group_id'] = params['mapping_group_id']  # noqa: E501

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'mapping_group' in params:
            body_params = params['mapping_group']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/mapping-groups/{mapping_group_id}', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)

    def update_mapping_group_client_group(self, mapping_group_id, client_group_id, **kwargs):  # noqa: E501
        """update_mapping_group_client_group  # noqa: E501

        update client group in mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_mapping_group_client_group(mapping_group_id, client_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupUpdateClientGroupReq client_group_id: client group id (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.update_mapping_group_client_group_with_http_info(mapping_group_id, client_group_id, **kwargs)  # noqa: E501
        else:
            (data) = self.update_mapping_group_client_group_with_http_info(mapping_group_id, client_group_id, **kwargs)  # noqa: E501
            return data

    def update_mapping_group_client_group_with_http_info(self, mapping_group_id, client_group_id, **kwargs):  # noqa: E501
        """update_mapping_group_client_group  # noqa: E501

        update client group in mapping group  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.update_mapping_group_client_group_with_http_info(mapping_group_id, client_group_id, async=True)
        >>> result = thread.get()

        :param async bool
        :param int mapping_group_id: mapping group id (required)
        :param MappingGroupUpdateClientGroupReq client_group_id: client group id (required)
        :return: MappingGroupResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['mapping_group_id', 'client_group_id']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_mapping_group_client_group" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'mapping_group_id' is set
        if ('mapping_group_id' not in params or
                params['mapping_group_id'] is None):
            raise ValueError("Missing the required parameter `mapping_group_id` when calling `update_mapping_group_client_group`")  # noqa: E501
        # verify the required parameter 'client_group_id' is set
        if ('client_group_id' not in params or
                params['client_group_id'] is None):
            raise ValueError("Missing the required parameter `client_group_id` when calling `update_mapping_group_client_group`")  # noqa: E501

        collection_formats = {}

        path_params = {}
        if 'mapping_group_id' in params:
            path_params['mapping_group_id'] = params['mapping_group_id']  # noqa: E501

        query_params = []

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'client_group_id' in params:
            body_params = params['client_group_id']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.select_header_accept(
            ['application/json'])  # noqa: E501

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.select_header_content_type(  # noqa: E501
            ['application/json'])  # noqa: E501

        # Authentication setting
        auth_settings = ['tokenInHeader', 'tokenInQuery']  # noqa: E501

        return self.api_client.call_api(
            '/mapping-groups/{mapping_group_id}/client-group', 'PATCH',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='MappingGroupResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
