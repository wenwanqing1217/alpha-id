# Alpha-ID API 参考

> 更新日期：2026-07-27
> 版本：v0.3.3
> 基础 URL：`http://localhost:8000`

---

## 一、认证说明

### 公开端点

以下端点无需认证：

- `GET /health` — 健康检查
- `GET /ready` — 就绪检查
- `GET /metrics` — Prometheus 指标
- `POST /api/v1/identity/register` — 用户注册
- `POST /api/v1/identity/login` — 登录
- `POST /api/v1/identity/refresh` — 令牌轮换
- `POST /api/v1/identity/auth/verify` — 跨服务验证
- `POST /api/v1/register/*` — 注册流程
- `POST /api/v1/risk/evaluate` — 风控评估
- `POST /api/v1/risk/voice-verify` — 声纹验证
- `GET /api/v1/identity/stats/overview` — 系统统计

### 受保护端点

需要 `Authorization: Bearer <access_token>` 头。

---

## 二、健康检查

### `GET /health`

详细健康检查，验证关键组件可达性。

**响应示例：**

```json
{
  "status": "ok",
  "version": "0.3.3",
  "service": "alpha-id",
  "database": "ok",
  "identity": "ok (42 users)",
  "memory": "ok (private=15, knowledge=128)"
}
```

### `GET /ready`

就绪探针，返回依赖是否就绪。

### `GET /metrics`

Prometheus 指标抓取端点。

---

## 三、身份认证

### `POST /api/v1/identity/register`

注册新用户。

**请求体：**

```json
{
  "device_fingerprint": "abc123",
  "is_founder": false,
  "founder_code": null
}
```

**响应示例：**

```json
{
  "success": true,
  "alpha_id": "Alpha-C82-777",
  "message": "注册成功"
}
```

---

### `POST /api/v1/identity/login`

用 alpha_id + 设备指纹获取令牌对。

**请求体：**

```json
{
  "alpha_id": "Alpha-C82-777",
  "device_fingerprint": "abc123"
}
```

**响应示例：**

```json
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in_minutes": 30
}
```

---

### `POST /api/v1/identity/refresh`

用刷新令牌轮换新的令牌对（旧 refresh token 立即失效）。

**请求体：**

```json
{
  "refresh_token": "eyJhbG..."
}
```

**响应：** 同 login。

---

### `POST /api/v1/identity/logout`

登出（客户端丢弃令牌，服务端短期过期）。

**响应示例：**

```json
{
  "success": true,
  "message": "已登出"
}
```

---

### `POST /api/v1/identity/auth/verify`

验证 AID 签发的 JWT 令牌（公开，供跨服务验证）。

**请求体：**

```json
{
  "token": "eyJhbG..."
}
```

**响应示例：**

```json
{
  "valid": true,
  "alpha_id": "Alpha-C82-777",
  "token_type": "access",
  "exp": 1721900000,
  "iat": 1721898200
}
```

---

### `GET /api/v1/identity/me`

获取当前用户信息（需认证）。

**响应示例：**

```json
{
  "alpha_id": "Alpha-C82-777",
  "user_id": "U-1001",
  "devices": ["abc123"],
  "total_sessions": 15,
  "status": "active",
  "created_at": "2026-07-20T10:00:00"
}
```

---

### `GET /api/v1/identity/{alpha_id}`

获取指定用户档案（需认证）。

---

### `POST /api/v1/identity/{alpha_id}/devices`

绑定新设备（需认证）。

**请求体：**

```json
{
  "new_device": "def456"
}
```

---

### `POST /api/v1/identity/{alpha_id}/sync`

跨设备同步（需认证）。

**请求体：**

```json
{
  "from_device": "abc123",
  "to_device": "def456"
}
```

---

### `POST /api/v1/identity/{alpha_id}/session`

记录会话（需认证）。

---

### `GET /api/v1/identity/stats/overview`

获取系统统计信息（公开）。

**响应示例：**

```json
{
  "total_users": 42,
  "active_today": 15,
  "total_sessions": 1280
}
```

---

## 四、社交网络

### `POST /api/v1/social/friend-request`

发送好友请求（需认证）。

**请求体：**

```json
{
  "from_alpha_id": "Alpha-C82-777",
  "to_alpha_id": "Alpha-C82-888",
  "message": "你好，想加你为好友"
}
```

---

### `PUT /api/v1/social/friend-request/{request_id}`

响应好友请求（需认证）。

**请求体：**

```json
{
  "response": "accept"
}
```

---

### `GET /api/v1/social/{alpha_id}/friends`

获取好友列表（需认证）。

---

### `GET /api/v1/social/{alpha_id}/requests`

获取待处理的好友请求（需认证）。

---

### `POST /api/v1/social/message`

发送消息给好友（需认证）。

**请求体：**

```json
{
  "from_alpha_id": "Alpha-C82-777",
  "to_alpha_id": "Alpha-C82-888",
  "content": "你好！",
  "message_type": "text"
}
```

---

### `GET /api/v1/social/{alpha_id}/messages`

获取消息列表（需认证）。

**查询参数：**

| 参数 | 类型 | 说明 |
|:-----|:-----|:-----|
| `unread_only` | `bool` | 是否只获取未读消息 |

---

## 五、双链记忆

### `POST /api/v1/dual-chain/save`

保存记忆（自动按敏感度分链）。

**请求体：**

```json
{
  "content": "我的银行密码是xxx",
  "category": "finance",
  "sensitivity": 90,
  "source": "self",
  "tags": ["密码", "银行"]
}
```

**响应示例：**

```json
{
  "success": true,
  "memory_id": "mem_abc123",
  "chain": "private",
  "encrypted": true,
  "message": "记忆已保存至私有链"
}
```

---

### `GET /api/v1/dual-chain/get/{memory_id}`

获取单条记忆（需认证）。

**查询参数：**

| 参数 | 类型 | 说明 |
|:-----|:-----|:-----|
| `chain` | `string` | 指定链：private/knowledge |

---

### `POST /api/v1/dual-chain/query`

查询记忆（需认证）。

**请求体：**

```json
{
  "chain": "all",
  "keyword": "密码",
  "category": "",
  "max_sensitivity": 100,
  "limit": 20
}
```

**响应示例：**

```json
{
  "results": [...],
  "count": 5
}
```

---

### `POST /api/v1/dual-chain/migrate`

迁移记忆到另一条链（需认证）。

**请求体：**

```json
{
  "memory_id": "mem_abc123",
  "target_chain": "knowledge"
}
```

---

### `GET /api/v1/dual-chain/stats`

获取双链统计（需认证）。

**响应示例：**

```json
{
  "private_count": 15,
  "knowledge_count": 128,
  "total_count": 143,
  "private_encrypted_ratio": 1.0
}
```

---

### `GET /api/v1/dual-chain/list/{chain}`

列出指定链的记忆（需认证）。

**路径参数：** `chain` = `private` 或 `knowledge`

**查询参数：**

| 参数 | 类型 | 说明 |
|:-----|:-----|:-----|
| `limit` | `int` | 最大返回数，默认 50 |

---

### `DELETE /api/v1/dual-chain/{memory_id}`

删除记忆（需认证）。

---

## 六、Agent 对话

### `POST /api/v1/agent/chat`

与 Agent 对话（需认证）。

**请求体：**

```json
{
  "message": "帮我查一下我的身份信息",
  "use_react": false
}
```

**响应示例：**

```json
{
  "alpha_id": "Alpha-C82-777",
  "reply": "您的身份信息如下...",
  "brain_state": "awake"
}
```

**模式说明：**

| `use_react` | 行为 |
|:------------|:-----|
| `false`（默认） | 使用标准 AgentLoop |
| `true` | 使用 ReAct 思考引擎 |

---

### `GET /api/v1/agent/status`

查询大脑状态（需认证）。

**响应示例：**

```json
{
  "alpha_id": "Alpha-C82-777",
  "state": "awake",
  "settings": {}
}
```

---

## 七、风控评估

### `POST /api/v1/risk/evaluate`

全量风控评估（公开）。

**请求体：**

```json
{
  "device_current": {
    "hardware_id": "HW-001",
    "ip_address": "192.168.1.1",
    "location": "Beijing",
    "browser_info": "Chrome/120",
    "screen_resolution": "1920x1080",
    "first_access_time": "2026-07-01T00:00:00"
  },
  "behavior_current": {
    "typing_speed": 45.5,
    "session_time": "00:15",
    "mouse_movement": 1200,
    "input_pattern": "fast",
    "language": "zh"
  },
  "voice_data": {
    "voice_match": 0.95,
    "habit_match": 0.88,
    "noise_level": 0.1,
    "audio_quality": 0.92
  }
}
```

**响应示例：**

```json
{
  "risk_score": 23.5,
  "risk_level": "medium",
  "device_score": 30.0,
  "behavior_score": 20.0,
  "voice_score": 15.0,
  "action_required": "加强监控",
  "recommended_verification": "二次验证"
}
```

---

### `POST /api/v1/risk/voice-verify`

声纹验证专用接口（公开）。

**请求体：**

```json
{
  "user_id": "Alpha-C82-777",
  "voice_match": 0.95,
  "habit_match": 0.88,
  "noise_level": 0.1,
  "audio_quality": 0.92
}
```

---

## 八、GDPR / 数据主权

### `GET /api/v1/gdpr/export`

导出全部个人数据（JSON 格式，需认证）。

**响应示例：**

```json
{
  "alpha_id": "Alpha-C82-777",
  "exported_at": "2026-07-27T10:00:00Z",
  "data": {
    "profile": {...},
    "memories": {
      "private": [...],
      "knowledge": [...]
    },
    "social": {
      "friends": [...],
      "requests": [...]
    }
  }
}
```

---

### `DELETE /api/v1/gdpr/delete`

删除全部个人数据（被遗忘权，需认证）。

**请求体：**

```json
{
  "confirmation": "Alpha-C82-777"
}
```

> 确认码必须等于 alpha_id 才能执行删除。

**响应示例：**

```json
{
  "success": true,
  "message": "您的全部个人数据已被删除",
  "stats": {
    "memories": 143,
    "social": 12,
    "profile": 1
  },
  "deleted_at": "2026-07-27T10:00:00Z"
}
```

---

## 九、注册流程

### `POST /api/v1/register/send-sms`

发送短信验证码（公开）。

### `POST /api/v1/register/verify-sms`

验证短信验证码（公开）。

### `POST /api/v1/register/face-verify`

发起人脸核验（公开）。

### `POST /api/v1/register/face-query`

查询人脸核验结果（公开）。

### `POST /api/v1/register/generate-did`

生成 DID（公开）。

### `POST /api/v1/register/complete`

完成注册（公开）。

---

## 十、错误响应

所有端点统一错误格式：

```json
{
  "detail": "错误描述"
}
```

| HTTP 状态码 | 说明 |
|:------------|:-----|
| 400 | 请求参数错误 |
| 401 | 认证失败（令牌无效/过期） |
| 403 | 权限不足（设备未绑定） |
| 404 | 资源不存在 |
| 429 | 请求过于频繁（限流） |
| 500 | 服务器内部错误 |

---

## 十一、相关文档

- [内部架构](architecture.md) — 模块设计与数据流
- [专家审计报告](EXPERT_AUDIT_2026-07-27.md) — 外部专家代码审计
- [Ghost 全局架构](../../docs/architecture/ARCHITECTURE.md) — 主仓库架构文档
- [Ghost 生态系统](../../docs/architecture/ECOSYSTEM.md) — 全组件串联
