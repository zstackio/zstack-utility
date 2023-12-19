## supported_arch_os:
Define arch and os to run unittest.
### format:
x86_64:c76
aarch64:ky10sp2


## blacklist:
filter the cases which is not suitable
### format:
kvmagent/test/shareblock_testsuite/test_shareblock_active_lv.py
zstacklib/test/zstacklib_unittest_suite.py

# prepare_env三个venv的作用
prepare_env.sh 中有三个 virtualenv，分别对应从源码到搭建集测环境的三个步骤，即
|阶段|prepare_env|从源码搭建集测环境|
|--|--|--|
|1|创建venv1并运行install.sh，生成kvma和zslib的tar包|从源码生成tar包及编译bin包|
|2|基于venv1运行kvm.py安装依赖及部署kvma服务，并生成venv2|搭建MN节点并添加Host|
|3|基于kvm.py生成的venv2创建venv3，运行测试用例|进入Host运行测试用例|

其中，venv2 是 {{zstack_root}}/virtualenv/kvm/, 在prepare_env.sh中即/var/lib/zstack/virtualenv/kvm/
