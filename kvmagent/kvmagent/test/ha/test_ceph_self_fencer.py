import json
import threading
import time
from unittest import mock

import pytest

from kvmagent.plugins import ha_plugin
from kvmagent.plugins.ha_plugin import CephFencerInitialization, HaPlugin
from zstacklib.utils import thread as thread_utils


def _request(**overrides):
    command = {
        'uuid': 'ps-uuid',
        'fsId': 'fs-id',
        'hostUuid': 'host-uuid',
        'interval': 1,
        'maxAttempts': 3,
        'storageCheckerTimeout': 1,
        'userKey': None,
        'poolNames': ['pool-a'],
        'monUrls': ['127.0.0.1:6789'],
        'strategy': 'Permissive',
        'fencers': [],
        'manufacturer': 'open-source',
    }
    command.update(overrides)
    return {'body': json.dumps(command)}


class FakeIoctx(object):
    def __init__(self, pool_name):
        self.pool_name = pool_name
        self.closed = False

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeCluster(object):
    def __init__(self, pool_errors=None, connect_error=None, connect_gate=None,
                 open_gates=None):
        self.pool_errors = pool_errors or {}
        self.connect_error = connect_error
        self.connect_gate = connect_gate
        self.open_gates = open_gates or {}
        self.connect_called = threading.Event()
        self.open_called = threading.Event()
        self.opened_pool = None
        self.ioctxs = []
        self.shutdown_called = False
        self.rados_kwargs = None

    def connect(self):
        self.connect_called.set()
        if self.connect_gate is not None:
            self.connect_gate.wait()
        if self.connect_error is not None:
            raise self.connect_error

    def open_ioctx(self, pool_name):
        self.opened_pool = pool_name
        self.open_called.set()
        gate = self.open_gates.get(pool_name)
        if gate is not None:
            gate.wait()
        if pool_name in self.pool_errors:
            raise self.pool_errors[pool_name]
        ioctx = FakeIoctx(pool_name)
        self.ioctxs.append(ioctx)
        return ioctx

    def shutdown(self):
        self.shutdown_called = True

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_args):
        self.shutdown()


class ClusterFactory(object):
    def __init__(self, **cluster_args):
        self.cluster_args = cluster_args
        self.clusters = []

    def __call__(self, **kwargs):
        cluster = FakeCluster(**self.cluster_args)
        cluster.rados_kwargs = kwargs
        self.clusters.append(cluster)
        return cluster


def _join_workers():
    for worker in thread_utils.started_threads:
        worker.join(2)
    assert not [worker for worker in thread_utils.started_threads if worker.is_alive()]


def _wait_until(predicate, timeout=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.001)
    return predicate()


def test_aborted_initialization_cannot_publish_during_commit():
    initialization = CephFencerInitialization(1)
    published = []
    initialization.abort('worker timed out')

    committed = initialization.commit(lambda: published.append(True))

    assert committed is False
    assert published == []


@pytest.fixture(autouse=True)
def clean_worker_threads():
    del thread_utils.started_threads[:]
    del thread_utils.worker_errors[:]
    yield
    _join_workers()
    assert thread_utils.worker_errors == []


@pytest.fixture
def plugin():
    instance = HaPlugin()
    with mock.patch.object(ha_plugin.AbstractHaFencer, 'exec_fencer_list'):
        yield instance
    instance.cancel_fencer('ps-uuid')


@pytest.fixture
def ceph_conf():
    with mock.patch('kvmagent.plugins.ha_plugin.ceph.update_ceph_client_access_conf',
                    return_value=('/tmp/ceph.conf', None, 'client.zstack')):
        yield


@pytest.mark.parametrize('existing_fencer', [False, True])
def test_setup_fails_without_publishing_state_when_rados_connect_fails(
        ceph_conf, plugin, existing_fencer):
    factory = ClusterFactory(connect_error=RuntimeError('cannot connect to ceph'))
    if existing_fencer:
        plugin.setup_fencer('ps-uuid-pool-a', time.time(), origin_uuid='ps-uuid')

    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=factory):
        response = json.loads(plugin.setup_ceph_self_fencer(_request()))

    assert response['success'] is False
    assert 'cannot connect to ceph' in response['error']
    assert 'ps-uuid' not in plugin.fencer_storage_list
    assert not any(key.startswith('ps-uuid-') for key in plugin.run_fencer_timestamp)
    assert factory.clusters[0].rados_kwargs['conf']['client_mount_timeout'] == '1'
    assert factory.clusters[0].rados_kwargs['conf']['rados_mon_op_timeout'] == '1'


def test_setup_fails_atomically_when_one_pool_cannot_open(ceph_conf, plugin):
    factory = ClusterFactory(pool_errors={'pool-b': RuntimeError('pool does not exist')})

    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=factory):
        response = json.loads(plugin.setup_ceph_self_fencer(
            _request(poolNames=['pool-a', 'pool-b'])))

    assert response['success'] is False
    assert 'pool-b' in response['error']
    assert plugin.fencer_storage_list == set()
    assert plugin.run_fencer_timestamp == {}
    _join_workers()
    assert all(cluster.shutdown_called for cluster in factory.clusters)
    assert all(ioctx.closed for cluster in factory.clusters for ioctx in cluster.ioctxs)


def test_worker_start_failure_aborts_started_workers_without_pending_state(
        ceph_conf, plugin):
    factory = ClusterFactory()
    original_async_thread = thread_utils.AsyncThread

    def fail_pool_b_start(func):
        async_func = original_async_thread(func)

        def start_worker(ps_uuid, pool_name):
            if pool_name == 'pool-b':
                raise RuntimeError('cannot start worker')
            return async_func(ps_uuid, pool_name)

        return start_worker

    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=factory), \
            mock.patch('kvmagent.plugins.ha_plugin.thread.AsyncThread',
                       side_effect=fail_pool_b_start):
        response = json.loads(plugin.setup_ceph_self_fencer(
            _request(poolNames=['pool-a', 'pool-b'])))

    _join_workers()
    assert response['success'] is False
    assert 'cannot start worker' in response['error']
    assert plugin.ceph_fencer_initializations == {}
    assert plugin.run_fencer_timestamp == {}
    assert plugin.fencer_storage_list == set()
    assert all(cluster.shutdown_called for cluster in factory.clusters)


def test_setup_publishes_all_pools_only_after_every_worker_is_ready(ceph_conf, plugin):
    second_pool_gate = threading.Event()
    factory = ClusterFactory(open_gates={'pool-b': second_pool_gate})

    response_holder = {}

    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=factory):
        request_thread = threading.Thread(target=lambda: response_holder.setdefault(
            'response', json.loads(plugin.setup_ceph_self_fencer(
                _request(poolNames=['pool-a', 'pool-b'], interval=0.01)))))
        request_thread.start()
        assert _wait_until(lambda: len(factory.clusters) == 2)
        assert _wait_until(lambda: any(
            cluster.opened_pool == 'pool-b' for cluster in factory.clusters))
        pool_b_cluster = next(cluster for cluster in factory.clusters
                              if cluster.opened_pool == 'pool-b')
        pool_b_cluster.open_called.wait(1)

        assert plugin.fencer_storage_list == set()
        assert plugin.run_fencer_timestamp == {}

        second_pool_gate.set()
        request_thread.join(2)

    assert response_holder['response']['success'] is True
    assert plugin.fencer_storage_list == {'ps-uuid'}
    assert set(plugin.run_fencer_timestamp) == {'ps-uuid-pool-a', 'ps-uuid-pool-b'}
    assert len(factory.clusters) == 2
    assert all(cluster.rados_kwargs['conf']['client_mount_timeout'] == '1'
               for cluster in factory.clusters)


def test_timeout_aborts_late_worker_without_publishing_state(ceph_conf, plugin):
    connect_gate = threading.Event()
    factory = ClusterFactory(connect_gate=connect_gate)

    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=factory):
        response = json.loads(plugin.setup_ceph_self_fencer(
            _request(poolNames=['pool-a', 'pool-b'], storageCheckerTimeout=0.05)))

        assert response['success'] is False
        assert 'timed out' in response['error']
        assert plugin.fencer_storage_list == set()
        assert plugin.run_fencer_timestamp == {}
        assert _wait_until(lambda: len(factory.clusters) == 2 and all(
            cluster.connect_called.is_set() for cluster in factory.clusters))

        retry_response = json.loads(plugin.setup_ceph_self_fencer(_request()))
        assert retry_response['success'] is False
        assert 'still exiting' in retry_response['error']
        assert len(factory.clusters) == 2

        connect_gate.set()

    _join_workers()
    assert plugin.ceph_fencer_initializations == {}
    assert plugin.fencer_storage_list == set()
    assert plugin.run_fencer_timestamp == {}

    healthy_factory = ClusterFactory()
    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=healthy_factory):
        recovery_response = json.loads(plugin.setup_ceph_self_fencer(
            _request(interval=0.01)))

    assert recovery_response['success'] is True
    assert plugin.fencer_storage_list == {'ps-uuid'}
    assert set(plugin.run_fencer_timestamp) == {'ps-uuid-pool-a'}


def test_cancel_during_initialization_prevents_late_publish(ceph_conf, plugin):
    open_gate = threading.Event()
    factory = ClusterFactory(open_gates={'pool-b': open_gate})
    response_holder = {}

    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados', side_effect=factory):
        request_thread = threading.Thread(target=lambda: response_holder.setdefault(
            'response', json.loads(plugin.setup_ceph_self_fencer(
                _request(poolNames=['pool-a', 'pool-b'])))))
        request_thread.start()
        assert _wait_until(lambda: len(factory.clusters) == 2)
        assert _wait_until(lambda: any(
            cluster.opened_pool == 'pool-b' for cluster in factory.clusters))
        assert _wait_until(lambda: any(
            cluster.opened_pool == 'pool-a' and cluster.ioctxs
            for cluster in factory.clusters))

        plugin.cancel_ceph_self_fencer(_request(poolNames=[]))
        open_gate.set()
        request_thread.join(2)

    _join_workers()
    assert response_holder['response']['success'] is False
    assert plugin.fencer_storage_list == set()
    assert plugin.run_fencer_timestamp == {}
    assert all(cluster.shutdown_called for cluster in factory.clusters)
    assert all(ioctx.closed for cluster in factory.clusters for ioctx in cluster.ioctxs)


@pytest.mark.parametrize('pool_names', [[], None])
def test_setup_rejects_empty_pool_list_without_starting_worker(pool_names, plugin):
    with mock.patch('kvmagent.plugins.ha_plugin.rados.Rados') as rados_factory:
        response = json.loads(plugin.setup_ceph_self_fencer(
            _request(poolNames=pool_names)))

    assert response['success'] is False
    assert 'without a pool name' in response['error']
    rados_factory.assert_not_called()
    assert plugin.fencer_storage_list == set()
    assert plugin.run_fencer_timestamp == {}
