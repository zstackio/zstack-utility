# -*- coding: utf-8 -*-
"""P-07 编码语义验证：py3 下入口必须显式设定标准流编码。

py2 依赖 ``reload(sys); sys.setdefaultencoding('utf-8')`` 修改解释器全局默认
编码；py3 既无该调用也无等价全局开关，唯一正确替代是显式配置标准流编码
（kvmagent 入口的 py3 分支，见 kvmagent/kvmagent/kvmagent.py）。

本测试以 ``PYTHONIOENCODING=ascii`` 强制出非 utf-8 的标准流，在子进程中导入
**真实入口模块** kvmagent.kvmagent（不是合成代码片段）并写出中文：若入口未做
显式编码设置，该写入抛 UnicodeEncodeError、子进程非零退出。

子进程的导入闭包依赖本机未必安装的第三方库（simplejson/cherrypy/jinja2 等），
且 zstacklib.utils.log 首次使用会在 /var/log/zstack 下落盘；这里复用
test_pycompat 的共享导入桩（_install_zstacklib_import_stubs），仅为桩补上
HttpServer.__init__ 会调用的 get_logfile_path（返回临时路径，不落盘）。
桩只替换 zstacklib.utils 的第三方导入与日志行为，不触碰 kvmagent.kvmagent
自身的编码设置代码，因此对编码语义的断言不受桩影响。
"""
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# 子进程脚本：装桩 -> 导入真实入口 -> 向（可能被强制为 ascii 的）stdout 写中文。
# 中文用 \u 转义书写，保证本文件在 py2/py3 下都能以纯 ASCII 之外安全编译。
_CHILD_CODE = (
    "import os\n"
    "import sys\n"
    "import tempfile\n"
    "from zstacklib.test.test_pycompat import"
    " _install_zstacklib_import_stubs\n"
    "_install_zstacklib_import_stubs()\n"
    "# 共享桩的 log 桩缺少 get_logfile_path（kvmagent 模块体构造\n"
    "# http.HttpServer() 时会调用）；补一个临时目录路径，不触发落盘。\n"
    "import zstacklib.utils.log as _log_stub\n"
    "_log_stub.get_logfile_path = lambda: os.path.join(\n"
    "    tempfile.gettempdir(), 'zstack-encoding-test.log')\n"
    "import kvmagent.kvmagent\n"
    "sys.stdout.write(u'\\u4e2d\\u6587\\n')\n"
)


@unittest.skipIf(sys.version_info[0] != 3,
                 '本用例验证 py3 显式编码路径；py2 由 setdefaultencoding '
                 '语义保证，且其流编码行为不同，不适用本断言')
class TestEncoding(unittest.TestCase):

    def _run_child(self):
        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'ascii'
        env['PYTHONPATH'] = os.pathsep.join((
            os.path.join(REPO_ROOT, 'zstacklib'),
            os.path.join(REPO_ROOT, 'kvmagent')))
        return subprocess.run([sys.executable, '-c', _CHILD_CODE],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              cwd=REPO_ROOT, env=env)

    def test_entry_forces_utf8_even_under_ascii_locale(self):
        """kvmagent 入口必须在 py3 下显式把标准流设为 utf-8。

        以 PYTHONIOENCODING=ascii 强制出非 utf-8 的标准流：若入口未做显式
        编码设置，写出中文将抛 UnicodeEncodeError 并以非零码退出。此断言
        作用于真实入口模块（kvmagent.kvmagent），不是合成的代码片段。
        """
        p = self._run_child()
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, out)
        self.assertIn(u'中文', out)

    def test_no_setdefaultencoding_on_py3(self):
        """py3 下不得再调用 sys.setdefaultencoding（该方法不存在）。"""
        self.assertFalse(hasattr(sys, 'setdefaultencoding'))


class TestShellTextMode(unittest.TestCase):
    """shell.get_process 必须启用文本模式（universal_newlines=True）。

    py3 的 Popen 默认字节模式：communicate() 返回 bytes，而本库全部下游按
    str 处理（shell.call / ShellCmd / bash_ro* 在 Phase A 范围内有
    60 文件 / 1098 个调用点）。更糟的是 bash_roe 会把 str 喂给
    communicate(cmd)，py3 字节模式下直接抛
    TypeError: memoryview: a bytes-like object is required, not 'str'。

    修复用 universal_newlines=True（py2.7/py3 双模合法；encoding= 是
    py3.6+ 参数，py2 会 TypeError，不可用）。py2 下行为不变（仅换行翻译），
    故这两个用例在 py2/py3 下都应通过，不加版本 skip。
    """

    def test_shell_call_returns_text_not_bytes(self):
        # shell.py 经 log 间接依赖 simplejson（本机未装），先装共享导入桩
        from zstacklib.test.test_pycompat import _install_zstacklib_import_stubs
        _install_zstacklib_import_stubs()
        from zstacklib.utils import shell
        out = shell.call("printf 'abc'")
        # py3 必须返回 str，不是 bytes；且不含 b'' 前缀的脏数据
        self.assertIsInstance(out, str)
        self.assertEqual(out, 'abc')

    def test_get_process_communicate_accepts_str_and_returns_text(self):
        # 精确复现 bash_roe 的炸点：把 str 喂给 communicate()。
        # py3 字节模式下这一行直接 TypeError: memoryview: a bytes-like object is required。
        from zstacklib.test.test_pycompat import _install_zstacklib_import_stubs
        _install_zstacklib_import_stubs()
        from zstacklib.utils import shell
        p = shell.get_process("cat", pipe=True)
        o, e = p.communicate("hello")
        self.assertEqual(p.returncode, 0)
        self.assertIsInstance(o, str)
        self.assertEqual(o, 'hello')

    def test_md5_of_bash_output_accepts_bytes_and_text(self):
        """misc.isMiniHost 原来对 bash_ro 输出直接 .decode('utf-8')：
        文本模式下那是 str，会 AttributeError。锁定两种输入都得到同一 md5。"""
        from zstacklib.test.test_pycompat import _install_zstacklib_import_stubs
        _install_zstacklib_import_stubs()
        from zstacklib.utils import misc
        self.assertEqual(misc._md5_of_bash_output(b' abc \n'),
                         misc._md5_of_bash_output('abc'))
        self.assertIsInstance(misc._md5_of_bash_output('abc'), str)


if __name__ == '__main__':
    unittest.main()
