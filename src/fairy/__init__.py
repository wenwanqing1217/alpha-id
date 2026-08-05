"""
NURO — 纯本地 AI 桌面精灵（贾维斯）

模块:
  - fairy_brain    : MiniCPM-o-4.5 多模态推理（Ollama）
  - fairy_voice    : Whisper STT + Coqui TTS
  - fairy_character: 2D 角色渲染（Tkinter Canvas）
  - fairy_observer : 主动观察循环（场景识别）
  - fairy_popup    : 气泡/弹幕/Toast 通知
  - fairy_identity : FOUNDER → NURO DID 派生
  - fairy_memory   : 双链记忆适配器
  - fairy_daily    : 每日总结 + 锐评

与项目衔接:
  - 复用 tools.screen_capture / tools.window_control（Computer Use）
  - 复用 core.dual_chain.DualChainManager（双链记忆）
  - 复用 alpha_id.did / alpha_id.signer（身份签名）
  - 复用 entrypoints.aid_mcp_server（31 个 MCP tools）
"""

__version__ = "3.0.0"
