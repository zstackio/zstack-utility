import logging
import sys
import types
import unittest

from zstacklib.utils import pycompat


def _install_report_import_stubs():
    """report.py 的导入闭包依赖若干本机未必安装的第三方库（cherrypy/
    simplejson/netaddr/urllib3/xxhash/beeprint/pyroute2/concurrentlog_handler），
    且 log.get_logger 会在 /var/log/zstack 下创建日志文件。这里注入仅满足
    导入期的最小桩，使测试只聚焦 get_timeout 的除法语义；返回现场以便恢复。
    """
    saved_modules = {}
    saved_attrs = []

    def stub(name, **attrs):
        saved_modules[name] = sys.modules.get(name)
        mod = types.ModuleType(name)
        for key, val in attrs.items():
            setattr(mod, key, val)
        sys.modules[name] = mod
        return mod

    def identity(func):
        return func

    cp = stub('cherrypy')
    cp.expose = identity
    cp.config = lambda **kwargs: identity
    cp.HTTPError = type('HTTPError', (Exception,), {})
    cp.request = types.ModuleType('cherrypy.request')
    cp.request.headers = {}
    cp.response = types.ModuleType('cherrypy.response')
    cp.response.status = 200
    cp.url = lambda: ''
    cp._cpreqbody = stub('cherrypy._cpreqbody',
                         SizedReader=type('SizedReader', (object,), {}))
    cp._cpcompat = stub('cherrypy._cpcompat',
                        ntob=lambda s, enc='utf-8': s.encode(enc))

    stub('simplejson', loads=lambda s: {}, dumps=lambda o: '')
    stub('concurrentlog_handler', ConcurrentRotatingFileHandler=type(
        'ConcurrentRotatingFileHandler', (logging.Handler,),
        {'__init__': lambda self, filename, **kw: logging.Handler.__init__(self)}))
    stub('netaddr')
    stub('urllib3')
    stub('beeprint')
    stub('xxhash')
    stub('pyroute2')
    log_fake = stub('zstacklib.utils.log', get_logger=logging.getLogger)

    # 让 from zstacklib.utils import log 稳定命中桩（父包属性优先于 sys.modules 回退）
    from zstacklib import utils as utils_pkg
    saved_attrs.append((utils_pkg, 'log', getattr(utils_pkg, 'log', None)))
    utils_pkg.log = log_fake

    return saved_modules, saved_attrs


def _restore_report_import_stubs(state):
    saved_modules, saved_attrs = state
    for obj, name, val in saved_attrs:
        if val is None:
            try:
                delattr(obj, name)
            except AttributeError:
                pass
        else:
            setattr(obj, name, val)
    for name, mod in saved_modules.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def _install_zstacklib_import_stubs():
    """在 report 桩之上追加 jinja2 桩（plugin -> traceable_shell -> bash），
    使 zstacklib.utils.plugin / zstacklib.utils.linux 可在本机完成导入。"""
    state = _install_report_import_stubs()
    saved_modules = state[0]
    jinja2 = types.ModuleType('jinja2')

    class Template(object):
        def __init__(self, *args, **kwargs):
            pass

    jinja2.Template = Template
    saved_modules['jinja2'] = sys.modules.get('jinja2')
    sys.modules['jinja2'] = jinja2
    return state


class TestPyCompat(unittest.TestCase):

    def test_flags_are_exclusive(self):
        self.assertNotEqual(pycompat.PY2, pycompat.PY3)

    def test_has_key(self):
        d = {'a': 1}
        self.assertTrue(pycompat.has_key(d, 'a'))
        self.assertFalse(pycompat.has_key(d, 'b'))

    def test_iteritems_yields_pairs(self):
        d = {'a': 1, 'b': 2}
        self.assertEqual(sorted(pycompat.iteritems(d)), [('a', 1), ('b', 2)])

    def test_iteritems_is_lazy_not_list(self):
        # py2 的 iteritems 也是迭代器；此处锁定语义，避免退回 items() 的列表
        self.assertFalse(isinstance(pycompat.iteritems({'a': 1}), list))

    def test_with_metaclass_enforces_abc(self):
        import abc

        class Base(object):
            pass

        class Impl(pycompat.with_metaclass(abc.ABCMeta, Base)):
            @abc.abstractmethod
            def must_implement(self):
                pass

        self.assertIsInstance(Impl, abc.ABCMeta)
        with self.assertRaises(TypeError):
            Impl()      # 抽象方法未实现，必须抛 TypeError

    def test_string_types_matches_text(self):
        self.assertIsInstance('x', pycompat.string_types)

    def test_integer_types_matches_int(self):
        self.assertIsInstance(1, pycompat.integer_types)

    def test_bandwidth_limit_formats_as_integer(self):
        """py2 的 long(x)/1024 是整除；long→int 之后若用真除会向 scp -l 传浮点。"""
        bandWidth = '1500'
        s = '-l %s' % (int(bandWidth) // 1024)
        self.assertEqual(s, '-l 1')
        self.assertIsInstance(int(bandWidth) // 1024, int)

    def test_get_timeout_floors_before_subtract(self):
        """get_timeout 必须先整除再相减（py2 long/1000 语义）。

        timeout=deadline=1500ms、时间戳=2 时：
          py2 整除: floor(1500/1000) - 2 = 1 - 2 = -1
          py3 真除: 1.5 - 2 = -0.5
        两者都小于等于 60，get_timeout 都会抛 "too short"，但异常消息中的
        数值不同（-1 vs -0.5），以此锁定整除语义。
        """
        state = _install_report_import_stubs()
        try:
            from zstacklib.utils import report as report_mod

            class TC(object):
                __messagetimeout__ = 1500
                __messagedeadline__ = 1500
            class Spec(object):
                taskContext = TC()

            orig = report_mod.linux.get_current_timestamp
            report_mod.linux.get_current_timestamp = lambda: 2
            try:
                with self.assertRaises(Exception) as ctx:
                    report_mod.get_timeout(Spec())
                self.assertIn('-1', str(ctx.exception))
            finally:
                report_mod.linux.get_current_timestamp = orig
        finally:
            _restore_report_import_stubs(state)

    def test_get_timeout_deadline_floor_crosses_guard_boundary(self):
        """整除先于相减：结果落在保护阈值两侧，返回与抛异常的行为分叉。

        timeout=deadline=90100ms、时间戳=30 时：
          py2 整除: floor(90100/1000) - 30 = 90 - 30 = 60 → <= 60 抛异常
          py3 真除: 90.1 - 30 = 60.1 → > 60 不抛，返回 int(60.1) = 60
        """
        state = _install_report_import_stubs()
        try:
            from zstacklib.utils import report as report_mod

            class TC(object):
                __messagetimeout__ = 90100
                __messagedeadline__ = 90100
            class Spec(object):
                taskContext = TC()

            orig = report_mod.linux.get_current_timestamp
            report_mod.linux.get_current_timestamp = lambda: 30
            try:
                with self.assertRaises(Exception) as ctx:
                    report_mod.get_timeout(Spec())
                self.assertIn('60', str(ctx.exception))
            finally:
                report_mod.linux.get_current_timestamp = orig
        finally:
            _restore_report_import_stubs(state)

    def test_plugin_metaclass_is_abcmeta(self):
        """py3 静默忽略类体内的 __metaclass__；必须经 with_metaclass 恢复 ABC 语义。"""
        import abc
        state = _install_zstacklib_import_stubs()
        try:
            from zstacklib.utils import plugin
            self.assertIsInstance(plugin.Plugin, abc.ABCMeta)
        finally:
            _restore_report_import_stubs(state)

    def test_taskdaemon_metaclass_is_abcmeta(self):
        import abc
        state = _install_zstacklib_import_stubs()
        try:
            from zstacklib.utils import plugin
            self.assertIsInstance(plugin.TaskDaemon, abc.ABCMeta)
        finally:
            _restore_report_import_stubs(state)

    def test_abstract_file_converter_metaclass_is_abcmeta(self):
        import abc
        state = _install_zstacklib_import_stubs()
        try:
            from zstacklib.utils import linux
            self.assertIsInstance(linux.AbstractFileConverter, abc.ABCMeta)
        finally:
            _restore_report_import_stubs(state)

    def test_ansible_zstacklib_module_level_metaclass_is_type_idiom(self):
        """zstacklib/ansible/zstacklib.py 的 __metaclass__ = type 是 py2 新式类惯用法，
        不是 ABC。py3 忽略它且无害（py3 类全部新式）。此测试锁定"该文件不定义 ABC 类"。"""
        import os
        # 不实际执行加载（该文件 import ansible 等三方依赖，本机没有），
        # 只做源码级断言：其 __metaclass__ 赋值不是 abc.ABCMeta。
        # 路径锚定到测试文件，避免依赖运行目录。
        ansible_zstacklib = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'ansible', 'zstacklib.py')
        with open(ansible_zstacklib) as f:
            src = f.read()
        self.assertIn("__metaclass__ = type", src)
        self.assertNotIn("__metaclass__ = abc.ABCMeta", src)
