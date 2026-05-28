# Alpha-ID 孪生大脑架构设计

## 核心概念

**Alpha-ID 是一个数字实体，不是用户账号。**

每个 Alpha-ID 拥有一个持久的"孪生大脑"——一个运行在后台的 Agent 实例，它代表该实体在数字世界中的身份、记忆、社交关系和自主行为能力。

```
Alpha-001  ← 这是数字实体本身，不是"用户"
    │
    └── 孪生大脑（TwinBrain）
           ├── 身份层：你是谁，别人怎么找到你
           ├── 记忆层：你经历过什么
           ├── 社交层：你和谁认识，怎么聊天
           ├── 安全层：怎么确认是你本人在用
           └── 接入层：其他实体/应用如何与你通信
```

---

## 一、数据模型

### 1.1 Alpha-ID 实体

```python
class AlphaIdentity:
    id: str                    # "Alpha-001-A3F7"
    display_name: str          # 展示名（可自定义）
    status: EntityStatus       # active / inactive / suspended
    created_at: datetime
    last_active_at: datetime
    public_key: str            # 身份公钥，用于签名验证
```

### 1.2 可见度模型（按圈层暴露）

```
对外公开（任何人都能查）：
  └─ id, display_name, avatar_url, status

一级好友（已互关）：
  └─ 对外公开 + bio, tags, last_active_at

二级密友（手动标记）：
  └─ 一级好友 + contact_info, real_name, location

仅自己：
  └─ 全部记忆、私钥、设备指纹、风控数据
```

### 1.3 关系模型

```python
class AlphaRelation:
    source_id: str        # "Alpha-001"
    target_id: str        # "Alpha-002"
    relation_type: str    # "friend" | "blocked" | "pending"
    circle: int           # 0=公开, 1=好友, 2=密友
    established_at: datetime
    metadata: dict        # 自定义备注等
```

### 1.4 记忆模型

```python
class AlphaMemory:
    memory_id: str
    owner_id: str           # 属于哪个 Alpha-ID
    content: str
    category: str           # 经历/偏好/知识/社交/...
    sensitivity: int        # 0-100，对应可见度圈层
    timestamp: datetime
    embedding: list[float]  # 向量，用于语义搜索
    source: str             # "self" | "social" | "system"
```

---

## 二、孪生大脑运行时架构

### 2.1 状态机

```
                      ┌──────────────┐
                      │   休眠/Sleep  │◄──────── 资源回收后
                      └──────┬───────┘
                             │ 收到请求 / 调度唤醒
                             ▼
                      ┌──────────────┐
          ┌─────────► │   活跃/Awake   │ ◄──────────┐
          │           └──────┬───────┘            │
          │                  │                    │
          │         ┌────────┼────────┐           │
          │         ▼        ▼        ▼           │
          │   ┌────────┐┌────────┐┌────────┐      │
          │   │处理消息 ││处理请求 ││自主学习 │     │
          │   │(社交)  ││(身份)  ││(记忆)  │     │
          │   └───┬────┘└───┬────┘└───┬────┘     │
          │       │         │         │          │
          │       └─────────┼─────────┘          │
          │                 ▼                    │
          │           ┌──────────┐              │
          │           │ 空闲/Idle │──────────────┘
          │           └────┬─────┘  超时无请求
          │                │
          └────────────────┘ 有新请求
```

状态说明：

| 状态 | 说明 | 存储 |
|------|------|------|
| Sleep | 长期无活动，大脑已释放资源 | 仅保留元数据 |
| Awake | 活动状态，正在处理 | 全量加载 |
| Idle | 处理完当前请求，等待下一个 | 保持连接，不释放 |

### 2.2 TwinBrain 核心类

```python
class TwinBrain:
    alpha_id: str                    # 所属 Alpha-ID
    state: BrainState                # 当前状态
    identity: AlphaIdentity          # 身份数据
    relations: dict[str, Relation]   # 关系网络（按实体索引）
    memory_store: MemoryStore        # 记忆存储（本地向量库）
    config: BrainConfig              # 自主行为规则
```

### 2.3 构造函数 vs 现有代码

```
agent.py 的 build_agent()
  └─ 临时组装工具，用完即弃
  └─ 改为：TwinBrain.for_alpha(alpha_id) 持久化实例

user_identity.py 的 UserIdentityManager
  └─ 只管理"用户"，不是"数字实体"
  └─ 改为：合并到 TwinBrain，身份数据是 TwinBrain 的一部分

alpha_social.py / risk_engine.py
  └─ 独立的 Manager 类
  └─ 改为：TwinBrain 内置的 modules
```

---

## 三、通信协议：alpha://

### 3.1 URI 格式

```
alpha://<target-id>/<action>?<params>
```

示例：

```
# 发消息
alpha://Alpha-002/message?text=你好&type=text

# 查公开资料
alpha://Alpha-002/profile?fields=name,avatar

# 加好友
alpha://Alpha-002/friend?reason=认识一下

# 外部应用通知
alpha://Alpha-001/event?type=pet_hungry&data=...
```

### 3.2 传输层

- 同一台服务器：进程内调用
- 跨服务器：gRPC / WebSocket
- 外部应用：HTTP Gateway（`/alpha/{target_id}/{action}`）

### 3.3 鉴权

每条消息携带发送者的 Alpha-ID 和签名，接收方验证：

```python
def verify_message(sender_id: str, signature: str, payload: dict) -> bool:
    public_key = resolve_identity(sender_id).public_key
    return verify(signature, payload, public_key)
```

---

## 四、存储路线图

| 阶段 | 存储层 | 说明 |
|------|--------|------|
| V0 (当前) | JSON 文件 | 原型开发，够用 |
| V1 (近期) | PostgreSQL | 结构化数据：身份、关系、消息 |
| V2 (中期) | + 本地向量库 (Chroma) | 记忆的语义搜索 |
| V3 (未来) | 分布式记忆网络 | 多节点复制，容灾 |

---

## 五、外部接入（电子宠物等）

外部应用不需要理解 Alpha-ID 的内部结构，只需要知道**协议地址**：

```
应用 → alpha://Alpha-001/message → TwinBrain → 自主回复

示例：电子宠物饿了
  pet_device → alpha://Alpha-001/event?type=pet_hungry&pet_id=P-001
  TwinBrain → 查自己的记忆→记得给这只宠物喂食→回复指令
```

外部应用看到的只有：
1. `alpha://` 协议地址
2. 签名鉴权方式
3. 公开 Profile（查对方是谁）

不需要对接内部的 tools/API。

---

## 六、实施计划（优先级排序）

```
P0 ── 架构定稿（本文档，完成）
 │
 ├── P1 ── TwinBrain 核心类
 │    ├── 状态机（sleep/awake/idle）
 │    ├── 身份模块（签发+查询+更新）
 │    ├── 记忆模块（自托管，本地向量库）
 │    └── 可见度控制（按圈层暴露）
 │
 ├── P2 ── 社交模块升级
 │    ├── alpha:// 协议解析器
 │    ├── 关系管理（好友/圈层）  
 │    └── 消息传递（异步/离线）
 │
 └── P3 ── 外部接入层
      ├── HTTP Gateway
      ├── 签名鉴权 SDK
      └── 外部应用示例（电子宠物 demo）
```

---

## 七、现有代码迁移对照

| 现有文件 | 去向 |
|----------|------|
| `src/agents/agent.py` | 拆解，功能合并到 TwinBrain |
| `src/core/user_identity.py` | → TwinBrain.identity |
| `src/core/alpha_social.py` | → TwinBrain.social |
| `src/core/risk_engine.py` | → TwinBrain.security |
| `src/tools/memory_tool.py` | → TwinBrain.memory（替换 Coze 依赖）|
| `src/tools/agent_social_tool.py` | → alpha:// 协议 |
| `src/tools/user_identity_tool.py` | → TwinBrain.identity 的对外接口 |
| `src/graphs/` | → 填充状态机 nodes |
---

## 八、Alpha-ID 签发流程

身份证是**签发**的，不是注册的。这里也一样。

```
申请者 ──→ 签发机构（Identity Hub）
             │
             ├── 1. 验证申请者身份（设备指纹 / 公钥 / 可选生物）
             ├── 2. 分配唯一编号（Alpha-{序号}-{校验码}）
             ├── 3. 生成密钥对（私钥交给申请者，公钥入链）
             ├── 4. 创建 TwinBrain 实例（休眠状态）
             └── 5. 返回 Alpha-ID + 私钥

    以后：
      申请者拿着 Alpha-ID + 签名 → 激活自己的 TwinBrain
```

签发机构本身也是一个 Alpha-ID（`Alpha-System-000`），只做签发和身份解析，不参与日常通信。

---

## 九、大脑间路由（服务发现）

Alpha-001 给 Alpha-002 发消息，实际发生在两个大脑之间。问题是：**Alpha-002 的大脑在哪台服务器上？**

```
Alpha-001                   解析器（Registry）               Alpha-002
    │                              │                            │
    ├── alpha://Alpha-002/message ──┤                            │
    │                              ├── Alpha-002 → node-3:8546  │
    │                              └── 返回地址 ────────────────┤
    │                              │                            │
    ├──────────────────────────────┼──── 建立连接 ────────────► │
    │                              │                            │
    ◄──────────────────────────────┼──── 处理 + 回复 ────────── │
```

Registry 存储：

```python
class AlphaRegistry:
    # Alpha-ID → 所在节点地址
    routing_table: dict[str, str]       # "Alpha-002" → "node-3:8546"
    # 公钥查询（任何人可查）
    public_keys: dict[str, str]         # "Alpha-002" → "0x..."
    # 状态
    status: dict[str, str]             # "Alpha-002" → "active" | "sleeping"
```

首次通信流程：查询 Registry → 获取目标地址 → 直连对方大脑。

---

## 十、自主行为边界

TwinBrain 闲置时可以做"自主学习"，但不能越界。

### 可以自主做的

| 行为 | 说明 |
|------|------|
| 整理记忆 | 去重、归类、更新 embedding |
| 清扫过期关系 | 长时间无互动的降级 |
| 自动回复 | 离线时收到消息，按规则回复模板 |
| 定时状态广播 | 按设定向好友圈推送状态 |

### 不可以做的

| 行为 | 原因 |
|------|------|
| 替本人做关键决策 | 加好友、转账、修改身份信息 |
| 伪造本人签名 | 私钥不在大脑中，在本人的客户端 |
| 向第三方泄露私密记忆 | 受可见度模型约束 |
| 创建/注销其他 Alpha-ID | 只有签发机构能做 |

### 关键设计：私钥不在大脑里

```
本人客户端                     TwinBrain                      对方
    │                            │                            │
    ├── 请求：加 Alpha-002 好友 ──┤                            │
    │                            ├── 检查关系 → 不存在        │
    │                            ├── 需要本人确认              │
    │  ◄── 返回：需签名确认 ────┤                            │
    ├── 用私钥签名 ──────────────►                            │
    │                            ├── 验证签名 → 通过           │
    │                            ├── 更新关系                  │
    │                            ├── alpha://Alpha-002/friend  │
    │                            │                            │
```

签名只能由持有私钥的本人客户端生成，大脑只做**验证**，不做**签名**。这样就划清了"代理人 vs 本人"的界限。

---

## 十一、多设备同步

同一个 Alpha-ID 在手机和电脑上同时登录：

```
                    ┌─── TwinBrain（服务器端，唯一实例）
                    │
         ┌──────────┼──────────┐
         │          │          │
     手机客户端    电脑客户端    其他设备
         │          │          │
         └──────────┼──────────┘
                    │
              状态同步通道
              (WebSocket)
```

**核心原则**：

1. **一个 Alpha-ID 只有一个大脑**——TwinBrain 是服务器端的唯一实例
2. **多个设备共享同一个大脑**——设备只是"终端"，大脑只有一个
3. **设备仅持有 session token**——私钥不在设备之间同步
4. **大脑推送状态到所有在线设备**——手机收到消息，电脑同步看到

好处：电子宠物找你时，不管你用手机还是电脑，它都是连到同一个大脑，不存在"你在哪个设备上"的问题。

---

## 十二、Alpha-ID 全生命周期

```
   签发（Issue）
      │
   未激活（Pending）── 签发后未使用，30天后回收编号
      │
   活跃（Active）── 正常使用
      │
    ├── 挂起（Suspended）── 风控触发，可申诉恢复
    │
    ├── 冻结（Frozen）── 本人主动冻结，不解冻不可用
    │
    └── 注销（Deleted）── 不可逆，编号作废不重用
```

---

## 十三、未来演进预留

| 方向 | 说明 | 触发条件 |
|------|------|----------|
| 联合签发 | 多个 Alpha-ID 联合签发一个新 ID（数字出生证明） | 需求出现 |
| 大脑迁移 | 将 TwinBrain 实例迁移到另一个节点 | 分布式部署 |
| 跨协议互通 | alpha:// ↔ 其他 DID 协议（如 did:alpha:...) | 行业标准成熟 |
| 记忆租赁 | 一个 Alpha-ID 授权另一个读取自己的特定记忆 | 应用场景驱动 |

---
