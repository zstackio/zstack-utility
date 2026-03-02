# 扁平网络 EIP ebtables 规则问题分析与修复方案

## 1. 网络拓扑

```
                    [物理交换机 / 物理网关 GW_MAC=xx:xx, IP=192.168.2.1]
                              |
                         [上行口 vxlan489]
                              |
                    =====[br_vx_489 (扁平网络 bridge)]==============================
                    |              |              |              |
                 vnic1.0        vnic2.0        vnic3.0       a471aa10f_o
                 (VM-A)         (VM-B)         (VM-C)        (NS私网外侧)
                 有EIP          无EIP          无EIP              |
                 .242           .243           .244          a471aa10f_i
                 网关=.1        网关=.1        网关=.1        (NS网关接口 .1)
                                                                  |
                                                             a471aa10f_ei (EIP .210)
                                                                  |
                                                             a471aa10f_eo
                                                                  |
                                                            [br_zsn0_31 公网bridge]
```

关键约束：**所有 VM 的网关都是 192.168.2.1**。有 EIP 的 VM 需要解析到 namespace MAC，无 EIP 的 VM 需要解析到物理网关 MAC。同一个 bridge 上，同一个网关 IP，不同 VM 需要不同的 MAC。

同网段还有物理服务器等非虚拟化设备直连物理交换机，必须能与所有 VM 正常通信。

---

## 2. 发现的问题

### 问题 #1：libvirt anti-spoof 规则顺序导致 EIP 的 ARP 拦截失效

**文件**：`kvmagent/kvmagent/plugins/deip.py` 第 365 行

**现象**：`set_gateway_arp_if_needed()` 使用 `-A`（append）将 EIP 的 PREROUTING 规则追加到链尾，排在 libvirt anti-spoof 规则之后：

```
-A PREROUTING -i vnic1.0 -j libvirt-I-vnic1.0   ← libvirt 先加，排在前面
-A PREROUTING -i vnic1.0 -j vnic1.0-gw           ← EIP 后加，排在后面
```

libvirt 链末尾有 `-p ARP -j ACCEPT`，ARP 包在 libvirt 链里就被 ACCEPT，永远到不了 EIP 的 `vnic1.0-gw` 链。

**后果**：
- VM-A 请求网关 .1 的 ARP 不会被 arpreply 拦截，而是正常广播
- 物理网关回复自己的 MAC，VM-A 学到错误的网关 MAC，流量不走 namespace
- 原始 ARP Request 广播到 bridge 所有端口，包括上行口和其他 namespace

**对比**：IPv6 版本 `set_gateway_arp_if_needed_v6()`（第 396 行）已经使用 `at_head=True`，IPv4 版本漏掉了。

### 问题 #2：kvmagent 重启删除 EIP ebtables 规则

**文件**：`kvmagent/kvmagent/plugins/mevoco.py` 第 1460 行

**现象**：`connect()` 方法（kvmagent 重连 MN 时调用）调用 `restore_ebtables_chain_except_kvmagent()`，该函数只保留匹配以下模式的链：

```python
patterns={"nat":["libvirt","(^z|^s)[0-9]*_"], "filter":["(^z|^s)[0-9]*_|^vr"]}
```

EIP 创建的链名（`vnic31.0-gw`、`a471aa10f_o-gw`、`a471aa10f_o-arp` 等）不匹配任何模式，全部被清除。

**后果**：每次 kvmagent 重连 MN，EIP 的所有 ebtables 规则被清空。虽然 MN 会重新下发 EIP 配置，但中间存在规则空窗期，导致网络中断。

### 问题 #3：缺少 ARP Reply 过滤（含免费 ARP）

**文件**：`kvmagent/kvmagent/plugins/deip.py`

**现象**：当前所有 POSTROUTING 和 PREROUTING 过滤规则只匹配 `--arp-op Request`，不匹配 `--arp-op Reply`。

**后果 3a — 冒充网关的免费 ARP Reply 穿透到有 EIP 的 VM**：

物理网络上有设备冒充 192.168.2.1 发送免费 ARP Reply（op=2），`vnic1.0-arp` 链只检查 `--arp-op Request`，Reply 不匹配，直接到达 VM-A，污染其 ARP 表。

**后果 3b — namespace 的免费 ARP Reply 泄漏到 bridge**：

namespace 接口 up 时内核可能发免费 ARP Reply（src-ip=.1, dst-ip=.1）。`a471aa10f_o-gw` 链只 DROP `--arp-op Request`，Reply 穿透到 bridge 广播到所有端口。VM-B/C 收到后可能把 .1 的 MAC 更新为 namespace MAC，导致跨网段流量走错路。

**后果 3c — namespace 回复非对应 VM 的 ARP**：

VM-B 广播请求 .1 的 ARP，请求到达 namespace，namespace 内核回复 ARP Reply（dst=.243）。`a471aa10f_o-gw` 链不过滤 Reply，回复穿透到 bridge，VM-B 学到 namespace 的 MAC 而非物理网关的 MAC。

### 问题 #4：EIP arpreply 规则绕过 libvirt anti-spoof 检查

**现象**：修复问题 #1 后，EIP 链排在 libvirt 前面。`eip-vnic1.0-gw` 链的 arpreply 规则只检查 `--arp-ip-dst`（目标 IP），不检查源 MAC 和源 IP：

```
-A eip-vnic1.0-gw -p ARP --arp-op Request --arp-ip-dst 192.168.2.1 -j arpreply --arpreply-mac ...
```

VM 内部伪造 ARP（假 src-mac/src-ip，dst-ip=网关），arpreply 匹配并消费了包，libvirt anti-spoof 没有机会检查。

**决策：不修复**。原因：
1. **实际影响极小**：arpreply 消费了原始包，伪造的 ARP 不会广播到网络上，VM 得到的只是网关 MAC（本来就应该知道的信息）。
2. **添加源检查会破坏无反欺诈场景**：如果 arpreply 规则加上 `--arp-mac-src` 和 `--arp-ip-src`，当关闭 libvirt anti-spoof 时，云主机修改了 MAC 或 IP 后将无法解析网关，导致 EIP 不可用。

### 问题 #5：ebtables 用户自定义链默认策略为 ACCEPT，导致 libvirt anti-spoof 被绕过

**文件**：`kvmagent/kvmagent/plugins/deip.py`

**现象**：ebtables 与 iptables 不同，用户自定义链（通过 `-N` 创建）的默认策略是 **ACCEPT** 而非隐式 RETURN。代码中所有 EIP 链只做了 `-N` 创建，未设置策略。

以 `eip-vnic1.0-gw` 为例，修复 #1 后该链排在 libvirt 前面，且跳转规则不限协议：

```
-I PREROUTING -i vnic1.0 -j eip-vnic1.0-gw       ← 所有帧都进入
  eip-vnic1.0-gw (policy: ACCEPT)                  ← 不匹配的包直接 ACCEPT
    -p ARP --arp-op Request ... -j arpreply         ← 只有一条规则
```

**后果**：所有从 vnic1.0 进入的非 ARP 帧（IP 数据包等）以及不匹配 arpreply 的 ARP 包，全部命中默认策略 ACCEPT，**libvirt anti-spoof 链完全被绕过**。VM 可以任意伪造 MAC/IP 发送流量。

**影响范围**：5 条 EIP 用户自定义链全部受影响，但 `eip-vnic1.0-gw` 是唯一**必须修复**的（后面有 libvirt 链需要检查），其余 4 条后面无 libvirt 链，功能上 ACCEPT 和 RETURN 等价。

---

## 3. 修复方案

### 修复 #1：PREROUTING 插入顺序 + 跳转限定 ARP + 链策略 RETURN

**文件**：`deip.py` `set_gateway_arp_if_needed()` 函数

**改动 1a**：PREROUTING 跳转规则加 `at_head=True` + 限定 `-p ARP`：

```python
# 修改前：
create_ebtable_rule_if_needed('nat', 'PREROUTING', '-i {{NIC_NAME}} -j {{CHAIN_NAME}}')

# 修改后：
create_ebtable_rule_if_needed('nat', 'PREROUTING', '-p ARP -i {{NIC_NAME}} -j {{CHAIN_NAME}}', at_head=True)
```

`-p ARP` 确保非 ARP 帧根本不进 EIP 链，直接到 libvirt 做 anti-spoof 检查。与 POSTROUTING 的 3 条跳转（已带 `-p ARP`）风格统一。

**改动 1b**：链创建后立即设置策略为 RETURN：

```python
if bash_r(EBTABLES_CMD + ' -t nat -L {{CHAIN_NAME}} > /dev/null 2>&1') != 0:
    bash_errorout(EBTABLES_CMD + ' -t nat -N {{CHAIN_NAME}}')
bash_errorout(EBTABLES_CMD + ' -t nat -P {{CHAIN_NAME}} RETURN')
```

双重保险：即使 `-p ARP` 被绕过（不会发生），RETURN 策略也保证不匹配的包返回 PREROUTING 继续处理。所有 5 条 EIP 链统一设为 RETURN。

**设计原理**：EIP 链和 libvirt anti-spoof 链通过两层机制串联配合：

```
PREROUTING 处理流程:

  -p ARP -i vnic1.0 -j eip-vnic1.0-gw  （只有 ARP 进入）
    eip-vnic1.0-gw (policy: RETURN)
      职责：只做一件事 — 请求网关 → arpreply
      不匹配的 ARP → 命中 RETURN 策略 → 回到 PREROUTING 继续
         ↓
  非 ARP 帧不匹配 -p ARP，直接到下一条:
  -i vnic1.0 -j libvirt-I-vnic1.0  （anti-spoof 链）
    职责：验证源 MAC 和源 IP 合法性
    不合法 → DROP
    合法 → RETURN
         ↓
  PREROUTING policy ACCEPT
```

两个链零耦合。`-p ARP` 过滤 + RETURN 策略是双重保险，任意一层都足以防止绕过 libvirt。

### 修复 #2：EIP 链统一前缀 + restore 保留

**涉及文件**：`deip.py`（链名加前缀）、`mevoco.py`（patterns 加匹配）

**改动 2a**：`deip.py` 中所有 EIP ebtables 链名加 `eip-` 前缀：

| 当前链名 | 重命名后 |
|---|---|
| `{NIC_NAME}-gw` | `eip-{NIC_NAME}-gw` |
| `{PRI_ODEV}-gw` | `eip-{PRI_ODEV}-gw` |
| `{PRI_ODEV}-arp` | `eip-{PRI_ODEV}-arp` |
| `{PUB_ODEV}-arp` | `eip-{PUB_ODEV}-arp` |
| `{NIC_NAME}-arp` | `eip-{NIC_NAME}-arp` |

最长链名 `eip-a471aa10f_eo-arp` = 23 字符，在 ebtables 31 字符限制内。

需要修改的函数：
- `set_gateway_arp_if_needed()`：`CHAIN_NAME`、`BLOCK_CHAIN_NAME` 构造
- `set_gateway_arp_if_needed_v6()`：`CHAIN_NAME` 构造
- `add_filter_to_prevent_namespace_arp_request()`：`PRI_ODEV_CHAIN` 构造
- `delete_arp_rules()`：`CHAIN_NAME`、`PRI_ODEV_CHAIN`、`BLOCK_CHAIN_NAME` 构造

**改动 2b**：`mevoco.py` 第 1460 行，patterns 增加 `"^eip-"`：

```python
# 修改前：
patterns={"nat":["libvirt","(^z|^s)[0-9]*_"], "filter":["(^z|^s)[0-9]*_|^vr"]}

# 修改后：
patterns={"nat":["libvirt","(^z|^s)[0-9]*_","^eip-"], "filter":["(^z|^s)[0-9]*_|^vr"]}
```

**选择统一前缀而非正则匹配现有名称的理由**：
- 与代码库现有约定一致（`USERDATA-` 前缀、`libvirt` 前缀、`z/s` 前缀）
- 消除 deip.py 和 mevoco.py 之间的隐式耦合，建立显式契约
- 未来 EIP 新增任何链，只要用 `eip-` 前缀就自动被保留
- 正则简单不可能写错：`"^eip-"` vs `"^[0-9a-f]+_(e?o)-(gw|arp)$"`

**升级兼容**：无需额外迁移逻辑。kvmagent 升级重启时，`restore_ebtables_chain_except_kvmagent()` 清理旧链（旧链名无前缀，不匹配任何保留模式），MN 重新下发 EIP 配置后 `apply_eip()` 用新前缀重建所有链。

### 修复 #3：增加 ARP Reply 过滤

**文件**：`deip.py`

**改动 3a**：`set_gateway_arp_if_needed()` 函数，`vnic1.0-arp` 链增加 Reply 过滤：

```python
# 现有规则（拦截冒充网关的 ARP Request）：
create_ebtable_rule_if_needed('nat', BLOCK_CHAIN_NAME,
    "-p ARP -o {{NIC_NAME}} --arp-op Request --arp-ip-src {{NIC_GATEWAY}} --arp-mac-src ! {{GATEWAY_MAC}} -j DROP")

# 新增规则（拦截冒充网关的 ARP Reply，含免费 ARP Reply）：
create_ebtable_rule_if_needed('nat', BLOCK_CHAIN_NAME,
    "-p ARP -o {{NIC_NAME}} --arp-op Reply --arp-ip-src {{NIC_GATEWAY}} --arp-mac-src ! {{GATEWAY_MAC}} -j DROP")
```

**改动 3b**：`add_filter_to_prevent_namespace_arp_request()` 函数，跳转限定 `-p ARP` + 链策略 RETURN + `a471aa10f_o-gw` 链增加 Reply 过滤：

```python
# 跳转规则加 -p ARP：
create_ebtable_rule_if_needed('nat', 'PREROUTING', '-p ARP -i {{PRI_ODEV}} -j {{PRI_ODEV_CHAIN}}')

# 链创建后设策略 RETURN：
bash_errorout(EBTABLES_CMD + ' -t nat -P {{PRI_ODEV_CHAIN}} RETURN')

# 现有规则：
create_ebtable_rule_if_needed('nat', PRI_ODEV_CHAIN,
    "-p ARP --arp-op Request --arp-ip-dst {{NIC_IP}} -j arpreply --arpreply-mac {{NIC_MAC_IN_EBTALES}}", True)
create_ebtable_rule_if_needed('nat', PRI_ODEV_CHAIN,
    "-p ARP --arp-ip-src {{NIC_GATEWAY}} -j dnat --to-destination {{NIC_MAC}}")

# 兜底 DROP 所有未匹配 ARP（dnat 规则已隐式处理 namespace 回复对应 VM 的 Reply）：
create_ebtable_rule_if_needed('nat', PRI_ODEV_CHAIN, "-p ARP -j DROP")
```

---

## 4. 修复后完整 ebtables 规则表

以 VM-A（vnic1.0, .242, 有EIP）为例，所有链名已加 `eip-` 前缀：

```
*nat
:PREROUTING ACCEPT
:OUTPUT ACCEPT
:POSTROUTING ACCEPT

# ==================== PREROUTING ====================

# EIP 链（-I 插入链头，排在 libvirt 前面）
# jump 时加 -p ARP：非 ARP 不进入链，直接 PREROUTING 下一条（libvirt）
-I PREROUTING -p ARP -i vnic1.0 -j eip-vnic1.0-gw

# libvirt anti-spoof（已存在，不修改）:
# -A PREROUTING -i vnic1.0 -j libvirt-I-vnic1.0

# namespace 私网外侧入口（同样加 -p ARP）
-A PREROUTING -p ARP -i a471aa10f_o -j eip-a471aa10f_o-gw

# --- eip-vnic1.0-gw (policy: RETURN) ---
# 请求网关 → arpreply 回复 namespace MAC（不检查源，见问题#4 决策说明）
# 不匹配 → RETURN 回 PREROUTING → libvirt anti-spoof 继续检查
-A eip-vnic1.0-gw -p ARP --arp-op Request \
   --arp-ip-dst 192.168.2.1 \
   -j arpreply --arpreply-mac f6:dc:24:e8:92:6e

# --- eip-a471aa10f_o-gw (policy: RETURN) ---
# namespace 请求 VM-A IP → arpreply 回复 VM-A MAC
-I eip-a471aa10f_o-gw -p ARP --arp-op Request --arp-ip-dst 192.168.2.242 \
   -j arpreply --arpreply-mac fa:3a:a0:c5:74:0
# namespace 网关 IP 的 ARP（含 Reply、免费 ARP）→ dnat 修改目标 MAC → VM-A 收到
-A eip-a471aa10f_o-gw -p ARP --arp-ip-src 192.168.2.1 \
   -j dnat --to-dst fa:3a:a0:c5:74:0
# 其他所有 ARP → DROP
-A eip-a471aa10f_o-gw -p ARP -j DROP

# ==================== POSTROUTING ====================

# 规则通过“先删后插头（-I）”保证最终位于 POSTROUTING 最前，避免被其他规则抢先命中
-I POSTROUTING -p ARP -o vnic1.0 -j eip-vnic1.0-arp
-I POSTROUTING -p ARP -o a471aa10f_o -j eip-a471aa10f_o-arp
-I POSTROUTING -p ARP -o a471aa10f_eo -j eip-a471aa10f_eo-arp

# --- eip-vnic1.0-arp (policy: RETURN) ---
# 拦截发往 VM-A 的冒充网关 .1 的 ARP（物理网关的 .1 ARP 也被拦截）
-A eip-vnic1.0-arp -p ARP -o vnic1.0 --arp-op Request \
   --arp-ip-src 192.168.2.1 --arp-mac-src ! f6:dc:24:e8:92:6e -j DROP
-A eip-vnic1.0-arp -p ARP -o vnic1.0 --arp-op Reply \
   --arp-ip-src 192.168.2.1 --arp-mac-src ! f6:dc:24:e8:92:6e -j DROP

# --- eip-a471aa10f_o-arp (policy: RETURN) ---
# 阻止非 VM-A 的网关 ARP 请求到达 namespace
-A eip-a471aa10f_o-arp -p ARP -o a471aa10f_o --arp-op Request \
   --arp-ip-dst 192.168.2.1 --arp-mac-src ! fa:3a:a0:c5:74:0 -j DROP

# --- eip-a471aa10f_eo-arp (policy: RETURN) ---
-A eip-a471aa10f_eo-arp -p ARP -o a471aa10f_eo --arp-op Request \
   --arp-ip-dst 192.168.2.1 --arp-mac-src ! fa:3a:a0:c5:74:0 -j DROP
```

---

## 5. 场景验证矩阵

### 基本 ARP 解析

| # | 场景 | 包路径 | 命中规则 | 结果 |
|---|---|---|---|---|
| 1 | VM-A(.242,有EIP) 请求网关 .1 | vnic1.0 入 → PREROUTING | `eip-vnic1.0-gw` arpreply | ✅ 得到 namespace MAC，原始包消费 |
| 2 | VM-A 请求 VM-B(.243) | vnic1.0 入 → PREROUTING | `-p ARP` 进入 `eip-vnic1.0-gw` → 不匹配 → RETURN → libvirt 放行 | ✅ 正常广播 |
| 3 | VM-B(.243,无EIP) 请求网关 .1 | vnic2.0 入（无EIP链）→ 广播 | 无 PREROUTING 拦截 | ✅ 物理网关回复 |
| 4 | VM-B 请求 VM-A(.242) | vnic2.0 入 → 广播 | 无拦截 | ✅ VM-A 正常回复 |
| 5 | NS 请求 VM-A(.242) | a471aa10f_o 入 | `eip-a471aa10f_o-gw` arpreply | ✅ 得到 VM MAC |
| 6 | NS 请求 VM-B(.243) | a471aa10f_o 入 | `eip-a471aa10f_o-gw` dnat src=.1 → 只到VM-A（VM-B收不到） | ✅ 被阻止 |

### 免费 ARP 防护

| # | 场景 | 包路径 | 命中规则 | 结果 |
|---|---|---|---|---|
| 7 | 物理网关 .1 免费ARP Req → VM-A | 上行口入 → 出 vnic1.0 | `eip-vnic1.0-arp` mac≠namespace → DROP | ✅ VM-A 不受影响 |
| 8 | 物理网关 .1 免费ARP Reply → VM-A | 上行口入 → 出 vnic1.0 | `eip-vnic1.0-arp` Reply 规则 DROP | ✅ VM-A 不受影响 |
| 9 | 物理网关 .1 免费ARP → VM-B | 上行口入 → 出 vnic2.0 | 无EIP链，正常通过 | ✅ VM-B 正常学习物理网关 MAC |
| 10 | NS 免费ARP Req(.1→.1) 出 bridge | a471aa10f_o 入 | `eip-a471aa10f_o-gw` dnat src=.1 → 只到VM-A（无害） | ✅ 不泄漏到其他VM |
| 11 | NS 免费ARP Reply(.1→.1) 出 bridge | a471aa10f_o 入 | `eip-a471aa10f_o-gw` dnat src=.1 → 只到VM-A（无害） | ✅ 不泄漏到其他VM |

### namespace 隔离

| # | 场景 | 包路径 | 命中规则 | 结果 |
|---|---|---|---|---|
| 12 | VM-B 请求 .1 → 到达 NS | 广播 → 出 a471aa10f_o | `eip-a471aa10f_o-arp` mac≠VM-A → DROP | ✅ 不到达 NS |
| 13 | NS 回复 VM-A 的 ARP | a471aa10f_o 入 | `eip-a471aa10f_o-gw` dnat src=.1 → 目标MAC改为VM-A | ✅ 正常到达 |
| 14 | NS 回复 VM-B 的 ARP(.1→.243) | a471aa10f_o 入 | `eip-a471aa10f_o-gw` dnat src=.1 → 目标MAC改为VM-A（VM-B收不到） | ✅ VM-B 不会学到 NS MAC |

### 物理网关直通与跨 namespace

| # | 场景 | 包路径 | 命中规则 | 结果 |
|---|---|---|---|---|
| 15 | 物理网关(.1,GW_MAC) 请求 VM-A(.242) | 上行口入 → 出 vnic1.0 | `eip-vnic1.0-arp` src=.1, mac=GW_MAC≠NS → DROP | ⚠️ 不可达（设计取舍） |
| 16 | 另一NS(.1,NS2_MAC) ARP广播 → VM-A | NS2外侧口入 → 广播 → 出 vnic1.0 | `eip-vnic1.0-arp` src=.1, mac=NS2≠NS → DROP | ✅ VM-A 不会学到其他NS的MAC |

> **场景 15 说明**：物理网关（IP=.1, MAC=GW_MAC）直接对有 EIP 的 VM 发 ARP Request 会被 `eip-vnic1.0-arp` 拦截，因为物理网关的 MAC 不等于 namespace MAC。这是 EIP 架构的**设计取舍**——有 EIP 的 VM 的网关是 namespace，物理网关无法通过私网 IP 直接 L2 访问该 VM。外部访问走 EIP 公网 IP → namespace 转发；同网段其他 VM 或物理机（src-ip≠.1）的 ARP 不受影响。
>
> **场景 16 说明**：同一 bridge 上另一个 EIP namespace（NS2）的 ARP（src-ip=.1, src-mac=NS2_MAC）理论上不会到达 bridge 广播（被 NS2 自身 PREROUTING 链 `eip-{NS2_o}-gw` DROP），此处 `eip-vnic1.0-arp` 提供纵深防御，确保 VM-A 不会误学到 NS2 的 MAC。

### anti-spoof 配合

| # | 场景 | 包路径 | 命中规则 | 结果 |
|---|---|---|---|---|
| 17 | VM-A 伪造src请求网关 .1 | vnic1.0 入 | `-p ARP` 进入 `eip-vnic1.0-gw` → arpreply 消费（见问题#4） | ⚠️ 伪造包不广播，仅得到网关MAC |
| 18 | VM-A 伪造src请求 .243 | vnic1.0 入 | `-p ARP` 进入 `eip-vnic1.0-gw` dst不匹配 → RETURN → libvirt DROP | ✅ 被拦截 |
| 19 | VM-A 正常请求 .243 | vnic1.0 入 | `-p ARP` 进入 `eip-vnic1.0-gw` RETURN → libvirt 放行 | ✅ 正常广播 |
| 20 | VM-A 发送非 ARP 帧 | vnic1.0 入 → PREROUTING | `-p ARP` 不匹配 → 跳过 EIP 链 → libvirt anti-spoof | ✅ 零开销通过 |

---

## 6. 改动清单

| 文件 | 位置 | 改动内容 |
|---|---|---|
| `deip.py` | `set_gateway_arp_if_needed()` | PREROUTING jump 加 `-p ARP`，仅 ARP 帧进入 EIP 链 |
| `deip.py` | `set_gateway_arp_if_needed()` | 所有 `-N` 后紧跟 `-P chain RETURN`，修复 ebtables 默认 ACCEPT 问题 |
| `deip.py` | `set_gateway_arp_if_needed()` | POSTROUTING 三条 ARP jump 改为"先删后 `-I`"强制链头 |
| `deip.py` | `set_gateway_arp_if_needed()` | `{NIC_NAME}-arp` 链增加 ARP Reply 过滤规则 |
| `deip.py` | `set_gateway_arp_if_needed_v6()` | IPv6 链 `-N` 后紧跟 `-P chain RETURN` |
| `deip.py` | `add_filter_to_prevent_namespace_arp_request()` | PREROUTING jump 加 `-p ARP`；`-N` 后设 `-P RETURN` |
| `deip.py` | `add_filter_to_prevent_namespace_arp_request()` | `{PRI_ODEV}-gw` 链增加兜底 `-p ARP -j DROP`（dnat 规则隐式处理 Reply） |
| `deip.py` | `delete_arp_rules()` | 兼容删除旧格式（`-i dev -j chain`）和新格式（`-p ARP -i dev -j chain`）PREROUTING 规则，改用无条件 `bash_r` |
| `deip.py` | `delete_ipv6_rules()` | 简化为无条件 `bash_r` 删除，无需先 grep 检查 |
| `deip.py` | 所有链名构造处（约20行） | 链名加 `eip-` 前缀 |
| `mevoco.py` | 第738行 | patterns nat 列表已含 `"^eip-"`（无需修改） |
