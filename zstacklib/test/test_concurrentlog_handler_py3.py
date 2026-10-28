# -*- coding: utf-8 -*-
import os
import unittest


class TestConcurrentLogHandlerPy3(unittest.TestCase):

    def test_concurrent_rotating_handler_opens_on_py3(self):
        """py3.11 的 FileHandler 把 encoding 默认成 'locale'，会使 codecs.open 抛
        LookupError。此测试锁定：handler 必须能打开文件并写出一条记录。"""
        import logging
        import tempfile

        from zstacklib.utils.concurrentlog_handler import ConcurrentRotatingFileHandler

        path = tempfile.mktemp(suffix=".log")
        try:
            h = ConcurrentRotatingFileHandler(path, "a")
            logger = logging.getLogger("test_concurrent_rotating")
            logger.addHandler(h)
            logger.setLevel(logging.INFO)
            logger.info("probe")
            h.close()
            with open(path) as f:
                self.assertIn("probe", f.read())
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
