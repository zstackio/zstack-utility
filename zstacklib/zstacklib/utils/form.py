

def load(stdout, sep=None):
    # type: (str, str) -> list[dict]
    ret = []
    lines = stdout.splitlines()
    if len(lines) < 2:
        return ret

    heads = lines[0].split(sep)
    for l in lines[1:]:
        o = {}
        for i, v in enumerate(l.split(sep)):
            o[heads[i]] = v
        ret.append(o)

    return ret
