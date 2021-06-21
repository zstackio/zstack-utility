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


class OsZonePairsApi(object):
    """NOTE: This class is auto generated by the swagger code generator program.

    Do not edit the class manually.
    Ref: https://github.com/swagger-api/swagger-codegen
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client

    def list_os_zone_pairs(self, **kwargs):  # noqa: E501
        """list_os_zone_pairs  # noqa: E501

        list os zone pairs  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_os_zone_pairs(async=True)
        >>> result = thread.get()

        :param async bool
        :param str min_clock_diff_abs: min clock diff absolute value for zone pairs
        :return: OSZonePairsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """
        kwargs['_return_http_data_only'] = True
        if kwargs.get('async'):
            return self.list_os_zone_pairs_with_http_info(**kwargs)  # noqa: E501
        else:
            (data) = self.list_os_zone_pairs_with_http_info(**kwargs)  # noqa: E501
            return data

    def list_os_zone_pairs_with_http_info(self, **kwargs):  # noqa: E501
        """list_os_zone_pairs  # noqa: E501

        list os zone pairs  # noqa: E501
        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async=True
        >>> thread = api.list_os_zone_pairs_with_http_info(async=True)
        >>> result = thread.get()

        :param async bool
        :param str min_clock_diff_abs: min clock diff absolute value for zone pairs
        :return: OSZonePairsResp
                 If the method is called asynchronously,
                 returns the request thread.
        """

        all_params = ['min_clock_diff_abs']  # noqa: E501
        all_params.append('async')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in six.iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method list_os_zone_pairs" % key
                )
            params[key] = val
        del params['kwargs']

        collection_formats = {}

        path_params = {}

        query_params = []
        if 'min_clock_diff_abs' in params:
            query_params.append(('min_clock_diff_abs', params['min_clock_diff_abs']))  # noqa: E501

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
            '/os-zone-pairs/', 'GET',
            path_params,
            query_params,
            header_params,
            body=body_params,
            post_params=form_params,
            files=local_var_files,
            response_type='OSZonePairsResp',  # noqa: E501
            auth_settings=auth_settings,
            async=params.get('async'),
            _return_http_data_only=params.get('_return_http_data_only'),
            _preload_content=params.get('_preload_content', True),
            _request_timeout=params.get('_request_timeout'),
            collection_formats=collection_formats)
