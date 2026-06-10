<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-%237c3aed" alt="Python">
  <img src="https://img.shields.io/badge/tests-715%20passing-%2322c55e" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/Codex_CLI-ready-%236d28d9" alt="Codex">
  <img src="https://img.shields.io/github/stars/wenwanqing1217/alpha-id?style=social" alt="Stars">
</p>

<h1 align="center">Alpha-ID</h1>

<p align="center">
  <strong>Ghost Layer for the AI Era.</strong><br>
  One identity. Every AI tool knows you.
</p>

---

## 🚀 What is Alpha-ID?

> You chat with ChatGPT for months — it knows your style, your tech stack, your thinking process.
> Then you open Claude. Nothing. You start over.
>
> **Alpha-ID makes sure this never happens again.**

Alpha-ID is a **Ghost Layer** that sits between you and every AI tool. It collects your digital traces (ChatGPT chats, code commits, browsing patterns), unifies them into a single identity (DID + Profile + Memory), and injects that identity into every AI tool you use via the MCP protocol.

**It's not another AI assistant. It's the layer that makes every AI assistant recognize you.**

---

## ✨ The Flow

```
aid init              → Create your DID identity (Ed25519 keypair, local only)
aid collect chatgpt   → Import your ChatGPT export → extract persona
aid collect scan      → Auto-detect all collectable data on your machine
aid profile show      → See your unified persona (table or JSON)
aid-mcp               → Start the MCP server → inject identity into AI tools
aid-daemon            → Background daemon for auto-injection
```

---

## 🔥 Why Now? (2026)

The AI tool landscape is fragmented:
- **ChatGPT** knows your writing style
- **Claude** knows your reasoning
- **Cursor / Windsurf / Codex CLI** know your code style
- **None of them share this knowledge**

Alpha-ID bridges that gap. One `pip install`, one `aid init`, and every tool you open knows who you are.

**Codex CLI** is a primary integration target — your Ghost Layer follows you from session to session.

---

## 🧱 Architecture

```
src/
├── alpha_id/          CLI commands, collectors, config, Web UI
├── core/              Zero-external-dep core (DID, memory, twin brain)
├── api/               FastAPI routes
├── auth/              JWT authentication
├── tools/             Desktop automation tools
└── aid_*.py           Entry points (daemon, MCP server, API)
```

---

## 🧪 Testing

```
715 tests passing · 0 failures · ruff lint: 9 warnings
```

Run tests:
```bash
pip install -e ".[dev]"
python -m pytest tests/ -q --tb=short
```

---

## 🖥 Web UI

Open `http://localhost:8899` after starting the API:

```bash
aid-api
# or
python -m uvicorn alpha_id.web:app --reload
```

See the full Ghost Layer showcase — star chain universe, DID demo, and tool integration guide.

---

## 📦 Install

```bash
pip install alpha-id
aid init
aid profile show     # You now have a digital soul
```

---

## 📄 License

MIT. Private keys stay on your machine — always.

---

<p align="center"><strong>Your digital existence should be continuous.</strong></p>
