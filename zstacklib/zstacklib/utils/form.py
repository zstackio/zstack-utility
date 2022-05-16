from zstacklib.utils import log

logger = log.get_logger(__name__)


def _load(stdout, sep=None):
    # type: (str, str) -> list[dict]
    ret = []
    lines = stdout.splitlines()
    if len(lines) < 2:
        return ret

    heads = lines[0].split(sep)
    for l in lines[1:]:
        o = {}
        # init
        for h in heads:
            o[h] = None

        for i, v in enumerate(l.split(sep)):
            o[heads[i]] = v
        ret.append(o)

    return ret


def load(stdout, sep=None):
    try:
        return _load(stdout, sep)
    except Exception as e:
        logger.debug("not a standard form:%s" % e.message)
        return []
