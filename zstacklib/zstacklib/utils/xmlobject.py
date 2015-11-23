'''

@author: Frank
'''
import xml.etree.ElementTree as etree
import re
import types

class XmlObjectError(Exception):
    '''XmlObject error'''

class XmlObject(object):
    def __init__(self, tag):
        self.__tag_name__ = tag
    
    def get_tag(self):
        return self.__tag_name__
    
    def put_attr(self, name, val):
        val = val.strip().strip('\t')
        setattr(self, name + '_', val)
    
    def put_text(self, val):
        val = val.strip().strip('\n').strip('\t')
        setattr(self, 'text_', val)

    def del_node(self, name):
        delattr(self, name)
    
    def hasattr(self, name):
        return hasattr(self, name)

    def replace_node(self, name, val):
        setattr(self, name, val)

    def put_node(self, name, val):
        if not hasattr(self, name):
            setattr(self, name, val)
            return
            
        nodes = getattr(self, name)
        if not isinstance(nodes, types.ListType):
            nodes = []
            old = getattr(self, name)
            nodes.append(old)
            nodes.append(val)
            setattr(self, name, nodes)
        else:
            nodes.append(val)
            setattr(self, name, nodes)
    
    def get(self, name, default=None):
        if hasattr(self, name):
            val = getattr(self, name)
            if name.endswith('_'):
                return val
            else:
                return val.text_
        else:
            return default
    
    def get_child_node(self, key):
        if not hasattr(self, key):
            return None
        return getattr(self, key)
    
    def get_child_node_as_list(self, key):
        if not hasattr(self, key):
            return []
        
        children = getattr(self, key)
        if isinstance(children, types.ListType):
            return children
        else:
            return [children]
    
    def get_children_nodes(self):
        children = {}
        for key, value in self.__dict__.items():
            if isinstance(value, XmlObject) or isinstance(value, types.ListType):
                children[key] = value
        return children
    
    
    def dump(self):
        def _dump(obj):
            xmlstr = []
            opentag = []
            opentag.append('<%s' % obj.get_tag())
            for key, val in obj.__dict__.iteritems():
                if not key.endswith('_') or key.startswith('_') or key == 'text_':
                    continue
                opentag.append('%s="%s"' % (key[:-1], val))
            xmlstr.append(' '.join(opentag))
            xmlstr.append('>')
            
            found_child = False
            for key, val in obj.__dict__.iteritems():
                if isinstance(val, XmlObject):
                    xmlstr.append(_dump(val))
                    found_child = True
                if isinstance(val, types.ListType):
                    for l in val:
                        if isinstance(l, XmlObject):
                            xmlstr.append(_dump(l))
                            found_child = True
                
            if not found_child and hasattr(obj, 'text_'):
                xmlstr.append(getattr(obj, 'text_'))
            xmlstr.append('</%s>' % obj.get_tag())
            return ''.join(xmlstr)
        
        return _dump(self)
    
    def __getattr__(self, name):
        if name.endswith('__'):
            n = name[:-1]
            if hasattr(self, n):
                return getattr(self, n)
            else:
                return None
        else:
            e = AttributeError('%s has no attribute %s. missing attribute %s in element <%s>' % (self.__class__.__name__, name, name, self.__tag_name__))
            setattr(e, 'missing_attrib', name)
            setattr(e, 'tag_name', self.__tag_name__)
            raise e
    
    def has_element(self, elementstr):
        return has_element(self, elementstr)

def _loads(node):
    xo = XmlObject(node.tag)
    for key in node.attrib.keys():
        xo.put_attr(key, node.attrib.get(key))
    if node.text:
        xo.put_text(node.text)
    else:
        xo.put_text('')
    for n in list(node):
        sub_xo = _loads(n)
        xo.put_node(n.tag, sub_xo)
    return xo
    
def loads(xmlstr):
    try:
        xmlstr = re.sub(r'xmlns=".*"', '', xmlstr)
        root = etree.fromstring(xmlstr)
        return _loads(root)
    except Exception as e:
        err = '''error when parsing xml document:
exception:
%s
xml content:
%s''' % (str(e), xmlstr)
        raise XmlObjectError(err)
        

def loads_from_xml_file(path):
    with open(path, 'r') as fd:
        xmlstr = fd.read()
    return loads(xmlstr)

def has_element(xmlobj, elementstr):
    elements = elementstr.split('.')
    it = elements.__iter__()
    
    def _has_element(obj):
        try:
            e = it.next()
            if hasattr(obj, e):
                return _has_element(getattr(obj, e))
            else:
                return False
        except StopIteration:
            return True
    
    return _has_element(xmlobj)

def safe_list(obj):
    if isinstance(obj, types.ListType):
        return obj
    else:
        return [obj]