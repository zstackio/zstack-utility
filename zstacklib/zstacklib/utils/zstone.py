import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import shell, bash
from distutils.version import LooseVersion

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

        if not calc_capacity_with_ratio():
            return
        ratio = get_full_ratio()
        for pool_capacity in result:
            pool_capacity.pool_total_size = long(pool_capacity.pool_total_size / ratio)
            pool_capacity.available_capacity = long(pool_capacity.available_capacity + pool_capacity.pool_total_size * (1-ratio))
            pool_capacity.used_capacity = pool_capacity.pool_total_size - pool_capacity.available_capacity



def calc_capacity_with_ratio():
    return LooseVersion(get_zstone_version()) >= LooseVersion("4.3.6")


def get_zstone_version():
    o = bash.bash_errorout("/opt/zstone/bin/zstnlet -h | grep Version:")
    return o.split("Version:")[1].strip()


def get_full_ratio():
    o = bash.bash_errorout("ceph osd dump | grep -E '^full_ratio'")
    return float(o.split()[1].strip())