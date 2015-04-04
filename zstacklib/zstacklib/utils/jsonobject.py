'''

@author: frank
'''

import simplejson
import json
import types
import inspect

class NoneSupportedTypeError(Exception):
    '''not supported type error'''

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
        elif isinstance(l, types.DictType):
            dobj = _parse_dict(l)
            vals.append(dobj)
        elif isinstance(l, types.ListType):
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
        elif isinstance(val, types.ListType):
            lst = _parse_list(val)
            setattr(dobj, key, lst)
        elif isinstance(val, types.DictType):
            nobj = _parse_dict(val)
            setattr(dobj, key, nobj)
        else:
            raise NoneSupportedTypeError("Cannot parse object: %s, type: %s, dict dump: %s" % (val, type(val), d))
        
    return dobj
            
def loads(jstr):
    try:
        root = simplejson.loads(jstr)
    except Exception as e:
        raise  NoneSupportedTypeError("Cannot compile string: %s to a jsonobject" % jstr)
    if isinstance(root, types.DictType):
        return _parse_dict(root)
    if isinstance(root, types.ListType):
        return _parse_list(root)
    else:
        return root

def _new_json_object():
    return JsonObject()

def nj():
    return _new_json_object()

def _is_unsupported_type(obj):
    return isinstance(obj, (types.ComplexType, types.TupleType, types.FunctionType, types.LambdaType,
                           types.GeneratorType, types.MethodType, types.UnboundMethodType, types.BuiltinFunctionType, types.BuiltinMethodType, types.FileType,
                           types.XRangeType, types.TracebackType, types.FrameType, types.DictProxyType, types.NotImplementedType, types.GetSetDescriptorType,
                           types.MemberDescriptorType))
    
def _is_primitive_types(obj):
    return isinstance(obj, (types.BooleanType, types.LongType, types.IntType, types.FloatType, types.StringType, types.UnicodeType))

def _dump_list(lst):
    nlst = []
    for val in lst:
        if _is_unsupported_type(val):
            raise NoneSupportedTypeError('Cannot dump val: %s, type: %s, list dump: %s' % (val, type(val), lst))
        
        if _is_primitive_types(val):
            nlst.append(val)
        elif isinstance(val, types.DictType):
            nlst.append(val)
        elif isinstance(val, types.ListType):        
            tlst = _dump_list(val)
            nlst.append(tlst)
        elif isinstance(val, types.NoneType):
            pass
        else:
            nmap = _dump(val)
            nlst.append(nmap)
    
    return nlst
            
def _dump_super(obj):
    s = super(type(obj), obj)
    
def _dump(obj):
    if _is_primitive_types(obj): return simplejson.dumps(obj, ensure_ascii=True)
    
    ret = {}
    items = obj.iteritems() if isinstance(obj, types.DictionaryType) else obj.__dict__.iteritems()
    #items = inspect.getmembers(obj)
    for key, val in items:
        if key.startswith('_'): continue
        
        if _is_unsupported_type(obj):
            raise NoneSupportedTypeError('cannot dump %s, type:%s, object dict: %s' % (val, type(val), obj.__dict__))
        
        if _is_primitive_types(val):
            ret[key] = val
        elif isinstance(val, types.DictType):
            ret[key] = val
        elif isinstance(val, types.ListType):
            nlst = _dump_list(val)
            ret[key] = nlst
        elif isinstance(val, types.NoneType):
            pass
        else:
            nmap = _dump(val)
            ret[key] = nmap
    return ret

def dumps(obj, pretty=False):
    jsonmap = _dump(obj)
    if pretty:
        return simplejson.dumps(jsonmap, ensure_ascii=True, sort_keys=True, indent=4)
    else:
        return simplejson.dumps(jsonmap, ensure_ascii=True)
