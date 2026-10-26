# dnsmasq SRPM build

这个目录用于从 dnsmasq src.rpm 编译出 ZStack 使用的 dnsmasq 二进制。
当前 `build.sh` 主要依赖 Red Hat 10 最新发布的 dnsmasq src.rpm 作为构建基线；
该 src.rpm 中已经包含 Red Hat 维护的安全漏洞修复 patch 栈。ZStack 自己维护的
功能和 bugfix patches 会在 src.rpm 自带 patch 栈之后继续追加。

`build.sh` 的输入是两个必填项：

```text
1. --src-rpm        dnsmasq source rpm
2. --patch-dir     额外 patch 目录，目录中必须包含 series
```

参数说明中省略了值占位，但执行命令时仍需要在参数后传入对应的文件或目录。
脚本不会联网下载源码或 patches。

## 目录结构

```text
rpmbuild/
└── dnsmasq/
    ├── build.sh
    ├── README.md
    └── v2.90/
        ├── series
        └── ZStack extra patches
```

`--patch-dir` 不要求固定命名为 `v2.90`，只要目录中有 `series`，并且
`series` 中引用的 patch 文件都在该目录下即可。

## 构建流程

执行流程：

1. 解包 Red Hat 10 dnsmasq `--src-rpm` 到临时工作目录。
2. 从 src.rpm 的 spec 中解析 `Name`、`Version`、`Source0` 和 `Patch*`。
3. 解压 `Source0` 对应的 dnsmasq 源码包。
4. 按 spec 中的 `Patch*` 顺序应用 src.rpm 自带 patches，包括 Red Hat 已发布的安全漏洞修复。
5. 读取 `--patch-dir/series`，继续应用外部 patches。
6. 编译 dnsmasq。
7. 如指定 `--output`，把编译出的二进制复制到目标路径。

`--patch-dir` 只放 ZStack 自己追加维护的 patch。Red Hat 维护的安全修复 patch
由 src.rpm 的 spec 自动解析并应用。

## 使用示例

按默认 native 平台编译：

```bash
./rpmbuild/dnsmasq/build.sh \
  --src-rpm ../patches/dnsmasq-2.90-7.el10_2.src.rpm \
  --patch-dir ./rpmbuild/dnsmasq/v2.90
```

编译并更新 KVM agent 使用的二进制：

```bash
./rpmbuild/dnsmasq/build.sh \
  --src-rpm ../patches/dnsmasq-2.90-7.el10_2.src.rpm \
  --patch-dir ./rpmbuild/dnsmasq/v2.90 \
  --output ./kvmagent/ansible/dnsmasq
```

指定工作目录：

```bash
./rpmbuild/dnsmasq/build.sh \
  --src-rpm ../patches/dnsmasq-2.90-7.el10_2.src.rpm \
  --patch-dir ./rpmbuild/dnsmasq/v2.90 \
  --work-dir ./build/dnsmasq
```

构建结束后，脚本会自动删除工作目录。

交叉编译 aarch64：

```bash
./rpmbuild/dnsmasq/build.sh \
  --src-rpm ../patches/dnsmasq-2.90-7.el10_2.src.rpm \
  --patch-dir ./rpmbuild/dnsmasq/v2.90 \
  --platform aarch64 \
  --output ./kvmagent/ansible/dnsmasq_aarch64
```

## 常用参数

```text
--src-rpm     dnsmasq source rpm，必填
--patch-dir   额外 patch 目录，必填，目录中必须包含 series
--platform    native/x86_64/aarch64/loongarch64/mips64el
--cc          指定 C 编译器，优先级高于 --platform 默认映射
--jobs        make 并发数，默认 nproc
--output      编译成功后复制 dnsmasq 二进制到指定路径
--work-dir    构建工作目录，默认自动创建临时目录
```

## 注意事项

- 脚本会在临时目录中解包并构建，不会修改外部 dnsmasq 源码目录。
- 即使指定 `--work-dir`，构建结束后该目录也会被清理。
- 外部 patches 的应用顺序完全由 `--patch-dir/series` 控制。
- 交叉编译需要目标平台 toolchain 已安装，例如 `aarch64-linux-gnu-gcc`。
