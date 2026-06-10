# Alpha-ID v2 架构设计 —— 数字孪生大脑

> 版本：v2.0 | 日期：2025-07 | 状态：草案

---

## 一、核心理念

**Alpha-ID 是一个数字实体，不是一串编号。**

每个 Alpha-ID 在系统中被激活后，拥有一个持久的孪生大脑（TwinBrain）。大脑管理该实体的身份、记忆、社交关系，并对外提供统一的通信接口。

两个 Alpha-ID 之间的交互是对等的（peer-to-peer），不存在"主从"关系。

---

## 二、Alpha-ID 数据模型

```
Alpha-001
 ├── meta                    # 元信息：创建时间、版本、状态
 ├── identity               # 身份层
 │   ├── number: "Alpha-001"           # 唯一编号（签发，非自注册）
 │   ├── nickname: str
 │   ├── avatar_url: str
 │   ├── device_fingerprint: str       # 设备绑定
 │   └── public_key: str               # 未来: 签名验签
 ├── profile                # 对外档案（按可见度分层）
 │   ├── public: { nickname, avatar }
 │   ├── friends: { bio, tags, status }
 │   ├── close: { real_name, contact }
 │   └── self: { full_memory, private_key, audit_log }
 ├── memory                 # 记忆层
 │   ├── storage: json | postgres | vector
 │   └── partitions:
 │       ├── public    (敏感度 0-20)
 │       ├── private   (敏感度 20-60)
 │       └── core      (敏感度 60-100)
 ├── social                 # 社交层
 │   ├── friends: [Alpha-ID列表]
 │   ├── blocked: [Alpha-ID列表]
 │   ├── friend_requests: [待处理请求]
 │   └── circles: { close: [], friends: [], known: [] }
 ├── brain_state            # 大脑运行时状态
 │   └── status: sleep | awake | busy
 └── settings               # 自主行为规则
     ├── auto_reply: bool
     ├── wake_hours: [8:00-22:00]
     └── auto_actions: []    # 定时/条件触发的自主行为
```

---

## 三、孪生大脑运行时架构

### 3.1 状态机

```
                  ┌──────────────────────┐
      ┌────────── │  sleep (休眠/离线)    │ ←──────────┐
      │           └──────────────────────┘            │
      │ 收到消息                 │ 超时/无活动         │
      │ 或定时唤醒               │                    │
      ▼                          ▼                    │
┌──────────────────────┐    ┌──────────────────────┐  │
│  awake (活跃)         │    │  idle (空闲待机)      │──┘
│  ┌────────────────┐   │    │                      │
│  │ processing_msg  │   │    │ 低功耗监听外部请求    │
│  │ processing_req  │   │    │ 可被唤醒进入awake    │
│  │ learning        │   │    └──────────────────────┘
│  │ thinking        │   │
│  └────────────────┘   │
└──────────────────────┘
         │
         │ error/exception
         ▼
┌──────────────────────┐
│  error (异常恢复)     │
│  进入安全模式         │
│  记录审计日志         │
└──────────────────────┘
```

### 3.2 核心类设计

```python
class TwinBrain:
    """每个 Alpha-ID 的孪生大脑实例"""

    alpha_id: str              # 所属编号
    state: BrainState          # 当前状态 (sleep/awake/idle/error)
    identity: IdentityManager  # 身份管理
    memory: MemoryManager      # 记忆管理
    social: SocialManager      # 社交管理
    risk: RiskEngine           # 风控引擎
    settings: BrainSettings    # 自主行为设置

    async def receive(self, message: Message) -> Response:
        """接收外部消息（来自其他 Alpha-ID 或外部应用）"""
        ...

    async def think(self) -> None:
        """自主学习周期：整理记忆、检查待办、更新状态"""
        ...

    async def act(self, action: Action) -> Response:
        """自主动作：发送消息、更新状态、执行定时任务"""
        ...
```

### 3.3 通信接口

统一消息格式，所有对内对外的通信走同一通道：

```python
@dataclass
class Message:
    version: str = "2.0"
    message_id: str           # 全局唯一
    sender: str               # 来源 Alpha-ID
    recipient: str            # 目标 Alpha-ID
    type: str                 # message | friend_request | query | action
    payload: dict             # 具体内容
    timestamp: float
    signature: str | None     # 未来：签名
```

协议 URI：

```
alpha://Alpha-002/message?text=你好
alpha://Alpha-002/friend_request?note=我是Alpha-001
alpha://Alpha-002/profile?layer=public
```

---

## 四、存储层升级路线

| 阶段 | 存储 | 用途 | 状态 |
|------|------|------|------|
| V1 | JSON 文件 | 开发/单机调试 | ✅ 已有 |
| V2 | PostgreSQL | 数据持久化、多实例 | 🏗 已有部分实现 |
| V3 | 本地向量库 (Chroma/FAISS) | 语义搜索记忆 | ❌ 待实现 |
| V4 | 分布式记忆网络 | 跨 Alpha-ID 共享记忆 | 🔮 远期 |

移除对第三方知识库（Coze Knowledge）的依赖，改为自有记忆栈。

---

## 五、可见度模型

对外查询 Alpha-ID 信息时，根据**查询方与目标的关系**返回不同层的数据：

```
查询方                返回的数据层
陌生 Alpha-ID    → public       (编号、昵称、头像)
好友 Alpha-ID    → public + friends (签名、动态、公开记忆)
密友 Alpha-ID    → public + friends + close (联系方式、真实姓名)
自己             → 全部
```

风控引擎介入：如果查询方被 blocked，返回 403。如果环境异常（新设备/异地），触发降级。

---

## 六、持续集成与测试

- pytest 覆盖核心类
- Graph 状态机单元测试覆盖所有状态转换
- CI: lint + type check + test

---

## 七、实施优先级

```
P0 — TwinBrain 核心类 + 状态机骨架
P1 — 数据模型重构（identity → meta/identity/profile）
P2 — 通信协议（Message 类 + alpha:// handler）
P3 — 可见度模型 + 圈层查询
P4 — 记忆自托管（PostgreSQL → 向量库）
P5 — 自主行为（定时任务/auto-reply）
P6 — 签发机构（identity.hub）
```
