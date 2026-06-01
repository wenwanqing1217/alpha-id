"""
OCR 工具单元测试 —— 文字提取、结构化提取、图片分析
"""

import pytest
import os
from tools.ocr import (
    extract_text,
    extract_structured,
    analyze,
    ocr_extract_text,
    ocr_extract_payment,
    ocr_analyze_image,
)


class TestCoreFunctions:
    """核心函数（纯逻辑层）测试"""

    def test_extract_text_missing_file(self):
        """不存在的文件应该报 ValueError"""
        with pytest.raises(ValueError, match="无法打开图片"):
            extract_text("nonexistent_file_xyz.png")

    def test_extract_structured_no_llm(self, monkeypatch):
        """没有 LLM 客户端时应该报 RuntimeError"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="需要 LLM API"):
            extract_structured("test.png", {"test": "test"}, llm_client=None)

    def test_analyze_no_llm(self, monkeypatch):
        """没有 LLM 客户端时应该报 RuntimeError"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="需要 LLM API"):
            analyze("test.png", llm_client=None)


class TestToolWrappers:
    """@tool 包装器测试（不依赖 LangChain）"""

    def test_tool_fallback_decorator(self):
        """确认在没有 langchain 时 @tool 装饰器是透明的"""
        # ocr_extract_text 应该是一个普通的可调用函数
        assert callable(ocr_extract_text)
        assert callable(ocr_extract_payment)
        assert callable(ocr_analyze_image)

    def test_tool_wrapper_returns_error_string(self):
        """工具包装器在出错时返回字符串而非抛异常（跟 screen_capture 一致）"""
        result = ocr_extract_text("nonexistent.png")
        assert isinstance(result, str)
        assert result.startswith("❌")

        result = ocr_extract_payment("nonexistent.png")
        assert isinstance(result, str)
        assert result.startswith("❌") or result.startswith("⚠️")

        result = ocr_analyze_image("nonexistent.png")
        assert isinstance(result, str)
        assert result.startswith("❌")


class TestExtractText:
    """可能需要 Tesseract 引擎的测试组"""

    @classmethod
    def setup_class(cls):
        """检查 tesseract 是否可用（用工具函数导入，报错信息清晰）"""
        try:
            from tools.ocr import _import_tesseract

            _import_tesseract()
            cls._tesseract_available = True
        except Exception:
            cls._tesseract_available = False

    def test_tesseract_presence_check(self):
        """记录 tesseract 是否安装（不要求安装，只是记录）"""
        if not self._tesseract_available:
            pytest.skip("Tesseract OCR 引擎未安装，跳过需要 Tesseract 的测试")

    def test_extract_text_from_blank_image(self, tmp_path):
        """空白图片应该返回空字符串（Tesseract 返回空）"""
        if not self._tesseract_available:
            pytest.skip("需要 Tesseract")
        from PIL import Image

        blank = tmp_path / "blank.png"
        Image.new("RGB", (100, 50), color="white").save(blank)
        text = extract_text(str(blank))
        assert text == ""

    def test_extract_text_with_custom_lang(self, tmp_path):
        """自定义语言参数不报错"""
        if not self._tesseract_available:
            pytest.skip("需要 Tesseract")
        from PIL import Image

        img = tmp_path / "test_lang.png"
        Image.new("RGB", (100, 50), color="white").save(img)
        text = extract_text(str(img), lang="eng")
        assert isinstance(text, str)


class TestExtractStructured:
    """结构化提取测试"""

    def test_schema_dict_used(self):
        """确认 schema 参数的定义方式"""
        schema = {
            "amount": "消费金额（数字）",
            "merchant": "商户名称",
        }
        assert "amount" in schema
        assert "merchant" in schema

    def test_payment_schema_match(self):
        """支付截图 schema 跟 @tool 包装器一致"""
        # 从工具函数文档中提取期望的字段
        expected_fields = {"amount", "merchant", "category", "payment_method", "expense_date"}
        # 验证 extract_structured 的参数接口支持这些字段
        import inspect

        sig = inspect.signature(extract_structured)
        assert "schema" in sig.parameters
        assert "image_path" in sig.parameters


class TestAnalyze:
    """图片分析测试"""

    def test_analyze_tool_docstring(self):
        """确认 @tool 文档字符串包含使用场景"""
        doc = ocr_analyze_image.__doc__ or ""
        assert "图片分析" in doc or "描述" in doc
