"""
Alpha-ID 头像生成工具

用于生成Alpha-ID专属头像形象

作者：Agent搭建专家
日期：2025-06-18
"""

import os
import requests
from langchain.tools import tool, ToolRuntime
from coze_coding_dev_sdk import ImageGenerationClient
from coze_coding_utils.runtime_ctx.context import new_context


@tool
def generate_alpha_id_avatar(
    style: str = "futuristic",
    color_scheme: str = "blue_cyan_gold",
    runtime: ToolRuntime = None
) -> str:
    """
    生成Alpha-ID专属头像

    Args:
        style: 头像风格（futuristic/scientific/friendly）
        color_scheme: 配色方案（blue_cyan_gold/purple_silver/white_black）

    Returns:
        生成的头像图片URL
    """
    ctx = runtime.context if runtime else new_context(method="generate_alpha_id_avatar")

    try:
        client = ImageGenerationClient(ctx=ctx)

        # 根据风格和配色方案生成不同的prompt
        prompts = {
            "futuristic": {
                "blue_cyan_gold": "A futuristic digital identity avatar representing Alpha-ID, featuring a glowing Greek letter Alpha (Α) at the center with neural network patterns and data streams. Holographic, ethereal appearance with blue and cyan colors and gold accents. Clean, minimalist design suitable for app avatar. High-tech aesthetic with soft, warm lighting. Professional, modern, authoritative yet approachable.",
                "purple_silver": "A futuristic digital identity avatar representing Alpha-ID, featuring a glowing Greek letter Alpha (Α) at the center with neural network patterns and data streams. Holographic, ethereal appearance with purple and violet colors and silver accents. Clean, minimalist design suitable for app avatar. High-tech aesthetic with soft, warm lighting. Professional, modern, authoritative yet approachable.",
                "white_black": "A futuristic digital identity avatar representing Alpha-ID, featuring a glowing Greek letter Alpha (Α) at the center with neural network patterns and data streams. Holographic, ethereal appearance with white and black colors with subtle blue glow. Clean, minimalist design suitable for app avatar. High-tech aesthetic with soft, warm lighting. Professional, modern, authoritative yet approachable."
            },
            "scientific": {
                "blue_cyan_gold": "A scientific digital identity avatar representing Alpha-ID, featuring a stylized Greek letter Alpha (Α) with molecular and atomic structures. Elegant, precise appearance with blue and cyan colors and gold accents. Clean, geometric design suitable for app avatar. Scientific aesthetic with clear, crisp lines. Professional, authoritative yet approachable.",
                "purple_silver": "A scientific digital identity avatar representing Alpha-ID, featuring a stylized Greek letter Alpha (Α) with molecular and atomic structures. Elegant, precise appearance with purple and violet colors and silver accents. Clean, geometric design suitable for app avatar. Scientific aesthetic with clear, crisp lines. Professional, authoritative yet approachable.",
                "white_black": "A scientific digital identity avatar representing Alpha-ID, featuring a stylized Greek letter Alpha (Α) with molecular and atomic structures. Elegant, precise appearance with white and black colors with subtle blue glow. Clean, geometric design suitable for app avatar. Scientific aesthetic with clear, crisp lines. Professional, authoritative yet approachable."
            },
            "friendly": {
                "blue_cyan_gold": "A friendly digital identity avatar representing Alpha-ID, featuring a welcoming Greek letter Alpha (Α) with soft curves and warm expressions. Approachable, friendly appearance with blue and cyan colors and gold accents. Clean, rounded design suitable for app avatar. Warm aesthetic with gentle lighting. Professional, trustworthy and approachable.",
                "purple_silver": "A friendly digital identity avatar representing Alpha-ID, featuring a welcoming Greek letter Alpha (Α) with soft curves and warm expressions. Approachable, friendly appearance with purple and violet colors and silver accents. Clean, rounded design suitable for app avatar. Warm aesthetic with gentle lighting. Professional, trustworthy and approachable.",
                "white_black": "A friendly digital identity avatar representing Alpha-ID, featuring a welcoming Greek letter Alpha (Α) with soft curves and warm expressions. Approachable, friendly appearance with white and black colors with subtle blue glow. Clean, rounded design suitable for app avatar. Warm aesthetic with gentle lighting. Professional, trustworthy and approachable."
            }
        }

        # 获取prompt
        prompt = prompts.get(style, {}).get(color_scheme, prompts["futuristic"]["blue_cyan_gold"])

        # 生成图片
        response = client.generate(
            prompt=prompt,
            size="2K",
            watermark=False
        )

        if response.success and response.image_urls:
            # 下载图片到临时目录
            img_url = response.image_urls[0]
            img_data = requests.get(img_url).content

            # 保存到assets目录
            assets_dir = os.path.join(os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"), "assets")
            os.makedirs(assets_dir, exist_ok=True)

            output_path = os.path.join(assets_dir, "alpha_id_avatar.png")
            with open(output_path, 'wb') as f:
                f.write(img_data)

            return f"✅ Alpha-ID头像生成成功！\n\n**设计信息：**\n- 风格：{style}\n- 配色：{color_scheme}\n- 本地路径：{output_path}\n- 在线地址：{img_url}\n\n头像已保存到assets目录，可以作为Alpha-ID的专属头像使用。"
        else:
            return f"❌ 头像生成失败：{response.error_messages}"

    except Exception as e:
        return f"❌ 头像生成异常：{str(e)}"
