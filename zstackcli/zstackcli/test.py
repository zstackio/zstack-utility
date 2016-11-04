'''

@author: frank
'''

import urwid
from zstacklib.utils import log

logger = log.get_logger(__name__)


class Test(object):
    palette = {}

    def main(self):
        lst = []
        walker = urwid.SimpleListWalker(lst)
        self.frame = urwid.ListBox(walker)
        for i in range(1000):
            txt = urwid.Text('%s' % i)
            lst.append(txt)
            walker._modified()
        self.frame.set_focus_valign('top')
        self.loop = urwid.MainLoop(self.frame, self.palette, unhandled_input=self.unhandled_input)
        self.loop.run()

    def unhandled_input(self, k):
        if k in ['q', 'Q']:
            raise urwid.ExitMainLoop()


if __name__ == '__main__':
    Test().main()
