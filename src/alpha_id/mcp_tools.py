"""
Alpha-ID MCP Tools — 新模块的 MCP 工具注册
============================================

将 Orchestrator 的各子模块能力暴露为 MCP 工具：
  1. 📰 资讯采集 — 拉取资讯、获取统计
  2. 🔍 智能采集 — 扫描产出、获取观察
  3. 📝 Obsidian — 写笔记、搜索笔记
  4. 🐾 NURO — 聊天、主动检查
  5. 🧬 自进化 — 教训记录、偏好审视
  6. 🎛 总调度 — 全局状态

使用方式：
    from entrypoints.aid_mcp_server import mcp
    from alpha_id.mcp_tools import register_orchestrator_tools
    register_orchestrator_tools(mcp)
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全局 orchestrator 实例（由外部注入）
_orchestrator = None


def set_orchestrator(orch):
    """注入 orchestrator 实例"""
    global _orchestrator
    _orchestrator = orch


def get_orchestrator():
    """获取当前 orchestrator 实例"""
    return _orchestrator


def register_orchestrator_tools(mcp_instance):
    """
    将所有新模块的 MCP 工具注册到指定的 MCP server 实例。

    Args:
        mcp_instance: FastMCP 实例（通常是从 aid_mcp_server 导入的 mcp）
    """

    # ══════════════════════════════════════════════
    #  📰 资讯采集工具
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def feed_fetch(limit: int = 10) -> str:
        """
        拉取最新 AI/科技资讯（GitHub Trending、HackerNews、ArXiv）。

        参数:
            limit: 最大返回条数（默认 10）

        返回 JSON 格式的资讯列表。
        """
        if not _orchestrator or not _orchestrator.feed:
            return "❌ 资讯模块未启用"
        try:
            items = _orchestrator.feed.fetch_latest()
            items = items[:limit]
            return json.dumps(
                [i.to_dict() for i in items],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"❌ 资讯拉取失败: {e}"

    @mcp_instance.tool()
    def feed_stats() -> str:
        """获取资讯采集统计（已拉取、已学习、已丢弃）"""
        if not _orchestrator or not _orchestrator.feed:
            return "❌ 资讯模块未启用"
        try:
            stats = _orchestrator.feed.get_stats()
            return json.dumps(stats, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 统计获取失败: {e}"

    # ══════════════════════════════════════════════
    #  🔍 智能采集工具
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def capture_scan() -> str:
        """
        执行一次智能采集扫描（Git 仓库、Obsidian 笔记、用户输入）。

        返回发现的观察列表（卡住、偏离、进展等）。
        """
        if not _orchestrator or not _orchestrator.capture:
            return "❌ 智能采集模块未启用"
        try:
            observations = _orchestrator.capture.scan()
            return json.dumps(
                [o.to_dict() for o in observations],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"❌ 扫描失败: {e}"

    @mcp_instance.tool()
    def capture_pending() -> str:
        """获取待处理的观察（需要用户回应的）"""
        if not _orchestrator or not _orchestrator.capture:
            return "❌ 智能采集模块未启用"
        try:
            pending = _orchestrator.capture.get_pending_actions()
            return json.dumps(
                [o.to_dict() for o in pending],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"❌ 获取失败: {e}"

    @mcp_instance.tool()
    def capture_input(text: str, source: str = "manual") -> str:
        """
        采集用户主动输入，分析并存储。

        参数:
            text: 用户输入的文本
            source: 来源标识（默认 manual）

        返回分析结果。
        """
        if not _orchestrator or not _orchestrator.capture:
            return "❌ 智能采集模块未启用"
        try:
            obs = _orchestrator.capture.capture_user_input(text, source)
            if obs:
                return json.dumps(obs.to_dict(), ensure_ascii=False, indent=2)
            return "⚠️ 输入太短或无法分析"
        except Exception as e:
            return f"❌ 采集失败: {e}"

    # ══════════════════════════════════════════════
    #  📝 Obsidian 工具
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def obsidian_write(title: str, content: str, folder: str = "",
                       tags: str = "", links: str = "") -> str:
        """
        写入笔记到 Obsidian 笔记库。

        参数:
            title: 笔记标题（不含 .md）
            content: Markdown 内容
            folder: 子文件夹路径（可选）
            tags: 逗号分隔的标签
            links: 逗号分隔的双向链接
        """
        if not _orchestrator or not _orchestrator.obsidian:
            return "❌ Obsidian 模块未启用或未配置路径"
        try:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
            link_list = [l.strip() for l in links.split(",") if l.strip()] if links else []
            path = _orchestrator.obsidian.write_note(
                title=title,
                content=content,
                folder=folder,
                tags=tag_list,
                links=link_list,
            )
            if path:
                return f"✅ 笔记已写入: {path}"
            return "❌ 写入失败"
        except Exception as e:
            return f"❌ 写入失败: {e}"

    @mcp_instance.tool()
    def obsidian_search(query: str, limit: int = 10) -> str:
        """
        搜索 Obsidian 笔记内容。

        参数:
            query: 搜索关键词
            limit: 最大返回条数
        """
        if not _orchestrator or not _orchestrator.obsidian:
            return "❌ Obsidian 模块未启用"
        try:
            results = _orchestrator.obsidian.search_notes(query, limit=limit)
            return json.dumps(results, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 搜索失败: {e}"

    @mcp_instance.tool()
    def obsidian_sync() -> str:
        """扫描 Obsidian 笔记变更（新增、修改、删除）"""
        if not _orchestrator or not _orchestrator.obsidian:
            return "❌ Obsidian 模块未启用"
        try:
            events = _orchestrator.obsidian.scan_changes()
            return json.dumps(
                [{"note": e.note_title, "action": e.action, "tags": e.tags} for e in events],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"❌ 同步失败: {e}"

    # ══════════════════════════════════════════════
    #  🐾 NURO 工具
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def nuro_chat(message: str, use_local: bool = True) -> str:
        """
        通过 NURO 桌宠聊天。

        简单问题用本地小模型（快、隐私），复杂问题交给云端 LLM。

        参数:
            message: 用户消息
            use_local: 是否优先使用本地模型（默认 True）
        """
        if not _orchestrator or not _orchestrator.nuro:
            return "❌ NURO 模块未启用"
        try:
            reply = _orchestrator.nuro.chat(message, use_local=use_local)
            return reply
        except Exception as e:
            return f"❌ 聊天失败: {e}"

    @mcp_instance.tool()
    def nuro_remind(message: str) -> str:
        """
        通过 NURO 向用户发送提醒。

        参数:
            message: 提醒内容
        """
        if not _orchestrator or not _orchestrator.nuro:
            return "❌ NURO 模块未启用"
        try:
            _orchestrator.nuro.reminder(message)
            return "✅ 提醒已发送"
        except Exception as e:
            return f"❌ 提醒失败: {e}"

    @mcp_instance.tool()
    def nuro_check() -> str:
        """触发 NURO 主动检查（截止日期、待办事项等）"""
        if not _orchestrator or not _orchestrator.nuro:
            return "❌ NURO 模块未启用"
        try:
            result = _orchestrator.nuro.proactive_check()
            return result or "暂无需要提醒的事项"
        except Exception as e:
            return f"❌ 检查失败: {e}"

    # ══════════════════════════════════════════════
    #  🧬 自进化工具
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def evolution_lessons(category: str = "", limit: int = 20) -> str:
        """
        查看已学到的教训。

        参数:
            category: 分类过滤（可选）
            limit: 最大返回条数
        """
        if not _orchestrator or not _orchestrator.evolution:
            return "❌ 自进化模块未启用"
        try:
            lessons = _orchestrator.evolution.get_lessons(category=category or None, limit=limit)
            return json.dumps(
                [l.to_dict() for l in lessons],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"❌ 获取失败: {e}"

    @mcp_instance.tool()
    def evolution_learn(scenario: str, mistake: str, correction: str,
                        lesson: str, category: str = "general") -> str:
        """
        记录一条新的教训。

        当用户纠正了 Alpha-ID 的错误理解时调用此工具。

        参数:
            scenario: 什么场景下学到的
            mistake: 之前做错了什么
            correction: 正确的做法
            lesson: 提炼出的教训
            category: 分类（默认 general）
        """
        if not _orchestrator or not _orchestrator.evolution:
            return "❌ 自进化模块未启用"
        try:
            result = _orchestrator.evolution.learn_from_correction(
                scenario=scenario,
                mistake=mistake,
                correction=correction,
                lesson=lesson,
                category=category,
            )
            return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 学习失败: {e}"

    @mcp_instance.tool()
    def evolution_audit() -> str:
        """审视所有偏好，标记需要重新评估的"""
        if not _orchestrator or not _orchestrator.evolution:
            return "❌ 自进化模块未启用"
        try:
            needs_review = _orchestrator.evolution.audit_preferences()
            return json.dumps(
                [a.__dict__ for a in needs_review],
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"❌ 审视失败: {e}"

    @mcp_instance.tool()
    def evolution_stats() -> str:
        """获取自进化统计（教训数、审视次数、沉淀数）"""
        if not _orchestrator or not _orchestrator.evolution:
            return "❌ 自进化模块未启用"
        try:
            stats = _orchestrator.evolution.get_stats()
            return json.dumps(stats, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 统计获取失败: {e}"

    # ══════════════════════════════════════════════
    #  🎛 总调度工具
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def orch_status() -> str:
        """获取 Alpha-ID 全局运行状态（所有模块）"""
        if not _orchestrator:
            return "❌ Orchestrator 未初始化"
        try:
            status = _orchestrator.get_status()
            return json.dumps(status, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 状态获取失败: {e}"

    @mcp_instance.tool()
    def orch_think(input_text: str = "") -> str:
        """
        触发 Alpha-ID 大脑思考。

        参数:
            input_text: 输入文本（可选，空则自主思考）
        """
        if not _orchestrator:
            return "❌ Orchestrator 未初始化"
        try:
            result = _orchestrator.think(input_text)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 思考失败: {e}"

    # ══════════════════════════════════════════════
    #  🎛 编程工具协同调度
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def tool_orch_submit(requirement: str, mode: str = "serial") -> str:
        """
        提交编程任务到协同调度器。

        参数:
            requirement: 需求描述
            mode: serial（串行）或 parallel（并行）

        返回任务 ID。
        """
        if not _orchestrator or not hasattr(_orchestrator, 'tool_orchestrator'):
            return "❌ 编程调度模块未启用"
        try:
            task_id = _orchestrator.tool_orchestrator.submit(requirement, mode)
            return json.dumps({"success": True, "task_id": task_id, "mode": mode}, ensure_ascii=False)
        except Exception as e:
            return f"❌ 提交失败: {e}"

    @mcp_instance.tool()
    def tool_orch_execute(task_id: str) -> str:
        """
        开始执行已提交的编程任务。

        参数:
            task_id: 任务 ID
        """
        if not _orchestrator or not hasattr(_orchestrator, 'tool_orchestrator'):
            return "❌ 编程调度模块未启用"
        try:
            ok = _orchestrator.tool_orchestrator.execute(task_id)
            return json.dumps({"success": ok, "task_id": task_id}, ensure_ascii=False)
        except Exception as e:
            return f"❌ 执行失败: {e}"

    @mcp_instance.tool()
    def tool_orch_status(task_id: str) -> str:
        """
        查询编程任务状态。

        参数:
            task_id: 任务 ID
        """
        if not _orchestrator or not hasattr(_orchestrator, 'tool_orchestrator'):
            return "❌ 编程调度模块未启用"
        try:
            result = _orchestrator.tool_orchestrator.get_result(task_id)
            if not result:
                return json.dumps({"error": "task not found"}, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 查询失败: {e}"

    @mcp_instance.tool()
    def tool_orch_list(limit: int = 10) -> str:
        """列出最近的编程任务"""
        if not _orchestrator or not hasattr(_orchestrator, 'tool_orchestrator'):
            return "❌ 编程调度模块未启用"
        try:
            tasks = _orchestrator.tool_orchestrator.list_tasks(limit)
            return json.dumps(tasks, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 列表获取失败: {e}"

    @mcp_instance.tool()
    def tool_orch_stats() -> str:
        """获取编程调度统计"""
        if not _orchestrator or not hasattr(_orchestrator, 'tool_orchestrator'):
            return "❌ 编程调度模块未启用"
        try:
            stats = _orchestrator.tool_orchestrator.stats
            return json.dumps(stats, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 统计获取失败: {e}"

    # ══════════════════════════════════════════════
    #  🤖 Codex CLI 接口
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def codex_ask(prompt: str, backend: str = "atomcode") -> str:
        """
        通过 Codex CLI 执行编程任务（单次调用）。

        参数:
            prompt: 编程需求
            backend: 后端名称（atomcode / codex，默认 atomcode）

        返回执行结果。
        """
        if not _orchestrator or not hasattr(_orchestrator, 'codex_api'):
            return "❌ Codex API 模块未启用"
        try:
            result = _orchestrator.codex_api.ask_once(prompt, backend=backend)
            return result
        except Exception as e:
            return f"❌ Codex 调用失败: {e}"

    # ══════════════════════════════════════════════
    #  🗺 百度地图 AI 技能
    # ══════════════════════════════════════════════

    @mcp_instance.tool()
    def baidu_map_search(query: str, region: str = "") -> str:
        """
        语义化 AI 地点检索。

        参数:
            query: 用户原始需求（如"北京可带宠物的咖啡馆"）
            region: 城市或区域限制（可选）
        """
        if not _orchestrator or not hasattr(_orchestrator, 'baidu_map'):
            return "❌ 百度地图模块未启用"
        try:
            result = _orchestrator.baidu_map.search_places(query, region)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 地点检索失败: {e}"

    @mcp_instance.tool()
    def baidu_map_route(origin: str, destination: str, mode: str = "driving") -> str:
        """
        语义化 AI 路线规划。

        参数:
            origin: 起点
            destination: 终点
            mode: 出行方式（driving / walking / riding / transit）
        """
        if not _orchestrator or not hasattr(_orchestrator, 'baidu_map'):
            return "❌ 百度地图模块未启用"
        try:
            result = _orchestrator.baidu_map.plan_route(origin, destination, mode)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 路线规划失败: {e}"

    @mcp_instance.tool()
    def baidu_map_weather(region: str = "") -> str:
        """
        天气查询。

        参数:
            region: 城市或区域（可选，默认使用配置的区域）
        """
        if not _orchestrator or not hasattr(_orchestrator, 'baidu_map'):
            return "❌ 百度地图模块未启用"
        try:
            result = _orchestrator.baidu_map.get_weather(region)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 天气查询失败: {e}"

    @mcp_instance.tool()
    def baidu_map_geocode(address: str) -> str:
        """
        地理编码（地址 → 坐标）。

        参数:
            address: 地址
        """
        if not _orchestrator or not hasattr(_orchestrator, 'baidu_map'):
            return "❌ 百度地图模块未启用"
        try:
            result = _orchestrator.baidu_map.geocode(address)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 地理编码失败: {e}"

    @mcp_instance.tool()
    def baidu_map_assist(user_request: str, region: str = "") -> str:
        """
        百度地图智能助手 — 自动判断意图并调用对应工具。

        支持：找XX（地点检索）、从A到B（路线规划）、天气、XX在哪里（地理编码）。

        参数:
            user_request: 用户原始请求
            region: 区域限制（可选）
        """
        if not _orchestrator or not hasattr(_orchestrator, 'baidu_map'):
            return "❌ 百度地图模块未启用"
        try:
            result = _orchestrator.baidu_map.assist(user_request, region)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"❌ 智能助手调用失败: {e}"

    logger.info("Alpha-ID Orchestrator MCP 工具已注册")
