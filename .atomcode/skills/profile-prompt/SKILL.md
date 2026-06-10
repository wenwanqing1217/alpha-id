---
name: profile-prompt
description: Alpha-ID Profile 数据模型与采集器技能。让 AI 理解 Profile Schema、ChatGPT/Claude/Cursor 采集器格式，辅助开发新的采集器或画像功能。
model_invocation: false
user_invocation: false
---

# Alpha-ID Profile 数据模型参考

## Schema v0.1 (已锁定)

Profile 数据位于 `~/.alpha-id/profiles/` 目录，每个用户一个 JSON 文件，文件名 = DID。

## 核心数据类型

### AlphaIDProfile
```python
@dataclass
class AlphaIDProfile:
    did: str                          # did:aid:xxx
    created_at: str                   # ISO 8601
    updated_at: str                   # ISO 8601
    persona: PersonaProfile            # 画像数据
    source: ProfileSource              # 来源追踪
    metadata: dict                     # 扩展字段
```

### PersonaProfile
```python
@dataclass
class PersonaProfile:
    communication_style: str           # 沟通风格描述
    tech_preferences: list[str]        # 技术偏好列表
    active_hours: str                  # 活跃时段描述
    summary: str                       # 一句话画像总结
    traits: list[str]                  # 人格特质标签
```

### ProfileSource
```python
@dataclass
class ProfileSource:
    type: str                          # "chatgpt_export" | "claude_export" | "cursor_export" | "wizard"
    imported_at: str                   # ISO 8601
    file_hash: str                     # SHA256 of original file
    conversation_count: int            # 导入的对话数
```

## 目录结构 (~/.alpha-id/)
```
~/.alpha-id/
  profiles/
    did:aid:xxx.json        # 用户画像
  keys/
    did:aid:xxx.ed25519     # 私钥
    did:aid:xxx.ed25519.pub # 公钥
  config.yaml               # 配置
```

## 采集器接口

每个采集器实现 `collect(source_path: str) -> AlphaIDProfile`：
- **chatgpt.py**: 解析 ChatGPT 导出 ZIP（conversations.json）
- **claude.py**: 解析 Claude 导出 JSON
- **cursor.py**: 解析 Cursor 会话数据

## CLI 命令

```bash
aid profile init              # 初始化 ~/.alpha-id/
aid collect chatgpt <zip>     # 导入 ChatGPT 导出
aid collect claude <json>     # 导入 Claude 导出
aid profile show              # 显示画像
aid profile export --format json  # 导出为 JSON
```

## 约束

- P0 只做 text/json 输出，不做 HTML 卡片
- 核心逻辑在 `src/alpha_id/profile_schema.py` (135行)
- CLI 在 `src/alpha_id/profile_cli.py` (72行)
- 禁止修改已有的测试文件
