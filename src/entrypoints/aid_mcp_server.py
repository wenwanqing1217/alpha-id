"""
AID MCP Server — 让 AID 的能力通过 MCP 协议暴露给 Claude Desktop 等客户端

运行方式：
    # stdio 模式（给 Claude Desktop 用）
    python src/aid_mcp_server.py

    # SSE 模式（给 Web 客户端用）
    python src/aid_mcp_server.py --transport sse --port 8001

Claude Desktop 配置（claude_desktop_config.json）：
    {
        "mcpServers": {
            "aid": {
                "command": "python",
                "args": ["-m", "src.aid_mcp_server"]
            }
        }
    }
"""

import json
import os
import sys
from typing import Optional

import typer

# 确保能找到 src/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from mcp.server import FastMCP

# 注册 Legacy 兼容的 `aid_mcp_server` 包，避免顶层文件与包冲突。
if "aid_mcp_server" not in sys.modules:
    import types

    _legacy_pkg = types.ModuleType("aid_mcp_server")
    _legacy_pkg.__path__ = [str(Path(__file__).resolve().parent)]
    _legacy_pkg.__spec__ = None
    _legacy_pkg.__name__ = "aid_mcp_server"
    sys.modules["aid_mcp_server"] = _legacy_pkg

# ── 工具导入（延迟导入，优雅降级） ──

# 截图工具
try:
    from tools.screen_capture import (
        capture_application_window as _capture_application_window,
    )
    from tools.screen_capture import (
        capture_full_screen as _capture_full_screen,
    )
    from tools.screen_capture import (
        capture_region as _capture_region,
    )
    from tools.screen_capture import (
        list_application_windows as _list_application_windows,
    )

    HAS_SCREEN_CAPTURE = True
except ImportError as e:
    HAS_SCREEN_CAPTURE = False
    _screen_import_error = str(e)

# 即使导入成功也确保 _screen_import_error 有默认值
if HAS_SCREEN_CAPTURE:
    _screen_import_error = ""

# OCR 工具
try:
    from tools.ocr import (
        analyze as _ocr_analyze,
    )
    from tools.ocr import (
        extract_text as _ocr_extract_text,
    )

    HAS_OCR = True
except ImportError as e:
    HAS_OCR = False
    _ocr_import_error = str(e)

if HAS_OCR:
    _ocr_import_error = ""

# 窗口控制
try:
    from tools.window_control import (
        click_on_screen as _click,
    )
    from tools.window_control import (
        focus_application_window as _focus_window,
    )
    from tools.window_control import (
        get_mouse_position as _get_mouse_position,
    )
    from tools.window_control import (
        press_key as _press_key,
    )
    from tools.window_control import (
        scroll_mouse as _scroll,
    )
    from tools.window_control import (
        type_at_position as _type_at_position,
    )
    from tools.window_control import (
        type_text as _type_text,
    )

    HAS_WINDOW_CONTROL = True
except ImportError as e:
    HAS_WINDOW_CONTROL = False
    _window_import_error = str(e)

if HAS_WINDOW_CONTROL:
    _window_import_error = ""

# 身份
try:
    from alpha_id import AIDSigner

    HAS_IDENTITY = True
    _signer = None  # 延迟初始化
except ImportError:
    HAS_IDENTITY = False


def _has_capability(name: str) -> bool:
    aid_mcp = sys.modules.get("aid_mcp_server")
    if aid_mcp is not None and hasattr(aid_mcp, name):
        return bool(getattr(aid_mcp, name))
    return bool(globals().get(name))


# 画像资源（MCP resource）


# Codex（纯 Python，无外部依赖）
try:
    from codex import Codex

    _codex = Codex()
    HAS_CODEX = True
except ImportError as e:
    HAS_CODEX = False
    _codex_import_error = str(e)

# Memory Graph（记忆网络可视化，纯 Python）
try:
    from memory_graph import memory_graph_delete as _mg_delete
    from memory_graph import memory_graph_html as _mg_html
    from memory_graph import memory_graph_save as _mg_save
    from memory_graph import memory_graph_search as _mg_search
    from memory_graph import memory_graph_stats as _mg_stats
    from memory_graph import memory_graph_update as _mg_update

    HAS_MEMORY_GRAPH = True
except ImportError as e:
    HAS_MEMORY_GRAPH = False
    _memory_graph_import_error = str(e)

# ── MCP Server ──

mcp = FastMCP(
    "aid",
    instructions="""
AID (Agent Identity Layer) MCP Server.

提供五组能力：
1. 📸 屏幕捕获 — 全屏截图、窗口截图、区域截图、列出窗口
2. 🔍 OCR/视觉 — 图片文字提取、图片内容分析
3. 🖱 窗口控制 — 聚焦窗口、点击、输入文字、键盘快捷键
4. 🪪 身份信息 — 当前 AID 身份 DID
5. 🧠 记忆网络 — 查看记忆统计、生成交互式记忆关联图

使用流程示例：
1. 先用 list_application_windows 看看当前有什么窗口
2. 用 capture_full_screen 截全屏
3. 用 ocr_analyze_image 分析截图内容
4. 用 focus_application_window + click_on_screen + type_text 操作界面
5. 用 memory_graph_stats 查看记忆网络统计
""",
)


# Codex 兼容导出由顶层兼容包提供，避免重复注册 MCP 工具。




def _load_profile_dict() -> dict:
    try:
        from alpha_id.profile_schema import load_profile

        profile = load_profile()
        if profile:
            return profile.to_dict()
    except Exception:
        pass
    return {}


@mcp.resource("profile://identity")
def profile_identity() -> str:
    """用户身份画像摘要（DID + 偏好）"""
    data = _load_profile_dict()
    if not data:
        return json.dumps({"status": "no_profile"}, ensure_ascii=False)
    info = {
        "did": data.get("did"),
        "alpha_id": data.get("alpha_id"),
        "persona": data.get("persona", {}),
    }
    return json.dumps(info, ensure_ascii=False, indent=2)


@mcp.resource("profile://style")
def profile_style() -> str:
    """用户的沟通风格 + 技术风格"""
    data = _load_profile_dict()
    if not data:
        return json.dumps({"status": "no_profile"}, ensure_ascii=False)
    persona = data.get("persona", {})
    return json.dumps(
        {
            "communication": persona.get("communication", {}),
            "technical": persona.get("technical", {}),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource("profile://memory")
def profile_memory() -> str:
    """当前画像中的记忆信号（时间 + 来源 + 质量）"""
    data = _load_profile_dict()
    if not data:
        return json.dumps({"status": "no_profile"}, ensure_ascii=False)
    memory = {
        "created_at": data.get("created_at"),
        "x_mining": data.get("x_mining"),
        "x_provenance": data.get("x_provenance"),
    }
    return json.dumps(memory, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════
#  第一组：屏幕捕获 tools
# ══════════════════════════════════════════════


@mcp.tool()
def capture_full_screen() -> str:
    """
    截取全屏截图，保存到本地文件。

    返回截图文件路径，可传给 ocr_* 工具做进一步分析。
    """
    if not HAS_SCREEN_CAPTURE:
        return f"❌ 截图工具不可用: {_screen_import_error}"
    return _capture_full_screen()


@mcp.tool()
def capture_window(window_title: str) -> str:
    """
    截取指定应用程序窗口的截图。

    参数:
        window_title: 窗口标题关键词（模糊匹配），如 "WeChat"、"Chrome"、"记事本"

    先用 list_windows 查看当前有哪些窗口。
    """
    if not HAS_SCREEN_CAPTURE:
        return f"❌ 截图工具不可用: {_screen_import_error}"
    return _capture_application_window(window_title)


@mcp.tool()
def capture_region(x: int, y: int, width: int, height: int) -> str:
    """
    截取屏幕指定区域。

    参数:
        x: 左上角 X 坐标
        y: 左上角 Y 坐标
        width: 区域宽度
        height: 区域高度

    适用于已知聊天区域位置后，精准截取消息列表。
    """
    if not HAS_SCREEN_CAPTURE:
        return f"❌ 截图工具不可用: {_screen_import_error}"
    return _capture_region(x, y, width, height)


@mcp.tool()
def list_windows() -> str:
    """
    列出当前桌面上所有可见窗口的标题和位置。

    在截图前先用此命令找到目标窗口的准确标题。
    """
    if not HAS_SCREEN_CAPTURE:
        return f"❌ 截图工具不可用: {_screen_import_error}"
    return _list_application_windows()


# ══════════════════════════════════════════════
#  第二组：OCR / 视觉分析 tools
# ══════════════════════════════════════════════


@mcp.tool()
def ocr_image(image_path: str, lang: str = "chi_sim+eng") -> str:
    """
    OCR 识别图片中的文字。

    参数:
        image_path: 图片本地路径（由 capture_* 返回的路径）
        lang: 语言，默认 "chi_sim+eng" 中英文混合

    适合：提取聊天截图文字、文档文字、界面按钮标签。
    """
    if not HAS_OCR:
        return f"❌ OCR 工具不可用: {_ocr_import_error}"
    try:
        text = _ocr_extract_text(image_path, lang=lang)
        if not text:
            return "⚠️ 未识别到文字（图片可能不含文字，或调整语言参数后重试）"
        return f"✅ 文字识别完成（{len(text)} 字符）\n\n{text[:3000]}"
    except Exception as e:
        return f"❌ 文字识别失败: {e}"


@mcp.tool()
def analyze_image(image_path: str, prompt: str = "请详细描述这张图片的内容。") -> str:
    """
    用视觉 LLM 分析图片内容。

    参数:
        image_path: 图片本地路径
        prompt: 分析角度，如：
                - "这个界面上有哪些按钮和输入框？"
                - "截图里最新的消息是什么？"
                - "桌面上有哪些文件和文件夹？"

    需要设置 OPENAI_API_KEY 环境变量（或兼容 API）。
    适合：截图后的理解环节——先截屏，再分析看到的内容。
    """
    if not HAS_OCR:
        return f"❌ 视觉分析工具不可用: {_ocr_import_error}"
    try:
        result = _ocr_analyze(image_path, prompt=prompt)
        return f"✅ 图片分析完成\n\n{result[:3000]}"
    except Exception as e:
        return f"❌ 图片分析失败: {e}"


# ══════════════════════════════════════════════
#  第三组：窗口控制 tools
# ══════════════════════════════════════════════


@mcp.tool()
def focus_window(window_title: str) -> str:
    """
    激活指定应用程序窗口，将其带到前台。

    参数:
        window_title: 窗口标题关键词（模糊匹配）

    在点击/输入之前，先确保窗口在前台。
    先用 list_windows 查看窗口列表。
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _focus_window(window_title)


@mcp.tool()
def click_screen(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """
    在屏幕指定坐标处点击。

    参数:
        x: X 坐标
        y: Y 坐标
        button: 鼠标按键 (left/right/middle)
        clicks: 点击次数 (1=单击, 2=双击)

    坐标来自截图分析或窗口定位信息。
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _click(x, y, button=button, clicks=clicks)


@mcp.tool()
def click_double(x: int, y: int) -> str:
    """在屏幕指定坐标处双击。"""
    return click_screen(x=x, y=y, button="left", clicks=2)


@mcp.tool()
def click_right(x: int, y: int) -> str:
    """在屏幕指定坐标处右键。"""
    return click_screen(x=x, y=y, button="right", clicks=1)


@mcp.tool()
def type_text(text: str, interval: float = 0.05) -> str:
    """
    在当前聚焦位置输入文本。

    参数:
        text: 要输入的文本内容（支持中文）
        interval: 每次按键间隔（秒），默认 0.05

    先确保目标输入框已聚焦（用 click_screen 点一下输入框）。
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _type_text(text=text, interval=interval)


@mcp.tool()
def type_at(text: str, x: int, y: int, interval: float = 0.05) -> str:
    """
    在屏幕指定坐标点击并输入文本。

    参数:
        text: 要输入的文本
        x: 输入框的 X 坐标
        y: 输入框的 Y 坐标
        interval: 按键间隔（秒）

    常用场景：分析完截图后，知道了消息输入框的位置，直接点进去打字。
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _type_at_position(text=text, x=x, y=y, interval=interval)


@mcp.tool()
def press_key(keys: str) -> str:
    """
    按下键盘快捷键。

    参数:
        keys: 按键组合，用 + 连接。
              例如: "enter", "ctrl+v", "alt+tab", "ctrl+shift+z"

    常用快捷键：
    - 发送消息: enter
    - 粘贴: ctrl+v
    - 复制: ctrl+c
    - 截全屏: alt+prtsc
    - 切换窗口: alt+tab
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _press_key(keys)


@mcp.tool()
def press_enter() -> str:
    """按下回车键（常用于发送消息或确认）。"""
    return press_key("enter")


@mcp.tool()
def scroll(clicks: int = -3, x: Optional[int] = None, y: Optional[int] = None) -> str:
    """
    滚动鼠标滚轮。

    参数:
        clicks: 滚动格数，正数=向上，负数=向下。默认 -3（向下滚3格）
        x: 滚动位置的 X 坐标（可选）
        y: 滚动位置的 Y 坐标（可选）
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _scroll(clicks=clicks, x=x, y=y)


@mcp.tool()
def mouse_position() -> str:
    """
    获取当前鼠标位置。

    用于定位坐标：先把鼠标放到目标位置，然后运行此命令获取坐标。
    """
    if not HAS_WINDOW_CONTROL:
        return f"❌ 窗口控制工具不可用: {_window_import_error}"
    return _get_mouse_position()


# ══════════════════════════════════════════════
#  第四组：身份信息 tools
# ══════════════════════════════════════════════


def _get_signer():
    """延迟初始化身份签名器"""
    global _signer
    if _signer is None:
        _signer = AIDSigner()
        try:
            _signer.load_from_aid_dir()
        except (FileNotFoundError, ValueError):
            pass  # 没有初始化身份也没关系
    return _signer


@mcp.tool()
def get_identity() -> str:
    """
    查看当前 AID 身份信息。

    返回 DID、公钥（前16位）和身份文件位置。
    如果没有初始化身份，会提示如何创建。
    """
    if not HAS_IDENTITY:
        return "❌ 身份 SDK 不可用。请先安装 alpha-id。"

    signer = _get_signer()
    if not signer.has_identity:
        return (
            "⚠️ 当前没有 AID 身份。\n\n"
            "创建身份（命令行）：\n"
            "  aid identity init\n\n"
            "或在 Python 中：\n"
            "  from alpha_id import AIDSigner\n"
            "  signer = AIDSigner()\n"
            "  signer.generate()\n"
            "  signer.save_to_aid_dir()"
        )

    did = signer.did
    pk = signer.public_key
    pk_hex = pk.hex()[:16] + "..." if pk else "无"

    return (
        f"🪪 AID 身份\n\n"
        f"  DID:      {did}\n"
        f"  公钥:     {pk_hex}\n"
        f"  密钥位置: ~/.aid/\n\n"
        f"这个身份在所有支持 MCP 的 AI 工具中共享。"
    )


@mcp.tool()
def verify_identity(did: str, message: str, signature_hex: str) -> str:
    """
    验证另一个 Agent 的身份签名。A2A 信任的基础。

    Args:
        did: 对方的 DID 字符串
        message: 被签名的原始消息
        signature_hex: 签名的 hex 字符串

    返回验证结果（valid: true/false）。
    """
    try:
        from alpha_id.crypto import verify

        sig = bytes.fromhex(signature_hex)
        pub_hex = did[-64:] if len(did) > 64 else ""
        if not pub_hex:
            return json.dumps({"valid": False, "error": "无法从 DID 提取公钥"})
        result = verify(sig, message.encode(), bytes.fromhex(pub_hex))
        return json.dumps({"valid": bool(result), "did": did})
    except Exception as e:
        return json.dumps({"valid": False, "error": str(e)})


@mcp.tool()
def get_server_info() -> str:
    """
    获取 AID MCP Server 的版本信息和可用能力列表。
    """
    capabilities = []
    if HAS_SCREEN_CAPTURE:
        capabilities.append("✅ 屏幕捕获")
    else:
        capabilities.append("❌ 屏幕捕获（需安装: pip install pyautogui pygetwindow Pillow）")

    if HAS_OCR:
        capabilities.append("✅ OCR/视觉分析")
    else:
        capabilities.append("❌ OCR/视觉分析（需安装: pip install pytesseract Pillow openai）")

    if HAS_WINDOW_CONTROL:
        capabilities.append("✅ 窗口控制")
    else:
        capabilities.append("❌ 窗口控制（需安装: pip install pyautogui pygetwindow）")

    if HAS_IDENTITY:
        capabilities.append("✅ AID 身份")
    else:
        capabilities.append("❌ AID 身份（alpha-id SDK 未就绪）")

    if HAS_CODEX:
        capabilities.append("✅ Codex 代码工具（read_code, search_code, edit_code, run_python, list_files, count_loc）")
    else:
        capabilities.append("❌ Codex 代码工具（codex.py 加载失败）")

    if HAS_MEMORY_GRAPH:
        capabilities.append(
            "✅ 记忆网络（memory_graph_stats, memory_graph_html, memory_graph_search, memory_graph_save, memory_graph_delete, memory_graph_update）"
        )
    else:
        capabilities.append("❌ 记忆网络（memory_graph.py 加载失败）")

    return (
        "🤖 AID MCP Server\n\n"
        "可用能力：\n" + "\n".join(f"  {c}" for c in capabilities) + "\n\n"
        "支持的传输方式：\n"
        "  - stdio（给 Claude Desktop 用）\n"
        "  - SSE（给 Web 客户端用）\n\n"
        "建议安装所有依赖以获得完整能力：\n"
        "  pip install pyautogui pygetwindow Pillow pytesseract openai"
    )


# ══════════════════════════════════════════════
#  Codex 代码工具
# ══════════════════════════════════════════════

if HAS_CODEX:

    def read_code(path: str, line_start: int = 1, line_end: int = 0) -> str:
        """读取代码文件，带行号显示。参数：path=文件路径，line_start=起始行，line_end=结束行"""
        return _codex.tools["read_code"]["fn"](path, line_start, line_end)

    def search_code(pattern: str, path: str = "") -> str:
        """在代码库中搜索文本或正则表达式。参数：pattern=搜索模式，path=可选目录"""
        return _codex.tools["search_code"]["fn"](pattern, path)

    def edit_code(path: str, old_string: str, new_string: str) -> str:
        """替换代码文件中的文本。参数：path=文件路径，old_string=旧文本，new_string=新文本"""
        return _codex.tools["edit_code"]["fn"](path, old_string, new_string)

    def run_python(code: str) -> str:
        """在隔离环境中执行 Python 代码片段。参数：code=要执行的代码"""
        return _codex.tools["run_python"]["fn"](code)

    def list_code_files(path: str = ".", pattern: str = "*.py") -> str:
        """列出代码目录中的文件。参数：path=目录路径，pattern=匹配模式"""
        return _codex.tools["list_files"]["fn"](path, pattern)

    def count_code_lines(path: str = ".") -> str:
        """统计代码目录中的 Python 行数。参数：path=目录路径"""
        return _codex.tools["count_loc"]["fn"](path)


# ══════════════════════════════════════════════


def export_mcp_tools(mcp_instance) -> None:
    """Register all legacy MCP tools on the provided MCP server instance."""
    for fn in [
        capture_full_screen,
        capture_window,
        capture_region,
        list_windows,
        ocr_image,
        analyze_image,
        focus_window,
        click_screen,
        click_double,
        click_right,
        type_text,
        type_at,
        press_key,
        press_enter,
        scroll,
        mouse_position,
        get_identity,
        verify_identity,
        get_server_info,
    ]:
        mcp_instance.add_tool(fn, name=fn.__name__)

    if globals().get('HAS_CODEX'):
        for fn in [read_code, search_code, edit_code, run_python, list_code_files, count_code_lines]:
            mcp_instance.add_tool(fn, name=fn.__name__)

    if globals().get('HAS_MEMORY_GRAPH'):
        for fn in [
            memory_graph_stats,
            memory_graph_html,
            memory_graph_search,
            memory_graph_save,
            memory_graph_delete,
            memory_graph_update,
        ]:
            mcp_instance.add_tool(fn, name=fn.__name__)

#  记忆网络工具
# ══════════════════════════════════════════════

if HAS_MEMORY_GRAPH:

    def memory_graph_stats(alpha_id: str = "Alpha-001") -> str:
        """
        查看记忆网络的统计摘要。显示记忆总数、分类分布、关联数量、枢纽节点。
        参数: alpha_id 大脑 ID（默认 Alpha-001）
        """
        return _mg_stats(alpha_id=alpha_id)

    def memory_graph_html(
        alpha_id: str = "Alpha-001",
        output_path: str = "",
        min_similarity: float = 0.05,
        max_nodes: int = 80,
    ) -> str:
        """
        生成记忆网络的交互式可视化 HTML 文件（D3.js 力导向图）。
        返回文件路径，可在浏览器中打开。

        参数:
            alpha_id: 大脑 ID（默认 Alpha-001）
            output_path: 输出路径（留空自动生成到临时目录）
            min_similarity: 最小相似度阈值 0-1（默认 0.05）
            max_nodes: 最大节点数（默认 80）
        """
        return _mg_html(
            alpha_id=alpha_id,
            output_path=output_path,
            min_similarity=min_similarity,
            max_nodes=max_nodes,
        )

    def memory_graph_search(
        alpha_id: str = "Alpha-001",
        query: str = "",
        limit: int = 20,
    ) -> str:
        """
        在记忆网络中搜索与关键词相关的记忆，返回带权重的文本列表。
        LLM 可使用此工具在对话中查询自己的记忆，辅助回答问题。

        参数:
            alpha_id: 大脑 ID（默认 Alpha-001）
            query: 搜索关键词（支持内容、标签、标题匹配）
            limit: 最大返回条数（默认 20）
        """
        return _mg_search(alpha_id=alpha_id, query=query, limit=limit)

    def memory_graph_save(
        alpha_id: str = "Alpha-001",
        content: str = "",
        category: str = "general",
        tags: str = "",
        sensitivity: int = 0,
        source: str = "llm",
    ) -> str:
        """
        保存一条新记忆到记忆网络。
        LLM 可用此工具记录对话中学习到的知识、用户偏好、问题解决方案等。

        参数:
            alpha_id: 大脑 ID（默认 Alpha-001）
            content: 记忆内容（必填）
            category: 分类（general / knowledge / error / daily / preference 等，默认 general）
            tags: 逗号分隔的标签（如 "python,flask,api"）
            sensitivity: 敏感度 0-5（0 最低，默认 0）
            source: 来源标记（默认 llm）
        """
        if not content:
            return "[Error] 请提供记忆内容 content"

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        return _mg_save(
            alpha_id=alpha_id,
            content=content,
            category=category,
            tags=tag_list,
            sensitivity=sensitivity,
            source=source,
        )

    def memory_graph_delete(alpha_id: str = "Alpha-001", memory_id: str = "") -> str:
        """
        从记忆网络中删除一条记忆。
        使用 memory_graph_search 找到目标记忆的 ID 后再调用此工具。

        参数:
            alpha_id: 大脑 ID（默认 Alpha-001）
            memory_id: 要删除的记忆 ID
        """
        if not memory_id:
            return "[Error] 请提供 memory_id"
        return _mg_delete(alpha_id=alpha_id, memory_id=memory_id)

    def memory_graph_update(
        alpha_id: str = "Alpha-001",
        memory_id: str = "",
        content: Optional[str] = None,
        category: Optional[str] = None,
        tags: str = "",
        sensitivity: Optional[int] = None,
        source: Optional[str] = None,
    ) -> str:
        """
        更新一条已有记忆。只更新提供的字段，其余保持不变。
        使用 memory_graph_search 找到目标记忆的 ID 后再调用此工具。

        参数:
            alpha_id: 大脑 ID（默认 Alpha-001）
            memory_id: 要更新的记忆 ID（必填）
            content: 新内容（可选）
            category: 新分类（可选）
            tags: 逗号分隔的新标签列表（可选）
            sensitivity: 新敏感度 0-5（可选）
            source: 新来源标记（可选）
        """
        if not memory_id:
            return "[Error] 请提供 memory_id"
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        return _mg_update(
            alpha_id=alpha_id,
            memory_id=memory_id,
            content=content,
            category=category,
            tags=tag_list,
            sensitivity=sensitivity,
            source=source,
        )


# ══════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════


def main():
    """AID MCP Server 入口点（CLI & pyproject entry point）"""
    import argparse

    # Windows GBK → UTF-8: 确保 emoji 不会炸掉 stderr/stdout
    if sys.platform == "win32":
        for s in (sys.stdout, sys.stderr):
            if hasattr(s, "reconfigure"):
                s.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="AID MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="传输方式（默认 stdio，给 Claude Desktop 用）",
    )
    parser.add_argument("--port", type=int, default=8001, help="SSE 模式端口（默认 8001）")
    parser.add_argument("--host", default="127.0.0.1", help="SSE 模式监听地址（默认 127.0.0.1）")
    args = parser.parse_args()

    if args.transport == "sse":
        typer.echo(f"[Server] AID MCP Server (SSE) → http://{args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        typer.echo("[Server] AID MCP Server (stdio)")
        mcp.run(transport="stdio")