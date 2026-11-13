import json
from unittest.mock import patch

import pytest

from zbsprimarystorage import zbsagent


def query_snapshot(entries):
    request = {zbsagent.http.REQUEST_BODY: json.dumps({'path': 'cbd:physical/logical/volume@snap'})}
    inventory = {'error': {'code': 0}, 'result': {'fileInfo': entries}}
    with patch.object(zbsagent.zbsutils, 'query_snapshot_info', return_value=json.dumps(inventory)) as query:
        reply = json.loads(zbsagent.ZbsAgent().query_snapshot(request))
    query.assert_called_once_with('logical', 'volume')
    return reply


@pytest.mark.parametrize('name', ['snap', 'logical/volume@snap', 'physical/logical/volume@snap'])
def test_snapshot_query_resolves_only_the_exact_source_snapshot(name):
    entries = [
        {'fileName': 'logical/volume@snap-other', 'seqNum': 1},
        {'fileName': 'logical/other@snap', 'seqNum': 2},
        {'fileName': name, 'seqNum': 17},
    ]
    reply = query_snapshot(entries)
    assert reply['success']
    assert reply['installPath'] == 'cbd:physical/logical/volume@17'


@pytest.mark.parametrize('entries', [
    [{'fileName': 'snap-other', 'seqNum': 17}],
    [{'fileName': 'logical/volume@snap', 'seqNum': 'unknown'}],
    [{'fileName': 'logical/volume@snap', 'seqNum': 17},
     {'fileName': 'physical/logical/volume@snap', 'seqNum': 18}],
])
def test_snapshot_query_rejects_unresolved_ambiguous_or_invalid_source(entries):
    assert not query_snapshot(entries)['success']
