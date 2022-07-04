# encoding: utf-8

import copy
import simplejson as json


class LogTree(object):
    '''
    Data structure of tree topology,
    all branch name must be unique.
    '''
    def __init__(self, compact=True):
        self.logs = {}
        self.root = None
        self._depth = {}
        # self._sign = {}
        self.curr_depth = 0
        self.curr_log = []
        self.fork = []
        self.branch_root = None
        self.compact = compact

    def seek(self, log):
        self.curr_log = self.logs[log]
        self.curr_depth = self._depth[log]
        if self.child(log):
            self.fork.append(log)

    def add(self, log, parent=None):
        if parent:
            self.seek(parent)
        if not self.logs:
            self.root = log
        elif log not in self.curr_log:
            self.curr_log.append(log)
        self.curr_depth += 1
        self.logs[log] = self.curr_log = []
        self._depth[log] = self.curr_depth

    def get_branch_root(self, log):
        up_log = self.parent(log)
        if len(self.child(up_log)) == 1:
            self.get_branch_root(up_log)
        else:
            self.branch_root = up_log

    def get_curr_log(self):
        for k in self.logs.keys():
            if self.logs[k] is self.curr_log:
                return k

    def clean_up(self, r=0):
        keys = self.logs.keys()
        logs = self.get_all_logs()
        for k in keys:
            if k not in logs:
                self.logs.pop(k)
        _fork = self.fork[:]
        for f in _fork:
            if (f not in logs) or len(self.child(f)) <= 1:
                f_count = self.fork.count(f)
                for _ in range(f_count):
                    self.fork.remove(f)
        depth_keys = self._depth.keys()
        for dk in depth_keys:
            if dk not in logs:
                self._depth.pop(dk)
        r -= 1
        if r > 0:
            self.clean_up(r)

    def get_all_logs(self):
        vals = self.logs.values()
        logs = [n for log in vals for n in log]
        if self.root in self.logs:
            logs.append(self.root)
        return logs

    def parent(self, log):
        if log == self.root:
            return None
        for k, v in self.logs.iteritems():
            if log in v:
                return k

    def child(self, log):
        return self.logs[log]

    def depth(self):
        return max(self._depth.values())

    def get_depth(self, log):
        return self._depth[log]

    def dump_logs(self):
        logs = copy.deepcopy(self.logs)
        for k, v in self.logs.items():
            if not v:
                logs.pop(k)
        print(json.dumps(logs, indent=4))

    def write_log(self, fpath=None):
        if not self.logs:
            print("Empty log tree.\n")
            return
        grp = []
        nc = []
        indent = {}
        rendered_logs = []
        unlinked_branch = []

        def get_unlinked_branch(rendtr):
            if len(rendtr) > 2:
                # compare indent size to check if branch linking needed
                if len(rendtr[-1][0]) < len(rendtr[-2][0]):
                    unlinked_branch.append(rendtr.pop())
                else:
                    rendtr.pop()
                get_unlinked_branch(rendtr)

        def link_branch(ubr, rendtr):
            nd = ubr.pop()
            nd_ascii = filter(lambda x: x and ord(x[0]) < 127 and not x.isspace(), nd)
            starter = 0 if self.compact else 1
            upbr = rendtr[starter:rendtr.index(nd)]
            upbr.reverse()

            for g in upbr:
                g_ascii = filter(lambda x: x and ord(x[0]) < 127 and not x.isspace(), g)
                if not g_ascii:
                    continue

                root_line = False
                _g = g[:6]

                if g == rendtr[0]:
                    g_index = rendtr.index(g)
                    g = g[6:]
                    root_line = True

                if self.get_depth(g_ascii[0]) <= self.get_depth(nd_ascii[0]) and not root_line:
                    break

                tr = g[0]
                g.remove(tr)
                g.insert(0, ' ' * len(nd[0]))
                g.insert(1, '│' + ' ' * (len(tr) - len(nd[0]) - 1))

                if root_line:
                    _g.extend(g)
                    rendtr[g_index] = _g

            if len(ubr) > 0:
                link_branch(ubr, rendtr)

        def list_all_logs(root=None):
            '''
            all node name shoud be unique except the end leaves
            '''
            if not root:
                root = self.root
            nc.append(root)
            cld = self.child(root)
            if not cld:
                _grp = [j for i in grp for j in i]
                # grp.append([x for x in _nc if x not in _grp])
                # show all end leaves with the same name
                leaf_branch = []
                for x in nc[:-1]:
                    if x in _grp:
                        continue
                    if self.compact:
                        grp.append([x])
                        continue
                    leaf_branch.append(x)

                if self.compact:
                    grp.append([nc[-1]])
                else:
                    leaf_branch.append(nc[-1])
                    grp.append(leaf_branch)

            for c in cld:
                list_all_logs(c)

        def render_logs(g, rendered_logs):
            _g = g[:]
            for n in g:
                indent[self.root] = '   ' if len(self.child(self.root)) > 1 or self.root in self.fork else '  '
                indent[self.root] += ' ' * len(self.root)
                if self.parent(n) in self.fork:
                    if self.fork.count(self.parent(n)) > 1 and n in self.child(self.parent(n))[1:-1]:
                        _g.insert(_g.index(n), ' ' * (len(indent[self.parent(n)]) - 2))
                        _g.insert(_g.index(n), '├─')

                    if len(self.child(self.parent(n))) > 1 and n == self.child(self.parent(n))[-1]:
                        _g.insert(_g.index(n), ' ' * (len(indent[self.parent(n)]) - 2))
                        _g.insert(_g.index(n), '└─')

                if n in self.fork:
                    _g.insert(_g.index(n) + 1, '─┬─')
                    if n not in indent:
                        indent[n] = indent[self.parent(n)] + ' ' * len(n) + '   '
                    for c in self.child(n):
                        if len(self.child(c)) > 1:
                            _indent = '   '
                        else:
                            _indent = '  '
                        indent[c] = indent[n] + ' ' * len(c) + _indent

                elif self.child(n):
                    _g.insert(_g.index(n) + 1, '──')
                    if n not in indent:
                        indent[n] = indent[self.parent(n)] + ' ' * len(n) + '  '

                else:
                    _g.insert(_g.index(n) + 1, '\n')

            rendered_logs.append(_g)

        def render_logs_compact(g, rendered_logs):
            _g = g[:]
            multiples = 2
            indent[self.root] = ' ' * multiples
            for n in g:
                _g.insert(_g.index(n) + 1, '\n')
                if n == self.root:
                    continue

                # add indent head
                _g.insert(_g.index(n), indent[self.parent(n)])

                if n == self.child(self.parent(n))[-1]:
                    _g.insert(_g.index(n), '└─')
                else:
                    _g.insert(_g.index(n), '├─')

                if n not in indent:
                    indent[n] = indent[self.parent(n)] + ' ' * multiples

                if n in self.fork:
                    for c in self.child(n):
                        indent[c] = indent[n] + ' ' * multiples

            rendered_logs.append(_g)

        list_all_logs()

        if self.compact:
            render_func = render_logs_compact
        else:
            render_func = render_logs

        for g in grp:
            render_func(g, rendered_logs)

        get_unlinked_branch(copy.deepcopy(rendered_logs))

        if unlinked_branch:
            link_branch(unlinked_branch, rendered_logs)

        log_tree_text = ''.join([s for t in rendered_logs for s in t])

        if fpath:
            with open(fpath, 'a+') as f:
                f.write(log_tree_text)
                f.write('\n')
        else:
            print(log_tree_text)
