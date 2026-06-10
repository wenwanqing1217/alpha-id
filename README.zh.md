<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/pypi/v/alpha-id-zix" alt="PyPI">
  <img src="https://img.shields.io/pypi/dm/alpha-id-zix" alt="Downloads">
</p>

<h1 align="center">Alpha-ID</h1>

<p align="center">
  <strong>你的数字灵魂。</strong><br>
  坐在所有 AI 工具之上——换模型、换平台、换设备，Alpha-ID 不换。
</p>

<p align="center">
  <a href="README.md">English</a>
</p>

---

## 🎯 P0: 现在就能用

导出你的 ChatGPT 数据 → Alpha-ID 读取它 → 你看到自己的 AI 人格画像。

```
aid init                     # 创建 DID 数字身份
aid collect chatgpt <zip>    # 导入 ChatGPT 导出 → 提取人格画像
aid profile show             # 展示画像 — 总结、风格、技术偏好
```

**用样本数据试试：**

```bash
git clone https://github.com/wenwanqing1217/alpha-id
cd alpha-id
pip install -e .
aid init
aid collect chatgpt sample_data/chatgpt_export_sample.json
aid profile show
```

**你会看到：**
```
DID:   did:aid:xxx
Since: 2026-06-05

📋 人格画像
  总结:     深夜技术探索者, Python/异步/Agent 方向
  风格:     简洁直接, 偏好功能性编程
  活跃时段: 22:00-03:00
  关注话题: MCP 协议, Python 异步, Rust 函数式
```

---

## 为什么需要 Alpha-ID？

| 场景 | 没有 Alpha-ID | 有 Alpha-ID |
|------|--------------|------------|
| 换 AI 工具 | 每个工具都要重新认识你 | 身份、人格、偏好自动跟着走 |
| 跨平台 | ChatGPT 不认识你的 Claude 历史 | 一个 DID 走遍所有平台 |
| 数字身份 | 分散在各平台 | 统一在私钥里 |
| 隐私 | 数据归平台 | 私钥在你手里 |

---

## 命令

| 命令 | 状态 | 说明 |
|------|:----:|------|
| `aid init` | ✅ P0 | 初始化 DID 数字身份 |
| `aid collect chatgpt <zip>` | ✅ P0 | 从 ChatGPT 导出导入 |
| `aid profile show` | ✅ P0 | 展示人格画像 |
| `aid profile export --format json` | ✅ P0 | 导出 JSON 画像 |
| `aid collect claude <zip>` | 🔜 P1 | 从 Claude 导入 |
| `aid wizard start` | 🔜 P1 | 3 个问题快速生成画像（无导出数据时） |
| `aid profile serve` | 🔜 P1 | MCP 身份注入（让 Claude Desktop 认识你） |
| `aid profile web` | 🔜 P1 | 浏览器画像仪表盘 |

---

## 核心理念

```
Alpha-ID = DID（去中心化身份） + Persona（人格画像） + 私钥（你控制）
```

- **DID** — `did:aid:xxx`，W3C 标准去中心化身份
- **Persona** — 从对话数据提取的沟通风格、技术偏好、工作节奏
- **MCP** — 通过 Anthropic MCP 协议注入任何 AI 工具
- **私钥在本地** — 没人能锁你的数据

---

## License

MIT

---

<p align="center">
  <i>项目入口：<a href="docs/AGENT_CONTEXT.md">AGENT_CONTEXT.md</a>（AI 必读）| 决策记录：<a href="docs/decisions.md">decisions.md</a> | 追踪：<a href="TODO.md">TODO.md</a></i>
</p>
