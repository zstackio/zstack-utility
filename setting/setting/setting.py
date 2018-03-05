'''

@author: frank
'''
import urwid

class SettingCategory(object):
    def __init__(self, name):
        self.name = name
        self.children = None
        self.mapping = None
    
    def get_child(self, name):
        if not self.mapping:
            self.mapping = {}
            for c in self.children:
                self.mapping[c.name] = c
        return self.mapping.get(name, None)
        
class SettingEntry(object):
    def __init__(self, name, default_value=None):
        self.name = name
        self.default_value = default_value
        self.help = None
        self.value = None
        
class EmptyWidget(urwid.TreeWidget):
    """A marker for expanded directories with no contents."""
    def __init__(self, node):
        super(EmptyWidget, self).__init__(node)
        
    def get_display_text(self):
        return ('flag', '(empty directory)')
    
class EmptyNode(urwid.TreeNode):
    def load_widget(self):
        return EmptyWidget(self)
    
class FileNode(urwid.TreeNode):
    def __init__(self, entry, parent=None):
        pass
        
class CategoryNode(urwid.ParentNode):
    
    def __init__(self, category, parent=None):
        self.category = category
        super(CategoryNode, self).__init__(self.category.children, key=self.category.name, parent=parent)
        
    def load_child_keys(self):
        return [c.name for c in self.category.children]
    
    def load_child_node(self, key):
        child = self.category.get_child(key)
        if not child:
            return EmptyNode()
        else:
            if issubclass(child.__class__, SettingEntry):
                pass
            else:
                return CategoryNode(child, self)
        
class Setting(object):
    '''
    classdocs
    '''

    palette = [
        ('body', 'black', 'light gray'),
        ('flagged', 'black', 'dark green', ('bold','underline')),
        ('focus', 'light gray', 'dark blue', 'standout'),
        ('flagged focus', 'yellow', 'dark cyan', 
                ('bold','standout','underline')),
        ('head', 'yellow', 'black', 'standout'),
        ('foot', 'light gray', 'black'),
        ('key', 'light cyan', 'black','underline'),
        ('title', 'white', 'black', 'bold'),
        ('dirmark', 'black', 'dark cyan', 'bold'),
        ('flag', 'dark gray', 'light gray'),
        ('error', 'dark red', 'light gray'),
        ]
    
    header_text = [
        ('title', "ZSTACK Setting"), "    ",
        ('key', "UP"), ",", ('key', "DOWN"), ",",
        ('key', "PAGE UP"), ",", ('key', "PAGE DOWN"),
        "  ",
        ('key', "SPACE"), "  ",
        ('key', "+"), ",",
        ('key', "-"), "  ",
        ('key', "LEFT"), "  ",
        ('key', "HOME"), "  ", 
        ('key', "END"), "  ",
        ('key', "Q"),
        ]
    
    def __init__(self, category_list):
        '''
        Constructor
        '''
        assert category_list
        self.category_list = category_list
        self.listbox = urwid.TreeListBox(urwid.TreeWalker(CategoryNode('test')))
        self.header = urwid.AttrWrap(urwid.Text(self.header_text), 'head')
        self.view = urwid.Frame(urwid.AttrWrap(self.listbox, 'body'),
                                header=self.header)
        
    def main(self):
        self.loop = urwid.MainLoop(self.view, self.palette, unhandled_input=self._unhandled_input)
        self.loop.run()
    
    def _unhandled_input(self, k):
        if k in ('q', 'Q'):
            raise urwid.ExitMainLoop()

if __name__ == '__main__':
    Setting().main()