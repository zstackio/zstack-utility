import simplejson
import types

from zstacklib.utils import pycompat


class NoneSupportedTypeError(Exception):
    """not supported type error"""
    pass


class JsonObject(object):
    def __init__(self):
        pass

    def put(self, name, val):
        setattr(self, name, val)

    def dump(self):
        return simplejson.dumps(self.__dict__, ensure_ascii=True)

    def hasattr(self, name):
        if getattr(self, name):
            return True
        return False

    def __getitem__(self, name):
        return getattr(self, name)

    def __getattr__(self, name):
        if name.endswith('_'):
            n = name[:-1]
            if hasattr(self, n):
                return getattr(self, n)
            else:
                return None
        else:
            return None

    def __len__(self):
        return len(self.__dict__)

    def to_dict(self):
        return self.__dict__


# covers long as well
def _is_int(val):
    try:
        int(val)
        return True
    except ValueError:
        return False


def _is_float(val):
    try:
        float(val)
        return True
    except ValueError:
        return False


def _is_bool(val):
    return val in ['True', 'true', 'False', 'false']


def _to_proper_type(val):
    if _is_bool(val):
        return bool(val)
    elif _is_float(val):
        return float(val)
    elif _is_int(val):
        return int(val)
    else:
        return str(val)


def _parse_list(lst):
    vals = []
    for l in lst:
        if _is_unsupported_type(l):
            raise NoneSupportedTypeError("Cannot parse object: %s, type: %s, list dump: %s" % (l, type(l), lst))

        if _is_primitive_types(l):
            vals.append(l)
        elif isinstance(l, dict):
            dobj = _parse_dict(l)
            vals.append(dobj)
        elif isinstance(l, list):
            lobj = _parse_list(l)
            vals.append(lobj)
        else:
            raise NoneSupportedTypeError("Cannot parse object: %s, type: %s, list dump: %s" % (l, type(l), lst))
    return vals


def _parse_dict(d):
    dobj = JsonObject()
    for key in d.keys():
        val = d[key]
        if _is_unsupported_type(val):
            raise NoneSupportedTypeError("Cannot parse object: %s, type: %s, dict dump: %s" % (val, type(val), d))

        if _is_primitive_types(val):
            setattr(dobj, key, val)
        elif isinstance(val, list):
            lst = _parse_list(val)
            setattr(dobj, key, lst)
        elif isinstance(val, dict):
            nobj = _parse_dict(val)
            setattr(dobj, key, nobj)
        elif val is None:
            setattr(dobj, key, None)
        else:
            raise NoneSupportedTypeError("Cannot parse object: %s, type: %s, dict dump: %s" % (val, type(val), d))

    return dobj


def loads(jstr):
    try:
        root = simplejson.loads(jstr)
    except Exception as e:
        raise NoneSupportedTypeError("Cannot compile string: %s to a jsonobject" % jstr)
    if isinstance(root, dict):
        return _parse_dict(root)
    if isinstance(root, list):
        return _parse_list(root)
    else:
        return root


def _new_json_object():
    return JsonObject()


def nj():
    return _new_json_object()


def _get_unsupported_types():
    '''py2/py3 语义等价的“不可 JSON 序列化类型”集合（按解释器各取合法名字）。

    py2 独有名 → py3 对应：ComplexType→complex、TupleType→tuple、FileType→io.IOBase、
    XRangeType→range、DictProxyType→types.MappingProxyType；
    UnboundMethodType 在 py3 无对应（方法统一为 MethodType，已被覆盖）。
    '''
    if pycompat.PY2:
        return (types.ComplexType, types.TupleType, types.FunctionType, types.LambdaType,
                types.GeneratorType, types.MethodType, types.UnboundMethodType, types.BuiltinFunctionType,
                types.BuiltinMethodType, types.FileType,
                types.XRangeType, types.TracebackType, types.FrameType, types.DictProxyType,
                types.NotImplementedType, types.GetSetDescriptorType,
                types.MemberDescriptorType)
    import io
    return (complex, tuple, types.FunctionType, types.LambdaType,
            types.GeneratorType, types.MethodType, types.BuiltinFunctionType,
            types.BuiltinMethodType, io.IOBase,
            range, types.TracebackType, types.FrameType, types.MappingProxyType,
            types.NotImplementedType, types.GetSetDescriptorType,
            types.MemberDescriptorType)


_UNSUPPORTED_TYPES = _get_unsupported_types()


def _is_unsupported_type(obj):
    return isinstance(obj, _UNSUPPORTED_TYPES)


def _is_primitive_types(obj):
    # py2: (bool,float,int,long,unicode,str) 与原 (BooleanType,LongType,IntType,FloatType,StringType,UnicodeType) 完全一致；
    # py3: str/bytes 分别承接 py2 的 unicode/str，接受集合语义不变
    return isinstance(obj, (bool, float) + pycompat.integer_types + (pycompat.text_type, pycompat.binary_type))


def _dump_list(lst):
    nlst = []
    for val in lst:
        if _is_unsupported_type(val):
            raise NoneSupportedTypeError('Cannot dump val: %s, type: %s, list dump: %s' % (val, type(val), lst))

        if _is_primitive_types(val):
            nlst.append(val)
        elif isinstance(val, dict):
            nlst.append(val)
        elif isinstance(val, list):
            tlst = _dump_list(val)
            nlst.append(tlst)
        elif isinstance(val, type(None)):
            pass
        else:
            nmap = _dump(val)
            nlst.append(nmap)

    return nlst


def _dump(obj, include_protected_attr=False):
    if _is_primitive_types(obj): return simplejson.dumps(obj, ensure_ascii=True)

    ret = {}
    items = pycompat.iteritems(obj) if isinstance(obj, dict) else pycompat.iteritems(obj.__dict__)
    for key, val in items:
        if key.startswith('_') and not include_protected_attr: continue
        if _is_unsupported_type(obj):
            raise NoneSupportedTypeError('cannot dump %s, type:%s, object dict: %s' % (val, type(val), obj.__dict__))

        if _is_primitive_types(val):
            ret[key] = val
        elif isinstance(val, dict):
            if len(val) == 0:
                ret[key] = val
                continue

            nmap = _dump(val, include_protected_attr=include_protected_attr)
            ret[key] = nmap
        elif isinstance(val, list):
            nlst = _dump_list(val)
            ret[key] = nlst
        elif isinstance(val, type(None)):
            pass
        else:
            nmap = _dump(val, include_protected_attr=include_protected_attr)
            ret[key] = nmap
    return ret


def dumps(obj, pretty=False, include_protected_attr=False):
    jsonmap = _dump(obj, include_protected_attr)
    if pretty:
        return simplejson.dumps(jsonmap, ensure_ascii=True, sort_keys=True, indent=4)
    else:
        return simplejson.dumps(jsonmap, ensure_ascii=True)


def from_dict(obj):
    # type: (dict) -> JsonObject

    return loads(dumps(obj))
