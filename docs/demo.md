# Alpha-ID Demo Script

## 30s 版本

```bash
aid init
aid profile mine --path .
aid profile show
aid profile web
python scripts/demo.py
```

一句话：**不是另一个 AI 助理，是坐在所有 AI 工具之上的 Ghost Layer。**

## 3min 版本

1. 问题：你在 ChatGPT、Claude、Cursor 里的记忆是孤岛，换工具就要重新介绍自己。
2. 方案：Alpha-ID 用 `did:aid:` 建立本地身份，把代码、对话、浏览器痕迹收拢成连续画像，并通过 MCP / A2A 注入所有工具。
3. 演示：
   - `aid init` 生成本地 DID，私钥不离开本机。
   - `aid profile mine --path .` 从本机痕迹直接认出你。
   - `aid profile show` 展示完整人格画像。
   - `aid profile web` 打开个人空间 + 模拟盘入口。
   - `python scripts/demo.py` 让 MCP 客户端读取 `profile://identity`。
4. 壁垒：用户的数字历史关系不可复制，本地优先 + 私钥自持不可复制。

## 公开 README 一句话

> 不是另一个 AI 助理，是坐在所有 AI 工具之上的 Ghost Layer。先看本机有什么，再决定采集什么；换工具、换平台，Alpha-ID 不换。
