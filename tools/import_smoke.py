#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入冒烟：对 Phase A 目标模块执行 import，暴露 R-01 / R-06 / R-11 等导入期失败。

只把第一方缺陷当作闸门失败（见 docstring 末尾的 CODE/ENV 判据）。
CODE: 首方代码缺陷，包括缺失根为第一方包，或为 py3 已移除的 py2 标准库模块
（ removed-py2-stdlib，如 commands/urlparse，属 R-06 代码缺陷，不是环境问题）。
ENV: 缺失根为第三方包，属环境缺依赖。
"""
import importlib
import os
import sys

FIRST_PARTY = ("zstacklib", "kvmagent")

# py2 stdlib modules removed in py3. A missing one is a first-party code defect
# (the code still imports it), not an environment problem.
PY2_ONLY_STDLIB = ("commands", "urlparse", "ConfigParser", "Queue",
                   "StringIO", "cStringIO", "httplib", "urllib2", "thread")
UTILS = "zstacklib/zstacklib/utils"
PLUGINS = "kvmagent/kvmagent/plugins"


def modules():
    out = ["zstacklib.utils.%s" % f[:-3] for f in sorted(os.listdir(UTILS))
           if f.endswith(".py") and f != "__init__.py"]
    out += ["kvmagent.plugins.%s" % f[:-3] for f in sorted(os.listdir(PLUGINS))
            if f.endswith(".py") and f != "__init__.py"]
    return out


def missing_root(exc):
    """沿异常链找出 ImportError 缺失模块的顶层名；找不到则返回 None。"""
    while exc is not None:
        if isinstance(exc, ImportError) and exc.name:
            return exc.name.split(".")[0]
        exc = exc.__cause__ or exc.__context__
    return None


def main():
    code_failed, env_missing = [], []
    for m in modules():
        try:
            importlib.import_module(m)
            print("OK    %s" % m)
        except Exception as e:
            root = missing_root(e)
            if (isinstance(e, ImportError) and root not in FIRST_PARTY
                    and root not in PY2_ONLY_STDLIB):
                print("ENV   %s  %s: %s" % (m, type(e).__name__, e))
                env_missing.append(m)
            else:
                print("CODE  %s  %s: %s" % (m, type(e).__name__, e))
                code_failed.append(m)
    print("\nfirst-party(CODE) 失败: %d    环境缺三方包(ENV): %d / 共 %d 模块"
          % (len(code_failed), len(env_missing), len(modules())))
    return 1 if code_failed else 0


if __name__ == "__main__":
    sys.exit(main())
