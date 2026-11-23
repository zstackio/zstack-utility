import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, str(Path(__file__).resolve().parents[3] / path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(monkeypatch):
    ceph = load_module('ceph_lifecycle', 'zstacklib/zstacklib/utils/ceph.py')
    clusters = []

    def create(**kwargs):
        cluster = MagicMock()
        cluster.contexts = []

        def open_ioctx(pool):
            assert cluster.shutdown.call_count == 0
            ioctx = MagicMock()
            ioctx.__enter__.return_value = ioctx
            ioctx.__exit__.side_effect = lambda *args: ioctx.close()
            ioctx.close.return_value = None
            cluster.contexts.append(ioctx)
            return ioctx

        def shutdown():
            assert cluster.shutdown.call_count == 1
            assert all(io.close.call_count == 1 for io in cluster.contexts)

        cluster.open_ioctx.side_effect = open_ioctx
        cluster.shutdown.side_effect = shutdown
        clusters.append(cluster)
        return cluster

    monkeypatch.setitem(sys.modules, 'rados', SimpleNamespace(Rados=create))
    return ceph.RadosClient('/etc/ceph/ceph.conf'), clusters


def test_reuses_connection_but_never_ioctx(client):
    manager, clusters = client
    with manager.get_ioctx('pool') as first:
        with manager.get_ioctx('pool') as second:
            assert first is not second
    with manager.get_ioctx('pool') as third:
        assert third not in (first, second)
    assert len(clusters) == 1
    assert all(io.close.call_count == 1 for io in clusters[0].contexts)
    clusters[0].shutdown.assert_not_called()


def test_reconnect_closes_idle_connection_and_uses_new_one(client):
    manager, clusters = client
    with manager.get_ioctx('pool') as first:
        pass
    first.close.assert_called_once()
    manager.reconnect()
    clusters[0].shutdown.assert_called_once()
    with manager.get_ioctx('pool') as second:
        assert second in clusters[1].contexts


def test_multiple_generations_wait_for_their_last_borrower(client):
    manager, clusters = client
    with manager.get_ioctx('pool') as first:
        with manager.get_ioctx('pool'):
            manager.reconnect()
        clusters[0].shutdown.assert_not_called()
        with manager.get_ioctx('other-pool'):
            manager.reconnect()
            assert len(clusters) == 3
            assert all(c.shutdown.call_count == 0 for c in clusters)
        clusters[1].shutdown.assert_called_once()
        first.close.assert_not_called()
    clusters[0].shutdown.assert_called_once()
    clusters[2].shutdown.assert_not_called()
    assert list(manager._refcount_by_connection) == [clusters[2]]


def test_business_exception_closes_ioctx_before_retired_connection(client):
    manager, clusters = client
    with pytest.raises(ValueError, match='business'):
        with manager.get_ioctx('pool'):
            manager.reconnect()
            raise ValueError('business')
    clusters[0].shutdown.assert_called_once()


def test_ioctx_close_exception_still_returns_reference(client):
    manager, clusters = client
    with pytest.raises(ValueError, match='close'):
        with manager.get_ioctx('pool') as ioctx:
            manager.reconnect()
            ioctx.close.side_effect = ValueError('close')
    clusters[0].shutdown.assert_called_once()


def test_failed_connect_keeps_current_connection(client):
    manager, clusters = client
    with manager.get_ioctx('pool'):
        pass
    native = sys.modules['rados']
    factory = native.Rados

    def failing_factory(**kwargs):
        cluster = factory(**kwargs)
        cluster.connect.side_effect = ValueError('connect')
        return cluster

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(native, 'Rados', failing_factory)
        with pytest.raises(ValueError, match='connect'):
            manager.reconnect()
    clusters[1].shutdown.assert_called_once()
    with manager.get_ioctx('pool') as ioctx:
        assert ioctx in clusters[0].contexts
    clusters[0].shutdown.assert_not_called()


@pytest.mark.parametrize('fail_open', [False, True])
def test_reconnect_during_open_keeps_old_connection_alive(client, fail_open):
    manager, clusters = client
    manager.reconnect()
    cluster = clusters[0]
    open_ioctx = cluster.open_ioctx.side_effect
    entered, release = Event(), Event()

    def blocked_open(pool):
        entered.set()
        assert release.wait(5)
        cluster.shutdown.assert_not_called()
        if fail_open:
            raise ValueError('open')
        return open_ioctx(pool)

    cluster.open_ioctx.side_effect = blocked_open

    def borrow():
        with manager.get_ioctx('pool'):
            pass

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(borrow)
        try:
            assert entered.wait(5)
            manager.reconnect()
            cluster.shutdown.assert_not_called()
        finally:
            release.set()
        if fail_open:
            with pytest.raises(ValueError, match='open'):
                future.result(timeout=5)
        else:
            future.result(timeout=5)
    cluster.shutdown.assert_called_once()


def test_shutdown_does_not_hold_borrow_lock(client):
    manager, clusters = client
    manager.reconnect()
    entered, release = Event(), Event()
    shutdown = clusters[0].shutdown.side_effect

    def blocked_shutdown():
        shutdown()
        entered.set()
        assert release.wait(5)

    clusters[0].shutdown.side_effect = blocked_shutdown
    with ThreadPoolExecutor(max_workers=2) as executor:
        reconnect = executor.submit(manager.reconnect)
        try:
            assert entered.wait(5)
            def borrow():
                with manager.get_ioctx('pool'):
                    pass
            executor.submit(borrow).result(timeout=2)
        finally:
            release.set()
        reconnect.result(timeout=5)


def test_concurrent_borrow_and_reconnect_close_each_retired_cluster_once(client):
    manager, clusters = client

    def borrow():
        for _ in range(100):
            with manager.get_ioctx('pool') as ioctx:
                ioctx.close.assert_not_called()

    def reconnect():
        for _ in range(50):
            manager.reconnect()

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(borrow) for _ in range(4)]
        futures += [executor.submit(reconnect) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    assert sum(c.shutdown.call_count for c in clusters) == len(clusters) - 1
    assert len(manager._refcount_by_connection) == 1


def test_initial_connect_failure_can_retry(client, monkeypatch):
    manager, clusters = client
    native = sys.modules['rados']
    factory = native.Rados
    def create(**kwargs):
        cluster = factory(**kwargs)
        if len(clusters) == 1:
            cluster.connect.side_effect = ValueError('connect')
        return cluster
    monkeypatch.setattr(native, 'Rados', create)
    with pytest.raises(ValueError, match='connect'):
        with manager.get_ioctx('pool'):
            pytest.fail('failed connection must not yield an ioctx')
    clusters[0].shutdown.assert_called_once()
    with manager.get_ioctx('pool') as ioctx:
        assert ioctx in clusters[1].contexts
