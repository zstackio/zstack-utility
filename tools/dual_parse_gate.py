#!/usr/bin/env python3
"""双模解析闸门：本地 py3 编译 + 远程 py2.7 编译（ssh stdin 管道，不在节点留文件）。"""
import subprocess
import sys

PY2_HOST = "root@55.32.170.150"
PY2 = "python2.7"


def py3_ok(path):
    src = open(path, encoding="utf-8", errors="ignore").read()
    try:
        compile(src, path, "exec")
        return None
    except SyntaxError as e:
        return "py3: %s (line %s)" % (e.msg, e.lineno)


def py2_ok(path):
    src = open(path, encoding="utf-8", errors="ignore").read()
    remote = "%s -c \"import sys; compile(sys.stdin.read(), 'f', 'exec')\"" % PY2
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", PY2_HOST, remote],
        input=src.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if p.returncode != 0:
        return "py2: " + p.stdout.decode("utf-8", "replace").strip().splitlines()[-1]
    return None


def main(argv):
    if "--selftest" in argv:
        # 自测：一个必然 py3 失败、py2 成功的样本（八进制字面量）
        bad = "/tmp/_py2ok_sample.py"
        open(bad, "w").write("x = 0775\n")
        assert py3_ok(bad) is not None, "selftest: py3 应拒绝 0775"
        assert py2_ok(bad) is None, "selftest: py2 应接受 0775（检查到 .150 的 ssh）"
        print("selftest OK")
        return 0
    files = [a for a in argv if not a.startswith("--")]
    failed = 0
    for f in files:
        err = py3_ok(f) or py2_ok(f)
        if err:
            print("FAIL %s  %s" % (f, err))
            failed += 1
        else:
            print("OK   %s" % f)
    print("\n%d/%d 通过" % (len(files) - failed, len(files)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
