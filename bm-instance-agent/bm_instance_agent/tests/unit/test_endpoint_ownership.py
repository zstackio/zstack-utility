import os
import re


EXISTING_V2_PATHS = (
    '/v2/console/prepare',
    '/v2/defaultRoute/change',
    '/v2/inspect',
    '/v2/nic/attach',
    '/v2/nic/detach',
    '/v2/password/change',
    '/v2/ping',
    '/v2/reboot',
    '/v2/stop',
    '/v2/volume/attach',
    '/v2/volume/detach',
)


def test_runtime_endpoints_have_unique_method_path_pairs():
    specs = _read_runtime_route_specs()
    assert len(specs) == len(set(specs))
    assert set(specs) == {
        ('GET', '/v2/runtime/capabilities'),
        ('POST', '/v2/runtime/reconcile'),
        ('PUT', '/v2/runtime/allocations/{allocationUuid}/prepare'),
        ('POST', '/v2/runtime/allocations/{allocationUuid}/start'),
        ('GET', '/v2/runtime/allocations/{allocationUuid}'),
        ('DELETE', '/v2/runtime/allocations/{allocationUuid}'),
        ('POST', '/v2/runtime/allocations/{allocationUuid}/stop'),
    }


def test_runtime_paths_do_not_overlap_existing_v2_paths():
    runtime_paths = set(path for _, path in _read_runtime_route_specs())
    assert not runtime_paths.intersection(EXISTING_V2_PATHS)


def _read_runtime_route_specs():
    path = os.path.join(
        os.path.dirname(__file__),
        '..', '..', 'api', 'controllers', 'v2', 'runtime.py')
    with open(os.path.abspath(path), 'r') as stream:
        text = stream.read()

    specs = []
    pattern = re.compile(r"\('([A-Z]+)', '([^']+)'\)")
    for method, route in pattern.findall(text):
        specs.append((method, route))
    return specs
