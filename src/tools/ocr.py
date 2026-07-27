"""
OCR 工具 —— TwinBrain 的"眼睛之瞳"

提供图片文字提取（OCR）和视觉分析能力。
与 screen_capture 配合：截图 → 文字提取 / 图片理解 → 决策。

双后端策略：
  1. 本地 Tesseract（离线、免费、快）—— 纯文字截图
  2. LLM 视觉模型（OpenAI 兼容 API）—— 复杂场景、结构化提取

兼容本地运行：有 langchain 则用 @tool，没有则用空装饰器。
"""

import os
import sys

from core.settings import settings
from typing import Any, Dict

# 兼容本地运行


def tool2(func=None, **kwargs):
    if func is not None:
        return func

    def decorator(f):
        return f

    return decorator


try:
    from langchain.tools import tool  # pyright: ignore[reportMissingImports]
except ImportError:
    tool = tool2

# ── 导入工具 ──


def _import_pil():
    """导入 Pillow"""
    try:
        from PIL import Image

        pil_image = Image
    except ImportError:
        pil_image = None
    if pil_image is None:
        pil_image = sys.modules.get("PIL.Image")
    if pil_image is None:
        raise ImportError("请安装 Pillow")
    return pil_image


def _import_tesseract():
    """导入 pytesseract，自动检测 Windows 路径"""
    try:
        import pytesseract
    except ImportError:
        pytesseract = None
    if pytesseract is None:
        pytesseract = sys.modules.get("pytesseract")
    if pytesseract is None:
        raise ImportError("请安装 pytesseract")
    if sys.platform == "win32":
        paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break
    return pytesseract


def _get_llm_client(client=None):
    if client is not None:
        return client
    try:
        from openai import OpenAI

        api_key = settings.llm_api_key
        base_url = settings.llm_base_url
        if api_key:
            return OpenAI(api_key=api_key, base_url=base_url if base_url else None)
    except ImportError:
        pass
    return None


# ── 核心函数 ──


def extract_text(
    image_path: str,
    lang: str = "chi_sim+eng",
    tesseract_config: str = None,
) -> str:
    """从图片中提取文字（纯文本 OCR）。

    参数:
        image_path: 图片文件路径
        lang: OCR 语言，默认 chi_sim+eng 中英文
        tesseract_config: 额外的 Tesseract 配置

    返回:
        提取的文本内容

    依赖:
        - pip install pytesseract Pillow
        - 系统安装 Tesseract OCR 引擎
    """
    if not os.path.exists(image_path):
        raise ValueError(f"无法打开图片 {image_path}: 文件不存在")
    image = _import_pil()
    pytesseract = _import_tesseract()
    try:
        img = image.open(image_path)
    except Exception as e:
        raise ValueError(f"无法打开图片 {image_path}: {e}")
    try:
        kwargs = {"lang": lang}
        if tesseract_config:
            kwargs["config"] = tesseract_config
        text = pytesseract.image_to_string(img, **kwargs)
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"OCR 识别失败: {e}")


def extract_structured(
    image_path: str,
    schema: Dict[str, str],
    llm_client: Any = None,
    model: str = "gpt-4o",
) -> Dict[str, Any]:
    """从图片中提取结构化信息（调用 LLM 视觉模型）。

    参数:
        image_path: 图片文件路径
        schema: 提取字段定义
        llm_client: OpenAI 兼容的客户端
        model: 视觉模型名称（默认 gpt-4o）

    返回:
        按 schema 提取的结构化数据 dict
    """
    client = llm_client or _get_llm_client()
    if client is None:
        raise RuntimeError("需要 LLM API，请设置 OPENAI_API_KEY")
    if not os.path.exists(image_path):
        raise ValueError(f"无法打开图片 {image_path}: 文件不存在")

    # 构建 prompt
    import json

    fields_desc = json.dumps(schema, ensure_ascii=False, indent=2)
    prompt = f"请分析这张图片，提取以下字段：\\n{fields_desc}\\n\\n请以纯 JSON 格式返回。如果某些信息无法识别，对应字段设为 null。"

    image = _import_pil()
    try:
        import base64
        from io import BytesIO

        img = image.open(image_path)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        raise ValueError(f"无法处理图片 {image_path}: {e}")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            temperature=0.1,
        )
        text = response.choices[0].message.content or "{}"
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        return json.loads(text)
    except Exception as e:
        raise RuntimeError(f"结构化提取失败: {e}")


def analyze(
    image_path: str,
    llm_client: Any = None,
    model: str = "gpt-4o",
    question: str = "请详细描述这张图片的内容。",
) -> str:
    """图片综合分析（调用 LLM 视觉模型）。

    适合："这张截图里发生了什么？"、界面说明、图表分析。
    需要 OPENAI_API_KEY 环境变量。

    参数:
        image_path: 图片文件路径
        llm_client: OpenAI 兼容的客户端
        model: 视觉模型名称（默认 gpt-4o）
        question: 针对图片的问题或指示

    返回:
        LLM 对图片的描述/分析文本
    """
    client = llm_client or _get_llm_client()
    if client is None:
        raise RuntimeError("需要 LLM API，请设置 OPENAI_API_KEY")
    if not os.path.exists(image_path):
        raise ValueError(f"无法打开图片 {image_path}: 文件不存在")

    image = _import_pil()
    try:
        import base64
        from io import BytesIO

        img = image.open(image_path)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        raise ValueError(f"无法处理图片 {image_path}: {e}")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"图片分析失败: {e}")


# ── MCP @tool 包装器 ──


@tool
def ocr_extract_text(image_path: str, lang: str = "chi_sim+eng") -> str:
    """
    从截图/图片中提取文字（OCR），返回纯文本。

    适合：聊天截图、文档截图、错误信息截图。
    需要系统安装 Tesseract OCR 引擎。

    参数:
        image_path: 图片文件路径
        lang: 语言，默认中英文 "chi_sim+eng"

    返回:
        提取的文字内容，没有文字则返回空字符串
    """
    try:
        return extract_text(image_path, lang=lang)
    except Exception as e:
        return f"\u274c OCR 提取失败: {e}"


@tool
def ocr_extract_payment(image_path: str) -> str:
    """
    识别支付截图/收据中的消费信息（金额、商户、分类等）。

    需要 OPENAI_API_KEY 环境变量（或者兼容的 LLM API）。

    参数:
        image_path: 支付截图的文件路径

    返回:
        JSON 格式的消费信息（amount, merchant, category, payment_method, expense_date）
    """
    try:
        schema = {
            "amount": "消费金额（数字）",
            "merchant": "商户名称",
            "category": "消费分类（餐饮/交通/购物/娱乐/医疗/教育/居住/通讯/其他）",
            "payment_method": "支付方式",
            "expense_date": "消费时间（YYYY-MM-DD HH:mm:ss）",
        }
        import json

        result = extract_structured(image_path, schema)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"\u26a0\ufe0f 支付信息提取失败: {e}"


@tool
def ocr_analyze_image(image_path: str, question: str = "请详细描述这张图片的内容。") -> str:
    """
    对截图/图片进行综合分析（需要 LLM 视觉模型支持）。

    适合："这张截图里发生了什么？"、界面说明、图表分析等。
    需要 OPENAI_API_KEY 环境变量（或者兼容的 LLM API）。

    参数:
        image_path: 图片文件路径
        question: 针对图片的问题或指示

    返回:
        分析描述文本
    """
    try:
        return analyze(image_path, question=question)
    except Exception as e:
        return f"\u274c 图片分析失败: {e}"
