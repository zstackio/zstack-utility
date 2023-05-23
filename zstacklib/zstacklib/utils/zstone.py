import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import shell

class ZStoneCephPoolCapacityGetter():
    def fill_pool_capacity(self, result):
        o = shell.call('ceph df detail -f json')
        r = jsonobject.loads(o)
        if not r.pools:
            return
        for pool in r.pools:
            for pool_capacity in result:
                if pool_capacity.pool_name == pool.name:
                    pool_capacity.available_capacity = pool.stats.max_avail
                    pool_capacity.used_capacity = pool.stats.stored
                    pool_capacity.pool_total_size = pool_capacity.available_capacity + pool_capacity.used_capacity
                    break