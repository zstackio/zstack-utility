import json

from pecan import expose
from pecan import request
from pecan import response
from pecan.rest import RestController

from bm_instance_agent import runtime


RUNTIME_ROUTE_SPECS = (
    ('GET', '/v2/runtime/capabilities'),
    ('POST', '/v2/runtime/reconcile'),
    ('PUT', '/v2/runtime/allocations/{allocationUuid}/prepare'),
    ('POST', '/v2/runtime/allocations/{allocationUuid}/start'),
    ('GET', '/v2/runtime/allocations/{allocationUuid}'),
    ('DELETE', '/v2/runtime/allocations/{allocationUuid}'),
    ('POST', '/v2/runtime/allocations/{allocationUuid}/stop'),
)


def get_runtime_route_specs():
    return list(RUNTIME_ROUTE_SPECS)


def _load_json_body(required=True):
    body = request.body or ''
    if not body:
        if required:
            raise runtime.RuntimeProxyError(
                400,
                'BMR-REQUEST-0001',
                'request body is required',
                False,
                'Caller')
        return {}
    if len(body) > runtime.RuntimeManager.MAX_REQUEST_BYTES:
        raise runtime.RuntimeProxyError(
            413,
            'BMR-REQUEST-0002',
            'request exceeds configured byte limit',
            False,
            'Caller')
    if not isinstance(body, str):
        try:
            body = body.decode('utf-8')
        except UnicodeError:
            raise runtime.RuntimeProxyError(
                400,
                'BMR-REQUEST-0001',
                'request body must be utf-8 json',
                False,
                'Caller')
    try:
        payload = json.loads(body)
    except ValueError:
        raise runtime.RuntimeProxyError(
            400,
            'BMR-REQUEST-0001',
            'request body must be valid json',
            False,
            'Caller')
    if not isinstance(payload, dict):
        raise runtime.RuntimeProxyError(
            400,
            'BMR-REQUEST-0001',
            'request body must be a json object',
            False,
            'Caller')
    return payload


def _render_proxy(method):
    def decorator(func):
        @expose(template='json')
        def wrap(*args, **kwargs):
            try:
                status, data = func(*args, **kwargs)
            except runtime.RuntimeProxyError as err:
                response.status = err.status
                return err.to_dict()

            response.status = status
            return data

        wrap.__name__ = method
        return wrap
    return decorator


class PrepareController(RestController):

    def __init__(self, runtime_manager, allocation_uuid):
        super(PrepareController, self).__init__()
        self.runtime_manager = runtime_manager
        self.allocation_uuid = allocation_uuid

    @_render_proxy('put')
    def put(self):
        payload = _load_json_body(required=True)
        payload = self.runtime_manager.materialize_prepare_payload(payload)
        return self.runtime_manager.prepare_allocation(
            self.allocation_uuid, payload)


class StartController(RestController):

    def __init__(self, runtime_manager, allocation_uuid):
        super(StartController, self).__init__()
        self.runtime_manager = runtime_manager
        self.allocation_uuid = allocation_uuid

    @_render_proxy('post')
    def post(self):
        return self.runtime_manager.start_allocation(
            self.allocation_uuid, _load_json_body(required=True))


class StopController(RestController):

    def __init__(self, runtime_manager, allocation_uuid):
        super(StopController, self).__init__()
        self.runtime_manager = runtime_manager
        self.allocation_uuid = allocation_uuid

    @_render_proxy('post')
    def post(self):
        return self.runtime_manager.stop_allocation(
            self.allocation_uuid, _load_json_body(required=True))


class AllocationController(RestController):

    def __init__(self, runtime_manager, allocation_uuid):
        super(AllocationController, self).__init__()
        self.runtime_manager = runtime_manager
        self.allocation_uuid = allocation_uuid
        self.prepare = PrepareController(runtime_manager, allocation_uuid)
        self.start = StartController(runtime_manager, allocation_uuid)
        self.stop = StopController(runtime_manager, allocation_uuid)

    @_render_proxy('get')
    def get(self):
        return self.runtime_manager.inspect_allocation(self.allocation_uuid)

    @_render_proxy('delete')
    def delete(self):
        return self.runtime_manager.release_allocation(
            self.allocation_uuid, _load_json_body(required=True))


class AllocationsController(RestController):

    def __init__(self, runtime_manager):
        super(AllocationsController, self).__init__()
        self.runtime_manager = runtime_manager

    @expose()
    def _lookup(self, allocation_uuid, *remainder):
        return AllocationController(self.runtime_manager, allocation_uuid), remainder


class ReconcileController(RestController):

    def __init__(self, runtime_manager):
        super(ReconcileController, self).__init__()
        self.runtime_manager = runtime_manager

    @_render_proxy('post')
    def post(self):
        return self.runtime_manager.reconcile(_load_json_body(required=True))


class CapabilitiesController(RestController):

    def __init__(self, runtime_manager):
        super(CapabilitiesController, self).__init__()
        self.runtime_manager = runtime_manager

    @_render_proxy('get')
    def get(self):
        return self.runtime_manager.get_capabilities()


class RuntimeController(RestController):

    def __init__(self, runtime_manager=None):
        super(RuntimeController, self).__init__()
        self.runtime_manager = runtime_manager or runtime.RuntimeManager()
        self.allocations = AllocationsController(self.runtime_manager)
        self.capabilities = CapabilitiesController(self.runtime_manager)
        self.reconcile = ReconcileController(self.runtime_manager)
