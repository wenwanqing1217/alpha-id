from langchain.tools import tool
from langchain.tools import ToolRuntime
from coze_coding_dev_sdk import KnowledgeClient, KnowledgeDocument, DataSourceType
from coze_coding_utils.runtime_ctx.context import new_context
from datetime import datetime
from typing import Any, List, Dict
import json


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


@tool
def save_memory(
    category: str,
    content: str,
    importance: str = "medium",
    timestamp: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    保存用户记忆到知识库。

    参数:
        category: 记忆分类（基本信息/个人特征/习惯偏好/目标规划/关系网络/决策历史/烦恼挑战）
        content: 记忆内容
        importance: 重要程度（high/medium/low）
        timestamp: 时间戳（可选），格式为YYYY-MM-DD HH:mm:ss

    返回:
        保存结果
    """
    try:
        client = KnowledgeClient(ctx=runtime.context if runtime else new_context(method="save_memory"))

        # 生成时间戳
        if timestamp:
            try:
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建记忆文档
        memory_doc = f"""
Alpha-ID Memory
时间: {time_str}
分类: {category}
重要程度: {importance}

内容:
{content}
"""

        # 添加到知识库
        doc = KnowledgeDocument(
            source=DataSourceType.TEXT,
            raw_data=memory_doc
        )

        response = client.add_documents(
            documents=[doc],
            table_name="alpha_id_memory"
        )

        if response.code == 0:
            return f"✅ 记忆已保存\n\n分类: {category}\n内容: {content}\n时间: {time_str}"
        else:
            return f"❌ 保存记忆失败: {response.msg}"

    except Exception as e:
        return f"❌ 保存记忆时出错: {str(e)}"


@tool
def query_memory(
    category: str = None,
    keywords: str = None,
    top_k: int = 5,
    runtime: ToolRuntime = None
) -> str:
    """
    查询用户记忆。

    参数:
        category: 记忆分类（可选）
        keywords: 关键词（可选）
        top_k: 返回结果数量（默认5）

    返回:
        记忆查询结果
    """
    try:
        client = KnowledgeClient(ctx=runtime.context if runtime else new_context(method="query_memory"))

        # 构建查询语句
        query_parts = []
        if category:
            query_parts.append(f"分类: {category}")
        if keywords:
            query_parts.append(keywords)

        query = " ".join(query_parts) if query_parts else "查询所有记忆"

        # 搜索记忆
        response = client.search(
            query=query,
            table_names=["alpha_id_memory"],
            top_k=top_k,
            min_score=0.3
        )

        if response.code == 0:
            if response.chunks:
                result = f"📚 找到 {len(response.chunks)} 条相关记忆\n\n"
                for i, chunk in enumerate(response.chunks, 1):
                    result += f"--- 记忆 {i} (相关度: {chunk.score:.2f}) ---\n"
                    result += chunk.content
                    result += "\n\n"
                return result
            else:
                return "📭 未找到相关记忆"
        else:
            return f"❌ 查询记忆失败: {response.msg}"

    except Exception as e:
        return f"❌ 查询记忆时出错: {str(e)}"


@tool
def search_knowledge(
    query: str,
    top_k: int = 5,
    runtime: ToolRuntime = None
) -> str:
    """
    在知识库中搜索信息。

    参数:
        query: 搜索查询
        top_k: 返回结果数量（默认5）

    返回:
        搜索结果
    """
    try:
        client = KnowledgeClient(ctx=runtime.context if runtime else new_context(method="search_knowledge"))

        # 搜索知识库
        response = client.search(
            query=query,
            top_k=top_k,
            min_score=0.4
        )

        if response.code == 0:
            if response.chunks:
                result = f"🔍 搜索结果（{len(response.chunks)} 条）\n\n"
                for i, chunk in enumerate(response.chunks, 1):
                    result += f"--- 结果 {i} (相关度: {chunk.score:.2f}) ---\n"
                    result += chunk.content
                    result += "\n\n"
                return result
            else:
                return "📭 未找到相关信息"
        else:
            return f"❌ 搜索失败: {response.msg}"

    except Exception as e:
        return f"❌ 搜索时出错: {str(e)}"
