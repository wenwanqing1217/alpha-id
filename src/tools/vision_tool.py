from langchain.tools import tool
from langchain.tools import ToolRuntime
from coze_coding_dev_sdk import ImageGenerationClient, LLMClient
from coze_coding_utils.runtime_ctx.context import new_context
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Any, List
import json


def _safe_str(value: Any) -> str:
    """安全转换为str"""
    if value is None:
        return ""
    return str(value)


@tool
def generate_image(
    prompt: str,
    size: str = "2K",
    style: str = None,
    runtime: ToolRuntime = None
) -> str:
    """
    生成图片。

    参数:
        prompt: 图片描述
        size: 图片大小（2K/4K/自定义，如1920x1080）
        style: 风格描述（可选）

    返回:
        图片URL
    """
    try:
        client = ImageGenerationClient(ctx=runtime.context if runtime else new_context(method="generate_image"))

        # 构建完整的prompt
        full_prompt = f"{style} {prompt}" if style else prompt

        # 生成图片
        response = client.generate(
            prompt=full_prompt,
            size=size,
            watermark=False
        )

        if response.success and response.image_urls:
            return f"✅ 图片生成成功\n\n描述: {prompt}\n风格: {style or '默认'}\n大小: {size}\n\n📥 图片链接: {response.image_urls[0]}"
        else:
            error_msg = ", ".join(response.error_messages) if response.error_messages else "未知错误"
            return f"❌ 图片生成失败: {error_msg}"

    except Exception as e:
        return f"❌ 图片生成时出错: {str(e)}"


@tool
def ocr_recognize(
    image_url: str,
    task: str = "extract_text",
    runtime: ToolRuntime = None
) -> str:
    """
    OCR识别图片内容。

    参数:
        image_url: 图片URL
        task: 任务类型（extract_text/analyze_content/detect_objects）

    返回:
        识别结果
    """
    try:
        client = LLMClient(ctx=runtime.context if runtime else new_context(method="ocr_recognize"))

        task_prompts = {
            "extract_text": "请提取这张图片中的所有文字内容，保持原有格式。",
            "analyze_content": "请详细分析这张图片的内容，包括主要元素、颜色、风格等。",
            "detect_objects": "请识别这张图片中的所有物体，并描述它们的位置和特征。"
        }

        prompt = task_prompts.get(task, task_prompts["extract_text"])

        messages = [
            SystemMessage(content="你是一个专业的图像识别助手，擅长OCR文字提取和图像内容分析。"),
            HumanMessage(content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ])
        ]

        response = client.invoke(
            messages=messages,
            model="doubao-seed-1-6-vision-250815",
            temperature=0.1
        )

        # 提取文本内容
        content = response.content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        return f"✅ 图像识别完成\n\n任务: {task}\n\n{content}"

    except Exception as e:
        return f"❌ 图像识别失败: {str(e)}"
