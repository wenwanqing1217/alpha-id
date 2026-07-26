# alpha-id-zix

<p align="center">
  <a href="https://pypi.org/project/alpha-id-zix/"><img src="https://img.shields.io/pypi/v/alpha-id-zix.svg?logo=pypi&label=PyPI&logoColor=gold" alt="PyPI"></a>
  <a href="https://pypi.org/project/alpha-id-zix/"><img src="https://img.shields.io/pypi/pyversions/alpha-id-zix.svg?logo=python&label=Python&logoColor=gold" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
</p>

---

你在 ChatGPT 里聊了三个月，它已经了解你的表达方式、你的技术栈、你犯过的错。然后你打开 Claude——一切归零。你要重新介绍自己是谁。

这不是不便。这是你的数字存在被碎片化了。

Alpha-ID 是 [Ghost](https://github.com/wenwanqing1217/ghost-showcase) 矩阵的**身份层核心包**。Ghost 是一个 A2A 智能体生态——身份、记忆、Agent 协作、商业闭环。Alpha-ID 为其提供底层身份基础设施。

This package is the identity layer of the [Ghost](https://github.com/wenwanqing1217/ghost-showcase) ecosystem — an A2A agent matrix for identity, memory, collaboration, and commerce.

---

## Quick Start / 快速开始

```bash
pip install alpha-id-zix
aid init                  # Create your DID / 创建数字身份
aid detect                # Scan local data / 扫描本机数据
aid profile show          # View digital profile / 查看数字画像
```

Web 注册分配的 Alpha-ID 格式：`Alpha-{3位随机前缀}-{顺序号}`（例：`Alpha-C82-777`），随机前缀防枚举，顺序号唯一递增。

实名绑定：注册后的人脸核验通过支付宝完成，服务端签发实名凭证写入你的 DID Document。该凭证仅证明"此 DID 已完成实名认证"，不会记录你的身份证号或人脸信息。

```bash
aid collect chatgpt ~/Downloads/chatgpt-data-export.zip
aid profile web
```

---

## Capabilities / 能力

| Module | EN | CN |
|:-------|:---|:----|
| DID identity | `did:aid` with Ed25519, locally generated | 本地生成的去中心化身份 |
| Dual-chain memory | Encrypted private + plaintext knowledge | 私链加密 + 知识链明文分离 |
| JWT auth | HMAC-SHA256 tokens with revocation | 令牌认证与撤销 |
| Agent SDK | Single `Agent` class for all operations | 一站式 Agent 接口 |
| Agent network | P2P friend system with trace | P2P 好友系统 |
| Skill signing | Package verification & attribution | 技能包签名与验证 |
| Proof of Execution | Verifiable execution records | 可验证的执行记录 |
| Digital profiling | Import from ChatGPT, Claude, Cursor, Trae | 多平台数据采集与画像 |
| REST API | FastAPI-based web service | FastAPI 后端服务 |
| MCP server | Model Context Protocol interface | MCP 协议接入 |

---

## Architecture / 架构

```
alpha-id / 身份层
  DID · JWT · signing · collectors · CLI
  
mindflow-map / 执行层
  workflow engine · intent recognition
  
zcode-brain / 编排层
  role matching · safety guardrails · task scheduling
```

---

## Development / 开发

```bash
git clone https://github.com/wenwanqing1217/alpha-id.git
cd alpha-id/projects
pip install -e ".[dev]"
pytest tests/test_registration.py -v --noconftest
```

---

## License / 许可证

[MIT](LICENSE)

---

<p align="center">
  <a href="https://pypi.org/project/alpha-id-zix/">PyPI</a> · <a href="https://github.com/wenwanqing1217/alpha-id">GitHub</a>
</p>
